"""Verify release packaging before the publication job can upload any assets."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
VERSION = "1.2.3"
REVISION = "a" * 40


class BundleTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for arch, machine in (("amd64", 62), ("arm64", 183)):
            (self.root / f"probe-{arch}").write_bytes(
                b"\x7fELF\x02\x01" + bytes(12) + machine.to_bytes(2, "little")
            )

    def package(self, dest):
        return subprocess.run(
            [
                sys.executable,
                ROOT / ".github/scripts/package-ci-utils.py",
                VERSION,
                REVISION,
                self.root,
                dest,
            ],
            capture_output=True,
            text=True,
        )

    def test_reproducible_archives_and_exact_checksums(self):
        first, second = self.root / "first", self.root / "second"
        for dest in (first, second):
            result = self.package(dest)
            self.assertEqual(result.returncode, 0, result.stderr)
        sums = f"ci-utils_{VERSION}_SHA256SUMS"
        self.assertEqual((first / sums).read_bytes(), (second / sums).read_bytes())
        names = set()
        for line in (first / sums).read_text().splitlines():
            digest, name = line.split()
            path = first / name
            names.add(name)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            arch = name.split("_")[-1].split(".")[0]
            base = name.removesuffix(".tar.gz")
            with tarfile.open(path) as tar:
                self.assertEqual(
                    json.load(tar.extractfile(f"{base}/lib/build.json")),
                    dict(version=VERSION, revision=REVISION, arch=arch),
                )
                self.assertEqual(
                    tar.extractfile(f"{base}/lib/ci-buildkit-probe").read(),
                    (self.root / f"probe-{arch}").read_bytes(),
                )
                for member in tar:
                    self.assertTrue(
                        member.isfile() and member.name.startswith(base + "/")
                    )
        self.assertEqual(
            names,
            {f"ci-utils_{VERSION}_linux_{arch}.tar.gz" for arch in ("amd64", "arm64")},
        )

    def test_rejects_a_probe_built_for_the_wrong_architecture(self):
        (self.root / "probe-amd64").write_bytes(
            (self.root / "probe-arm64").read_bytes()
        )
        result = self.package(self.root / "output")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("amd64", result.stderr)

    def test_every_release_command_has_a_spec_and_an_indexed_reference(self):
        dest = self.root / "inventory"
        result = self.package(dest)
        self.assertEqual(result.returncode, 0, result.stderr)
        with tarfile.open(dest / f"ci-utils_{VERSION}_linux_arm64.tar.gz") as archive:
            commands = {
                Path(member.name).name for member in archive if "/bin/" in member.name
            }
        self.assertEqual(len(commands), 8)
        expected = commands | {"install", "ci-buildkit-probe"}
        specs = ROOT / "scripts/tests/ci-utils"
        docs = ROOT / "scripts/docs/ci-utils"
        self.assertEqual(
            {p.name.removesuffix("_spec.sh") for p in specs.glob("*_spec.sh")}, expected
        )
        self.assertEqual({p.stem for p in docs.glob("*.md")}, expected)
        index = (ROOT / "scripts/ci-utils/README.md").read_text()
        for name in expected:
            self.assertIn(f"../docs/ci-utils/{name}.md)", index)
            self.assertIn(
                f"shellspec tests/ci-utils/{name}_spec.sh",
                (docs / f"{name}.md").read_text(),
            )
