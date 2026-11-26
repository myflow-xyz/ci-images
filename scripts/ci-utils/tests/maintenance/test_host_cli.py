"""T-18–20/22/24/28/32/33: public host launcher and retained uncertainty."""

import datetime as dt
import json
import os
import pathlib
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import unittest

from tests.maintenance.host_fixture import stage_release
from tests.maintenance.service_fixture import service_command
from tests.maintenance.test_apply_cli import DIGEST, ROOT, StatefulAPI

from lib.maintenance.ci_docker_gate import Gate, GateError


@unittest.skipUnless(
    hasattr(socket, "SO_PEERCRED") and os.geteuid() == 0,
    "host launcher requires an isolated Linux root controller",
)
class HostCLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cu-host-", dir="/tmp")
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.launcher = stage_release(self.root)
        self.api = self.enterContext(StatefulAPI())
        (self.root / "docker-data").mkdir()
        self.api.routes[("GET", "/v1.48/info")][1].update(
            Driver="overlay2",
            DriverStatus=[],
            DockerRootDir=str(self.root / "docker-data"),
        )
        self.policy = {
            "schema_version": 1,
            "endpoint": self.api.endpoint,
            "expected_daemon_id": "fixture-daemon",
            "cache": {"mode": "off"},
            "tagged_image_trigger": "scheduled",
            "image_scope": {"mode": "daemon-wide", "daemon_wide_approved": True},
        }
        self.settings = {
            "schema_version": 1,
            "policy_path": str(self.root / "policy.json"),
            "gate_directory": str(self.root / "gate"),
            "job_gid": 0,
            "participants": ["test-runner"],
            "admission_evidence": "fixture-only-lifecycle-adapter",
            "docker_cli": str(pathlib.Path(shutil.which("true")).resolve()),
            "storage": {
                "docker": str(self.root / "docker-data"),
                "containerd": None,
                "other": [],
            },
        }
        self.save()
        result, _ = self.invoke("init")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def save(self):
        for name, value in (("host", self.settings), ("policy", self.policy)):
            path = self.root / (name + ".json")
            path.write_text(json.dumps(value))
            path.chmod(0o644)

    def invoke(self, *args, service=False, **identity):
        command = [
            sys.executable,
            "-B",
            str(self.launcher),
            "ci-docker-maintenance",
            "--config",
            str(self.root / "host.json"),
            *args,
        ]
        if service:
            command = service_command(command, self.settings["job_gid"])
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=25,
            check=False,
            **identity,
        )
        return result, [json.loads(line) for line in result.stdout.splitlines()]

    def test_apply_releases_after_verified_terminal_result(self):
        result, events = self.invoke("apply", "--profile", "weekly")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIsNone(Gate(self.root / "gate").status()["maintenance"])
        self.assertEqual([e["phase"] for e in events if e["event"] == "host_observations"], ["before", "after"])
        self.assertTrue(events[-1]["completion_known"])
        self.assertEqual(events[-1]["archive_digest"], DIGEST)

    def worker_fault(self, statement):
        original = self.launcher.read_text()
        self.launcher.write_text(
            'import sys\nif sys.argv[1] in ("ci-remove-images", "ci-docker-cleanup"):\n    '
            + statement + "\n" + original
        )
        return original

    def version_fixture(self, **images):
        from tests.images.test_remove_images import VersionAPI

        self.api = self.enterContext(VersionAPI(**images))
        self.policy["endpoint"] = self.api.endpoint
        self.save()

    def test_version_removal_preserves_other_tags(self):
        from tests.images.test_remove_images import ALIAS, IID

        self.version_fixture()
        result, events = self.invoke("remove-images", "--versions", "0.0.1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(any(e["event"] == "would-remove" for e in events))
        self.assertTrue(all(method == "GET" for method, _ in self.api.requests))
        result, events = self.invoke(
            "remove-images", "--versions", "0.0.1", "--apply"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.api.objects["images"][IID]["RepoTags"], [ALIAS])
        self.assertIsNone(Gate(self.root / "gate").status()["maintenance"])

    def test_omitted_versions_use_the_guarded_retirement_command(self):
        from tests.images.test_remove_images import ALIAS, IID, PREFIX

        self.version_fixture(extra_tags={"sha256:" + "4" * 64: [PREFIX + "go:latest"]})
        result, events = self.invoke("remove-images", "--apply")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.api.objects["images"][IID]["RepoTags"], [ALIAS])
        self.assertTrue(any(e["event"] == "removed" for e in events))
        self.assertIsNone(Gate(self.root / "gate").status()["maintenance"])

    def test_version_lease_rejects_changed_selection(self):
        self.version_fixture()
        self.worker_fault('sys.argv[sys.argv.index("--versions") + 1] = "9.9.9"')
        result, _ = self.invoke(
            "remove-images", "--versions", "0.0.1", "--apply"
        )
        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        self.assertTrue(all(method == "GET" for method, _ in self.api.requests))
        self.assertEqual(
            Gate(self.root / "gate").status()["maintenance"]["phase"], "uncertain"
        )

    def test_version_removal_lost_report_retains_admission_block(self):
        self.version_fixture()
        self.worker_fault("sys.exit(0)")
        result, _ = self.invoke(
            "remove-images", "--versions", "0.0.1", "--apply"
        )
        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        self.assertEqual(
            Gate(self.root / "gate").status()["maintenance"]["phase"], "uncertain"
        )

    def test_lost_terminal_report_preserves_admission_block(self):
        # Separate cases need separate provisioned gates; no test reset conceals uncertainty.
        self.worker_fault("sys.exit(0)")
        result, _ = self.invoke("apply")
        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        gate = Gate(self.root / "gate")
        self.assertEqual(gate.status()["maintenance"]["phase"], "uncertain")
        with self.assertRaises(GateError), gate.job(wait_seconds=0.02):
            self.fail("lost terminal report reopened admission")

    def test_report_for_another_daemon_is_rejected(self):
        from lib.maintenance.ci_docker_maintenance import terminal_result

        event = {"event": "result", "run_id": "run", "mode": "apply", "profile": "weekly",
                 "archive_digest": DIGEST, "exit_code": 0, "completion_known": True,
                 "mutation_started": True, "policy_hash": "policy", "daemon_id": "different"}
        with self.assertRaises(GateError):
            terminal_result(json.dumps(event), 0, "run", "policy", DIGEST,
                            "apply", "weekly", "fixture-daemon")

    def test_stale_or_mismatched_reconciliation_does_not_clear_records(self):
        record, path = self.reconciliation_evidence()
        original = json.loads(path.read_text())
        for patch in (
            {"record_id": "0" * 32},
            {"daemon_id": "other"},
            {"observed_at": "2000-01-01T00:00:00Z"},
            {"daemon_operations_complete": False},
        ):
            with self.subTest(patch=patch):
                path.write_text(json.dumps({**original, **patch}))
                result, _ = self.invoke(
                    "reconcile", "--record-id", record["id"], "--evidence", str(path)
                )
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertEqual(
                    Gate(self.root / "gate").status()["maintenance"]["id"], record["id"]
                )

    def test_unverified_archive_and_mutable_settings_fail_before_launch(self):
        metadata = self.launcher.parents[1] / "archive.sha256"
        checksum = metadata.read_text()
        metadata.write_text("invalid")
        result, _ = self.invoke("apply")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIsNone(Gate(self.root / "gate").status()["maintenance"])
        metadata.write_text(checksum)
        (self.root / "host.json").chmod(0o666)
        result, _ = self.invoke("apply")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def job_program(self, code=0, complete=True, background=False):
        return "\n".join(
            [
                "import subprocess, sys",
                (
                    "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(2)'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)"
                    if background
                    else ""
                ),
                (
                    f"subprocess.run([sys.executable, '-B', {str(self.launcher)!r}, 'ci-docker-maintenance', 'job-complete'], check=True)"
                    if complete
                    else ""
                ),
                f"sys.exit({code})",
            ]
        )

    def test_job_result_and_lifecycle_completion_are_independent(self):
        self.policy["pressure"] = {"reserve_bytes": 1}
        self.save()
        result, events = self.invoke(
            "job",
            "--participant",
            "test-runner",
            "--",
            sys.executable,
            "-c",
            self.job_program(code=1),
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(Gate(self.root / "gate").status()["jobs"], [])
        self.assertTrue(events[-1]["completion_known"])
        self.assertEqual(events[-1]["job_exit_code"], 1)

    def test_non_root_job_admission_with_restrictive_umask(self):
        self.root.chmod(0o755)
        self.api.path.parent.chmod(0o755)
        os.chown(self.api.path, -1, 2001)
        self.api.path.chmod(0o660)
        self.settings["gate_directory"] = str(self.root / "group-gate")
        self.settings["job_gid"] = 2001
        self.policy["pressure"] = {"reserve_bytes": 1}
        self.save()
        result, _ = self.invoke("init", umask=0o077)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result, events = self.invoke(
            "job",
            "--participant",
            "test-runner",
            "--",
            sys.executable,
            "-c",
            self.job_program(),
            user=1001,
            group=2001,
            extra_groups=[],
            umask=0o077,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(events[-1]["completion_known"])
        self.assertEqual(Gate(self.settings["gate_directory"]).status()["jobs"], [])
        self.assertIn(("GET", "/v1.48/info"), self.api.requests)
        self.assertFalse(any(method == "DELETE" for method, _ in self.api.requests))

    def test_job_without_completion_receipt_blocks_later_admission(self):
        self.policy["pressure"] = {"reserve_bytes": 1}
        self.save()
        result, _ = self.invoke(
            "job",
            "--participant",
            "test-runner",
            "--",
            sys.executable,
            "-c",
            self.job_program(complete=False),
        )
        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        with (
            self.assertRaises(GateError),
            Gate(self.root / "gate").job(wait_seconds=0.02),
        ):
            self.fail("missing completion receipt reopened admission")

    def test_interrupted_job_launch_keeps_admission_blocked(self):
        self.policy["pressure"] = {"reserve_bytes": 1}
        self.save()
        pid_path = self.root / "child.pid"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(ROOT / "scripts/ci-utils/tests/maintenance/interrupt_job_launch.py"),
                    str(pid_path),
                    str(self.launcher),
                    "ci-docker-maintenance",
                    "--config",
                    str(self.root / "host.json"),
                    "job",
                    "--participant",
                    "test-runner",
                    "--",
                    sys.executable,
                    "-c",
                    "import time; time.sleep(60)",
                ],
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
            os.kill(int(pid_path.read_text()), 0)
            gate = Gate(self.root / "gate")
            self.assertEqual(len(gate.status()["jobs"]), 1)
            self.assertEqual(gate.status()["jobs"][0]["phase"], "uncertain")
            result, _ = self.invoke("apply", "--wait", "1s")
            self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
            self.assertFalse(any(method == "DELETE" for method, _ in self.api.requests))
        finally:
            if pid_path.exists():
                os.killpg(int(pid_path.read_text()), signal.SIGTERM)

    def test_background_client_prevents_completion_even_with_receipt(self):
        self.policy["pressure"] = {"reserve_bytes": 1}
        self.save()
        result, _ = self.invoke(
            "job",
            "--participant",
            "test-runner",
            "--",
            sys.executable,
            "-c",
            self.job_program(background=True),
        )
        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        self.assertEqual(
            Gate(self.root / "gate").status()["jobs"][0]["phase"], "uncertain"
        )

    def test_insufficient_capacity_blocks_job_before_its_command(self):
        self.policy["pressure"] = {"reserve_bytes": 2**63 - 1}
        self.save()
        marker = self.root / "job-started"
        result, _ = self.invoke(
            "job",
            "--participant",
            "test-runner",
            "--",
            sys.executable,
            "-c",
            f"open({str(marker)!r}, 'w').close()",
        )
        self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
        self.assertFalse(marker.exists())
        self.assertEqual(Gate(self.root / "gate").status()["jobs"], [])

    def reconciliation_evidence(self):
        original = self.worker_fault("sys.exit(0)")
        result, _ = self.invoke("apply")
        self.launcher.write_text(original)
        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        record = Gate(self.root / "gate").status()["maintenance"]
        proof = {
            "schema_version": 1,
            "record_id": record["id"],
            "daemon_id": "fixture-daemon",
            "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "observer": "fixture-operator",
            "evidence": "fixture-only: stopped process and completed API handlers",
            "participants_drained": True,
            "daemon_operations_complete": True,
        }
        path = self.root / "reconciled.json"
        path.write_text(json.dumps(proof))
        path.chmod(0o644)
        return record, path

    def test_explicit_reconciliation_audits_before_reopening_admission(self):
        record, path = self.reconciliation_evidence()
        result, events = self.invoke(
            "reconcile", "--record-id", record["id"], "--evidence", str(path)
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        gate = Gate(self.root / "gate")
        self.assertIsNone(gate.status()["maintenance"])
        with gate.job() as lease:
            lease.complete()
        self.assertEqual(events[-1]["record_id"], record["id"])
        audits = list((self.root / "gate/reconciliations").glob("*.json"))
        self.assertEqual(len(audits), 1)
        self.assertEqual(
            json.loads(audits[0].read_text())["evidence"]["record_id"], record["id"]
        )

    def test_reconciliation_cannot_override_a_running_recorded_container(self):
        record, path = self.reconciliation_evidence()
        record["container_id"] = "f" * 64
        (self.root / "gate/maintenance.json").write_text(json.dumps(record))
        self.api.routes[
            ("GET", "/v1.48/containers/" + record["container_id"] + "/json")
        ] = (200, {"Id": record["container_id"], "State": {"Running": True}})
        result, _ = self.invoke(
            "reconcile", "--record-id", record["id"], "--evidence", str(path)
        )
        self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
        self.assertIsNotNone(Gate(self.root / "gate").status()["maintenance"])

    def test_refused_maintenance_needs_only_the_original_job_reconciled(self):
        gate = Gate(self.root / "gate")
        with gate.job(participant="test-runner", daemon_id="fixture-daemon") as lease:
            identifier = lease.id
        result, _ = self.invoke("apply", "--wait", "1s")
        self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
        self.assertIsNone(gate.status()["maintenance"])
        self.assertEqual([job["id"] for job in gate.status()["jobs"]], [identifier])
        proof = {
            "schema_version": 1,
            "record_id": identifier,
            "daemon_id": "fixture-daemon",
            "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "observer": "fixture-operator",
            "evidence": "isolated job exited and the fixture has no pending daemon operations",
            "participants_drained": True,
            "daemon_operations_complete": True,
        }
        path = self.root / "job-reconciled.json"
        path.write_text(json.dumps(proof))
        result, _ = self.invoke(
            "reconcile", "--record-id", identifier, "--evidence", str(path)
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result, _ = self.invoke("apply")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_service_recovery_reads_non_root_participant_records(self):
        self.root.chmod(0o755)
        self.api.path.parent.chmod(0o755)
        os.chown(self.api.path, -1, 2001)
        self.api.path.chmod(0o660)
        self.settings["gate_directory"] = str(self.root / "service-gate")
        self.settings["job_gid"] = 2001
        self.policy["pressure"] = {"reserve_bytes": 1}
        self.save()
        result, _ = self.invoke("init")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result, _ = self.invoke(
            "job",
            "--participant",
            "test-runner",
            "--",
            sys.executable,
            "-c",
            self.job_program(complete=False),
            user=1001,
            group=2001,
            extra_groups=[],
        )
        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        gate = Gate(self.settings["gate_directory"])
        identifier = gate.status()["jobs"][0]["id"]
        record = gate.directory / "jobs" / (identifier + ".json")
        self.assertEqual(record.stat().st_uid, 1001)
        self.assertEqual(record.stat().st_gid, 2001)
        result, _ = self.invoke("apply", "--wait", "1s", service=True)
        self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
        self.assertIsNone(gate.status()["maintenance"])
        self.assertFalse(any(method == "DELETE" for method, _ in self.api.requests))
        path = self.root / "reconcile-job.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "record_id": identifier,
                    "daemon_id": "fixture-daemon",
                    "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "observer": "fixture-operator",
                    "evidence": "The fixture job exited and no daemon operations remain active.",
                    "participants_drained": True,
                    "daemon_operations_complete": True,
                }
            )
        )
        result, _ = self.invoke(
            "reconcile",
            "--record-id",
            identifier,
            "--evidence",
            str(path),
            service=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(gate.status()["jobs"], [])
        result, _ = self.invoke("apply", service=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIsNone(gate.status()["maintenance"])


if __name__ == "__main__":
    unittest.main()
