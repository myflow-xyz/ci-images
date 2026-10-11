"""T-18–20: real host-lease protocol and revocation across a Unix socket."""

import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "images/utils")]

from ci_docker_gate import Gate, LeaseServer
from ci_utils.engine import Engine, Failure
from ci_utils.guard import LeaseGuard

POLICY = "a" * 64
DIGEST = "sha256:" + "b" * 64


@unittest.skipUnless(
    hasattr(socket, "SO_PEERCRED") and os.geteuid() == 0,
    "host lease tests require an isolated Linux root controller",
)
class GuardTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory(prefix="ci-utils-lease-", dir="/tmp")
        self.addCleanup(self.root.cleanup)
        self.gate = Gate(pathlib.Path(self.root.name) / "gate")
        self.gate.initialize()
        self.engine = Engine("unix:///unused.sock")

    def guard(self, server, lease, **changes):
        fields = {
            "run_id": lease.id,
            "daemon_id": "daemon",
            "policy_hash": POLICY,
            "profile": "daily",
            "image_digest": DIGEST,
        }
        fields.update(changes)
        return LeaseGuard(self.engine, str(server.path), **fields)

    def test_live_lease_binds_daemon_policy_profile_image_and_run(self):
        with (
            self.gate.maintenance("daemon", POLICY) as lease,
            LeaseServer(
                self.gate, lease, "daily", DIGEST, client_pid=os.getpid()
            ) as server,
        ):
            self.guard(server, lease).check()
            for change in [
                {"daemon_id": "other"},
                {"policy_hash": "c" * 64},
                {"profile": "weekly"},
                {"image_digest": "sha256:" + "d" * 64},
                {"run_id": "e" * 32},
            ]:
                with self.subTest(change=change):
                    with self.assertRaises(Failure) as raised:
                        self.guard(server, lease, **change).check()
                    self.assertEqual(raised.exception.code, 4)
            lease.complete()

    def test_complete_or_expired_lease_cannot_authorize_more_requests(self):
        with (
            self.gate.maintenance("daemon", POLICY) as lease,
            LeaseServer(
                self.gate, lease, "daily", DIGEST, timeout=0.02, client_pid=os.getpid()
            ) as server,
        ):
            time.sleep(0.03)
            with self.assertRaises(Failure) as raised:
                self.guard(server, lease).check()
            self.assertEqual(raised.exception.code, 4)
            lease.complete()
        with (
            self.gate.maintenance("daemon", POLICY) as lease,
            LeaseServer(
                self.gate, lease, "daily", DIGEST, client_pid=os.getpid()
            ) as server,
        ):
            lease.complete()
            with self.assertRaises(Failure):
                self.guard(server, lease).check()

    def test_lost_lease_after_a_mutation_requires_reconciliation(self):
        with (
            self.gate.maintenance("daemon", POLICY) as lease,
            LeaseServer(
                self.gate, lease, "daily", DIGEST, client_pid=os.getpid()
            ) as server,
        ):
            guard = self.guard(server, lease)
            self.engine.mutation_started = True
            lease.complete()
            with self.assertRaises(Failure) as raised:
                guard.check()
            self.assertEqual(raised.exception.code, 6)

    def test_another_process_cannot_borrow_the_same_lease(self):
        with (
            self.gate.maintenance("daemon", POLICY) as lease,
            LeaseServer(
                self.gate, lease, "daily", DIGEST, client_pid=os.getpid()
            ) as server,
        ):
            program = """
import sys
from ci_utils.engine import Engine, Failure
from ci_utils.guard import LeaseGuard
try:
    LeaseGuard(Engine('unix:///unused.sock'), *sys.argv[1:]).check()
except Failure as error:
    sys.exit(error.code)
"""
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    program,
                    str(server.path),
                    lease.id,
                    "daemon",
                    POLICY,
                    "daily",
                    DIGEST,
                ],
                env={**os.environ, "PYTHONPATH": str(ROOT / "images/utils")},
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            self.assertEqual(result.returncode, 4, result.stderr)
            self.guard(server, lease).check()
            lease.complete()

    def test_missing_socket_is_not_an_authority_flag(self):
        guard = LeaseGuard(
            self.engine, "/missing/socket", "a" * 32, "daemon", POLICY, "daily", DIGEST
        )
        with self.assertRaises(Failure) as raised:
            guard.check()
        self.assertEqual(raised.exception.code, 4)


if __name__ == "__main__":
    unittest.main()
