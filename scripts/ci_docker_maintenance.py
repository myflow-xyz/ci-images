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
import time
import uuid

from ci_docker_gate import Gate, GateError, LeaseServer
from ci_docker_storage import measure
from ci_utils.cleanup import reject_constant, strict_object
from ci_utils.engine import Engine, Failure
from ci_utils.policy import InvalidPolicy, configuration, duration, reference_name


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
        raise GateError(2, "trusted host path is unavailable") from error
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
    fields = {
        "schema_version",
        "policy_path",
        "image",
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
    image = settings["image"]
    digest = image.rsplit("@", 1)[-1] if isinstance(image, str) else ""
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise GateError(2, "maintenance image must be pinned to an immutable digest")
    if "@" in image:
        reference_name(image)
    elif image != digest:
        raise GateError(2, "invalid immutable image reference")
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


class Docker:
    def __init__(self, settings, policy, directory):
        self.policy = policy
        self.deadline = time.monotonic() + duration(policy["timeouts"]["run"]) + 30
        config = pathlib.Path(directory) / "docker"
        config.mkdir(mode=0o700)
        (config / "config.json").write_text("{}\n")
        self.prefix = [
            settings["docker_cli"],
            "--config",
            str(config),
            "--host",
            policy["endpoint"],
        ]
        self.env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(directory),
            "TMPDIR": str(directory),
            "LANG": "C.UTF-8",
        }

    def call(self, *args, wait=False):
        timeout = self.deadline - time.monotonic()
        if not wait:
            timeout = min(timeout, duration(self.policy["timeouts"]["operation"]))
        if timeout <= 0:
            raise GateError(7, "host Docker deadline exceeded")
        try:
            with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
                result = subprocess.run(
                    [*self.prefix, *args],
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=errors,
                    env=self.env,
                    timeout=timeout,
                    check=False,
                )
                if result.returncode:
                    raise GateError(
                        7,
                        "host Docker command failed; inspect the retained maintenance record",
                    )
                output.seek(0)
                raw = output.read(16 * 1024 * 1024 + 1)
                if len(raw) > 16 * 1024 * 1024:
                    raise GateError(
                        7, "host Docker output exceeds the bounded report limit"
                    )
                return raw.decode()
        except (OSError, UnicodeError, subprocess.TimeoutExpired) as error:
            raise GateError(
                7, "host Docker command unavailable or timed out"
            ) from error

    def inspect(self, kind, identifier):
        try:
            value = json.loads(self.call(kind, "inspect", identifier))
            if (
                not isinstance(value, list)
                or len(value) != 1
                or not isinstance(value[0], dict)
            ):
                raise ValueError("inspect shape")
            return value[0]
        except ValueError as error:
            raise GateError(7, "host Docker inspection is indeterminate") from error


def verify_image(docker, reference):
    item = docker.inspect("image", reference)
    if ("@" in reference and reference not in (item.get("RepoDigests") or [])) or (
        "@" not in reference and item.get("Id") != reference
    ):
        raise GateError(2, "local maintenance image does not match the approved digest")
    config = item.get("Config")
    if (
        not isinstance(config, dict)
        or config.get("User") not in ("ci", "1001", "1001:2001")
        or config.get("Volumes")
        or config.get("Entrypoint")
        or not isinstance(config.get("Labels"), dict)
        or config["Labels"].get("org.myflow.ci.utils-host-protocol") != "1"
    ):
        raise GateError(
            2, "local image does not implement the reviewed ci-utils runtime contract"
        )


def launch_args(
    settings, policy, root, run_id, operation, profile, socket_gid, lease_path=None
):
    def mount(source, target):
        if any(character in str(source) for character in (",", "\n", "\r")):
            raise GateError(2, "host mount path cannot be represented safely")
        return ["--mount", f"type=bind,src={source},dst={target},readonly"]

    socket_path = policy["endpoint"][len("unix://") :]
    args = [
        "create",
        "--pull=never",
        "--name",
        "ci-utils-" + run_id,
        "--label",
        "xyz.myflow.cleanup.protect=true",
        "--label",
        "xyz.myflow.cleanup.run=" + run_id,
        "--network=none",
        "--read-only",
        "--user=1001:2001",
        "--group-add=" + str(socket_gid),
        "--group-add=" + str(settings["job_gid"]),
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--memory=512m",
        "--pids-limit=128",
        "--cpus=1",
        "--restart=no",
        "--log-driver=local",
        "--log-opt=max-size=10m",
        "--log-opt=max-file=2",
        "--tmpfs",
        "/var/tmp:rw,noexec,nosuid,nodev,size=256m,mode=1777",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777",
        "--env",
        "TMPDIR=/var/tmp",
        "--env",
        "HOME=/var/tmp",
        "--env",
        "CI_UTILS_IMAGE_DIGEST=" + settings["image"].rsplit("@", 1)[-1],
        *mount(socket_path, socket_path),
        *mount(root / "policy.json", "/etc/ci-utils/cleanup.json"),
        *mount(root / "storage.json", "/run/ci-utils/storage.json"),
    ]
    if lease_path:
        args += mount(lease_path, "/run/ci-utils/lease.sock")
    args += [
        "--entrypoint",
        "/opt/ci-tools/bin/ci-docker-cleanup",
        settings["image"],
        operation,
        "--profile",
        profile,
        "--run-id",
        run_id,
        "--observations",
        "/run/ci-utils/storage.json",
    ]
    if lease_path:
        args += ["--lease-socket", "/run/ci-utils/lease.sock"]
    return args


def terminal_result(
    text, exit_code, run_id, policy_hash, image_digest, operation, profile
):
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
            "image_digest": image_digest,
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
            or (result["mutation_started"] and result.get("policy_hash") != policy_hash)
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


def maintain(settings, policy, operation, profile, wait_seconds):
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
                docker = Docker(settings, policy, root)
                verify_image(docker, settings["image"])
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
                    "image_digest": settings["image"].rsplit("@", 1)[-1],
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
                        host_context["image_digest"],
                        timeout=duration(policy["timeouts"]["run"]) + 30,
                    )
                    if lease
                    else contextlib.nullcontext(None)
                )
                with server_context as server:
                    identifier = docker.call(
                        *launch_args(
                            settings,
                            policy,
                            root,
                            run_id,
                            operation,
                            profile,
                            metadata.st_gid,
                            server.path if server else None,
                        )
                    ).strip()
                    if not re.fullmatch(r"[a-f0-9]{64}", identifier):
                        raise GateError(
                            7, "Docker did not return a full maintenance container ID"
                        )
                    if lease:
                        lease.record.update(
                            container_id=identifier,
                            image=settings["image"],
                            profile=profile,
                        )
                        with gate._admission(gate._deadline(5)):
                            gate._write(
                                gate.directory / "maintenance.json", lease.record
                            )
                    started = True
                    docker.call("start", identifier)
                    state = docker.inspect("container", identifier).get("State", {})
                    if server and state.get("Running") is True:
                        server.bind_client(state.get("Pid"))
                    exit_text = docker.call("wait", identifier, wait=True).strip()
                    if not exit_text.isdecimal():
                        raise GateError(
                            7, "maintenance container exit is indeterminate"
                        )
                    exit_code = int(exit_text)
                    state = docker.inspect("container", identifier).get("State", {})
                    if (
                        state.get("Running") is not False
                        or state.get("Status") != "exited"
                        or state.get("ExitCode") != exit_code
                        or state.get("OOMKilled") is not False
                    ):
                        raise GateError(
                            6,
                            "maintenance container has no cleanly observed terminal state",
                        )
                    logs = docker.call("logs", identifier)
                    events = terminal_result(
                        logs,
                        exit_code,
                        run_id,
                        policy_hash,
                        host_context["image_digest"],
                        operation,
                        profile,
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
                    docker.call("rm", identifier)
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
    for operation in ("check", "plan", "apply"):
        command = sub.add_parser(operation)
        command.add_argument("--profile", choices=("daily", "weekly"), default="daily")
        command.add_argument("--wait", default="15m")
    return parser.parse_args(argv)


def interrupted(signum, frame):
    raise GateError(
        6, "host operation interrupted; reconcile completion before restoring admission"
    )


def main(argv=None):
    old_signals = {}
    try:
        args = arguments(argv)
        if sys.platform != "linux":
            raise GateError(
                2,
                "the host adapter requires native Linux in the Docker daemon PID namespace",
            )
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
