"""Shared admission covering one job and its explicit Docker finalization."""

import datetime as dt
import json
import os
import pathlib
import re
import signal
import stat
import subprocess
import tempfile
import uuid

from ci_docker_gate import Gate, GateError
from ci_docker_storage import measure
from ci_utils.engine import Engine
from ci_utils.policy import duration
from ci_utils.storage import evaluate


def complete():
    path = os.environ.get("CI_DOCKER_JOB_RECEIPT", "")
    job_id = os.environ.get("CI_DOCKER_JOB_ID", "")
    token = os.environ.get("CI_DOCKER_JOB_TOKEN", "")
    if (
        not pathlib.Path(path).is_absolute()
        or not re.fullmatch(r"[a-f0-9]{32}", job_id)
        or not re.fullmatch(r"[a-f0-9]{32}", token)
    ):
        raise GateError(2, "job-complete must run inside the admitted job lifecycle")
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "w") as output:
        json.dump({"schema_version": 1, "job_id": job_id, "token": token}, output)
        output.flush()
        os.fsync(output.fileno())
    return 0


def process_group_gone(pid):
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def read_receipt(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        metadata = os.fstat(handle.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid():
            raise ValueError("untrusted completion receipt")
        raw = handle.read(4097)
        if len(raw) > 4096:
            raise ValueError("receipt limit")
        return json.loads(raw)


def run(settings, policy, args, emit):
    if args.participant not in settings["participants"]:
        raise GateError(
            2, "job participant is not in the reviewed daemon-user inventory"
        )
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise GateError(
            2, "job needs the complete lifecycle command, including its finalizer"
        )
    timeout = duration(args.timeout)
    if timeout > 86400:
        raise GateError(2, "job timeout must be at most 24h")
    if policy["pressure"]["reserve_bytes"] is None:
        raise GateError(
            2, "job admission requires a reviewed capacity reserve in bytes"
        )
    gate = Gate(settings["gate_directory"])
    with gate.job(duration(args.wait), args.participant) as lease:
        process = None
        try:
            engine = Engine(policy["endpoint"])
            info = engine.preflight(policy["expected_daemon_id"])
            sample = measure(info, settings["storage"], lease.id)
            pressure = evaluate(
                sample, policy, info["ID"], lease.id, dt.datetime.now(dt.timezone.utc)
            )
            if pressure["critical"] is not False:
                raise GateError(
                    4,
                    "job admission blocked: capacity is unknown or below the reviewed reserve",
                )
            with tempfile.TemporaryDirectory(
                prefix="ci-utils-job-", dir="/tmp"
            ) as directory:
                receipt = pathlib.Path(directory) / "complete.json"
                token = uuid.uuid4().hex
                environment = {
                    **os.environ,
                    "CI_DOCKER_JOB_ID": lease.id,
                    "CI_DOCKER_JOB_TOKEN": token,
                    "CI_DOCKER_JOB_RECEIPT": str(receipt),
                }
                emit(
                    "job_admitted",
                    job_id=lease.id,
                    participant=args.participant,
                    daemon_id=info["ID"],
                )
                process = subprocess.Popen(
                    command, env=environment, start_new_session=True
                )
                try:
                    code = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired as error:
                    raise GateError(
                        6,
                        "job deadline exceeded; lifecycle completion requires reconciliation",
                    ) from error
                try:
                    value = read_receipt(receipt)
                    if (
                        value
                        != {"schema_version": 1, "job_id": lease.id, "token": token}
                        or type(value.get("schema_version")) is not int
                        or code < 0
                        or not process_group_gone(process.pid)
                    ):
                        raise ValueError("unresolved job lifecycle")
                except (OSError, ValueError, TypeError) as error:
                    raise GateError(
                        6,
                        "job exited without established finalization; admission remains blocked",
                    ) from error
                lease.complete()
                emit(
                    "job_result",
                    job_id=lease.id,
                    participant=args.participant,
                    job_exit_code=code,
                    completion_known=True,
                )
                return code
        except BaseException:
            if process is None:
                lease.complete()
            elif not process_group_gone(process.pid):
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            raise
