"""Explicit operator reconciliation; released process locks are never sufficient."""

import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import stat

from ci_docker_gate import Gate, GateError
from ci_utils.engine import APIError, Engine
from ci_utils.policy import OBJECT_ID, timestamp


def reconcile(settings, policy, identifier, evidence, emit):
    if os.geteuid() != 0:
        raise GateError(2, "reconciliation requires the host administrator")
    fields = {
        "schema_version",
        "record_id",
        "daemon_id",
        "observed_at",
        "observer",
        "evidence",
        "participants_drained",
        "daemon_operations_complete",
    }
    if (
        not isinstance(identifier, str)
        or not re.fullmatch(r"[a-f0-9]{32}", identifier)
        or not isinstance(evidence, dict)
        or set(evidence) != fields
        or type(evidence.get("schema_version")) is not int
        or evidence["schema_version"] != 1
        or evidence.get("record_id") != identifier
        or evidence.get("daemon_id") != policy["expected_daemon_id"]
        or evidence.get("participants_drained") is not True
        or evidence.get("daemon_operations_complete") is not True
    ):
        raise GateError(
            2, "reconciliation requires matching, explicit operator evidence"
        )
    for key, minimum, maximum in (("observer", 1, 128), ("evidence", 16, 4096)):
        if (
            not isinstance(evidence[key], str)
            or not minimum <= len(evidence[key]) <= maximum
        ):
            raise GateError(
                2, "reconciliation needs an observer and completion evidence reference"
            )
    observed = timestamp(evidence["observed_at"])
    if (
        observed is None
        or not -5
        <= (dt.datetime.now(dt.timezone.utc) - observed).total_seconds()
        <= 900
    ):
        raise GateError(
            2, "reconciliation observations must be current within 15 minutes"
        )
    gate = Gate(settings["gate_directory"])
    with gate._admission(gate._deadline(5)):
        descriptor = gate._acquire("activity.lock", fcntl.LOCK_EX, gate._deadline(5))
        try:
            maintenance = gate._read(gate.directory / "maintenance.json")
            records = ([maintenance] if maintenance else []) + gate._jobs()
            selected = [record for record in records if record["id"] == identifier]
            if (
                len(selected) != 1
                or selected[0].get("daemon_id") != policy["expected_daemon_id"]
            ):
                raise GateError(
                    4,
                    "the unresolved record or daemon changed; do not clear another run",
                )
            record = selected[0]
            if record["kind"] not in ("maintenance", "job"):
                raise GateError(4, "unrecognized admission record")
            engine = Engine(policy["endpoint"])
            engine.preflight(policy["expected_daemon_id"])
            container_id = record.get("container_id")
            if container_id is not None:
                if not isinstance(container_id, str) or not OBJECT_ID.fullmatch(
                    container_id
                ):
                    raise GateError(
                        4, "maintenance container identity is indeterminate"
                    )
                try:
                    item = engine.inspect("containers", container_id)
                except APIError as error:
                    if error.status != 404:
                        raise
                else:
                    state = item.get("State", {}) if isinstance(item, dict) else {}
                    config = item.get("Config") if isinstance(item, dict) else None
                    labels = config.get("Labels") if isinstance(config, dict) else None
                    if (
                        not isinstance(item, dict)
                        or item.get("Id") != container_id
                        or not isinstance(state, dict)
                        or state.get("Running") is not False
                        or state.get("Status") not in ("created", "exited")
                        or state.get("Pid") != 0
                        or type(state.get("Pid")) is not int
                        or not isinstance(labels, dict)
                        or labels.get("xyz.myflow.cleanup.run") != identifier
                    ):
                        raise GateError(
                            4,
                            "maintenance container is active or indeterminate; admission remains blocked",
                        )
            audit_dir = gate.directory / "reconciliations"
            metadata = audit_dir.lstat()
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != 0
                or metadata.st_mode & 0o022
            ):
                raise GateError(4, "reconciliation audit directory is not trusted")
            digest = hashlib.sha256(
                json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            audit = {
                **gate._record("reconciliation", "complete"),
                "record_id": identifier,
                "daemon_id": policy["expected_daemon_id"],
                "evidence_hash": digest,
                "evidence": evidence,
            }
            gate._write(audit_dir / (audit["id"] + ".json"), audit)
            path = gate.directory / (
                "maintenance.json"
                if record["kind"] == "maintenance"
                else "jobs/" + identifier + ".json"
            )
            gate._remove(path, identifier)
        finally:
            os.close(descriptor)
    emit(
        "reconciled",
        record_id=identifier,
        daemon_id=policy["expected_daemon_id"],
        evidence_hash=digest,
    )
    return 0
