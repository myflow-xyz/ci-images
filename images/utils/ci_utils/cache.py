"""Explicit local-builder cache maintenance."""

import datetime as dt
import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import time

from .engine import Failure
from .policy import duration, space_bytes, timestamp


class BuildCache:
    def __init__(self, engine, policy, daemon_id, report):
        self.engine = engine
        self.policy = policy["cache"]
        self.daemon_id = daemon_id
        self.report = report
        self.directory = None
        self.verified = False
        self.records = []

    def __enter__(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ci-utils-client-")
        config = pathlib.Path(self.directory.name) / "docker"
        config.mkdir(mode=0o700)
        (config / "config.json").write_text("{}\n")
        self.environ = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": self.directory.name,
            "DOCKER_CONFIG": str(config),
            "TMPDIR": self.directory.name,
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        self.config_dir = str(config)
        return self

    def __exit__(self, *args):
        if self.directory is not None:
            self.directory.cleanup()

    def _command(self, args, mutation=False):
        timeout = self.engine.remaining()
        if mutation:
            self.engine.mutation_started = True
        failure_code = 6 if self.engine.mutation_started else 2
        try:
            with (
                tempfile.TemporaryFile(dir=self.directory.name) as output,
                tempfile.TemporaryFile(dir=self.directory.name) as errors,
            ):
                result = subprocess.run(
                    args,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=errors,
                    env=self.environ,
                    timeout=timeout,
                    check=False,
                )
                if result.returncode:
                    raise Failure(
                        failure_code,
                        "cache command failed; "
                        + (
                            "completion requires reconciliation"
                            if mutation
                            else "required backend capability is unavailable"
                        ),
                    )
                output.seek(0)
                data = output.read(32 * 1024 * 1024 + 1)
                if len(data) > 32 * 1024 * 1024:
                    raise Failure(
                        failure_code, "cache response exceeds inventory limit"
                    )
                return data.decode("utf-8")
        except (OSError, UnicodeError, subprocess.TimeoutExpired) as error:
            raise Failure(
                failure_code, "cache command unavailable or deadline exceeded"
            ) from error

    def _docker(self, *args):
        return [
            self.docker,
            "--config",
            self.config_dir,
            "--host",
            self.engine.endpoint,
            *args,
        ]

    def _buildx(self, *args):
        return self._docker("buildx", "--builder", "default", *args)

    def preflight(self):
        if self.policy["mode"] == "off":
            self.report.emit("cache", mode="off", builder="default", status="unmanaged")
            self.verified = True
            return
        self.docker = shutil.which("docker", path=self.environ["PATH"])
        probe = shutil.which("ci-buildkit-probe", path=self.environ["PATH"])
        if not self.docker or not probe:
            raise Failure(2, "Docker CLI, Buildx, and ci-buildkit-probe are required")
        try:
            proof = json.loads(
                self._command(
                    [
                        probe,
                        "--host",
                        self.engine.endpoint,
                        "--expected-daemon-id",
                        self.daemon_id,
                        "--timeout",
                        f"{self.engine.remaining()}s",
                    ]
                )
            )
        except ValueError as error:
            raise Failure(2, "malformed BuildKit capability response") from error
        if (
            not isinstance(proof, dict)
            or proof.get("daemon_id") != self.daemon_id
            or proof.get("builder") != "default"
            or proof.get("driver") != "docker"
            or not isinstance(proof.get("worker_id"), str)
            or not re.fullmatch(r"[a-zA-Z0-9._:-]{1,256}", proof["worker_id"])
            or type(proof.get("gc_space_filters")) is not bool
        ):
            raise Failure(
                2, "capability probe did not identify the selected local backend"
            )
        if (
            self.policy["mode"] == "scheduled"
            and proof.get("gc_space_filters") is not True
        ):
            raise Failure(2, "backend does not advertise cache-space filter support")
        inspection = self._command(self._buildx("inspect", "default"))
        endpoints = re.findall(r"(?m)^Endpoint:\s*(\S+)\s*$", inspection)
        if (
            re.findall(r"(?m)^Driver:\s*(\S+)\s*$", inspection) != ["docker"]
            or len(endpoints) != 1
            or endpoints[0] not in ("default", self.engine.endpoint)
            or re.search(r"(?m)^\s*Error:", inspection)
            or re.findall(r"(?m)^Status:\s*(\S+)\s*$", inspection) != ["running"]
        ):
            raise Failure(
                2, "Buildx does not select the existing local default backend"
            )
        if self.policy["mode"] == "scheduled":
            help_text = self._command(self._buildx("prune", "--help"))
            if any(
                flag not in help_text
                for flag in ("--filter", "--max-used-space", "--all")
            ):
                raise Failure(2, "Buildx lacks a required cache prune flag")
        self.report.emit(
            "cache",
            mode=self.policy["mode"],
            builder="default",
            driver="docker",
            worker_id=proof["worker_id"],
            buildkit_version=proof.get("buildkit_version"),
            gc_space_filters=proof.get("gc_space_filters"),
            docker_cli=self._command(self._docker("--version")).strip()[:160],
            buildx=self._command(self._docker("buildx", "version")).strip()[:160],
        )
        self.observe()
        self.verified = True

    def observe(self):
        if self.policy["mode"] == "off":
            return None
        # Buildx du formats bytes and timestamps for display, even in JSON.
        # Engine disk usage describes the same default docker-driver backend.
        usage = self.engine.get("/system/df?type=build-cache")
        records = []
        seen = set()
        try:
            if not isinstance(usage, dict) or not isinstance(
                usage.get("BuildCache"), list
            ):
                raise TypeError("indeterminate cache inventory")
            for item in usage["BuildCache"]:
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("ID"), str)
                    or not re.fullmatch(r"[a-zA-Z0-9_-]{1,256}", item["ID"])
                    or item["ID"] in seen
                    or type(item.get("InUse")) is not bool
                    or type(item.get("Shared")) is not bool
                ):
                    raise ValueError("indeterminate cache metadata")
                size = item.get("Size")
                if type(size) is not int or not 0 <= size <= 2**63 - 1:
                    raise ValueError("indeterminate cache size")
                item["bytes"] = size
                records.append(item)
                seen.add(item["ID"])
        except (ValueError, TypeError) as error:
            raise Failure(
                2, "cannot establish cache record identity, state, or accounting"
            ) from error
        self.records = records
        return {
            "reported_bytes": sum(item["bytes"] for item in records),
            "shared_reported_bytes": sum(
                item["bytes"] for item in records if item["Shared"]
            ),
            "records": len(records),
            "reclaimable_records": sum(not item["InUse"] for item in records),
            "physical_reclaimed_bytes": None,
        }

    def _eligible(self, item):
        return (
            not item["InUse"]
            and item.get("Type")
            in (
                "regular",
                "source.local",
                "source.git.checkout",
                "exec.cachemount",
                "internal",
                "frontend",
            )
            and (
                self.policy["include_internal"]
                or item.get("Type") not in ("internal", "frontend")
            )
        )

    def plan(self, cutoff):
        if self.policy["mode"] != "scheduled":
            return
        threshold = cutoff - dt.timedelta(
            seconds=duration(self.policy["max_unused_age"])
        )
        known = [
            item
            for item in self.records
            if self._eligible(item) and timestamp(item.get("LastUsedAt")) is not None
        ]
        self.report.emit(
            "cache_plan",
            builder="default",
            age_candidates=sum(
                timestamp(item["LastUsedAt"]) < threshold for item in known
            ),
            indeterminate_last_use=sum(
                self._eligible(item) and timestamp(item.get("LastUsedAt")) is None
                for item in self.records
            ),
            budget_target_bytes=space_bytes(self.policy["max_used_space"]),
            budget_may_remove_recent_records=True,
            exact_native_candidates=False,
            exact_reclaimed_bytes=None,
        )

    def _apply_observation(self):
        try:
            return self.observe()
        except Failure as error:
            self.report.emit(
                "cache_budget",
                status="unknown",
                target_met=None,
                remaining_bytes=None,
                target_bytes=space_bytes(self.policy["max_used_space"]),
                reclaimed_bytes=None,
            )
            raise Failure(
                6 if error.code == 6 else 5,
                "cache state is unknown; later cleanup stages must stop",
            ) from error

    def prune(self, cutoff, guard):
        if self.policy["mode"] != "scheduled":
            return
        if not self.verified:
            raise Failure(2, "cache preflight is required")
        threshold = cutoff - dt.timedelta(
            seconds=duration(self.policy["max_unused_age"])
        )
        self._apply_observation()
        candidates = [
            item["ID"]
            for item in self.records
            if self._eligible(item)
            and timestamp(item.get("LastUsedAt")) is not None
            and timestamp(item["LastUsedAt"]) < threshold
        ]
        extra = ["--all"] if self.policy["include_internal"] else []
        started = time.monotonic()
        # Bound argument size. Exact IDs protect age-indeterminate records from this stage.
        for offset in range(0, len(candidates), 100):
            guard()
            unused = math.ceil(
                (dt.datetime.now(dt.timezone.utc) - threshold).total_seconds()
            )
            identifiers = (
                "^("
                + "|".join(re.escape(key) for key in candidates[offset : offset + 100])
                + ")$"
            )
            self._command(
                self._buildx(
                    "prune",
                    "--force",
                    "--filter",
                    f"until={unused}s",
                    "--filter",
                    "id=" + identifiers,
                    *extra,
                ),
                mutation=True,
            )
        self.report.emit(
            "cache_stage",
            stage="age",
            duration_seconds=time.monotonic() - started,
            submitted_candidates=len(candidates),
            reclaimed_bytes=None,
        )
        before = self._apply_observation()
        started = time.monotonic()
        target = space_bytes(self.policy["max_used_space"])
        candidates = [
            item["ID"]
            for item in self.records
            if self._eligible(item) and timestamp(item.get("LastUsedAt")) is not None
        ]
        eligible = len(candidates)
        if before["reported_bytes"] > target:
            for offset in range(0, len(candidates), 100):
                guard()
                identifiers = (
                    "^("
                    + "|".join(
                        re.escape(key) for key in candidates[offset : offset + 100]
                    )
                    + ")$"
                )
                self._command(
                    self._buildx(
                        "prune",
                        "--force",
                        "--filter",
                        "id=" + identifiers,
                        "--max-used-space",
                        self.policy["max_used_space"],
                        *extra,
                    ),
                    mutation=True,
                )
                if self._apply_observation()["reported_bytes"] <= target:
                    break
        after = self._apply_observation()
        status = (
            "achieved"
            if after["reported_bytes"] <= target
            else "target-unmet"
            if eligible
            else "no-eligible-records"
        )
        self.report.emit(
            "cache_budget",
            status=status,
            target_met=after["reported_bytes"] <= target,
            remaining_bytes=after["reported_bytes"],
            target_bytes=target,
            duration_seconds=time.monotonic() - started,
            reclaimed_bytes=None,
            budget_may_remove_recent_records=True,
        )
