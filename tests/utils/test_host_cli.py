"""T-18–20/22/24/28/32/33: public host launcher and retained uncertainty."""

import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import unittest

from host_fixture import HostDocker
from test_apply_cli import DIGEST, ROOT, StatefulAPI

sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "images/utils")]
from ci_docker_gate import Gate, GateError


@unittest.skipUnless(
    hasattr(socket, "SO_PEERCRED") and os.geteuid() == 0,
    "host launcher requires an isolated Linux root controller",
)
class HostCLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cu-host-", dir="/tmp")
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.api = self.enterContext(StatefulAPI())
        self.docker = self.enterContext(HostDocker(self.root, self.api.endpoint))
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
            "image": DIGEST,
            "gate_directory": str(self.root / "gate"),
            "job_gid": 0,
            "participants": ["test-runner"],
            "admission_evidence": "fixture-only-lifecycle-adapter",
            "docker_cli": str(self.docker.path),
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

    def invoke(self, *args):
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "scripts/ci-docker-maintenance"),
                "--config",
                str(self.root / "host.json"),
                *args,
            ],
            text=True,
            capture_output=True,
            timeout=25,
            check=False,
        )
        return result, [json.loads(line) for line in result.stdout.splitlines()]

    def test_success_has_hardened_launch_and_releases_only_after_final_result(self):
        result, events = self.invoke("apply", "--profile", "weekly")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIsNone(Gate(self.root / "gate").status()["maintenance"])
        for flag in (
            "--pull=never",
            "--network=none",
            "--read-only",
            "--user=1001:2001",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--group-add=0",
        ):
            self.assertIn(flag, self.docker.create)
        self.assertEqual(
            [e["phase"] for e in events if e["event"] == "host_observations"],
            ["before", "after"],
        )
        self.assertTrue(events[-1]["completion_known"])
        self.assertEqual(self.docker.calls[-1][0], "rm")
        self.assertFalse(
            any(
                call[0] in ("pull", "build", "stop", "kill")
                for call in self.docker.calls
            )
        )

    def test_launcher_failure_before_start_is_distinct_and_can_release(self):
        self.docker.mode = "create-error"
        result, events = self.invoke("apply")
        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertEqual(events[-1]["exit_code"], 7)
        self.assertIsNone(Gate(self.root / "gate").status()["maintenance"])
        self.assertFalse(any(method == "DELETE" for method, _ in self.api.requests))

    def test_unknown_start_or_lost_terminal_report_preserves_admission_block(self):
        # Separate cases need separate provisioned gates; no test reset conceals uncertainty.
        self.docker.mode = "lost-report"
        result, _ = self.invoke("apply")
        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        gate = Gate(self.root / "gate")
        self.assertEqual(gate.status()["maintenance"]["phase"], "uncertain")
        with self.assertRaises(GateError), gate.job(wait_seconds=0.02):
            self.fail("lost terminal report reopened admission")
        self.assertFalse(
            any(call[0] in ("rm", "stop", "kill") for call in self.docker.calls)
        )

    def test_failed_start_reply_retains_unknown_state_without_forcing_a_stop(self):
        self.docker.mode = "start-error"
        result, _ = self.invoke("apply")
        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertEqual(
            Gate(self.root / "gate").status()["maintenance"]["phase"], "uncertain"
        )
        self.assertFalse(
            any(call[0] in ("rm", "stop", "kill") for call in self.docker.calls)
        )

    def test_unqualified_image_and_mutable_settings_fail_before_launch(self):
        self.docker.mode = "wrong-image"
        result, _ = self.invoke("apply")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertFalse(any(call[0] == "create" for call in self.docker.calls))
        self.assertIsNone(Gate(self.root / "gate").status()["maintenance"])
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
                    f"subprocess.run([sys.executable, '-B', {str(ROOT / 'scripts/ci-docker-maintenance')!r}, 'job-complete'], check=True)"
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


if __name__ == "__main__":
    unittest.main()
