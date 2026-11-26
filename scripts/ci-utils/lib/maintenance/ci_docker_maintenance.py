"""Trusted native Linux host launcher for guarded CI Docker maintenance."""

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import signal
import stat
import subprocess
import sys
import tempfile
import uuid

from lib.maintenance import ci_docker_job
from lib.maintenance.ci_docker_gate import Gate, GateError, LeaseServer
from lib.maintenance.ci_docker_reconcile import reconcile
from lib.maintenance.ci_docker_storage import measure
from lib.maintenance.cleanup import build_metadata, reject_constant, strict_object
from lib.maintenance.engine import Engine, Failure
from lib.maintenance.policy import InvalidPolicy, configuration, duration
from lib.images.remove_images import PROFILE, scope_hash, versions


def emit(event, **fields):
    print(
        json.dumps(
            {
                "event": event,
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                **fields,
            },
            sort_keys=True,
            allow_nan=False,
        ),
        flush=True,
    )


def trusted_path(value, directory=False):
    path = pathlib.Path(value)
    if not path.is_absolute():
        raise GateError(2, "trusted host paths must be absolute")
    try:
        for parent in (path, *path.parents):
            metadata = parent.lstat()
            if metadata.st_uid != 0 or stat.S_ISLNK(metadata.st_mode):
                raise GateError(
                    2,
                    "host configuration paths must be root-owned and free of symlinks",
                )
            if metadata.st_mode & 0o022 and not (
                parent != path
                and stat.S_ISDIR(metadata.st_mode)
                and metadata.st_mode & stat.S_ISVTX
            ):
                raise GateError(
                    2, "host configuration paths must not be writable by jobs"
                )
        expected = stat.S_ISDIR if directory else stat.S_ISREG
        if not expected(path.stat().st_mode):
            raise GateError(2, "trusted host path has the wrong type")
    except OSError as error:
        raise GateError(2, f"trusted host path is unavailable: {path}") from error
    return path


def trusted_json(path):
    path = trusted_path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as source:
        data = source.read(65537)
    if len(data) > 65536:
        raise GateError(2, "host input exceeds 64 KiB")
    try:
        return json.loads(
            data, object_pairs_hook=strict_object, parse_constant=reject_constant
        )
    except (ValueError, UnicodeError) as error:
        raise GateError(2, "host input is not valid declarative JSON") from error


def load_settings(path):
    settings = trusted_json(path)
    if isinstance(settings, dict):
        settings.pop("image", None)  # Accepted in existing schema-version 1 settings.
    fields = {
        "schema_version",
        "policy_path",
        "gate_directory",
        "job_gid",
        "participants",
        "admission_evidence",
        "docker_cli",
        "storage",
    }
    if not isinstance(settings, dict) or set(settings) != fields:
        raise GateError(2, "host settings have missing or unknown fields")
    if type(settings["schema_version"]) is not int or settings["schema_version"] != 1:
        raise GateError(2, "host schema_version must be 1")
    if any(
        not isinstance(settings[key], str) or not settings[key]
        for key in ("policy_path", "gate_directory", "docker_cli")
    ):
        raise GateError(2, "host paths must be nonempty strings")
    participants = settings["participants"]
    if (
        not isinstance(participants, list)
        or not participants
        or len(participants) > 256
        or any(
            not isinstance(value, str)
            or not re.fullmatch(r"[A-Za-z0-9_.@:-]{1,128}", value)
            for value in participants
        )
        or len(set(participants)) != len(participants)
    ):
        raise GateError(
            2, "declare every daemon participant for the shared-job-lease adapter"
        )
    evidence = settings["admission_evidence"]
    if not isinstance(evidence, str) or not 16 <= len(evidence) <= 1024:
        raise GateError(
            2, "a reviewed complete-lifecycle admission evidence reference is required"
        )
    if (
        type(settings["job_gid"]) is not int
        or not 0 <= settings["job_gid"] <= 2**31 - 1
    ):
        raise GateError(2, "job_gid must identify the trusted participant group")
    gate = pathlib.Path(settings["gate_directory"])
    trusted_path(str(gate.parent), directory=True)
    trusted_path(settings["docker_cli"])
    if not os.access(settings["docker_cli"], os.X_OK):
        raise GateError(2, "the trusted Docker CLI must be executable")
    policy = configuration(trusted_json(settings["policy_path"]), {})
    if not policy["expected_daemon_id"]:
        raise GateError(2, "host operation requires the expected daemon identity")
    return settings, policy


def worker_command(operation, profile, selected, observations):
    if profile == PROFILE:
        command = ["ci-remove-images"]
        if selected is not None:
            command += ["--versions", ",".join(selected)]
        if operation == "apply":
            command.append("--apply")
    else:
        command = [
            "ci-docker-cleanup", operation, "--profile", profile,
            "--observations", str(observations),
        ]
    return command


def terminal_result(text, exit_code, run_id, policy_hash, archive_digest, operation, profile, daemon_id):
    try:
        events = [json.loads(line) for line in text.splitlines()]
        if (
            not events
            or any(
                not isinstance(item, dict) or item.get("run_id") != run_id
                for item in events
            )
            or sum(item.get("event") == "result" for item in events) != 1
        ):
            raise ValueError("report shape")
        result = events[-1]
        expected = {
            "event": "result",
            "run_id": run_id,
            "mode": operation,
            "profile": profile,
            "archive_digest": archive_digest,
            "exit_code": exit_code,
            "completion_known": True,
        }
        if (
            any(result.get(key) != value for key, value in expected.items())
            or type(result.get("exit_code")) is not int
            or result.get("completion_known") is not True
            or type(result.get("mutation_started")) is not bool
            or exit_code not in (0, 2, 3, 4, 5)
            or result.get("policy_hash") not in (None, policy_hash)
            or result.get("daemon_id") not in (None, daemon_id)
            or (
                (exit_code == 0 or result["mutation_started"])
                and (
                    result.get("policy_hash") != policy_hash
                    or result.get("daemon_id") != daemon_id
                )
            )
        ):
            raise ValueError("completion contract")
        return events
    except (ValueError, TypeError) as error:
        raise GateError(
            6, "application completion is not established; admission remains blocked"
        ) from error


def snapshot(path, value):
    path.write_text(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")
    path.chmod(0o444)


def native_result(child, output, server, timeout):
    try:
        if server:
            server.bind_client(child.pid)
        code = child.wait(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise GateError(6, "native maintenance timed out; reconcile the run") from error
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
    output.seek(0)
    raw = output.read(16 * 1024 * 1024 + 1)
    if len(raw) > 16 * 1024 * 1024:
        raise GateError(6, "native maintenance report exceeds the limit")
    return raw.decode(), code


def maintain(settings, policy, operation, profile, wait_seconds, selected=None):
    if os.geteuid() != 0:
        raise GateError(2, "maintenance requires the native host administrator")
    gate = Gate(settings["gate_directory"])
    gate._validate()
    engine = Engine(policy["endpoint"])
    info = engine.preflight(policy["expected_daemon_id"])
    metadata = pathlib.Path(engine.socket_path).stat()
    if not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid != 0:
        raise GateError(
            3, "rootful Docker socket is not owned by the host administrator"
        )
    if profile == PROFILE:
        policy_hash = scope_hash(policy, selected)
    else:
        policy_hash = hashlib.sha256(
            json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    context = (
        gate.maintenance(info["ID"], policy_hash, wait_seconds)
        if operation == "apply"
        else contextlib.nullcontext(None)
    )
    with context as lease:
        run_id = lease.id if lease else uuid.uuid4().hex
        engine = Engine(
            policy["endpoint"],
            duration(policy["timeouts"]["operation"]),
            duration(policy["timeouts"]["run"]) + 30,
        )
        started = False
        try:
            with tempfile.TemporaryDirectory(
                prefix="run-", dir=gate.directory.parent
            ) as directory:
                root = pathlib.Path(directory)
                library = pathlib.Path(__file__).resolve().parents[1]
                entry = trusted_path(library / "installation/run.py")
                trusted_path(library / "archive.sha256")
                digest = build_metadata().get("archive_digest")
                if not digest:
                    raise GateError(2, "a verified installed native release is required")
                info = engine.preflight(policy["expected_daemon_id"])
                try:
                    storage = measure(info, settings["storage"], run_id)
                except GateError:
                    storage = None
                snapshot(root / "policy.json", policy)
                snapshot(root / "storage.json", storage)
                host_context = {
                    "run_id": run_id,
                    "daemon_id": info["ID"],
                    "policy_hash": policy_hash,
                    "archive_digest": digest,
                    "profile": profile,
                }
                emit(
                    "host_observations", phase="before", storage=storage, **host_context
                )
                server_context = (
                    LeaseServer(
                        gate,
                        lease,
                        profile,
                        digest,
                        timeout=duration(policy["timeouts"]["run"]) + 30,
                    )
                    if lease
                    else contextlib.nullcontext(None)
                )
                with server_context as server:
                    if lease:
                        lease.record.update(archive_digest=digest, profile=profile, operation=operation)
                        with gate._admission(gate._deadline(5)):
                            gate._write(gate.directory / "maintenance.json", lease.record)
                    interpreter = trusted_path(pathlib.Path(sys.executable).resolve())
                    args = worker_command(operation, profile, selected, root / "storage.json")
                    args += ["--config", str(root / "policy.json"), "--run-id", run_id]
                    if server:
                        args += ["--lease-socket", str(server.path)]
                    with tempfile.TemporaryFile(dir=root) as output:
                        # A signal during Popen can arrive after the child exists.
                        started = True
                        child = subprocess.Popen(
                            [str(interpreter), "-IB", str(entry), *args], cwd=root,
                            stdin=subprocess.DEVNULL, stdout=output,
                            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "TMPDIR": str(root),
                                 "HOME": str(root), "CI_UTILS_DOCKER_CLI": settings["docker_cli"]},
                            # The worker retains exclusive activity through coordinator loss.
                            pass_fds=(lease.descriptor,) if lease else (),
                        )
                        logs, exit_code = native_result(
                            child, output, server, duration(policy["timeouts"]["run"]) + 30,
                        )
                    events = terminal_result(
                        logs,
                        exit_code,
                        run_id,
                        policy_hash,
                        digest,
                        operation,
                        profile,
                        info["ID"],
                    )
                    for event in events:
                        print(json.dumps(event, sort_keys=True), flush=True)
                    if lease:
                        lease.complete()
                    try:
                        info = engine.preflight(policy["expected_daemon_id"])
                        storage = measure(info, settings["storage"], run_id)
                    except (Failure, GateError):
                        storage = None
                    emit(
                        "host_observations",
                        phase="after",
                        storage=storage,
                        **host_context,
                    )
                    emit(
                        "host_result",
                        application_exit_code=exit_code,
                        completion_known=True,
                        **host_context,
                    )
                    return exit_code
        except BaseException:
            if lease and not started:
                lease.complete()
            raise


def arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="/etc/ci-utils/host.json")
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("init")
    sub.add_parser("status")
    sub.add_parser("job-complete")
    recovery = sub.add_parser("reconcile")
    recovery.add_argument("--record-id", required=True)
    recovery.add_argument("--evidence", required=True)
    job = sub.add_parser("job")
    job.add_argument("--participant", required=True)
    job.add_argument("--wait", default="15m")
    job.add_argument("--timeout", default="12h")
    job.add_argument("command", nargs=argparse.REMAINDER)
    for operation in ("check", "plan", "apply"):
        command = sub.add_parser(operation)
        command.add_argument("--profile", choices=("daily", "weekly"), default="daily")
        command.add_argument("--wait", default="15m")
    retirement = sub.add_parser("remove-images")
    retirement.add_argument("--versions", help="omit to keep the latest local versions")
    retirement.add_argument("--apply", action="store_true")
    retirement.add_argument("--wait", default="15m")
    return parser.parse_args(argv)


def interrupted(signum, frame):
    raise GateError(
        6, "host operation interrupted; reconcile completion before restoring admission"
    )


def main(argv=None):
    old_signals = {}
    try:
        args = arguments(argv)
        selected = None
        if args.operation == PROFILE and args.versions is not None:
            selected = versions(args.versions)
        if sys.platform != "linux":
            raise GateError(
                2,
                "the host adapter requires native Linux",
            )
        if args.operation == "job-complete":
            return ci_docker_job.complete()
        settings, policy = load_settings(args.config)
        gate = Gate(settings["gate_directory"])
        if args.operation == "init":
            if os.geteuid() != 0:
                raise GateError(2, "gate provisioning requires the host administrator")
            gate.initialize(settings["job_gid"])
            emit("gate_initialized", gate_directory=settings["gate_directory"])
            return 0
        if args.operation == "status":
            emit("gate_status", **gate.status())
            return 0
        for signum in (signal.SIGTERM, signal.SIGINT):
            old_signals[signum] = signal.signal(signum, interrupted)
        if args.operation == "job":
            return ci_docker_job.run(settings, policy, args, emit)
        if args.operation == "reconcile":
            return reconcile(
                settings, policy, args.record_id, trusted_json(args.evidence), emit
            )
        if args.operation == PROFILE:
            return maintain(
                settings, policy, "apply" if args.apply else "plan", PROFILE,
                duration(args.wait), selected,
            )
        return maintain(
            settings, policy, args.operation, args.profile, duration(args.wait)
        )
    except (InvalidPolicy, GateError, Failure, OSError) as error:
        code = error.code if isinstance(error, (GateError, Failure)) else 2
        emit("host_error", exit_code=code, message=str(error), completion_known=False)
        return code
    finally:
        for signum, handler in old_signals.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
