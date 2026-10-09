"""T-18–20: daemon-wide admission, draining, and durable uncertain state."""

import concurrent.futures
import os
import pathlib
import select
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))

from ci_docker_gate import Gate, GateError


class GateTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory(prefix="ci-utils-gate-", dir="/tmp")
        self.addCleanup(self.root.cleanup)
        self.path = pathlib.Path(self.root.name) / "gate"
        self.gate = Gate(self.path)
        self.gate.initialize()

    def start_holder(self, kind):
        program = """
import signal, sys
from ci_docker_gate import Gate
gate = Gate(sys.argv[1])
context = gate.job() if sys.argv[2] == 'job' else gate.maintenance('daemon', 'policy')
with context:
    print('ready', flush=True)
    signal.pause()
"""
        process = subprocess.Popen(
            [sys.executable, "-B", "-c", program, str(self.path), kind],
            env={
                **os.environ,
                "PYTHONPATH": str(
                    pathlib.Path(__file__).resolve().parents[2] / "scripts"
                ),
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        def finish():
            if process.poll() is None:
                process.kill()
            process.wait(timeout=2)
            process.stdout.close()

        self.addCleanup(finish)
        ready, _, _ = select.select([process.stdout], [], [], 2)
        self.assertTrue(ready, "lease holder did not initialize")
        self.assertEqual(process.stdout.readline().strip(), "ready")
        return process

    def test_killed_maintenance_process_does_not_reopen_admission(self):
        holder = self.start_holder("maintenance")
        holder.kill()
        holder.wait(timeout=2)
        self.assertIsNotNone(Gate(self.path).status()["maintenance"])
        with self.assertRaises(GateError), Gate(self.path).job(wait_seconds=0.02):
            self.fail("a released process lock was mistaken for completed cleanup")

    def test_two_worker_processes_and_crashed_jobs_remain_protected(self):
        first = self.start_holder("job")
        second = self.start_holder("job")
        with (
            self.assertRaises(GateError),
            Gate(self.path).maintenance("daemon", "policy", wait_seconds=0.02),
        ):
            self.fail("maintenance overlapped separate worker processes")
        first.kill()
        second.kill()
        first.wait(timeout=2)
        second.wait(timeout=2)
        with (
            self.assertRaises(GateError),
            Gate(self.path).maintenance("daemon", "policy", wait_seconds=0.02),
        ):
            self.fail("crashed jobs lost their persistent completion records")
        self.assertEqual(len(self.gate.status()["jobs"]), 2)
        self.assertIsNone(self.gate.status()["maintenance"])
        with self.assertRaises(GateError), Gate(self.path).job(wait_seconds=0.02):
            self.fail("refused maintenance must preserve unresolved job admission")

    def test_crashed_job_blocks_new_jobs_before_any_maintenance_attempt(self):
        holder = self.start_holder("job")
        holder.kill()
        holder.wait(timeout=2)
        with self.assertRaises(GateError), Gate(self.path).job(wait_seconds=0.02):
            self.fail("new job entered after an unresolved worker crash")

    def test_jobs_share_access_and_maintenance_waits_for_both(self):
        with self.gate.job() as first, Gate(self.path).job() as second:
            self.assertEqual(len(self.gate.status()["jobs"]), 2)
            with (
                self.assertRaises(GateError) as raised,
                Gate(self.path).maintenance("daemon", "policy", wait_seconds=0.05),
            ):
                self.fail("maintenance overlapped jobs")
            self.assertEqual(raised.exception.code, 4)
            self.assertIsNone(self.gate.status()["maintenance"])
            first.complete()
            second.complete()
        with self.gate.maintenance("daemon", "policy") as maintenance:
            self.assertEqual(self.gate.status()["maintenance"]["phase"], "active")
            maintenance.complete()
        self.assertIsNone(self.gate.status()["maintenance"])

    def test_new_job_cannot_enter_while_maintenance_drains(self):
        def maintain():
            with Gate(self.path).maintenance(
                "daemon", "policy", wait_seconds=1
            ) as lease:
                lease.complete()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            with self.gate.job() as job:
                worker = executor.submit(maintain)
                deadline = time.monotonic() + 0.5
                while (
                    self.gate.status()["maintenance"] is None
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.005)
                self.assertIsNotNone(self.gate.status()["maintenance"])
                with (
                    self.assertRaises(GateError),
                    Gate(self.path).job(wait_seconds=0.03),
                ):
                    self.fail("new job entered during drain")
                self.assertFalse(worker.done())
                job.complete()
            worker.result(timeout=2)

    def test_uncertain_maintenance_stays_blocked_after_lock_release(self):
        with self.gate.maintenance("daemon", "policy"):
            pass
        self.assertEqual(self.gate.status()["maintenance"]["phase"], "uncertain")
        with self.assertRaises(GateError), Gate(self.path).job(wait_seconds=0.02):
            pass
        with (
            self.assertRaises(GateError),
            Gate(self.path).maintenance("daemon", "policy", wait_seconds=0.02),
        ):
            pass

    def test_uncertain_job_prevents_cleanup_after_shared_lock_release(self):
        with self.gate.job():
            pass
        self.assertEqual(len(self.gate.status()["jobs"]), 1)
        with (
            self.assertRaises(GateError),
            self.gate.maintenance("daemon", "policy", wait_seconds=0.03),
        ):
            self.fail("cleanup entered with unresolved job completion")

    def test_manual_and_scheduled_runs_use_one_exclusive_gate(self):
        with self.gate.maintenance("daemon", "policy") as lease:
            with (
                self.assertRaises(GateError),
                Gate(self.path).maintenance("daemon", "policy", wait_seconds=0.02),
            ):
                pass
            lease.complete()

    def test_untrusted_state_directory_and_lock_symlink_are_rejected(self):
        self.path.chmod(0o777)
        with self.assertRaises(GateError), Gate(self.path).job():
            pass
        self.path.chmod(0o750)
        lock = self.path / "activity.lock"
        lock.unlink(missing_ok=True)
        lock.symlink_to(self.path / "admission.lock")
        with self.assertRaises(GateError), Gate(self.path).job():
            pass


if __name__ == "__main__":
    unittest.main()
