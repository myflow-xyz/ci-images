"""T-24: host path verification and filesystem deduplication."""

import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))

from ci_docker_gate import GateError
from ci_docker_storage import measure


class HostStorageTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory(prefix="ci-utils-storage-", dir="/tmp")
        self.addCleanup(self.root.cleanup)
        self.path = pathlib.Path(self.root.name)
        for name in ("docker", "containerd"):
            (self.path / name).mkdir()
        self.info = {
            "ID": "daemon",
            "DockerRootDir": str(self.path / "docker"),
            "Driver": "overlayfs",
            "DriverStatus": [["driver-type", "io.containerd.snapshotter.v1"]],
        }
        self.sources = {
            "docker": str(self.path / "docker"),
            "containerd": str(self.path / "containerd"),
            "other": [],
        }

    def test_real_shared_filesystem_is_measured_once_with_both_storage_sources(self):
        value = measure(self.info, self.sources, "a" * 32)
        self.assertTrue(value["complete"])
        self.assertEqual(value["daemon_id"], "daemon")
        self.assertEqual(len(value["filesystems"]), 1)
        record = value["filesystems"][0]
        self.assertEqual(set(record["roles"]), {"docker", "containerd"})
        self.assertEqual(len(record["paths"]), 2)
        self.assertGreater(record["total_bytes"], 0)
        self.assertGreaterEqual(record["available_bytes"], 0)

    def test_wrong_docker_root_and_missing_containerd_are_not_partial_success(self):
        for patch in (
            {"docker": str(self.path / "containerd")},
            {"containerd": None},
            {"containerd": str(self.path / "missing")},
        ):
            with self.subTest(patch=patch), self.assertRaises(GateError):
                measure(self.info, {**self.sources, **patch}, "a" * 32)

    def test_classic_store_can_explicitly_omit_separate_containerd_storage(self):
        value = measure(
            {**self.info, "Driver": "overlay2", "DriverStatus": []},
            {**self.sources, "containerd": None},
            "a" * 32,
        )
        self.assertTrue(value["complete"])
        self.assertEqual(value["filesystems"][0]["roles"], ["docker"])

    def test_unknown_store_layout_is_not_guessed(self):
        with self.assertRaises(GateError):
            measure({**self.info, "DriverStatus": None}, self.sources, "a" * 32)

    @unittest.skipUnless(hasattr(os, "O_PATH"), "Linux host path handle")
    def test_measurement_does_not_require_reading_storage_directory_contents(self):
        path = self.path / "docker"
        path.chmod(0)
        try:
            self.assertTrue(measure(self.info, self.sources, "a" * 32)["complete"])
        finally:
            path.chmod(0o700)


if __name__ == "__main__":
    unittest.main()
