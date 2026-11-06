"""Public command discovery and usage help work without daemon or cache access."""

import os
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class CatalogTests(unittest.TestCase):
    def invoke(self, command, *args):
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "images/utils/bin" / command), *args],
            env={**os.environ, "PATH": "", "DOCKER_HOST": "invalid-for-discovery"},
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout

    def test_list_describes_supported_commands_and_operations(self):
        catalog = self.invoke("ci-utils-list")
        for text in (
            "ci-utils",
            "ci-utils-list",
            "ci-docker-cleanup",
            "ci-remove-images",
            "ci-go-cleanup",
            "ci-pnpm-cleanup",
            "check|plan|apply|version",
            "--versions",
            "--build-cache",
            "--mod-cache",
            "--store-dir",
            "docker buildx",
            "ci-buildkit-probe",
            "Internal capability checker",
            "full reset",
        ):
            with self.subTest(text=text):
                self.assertIn(text, catalog)
        self.assertIn(catalog.strip(), self.invoke("ci-utils"))

    def test_short_help_has_defaults_and_examples(self):
        for command, paths, example in (
            (
                "ci-go-cleanup",
                (
                    "/opt/actions-runner/shared/cache/go/build",
                    "/opt/actions-runner/shared/cache/go/mod",
                ),
                "ci-go-cleanup --build-cache /var/cache/go/build",
            ),
            (
                "ci-pnpm-cleanup",
                ("/opt/actions-runner/shared/cache/pnpm/store",),
                "ci-pnpm-cleanup --store-dir /var/cache/pnpm/store",
            ),
        ):
            with self.subTest(command=command):
                output = self.invoke(command, "-h")
                self.assertIn("Examples:", output)
                self.assertIn("preview only", output)
                self.assertIn(example, output)
                self.assertIn(command + " --apply", output)
                for path in paths:
                    self.assertIn(path, output)

    def test_catalog_commands_support_short_help_with_examples(self):
        for command in ("ci-utils", "ci-utils-list"):
            with self.subTest(command=command):
                output = self.invoke(command, "-h")
                self.assertIn(f"usage: {command}", output)
                self.assertIn("Examples:", output)
                self.assertIn("ci-go-cleanup -h", output)
                self.assertIn("ci-pnpm-cleanup -h", output)


if __name__ == "__main__":
    unittest.main()
