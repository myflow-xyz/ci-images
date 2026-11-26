"""Installed adapter -> Unix Engine HTTP API -> admission state after a lost reply."""

import datetime as dt
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import unittest

from test_apply_cli import StatefulAPI
from test_policy import CID


class NativeAdmission(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/tmp")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.api = StatefulAPI()
        self.api.__enter__()
        self.addCleanup(self.api.__exit__, None, None, None)
        self.api.routes[("GET", "/v1.48/info")][1].update(
            Driver="overlay2", DriverStatus=[], DockerRootDir=str(self.root)
        )
        self.policy = self.root / "cleanup.json"
        self.policy.write_text(
            json.dumps(
                dict(
                    schema_version=1,
                    endpoint=self.api.endpoint,
                    expected_daemon_id="fixture-daemon",
                    cache={"mode": "off"},
                )
            )
        )
        host = self.root / "host.json"
        host.write_text(
            json.dumps(
                dict(
                    schema_version=1,
                    policy_path=str(self.policy),
                    gate_directory=str(self.root / "gate"),
                    job_gid=0,
                    participants=["test"],
                    admission_evidence="disposable lifecycle fixture",
                    docker_cli=str(Path(shutil.which("docker")).resolve()),
                    storage=dict(docker=str(self.root), containerd=None, other=[]),
                )
            )
        )
        self.host = ["ci-docker-maintenance", "--config", str(host)]
        self.invoke("init")

    def invoke(self, *args, status=0, env=None):
        result = subprocess.run(
            [*self.host, *args], capture_output=True, timeout=15, text=True, env=env
        )
        self.assertEqual(result.returncode, status, result.stdout + result.stderr)
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_denial_and_terminal_apply(self):
        before = list(self.api.objects["containers"])
        denied = subprocess.run(
            ["ci-docker-cleanup", "apply", "--config", self.policy],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(denied.returncode, 4, denied.stdout)
        self.assertFalse(any(m == "DELETE" for m, _ in self.api.requests))
        self.assertEqual(list(self.api.objects["containers"]), before)
        events = self.invoke("apply")
        self.assertTrue(
            any(e["event"] == "result" and e["completion_known"] for e in events)
        )
        self.assertIn("archive_digest", events[-1])
        self.assertNotIn(CID, self.api.objects["containers"])
        self.assertIsNone(self.invoke("status")[0]["maintenance"])

    def test_setup_refusal_releases_admission_without_worker_requests(self):
        interpreter = self.root / "python3"
        shutil.copy2(sys.executable, interpreter)
        interpreter.chmod(0o775)
        env = {**os.environ, "PATH": f"{self.root}:{os.environ['PATH']}"}
        refusal = self.invoke("apply", status=2, env=env)
        self.assertIn("must not be writable", refusal[-1]["message"])
        self.assertFalse(any(method != "GET" for method, _ in self.api.requests))
        self.assertIsNone(self.invoke("status")[0]["maintenance"])

        interpreter.chmod(0o755)
        policy = json.loads(self.policy.read_text())
        policy["pressure"] = {"reserve_bytes": 1}
        self.policy.write_text(json.dumps(policy))
        self.invoke(
            "job",
            "--participant",
            "test",
            "--wait",
            "1s",
            "--",
            "ci-docker-maintenance",
            "job-complete",
            env=env,
        )
        self.invoke("apply", "--wait", "1s", env=env)

    def test_interruption_during_worker_creation_keeps_admission_blocked(self):
        worker_pid = self.root / "worker.pid"
        adapter = Path(shutil.which("ci-docker-maintenance")).resolve()
        dispatch = adapter.parents[1] / "lib/run.py"
        result = subprocess.run(
            [sys.executable, "-IB", Path(__file__).with_name("interrupt_job_launch.py"),
             worker_pid, dispatch, *self.host, "apply"],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        self.assertGreater(int(worker_pid.read_text()), 0)
        self.assertEqual(self.invoke("status")[0]["maintenance"]["phase"], "uncertain")
        self.invoke("apply", "--wait", "1s", status=4)

    def test_interrupted_delete_requires_reconciliation(self):
        deleted, resume = threading.Event(), threading.Event()

        def hold_response(kind, identifier):
            if kind == "containers" and identifier == CID:
                deleted.set()
                resume.wait(10)

        self.api.after_remove = hold_response
        with subprocess.Popen(
            [*self.host, "apply"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        ) as proc:
            try:
                self.assertTrue(
                    deleted.wait(8), "apply did not reach the Engine DELETE"
                )
                proc.send_signal(signal.SIGTERM)
            finally:
                resume.set()
            output, errors = proc.communicate(timeout=10)
            self.assertEqual(proc.returncode, 6, (output, errors))
        record = self.invoke("status")[0]["maintenance"]
        self.assertIsNotNone(record)
        self.invoke("apply", "--wait", "1s", status=4)
        self.assertEqual(sum(m == "DELETE" for m, _ in self.api.requests), 1)
        evidence = self.root / "proof.json"
        evidence.write_text(
            json.dumps(
                dict(
                    schema_version=1,
                    record_id=record["id"],
                    daemon_id="fixture-daemon",
                    observed_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                    observer="fixture",
                    evidence="worker exited and fixture completed the only DELETE",
                    participants_drained=True,
                    daemon_operations_complete=True,
                )
            )
        )
        self.invoke(
            "reconcile", "--record-id", record["id"], "--evidence", str(evidence)
        )
        self.assertIsNone(self.invoke("status")[0]["maintenance"])


if __name__ == "__main__":
    unittest.main()
