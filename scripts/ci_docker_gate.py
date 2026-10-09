"""Shared job and exclusive maintenance admission for one local daemon."""

import contextlib
import datetime as dt
import fcntl
import json
import math
import os
import pathlib
import stat
import time
import uuid


class GateError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class Lease:
    def __init__(self, record, descriptor):
        self.known = False
        self.record = record
        self.descriptor = descriptor

    @property
    def id(self):
        return self.record["id"]

    def complete(self):
        self.known = True


class Gate:
    def __init__(self, directory):
        self.directory = pathlib.Path(directory)

    def initialize(self, group=None):
        """Provision once from a trusted host path; never repair existing state."""
        if not self.directory.is_absolute():
            raise GateError(2, "gate directory must be absolute")
        self.directory.mkdir(mode=0o750)
        if group is not None:
            os.chown(self.directory, -1, group)
        self.directory.chmod(0o2750)
        jobs = self.directory / "jobs"
        jobs.mkdir(mode=0o770)
        jobs.chmod(0o3770)
        for name in ("admission.lock", "activity.lock"):
            fd = os.open(
                self.directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640
            )
            os.close(fd)
        self._sync_directory(self.directory)

    def _validate(self):
        try:
            metadata = self.directory.lstat()
            jobs = (self.directory / "jobs").lstat()
        except OSError as error:
            raise GateError(
                4, "gate state is unavailable; provision the trusted host gate"
            ) from error
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid not in (0, os.geteuid())
            or metadata.st_mode & 0o022
            or not stat.S_ISDIR(jobs.st_mode)
            or jobs.st_uid != metadata.st_uid
            or jobs.st_mode & 0o007
        ):
            raise GateError(4, "gate state ownership or permissions are not trusted")

    @staticmethod
    def _deadline(wait_seconds):
        if (
            not isinstance(wait_seconds, (int, float))
            or not math.isfinite(wait_seconds)
            or wait_seconds <= 0
        ):
            raise GateError(2, "gate wait must be a positive finite duration")
        return time.monotonic() + wait_seconds

    def _acquire(self, name, operation, deadline):
        self._validate()
        try:
            fd = os.open(
                self.directory / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            )
        except OSError as error:
            raise GateError(4, "gate lock cannot be opened safely") from error
        try:
            metadata = os.fstat(fd)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != self.directory.stat().st_uid
            ):
                raise GateError(4, "gate lock is not a trusted regular file")
            while True:
                try:
                    fcntl.flock(fd, operation | fcntl.LOCK_NB)
                    return fd
                except BlockingIOError as error:
                    if time.monotonic() >= deadline:
                        raise GateError(
                            4, "exclusive maintenance or job admission is unavailable"
                        ) from error
                    time.sleep(min(0.01, max(0, deadline - time.monotonic())))
        except BaseException:
            os.close(fd)
            raise

    @contextlib.contextmanager
    def _admission(self, deadline):
        descriptor = self._acquire("admission.lock", fcntl.LOCK_EX, deadline)
        try:
            yield
        finally:
            os.close(descriptor)

    @staticmethod
    def _sync_directory(path):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _write(self, path, record):
        temporary = path.parent / (".pending-" + uuid.uuid4().hex)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(
                    record, output, ensure_ascii=True, sort_keys=True, allow_nan=False
                )
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            self._sync_directory(path.parent)
        finally:
            temporary.unlink(missing_ok=True)

    def _read(self, path):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return None
        except OSError as error:
            raise GateError(4, "gate state cannot be read safely") from error
        try:
            with os.fdopen(fd, "rb") as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    raise GateError(4, "gate state must be a regular file")
                raw = handle.read(65537)
            if len(raw) > 65536:
                raise ValueError("state limit")
            record = json.loads(raw)
            if (
                not isinstance(record, dict)
                or record.get("schema_version") != 1
                or record.get("phase") not in ("waiting", "active", "uncertain")
                or not isinstance(record.get("id"), str)
                or len(record["id"]) != 32
                or uuid.UUID(record["id"]).hex != record["id"]
            ):
                raise ValueError("state schema")
            return record
        except (ValueError, UnicodeError, OSError) as error:
            raise GateError(
                4, "gate state is indeterminate; admission remains blocked"
            ) from error

    def _remove(self, path, identifier):
        record = self._read(path)
        if record is None or record["id"] != identifier:
            raise GateError(4, "gate record changed; reconciliation is required")
        path.unlink()
        self._sync_directory(path.parent)

    @staticmethod
    def _record(kind, phase):
        return {
            "schema_version": 1,
            "id": uuid.uuid4().hex,
            "kind": kind,
            "phase": phase,
            "pid": os.getpid(),
            "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }

    def _jobs(self):
        result = []
        for path in sorted((self.directory / "jobs").glob("*.json")):
            record = self._read(path)
            if record is not None:
                if record.get("kind") != "job" or path.stem != record["id"]:
                    raise GateError(4, "job registration is indeterminate")
                result.append(record)
        return result

    @contextlib.contextmanager
    def job(self, wait_seconds=1):
        deadline = self._deadline(wait_seconds)
        descriptor = None
        record = self._record("job", "active")
        path = self.directory / "jobs" / (record["id"] + ".json")
        while descriptor is None:
            with self._admission(deadline):
                state = self._read(self.directory / "maintenance.json")
                uncertain = any(job["phase"] == "uncertain" for job in self._jobs())
                if state is None and not uncertain:
                    descriptor = self._acquire("activity.lock", fcntl.LOCK_SH, deadline)
                    try:
                        self._write(path, record)
                    except BaseException:
                        os.close(descriptor)
                        raise
            if descriptor is None:
                if time.monotonic() >= deadline:
                    raise GateError(
                        4, "job admission is blocked by maintenance or unresolved work"
                    )
                time.sleep(min(0.01, max(0, deadline - time.monotonic())))
        lease = Lease(record, descriptor)
        try:
            yield lease
        finally:
            try:
                with self._admission(self._deadline(5)):
                    if lease.known:
                        self._remove(path, lease.id)
                    else:
                        self._write(path, {**record, "phase": "uncertain"})
            finally:
                os.close(descriptor)

    @contextlib.contextmanager
    def maintenance(self, daemon_id, policy_hash, wait_seconds=1):
        deadline = self._deadline(wait_seconds)
        record = {
            **self._record("maintenance", "waiting"),
            "daemon_id": daemon_id,
            "policy_hash": policy_hash,
        }
        path = self.directory / "maintenance.json"
        with self._admission(deadline):
            if self._read(path) is not None:
                raise GateError(
                    4, "another or unresolved maintenance run blocks admission"
                )
            self._write(path, record)
        try:
            descriptor = self._acquire("activity.lock", fcntl.LOCK_EX, deadline)
        except BaseException:
            # No cleanup lease was granted. A known acquisition failure can reopen admission.
            with self._admission(self._deadline(5)):
                self._remove(path, record["id"])
            raise
        lease = Lease(record, descriptor)
        try:
            with self._admission(self._deadline(5)):
                if self._jobs():
                    raise GateError(
                        4, "job completion is unresolved despite released process locks"
                    )
                record["phase"] = "active"
                self._write(path, record)
            yield lease
        finally:
            try:
                with self._admission(self._deadline(5)):
                    if lease.known:
                        self._remove(path, lease.id)
                    else:
                        self._write(path, {**record, "phase": "uncertain"})
            finally:
                os.close(descriptor)

    def status(self):
        self._validate()
        return {
            "maintenance": self._read(self.directory / "maintenance.json"),
            "jobs": self._jobs(),
        }
