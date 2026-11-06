"""Cache resets stay inside explicit roots and preserve administrator permissions."""

import contextlib
import fcntl
import io
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "images/utils"))

from ci_utils import file_cache


class FileCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ci-file-cache-")
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name).resolve()
        self.build = self.root / "go/build"
        self.mod = self.root / "go/mod"
        self.store = self.root / "pnpm/store"
        for path in (self.build, self.mod, self.store):
            path.mkdir(parents=True)
            (path / ".fixture").write_text("cache data")

    def invoke(self, tool, *args):
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / f"images/utils/bin/ci-{tool}-cleanup"),
                *map(str, args),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        events = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertTrue(events, result.stderr)
        self.assertEqual(events[-1]["exit_code"], result.returncode, result.stderr)
        return result.returncode, events

    def invoke_in_process(self, tool, *args):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = file_cache.main(tool, list(map(str, args)))
        return code, [json.loads(line) for line in output.getvalue().splitlines()]

    def test_omitted_paths_select_mfci_defaults(self):
        build = ("go-build", pathlib.Path("/opt/actions-runner/shared/cache/go/build"))
        mod = ("go-mod", pathlib.Path("/opt/actions-runner/shared/cache/go/mod"))
        store = (
            "pnpm-store",
            pathlib.Path("/opt/actions-runner/shared/cache/pnpm/store"),
        )
        for tool, args, expected in (
            ("go", [], [build, mod]),
            ("go", ["--build-cache"], [build]),
            ("go", ["--mod-cache"], [mod]),
            ("go", ["--build-cache", "--mod-cache"], [build, mod]),
            ("pnpm", [], [store]),
            ("pnpm", ["--store-dir"], [store]),
        ):
            with self.subTest(tool=tool, args=args):
                parsed, selected = file_cache.arguments(tool, args)
                self.assertEqual(selected, expected)
                self.assertFalse(parsed.apply)

    def test_no_arguments_preview_and_apply_only_default_caches(self):
        defaults = {
            "go-build": str(self.build),
            "go-mod": str(self.mod),
            "pnpm-store": str(self.store),
        }
        with mock.patch.dict(file_cache.DEFAULT_PATHS, defaults):
            for tool, selected in (
                ("go", [self.build, self.mod]),
                ("pnpm", [self.store]),
            ):
                with self.subTest(tool=tool):
                    code, events = self.invoke_in_process(tool)
                    self.assertEqual(code, 0, events)
                    self.assertFalse(events[-1]["mutation_started"])
                    self.assertEqual(
                        [
                            event["path"]
                            for event in events
                            if event["event"] == "cache_plan"
                        ],
                        list(map(str, selected)),
                    )
                    self.assertTrue(
                        all((path / ".fixture").is_file() for path in selected)
                    )
                    code, events = self.invoke_in_process(tool, "--apply")
                    self.assertEqual(code, 0, events)
                    self.assertTrue(all(not list(path.iterdir()) for path in selected))

    def test_bare_cache_flag_resets_only_that_default(self):
        defaults = {"go-build": str(self.build), "go-mod": str(self.mod)}
        for option, selected, retained in (
            ("--build-cache", self.build, self.mod),
            ("--mod-cache", self.mod, self.build),
        ):
            with (
                self.subTest(option=option),
                mock.patch.dict(file_cache.DEFAULT_PATHS, defaults),
            ):
                for path in (self.build, self.mod):
                    (path / ".fixture").write_text("cache data")
                code, events = self.invoke_in_process("go", option, "--apply")
                self.assertEqual(code, 0, events)
                self.assertEqual(list(selected.iterdir()), [])
                self.assertTrue((retained / ".fixture").is_file())

    def test_missing_default_prevents_any_deletion(self):
        missing = self.root / "missing/go/mod"
        defaults = {"go-build": str(self.build), "go-mod": str(missing)}
        with mock.patch.dict(file_cache.DEFAULT_PATHS, defaults):
            code, events = self.invoke_in_process("go", "--apply")
        self.assertEqual(code, 2, events)
        self.assertFalse(events[-1]["mutation_started"])
        self.assertTrue((self.build / ".fixture").is_file())
        self.assertFalse(missing.exists())

    def test_default_preview_counts_content_without_changes(self):
        for tool, option, path in (
            ("go", "--build-cache", self.build),
            ("go", "--mod-cache", self.mod),
            ("pnpm", "--store-dir", self.store),
        ):
            with self.subTest(tool=tool, option=option):
                (path / "nested").mkdir()
                (path / "nested/item").write_bytes(b"1234")
                (path / "link").symlink_to("missing")
                before = path.stat()
                code, events = self.invoke(tool, option, path)
                self.assertEqual(code, 0, events)
                plan = next(event for event in events if event["event"] == "cache_plan")
                self.assertEqual(plan["files"], 2)
                self.assertEqual(plan["directories"], 1)
                self.assertEqual(plan["symlinks"], 1)
                self.assertEqual(plan["logical_bytes"], 14)
                self.assertIsNone(plan["physical_reclaimed_bytes"])
                self.assertTrue(plan["requires_idle_consumers"])
                self.assertFalse(events[-1]["mutation_started"])
                self.assertEqual((path / "nested/item").read_bytes(), b"1234")
                self.assertTrue((path / "link").is_symlink())
                self.assertEqual(path.stat().st_mtime_ns, before.st_mtime_ns)

    def test_go_reset_selects_only_requested_caches_and_keeps_roots(self):
        self.build.chmod(0o2770)
        before = self.build.stat()
        code, events = self.invoke("go", "--build-cache", self.build, "--apply")
        self.assertEqual(code, 0, events)
        self.assertEqual(list(self.build.iterdir()), [])
        after = self.build.stat()
        self.assertEqual(
            (after.st_ino, after.st_uid, after.st_gid, after.st_mode),
            (before.st_ino, before.st_uid, before.st_gid, before.st_mode),
        )
        self.assertTrue((self.mod / ".fixture").is_file())
        self.assertTrue((self.store / ".fixture").is_file())

    def test_both_go_caches_can_be_reset_together(self):
        code, events = self.invoke(
            "go", "--build-cache", self.build, "--mod-cache", self.mod, "--apply"
        )
        self.assertEqual(code, 0, events)
        self.assertEqual(list(self.build.iterdir()), [])
        self.assertEqual(list(self.mod.iterdir()), [])
        self.assertEqual(sum(e["event"] == "cache_reset" for e in events), 2)

    def test_read_only_go_modules_are_removed(self):
        directory = self.mod / "example.test/module@v1.0.0/nested"
        directory.mkdir(parents=True)
        (directory / "source.go").write_text("package fixture\n")
        (directory / "source.go").chmod(0o444)
        directory.chmod(0o555)
        directory.parent.chmod(0o555)
        code, events = self.invoke("go", "--mod-cache", self.mod, "--apply")
        self.assertEqual(code, 0, events)
        self.assertEqual(list(self.mod.iterdir()), [])

    def test_pnpm_reset_clears_all_store_versions_and_hidden_entries(self):
        for version in ("v10", "v11"):
            path = self.store / version / "files/ab"
            path.mkdir(parents=True)
            (path / "fixture").write_text("package content")
        before = self.store.stat()
        code, events = self.invoke("pnpm", "--store-dir", self.store, "--apply")
        self.assertEqual(code, 0, events)
        self.assertEqual(list(self.store.iterdir()), [])
        self.assertEqual(self.store.stat().st_ino, before.st_ino)
        self.assertEqual(self.store.stat().st_mode, before.st_mode)

    def test_symlink_targets_and_external_hard_links_survive(self):
        outside = self.root / "outside"
        outside.mkdir()
        original = outside / "keep"
        original.write_text("must survive")
        (self.store / "directory-link").symlink_to(outside, target_is_directory=True)
        (self.store / "file-link").symlink_to(original)
        (self.store / "missing-link").symlink_to(outside / "missing")
        os.link(original, self.store / "hard-link")
        code, events = self.invoke("pnpm", "--store-dir", self.store, "--apply")
        self.assertEqual(code, 0, events)
        self.assertEqual(original.read_text(), "must survive")
        self.assertEqual(list(self.store.iterdir()), [])

    def test_empty_caches_are_successful_noops(self):
        (self.build / ".fixture").unlink()
        for args in ([], ["--apply"]):
            code, events = self.invoke("go", "--build-cache", self.build, *args)
            self.assertEqual(code, 0, events)
            plan = next(event for event in events if event["event"] == "cache_plan")
            self.assertEqual(plan["files"], 0)
            self.assertEqual(plan["logical_bytes"], 0)

    def test_explicit_paths_must_be_valid_and_never_fall_back_to_defaults(self):
        for tool, args in (
            ("go", ["--build-cache", ""]),
            ("go", ["--mod-cache", ""]),
            ("pnpm", ["--store-dir", ""]),
            ("go", ["--build-cache", "/"]),
            ("go", ["--build-cache", str(self.root)]),
            ("go", ["--build-cache", "go/build"]),
            ("go", ["--build-cache", str(self.mod)]),
            ("go", ["--build-cache", str(self.build) + "/"]),
            ("go", ["--build-cache", str(self.root) + "/go/../go/build"]),
            ("pnpm", ["--store-dir", str(self.store / "v11")]),
        ):
            with self.subTest(tool=tool, args=args):
                code, events = self.invoke(tool, *args, "--apply")
                self.assertEqual(code, 2, events)
                self.assertFalse(events[-1]["mutation_started"])
                self.assertTrue((self.build / ".fixture").is_file())

    def test_missing_second_cache_prevents_any_deletion(self):
        missing = self.root / "missing/go/mod"
        code, events = self.invoke(
            "go", "--build-cache", self.build, "--mod-cache", missing, "--apply"
        )
        self.assertEqual(code, 2, events)
        self.assertFalse(events[-1]["mutation_started"])
        self.assertFalse(missing.exists())
        self.assertTrue((self.build / ".fixture").is_file())

    def test_symlink_cache_root_is_rejected(self):
        link = self.root / "alias/go/build"
        link.parent.mkdir(parents=True)
        link.symlink_to(self.build, target_is_directory=True)
        code, events = self.invoke("go", "--build-cache", link, "--apply")
        self.assertEqual(code, 2, events)
        self.assertTrue(link.is_symlink())
        self.assertTrue((self.build / ".fixture").is_file())

    def test_symlink_ancestor_is_rejected(self):
        link = self.root / "alias"
        link.symlink_to(self.root, target_is_directory=True)
        code, events = self.invoke("go", "--build-cache", link / "go/build", "--apply")
        self.assertEqual(code, 2, events)
        self.assertTrue((self.build / ".fixture").is_file())

    def test_overlapping_caches_are_rejected(self):
        nested = self.build / "go/mod"
        nested.mkdir(parents=True)
        code, events = self.invoke(
            "go", "--build-cache", self.build, "--mod-cache", nested, "--apply"
        )
        self.assertEqual(code, 2, events)
        self.assertTrue((self.build / ".fixture").is_file())

    def test_special_file_prevents_any_deletion(self):
        os.mkfifo(self.mod / "pipe")
        code, events = self.invoke(
            "go", "--build-cache", self.build, "--mod-cache", self.mod, "--apply"
        )
        self.assertEqual(code, 2, events)
        self.assertFalse(events[-1]["mutation_started"])
        self.assertTrue((self.build / ".fixture").is_file())

    def test_busy_second_cache_prevents_any_deletion(self):
        fd = os.open(self.mod, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            code, events = self.invoke(
                "go", "--build-cache", self.build, "--mod-cache", self.mod, "--apply"
            )
        finally:
            os.close(fd)
        self.assertEqual(code, 4, events)
        self.assertFalse(events[-1]["mutation_started"])
        self.assertTrue((self.build / ".fixture").is_file())

    def test_same_filesystem_nested_bind_mount_prevents_any_deletion(self):
        nested = self.store / "mounted store"
        nested.mkdir()
        mountpoint = str(nested).replace(" ", "\\040")
        mounts = f"1 0 0:1 / / rw - tmpfs tmpfs rw\n2 1 0:1 / {mountpoint} rw - tmpfs tmpfs rw\n"
        with (
            mock.patch.object(file_cache.sys, "platform", "linux"),
            mock.patch.object(pathlib.Path, "read_text", return_value=mounts),
        ):
            code, events = self.invoke_in_process(
                "pnpm", "--store-dir", self.store, "--apply"
            )
        self.assertEqual(code, 2, events)
        self.assertFalse(events[-1]["mutation_started"])
        self.assertTrue((self.store / ".fixture").is_file())

    def test_root_replacement_after_preview_prevents_deletion(self):
        original_walk = file_cache.walk_cache
        moved = self.build.with_name("original-build")

        def replace_root(fd, path, device, **kwargs):
            counts = original_walk(fd, path, device, **kwargs)
            if path == self.build and not kwargs.get("remove"):
                path.rename(moved)
                path.mkdir()
                (path / "replacement").write_text("keep replacement")
            return counts

        with mock.patch.object(file_cache, "walk_cache", side_effect=replace_root):
            code, events = self.invoke_in_process(
                "go", "--build-cache", self.build, "--apply"
            )
        self.assertEqual(code, 2, events)
        self.assertFalse(events[-1]["mutation_started"])
        self.assertTrue((moved / ".fixture").is_file())
        self.assertTrue((self.build / "replacement").is_file())

    def test_failure_reports_partial_reset_and_restores_directory_permissions(self):
        directory = self.mod / "readonly"
        directory.mkdir()
        (directory / "source.go").write_text("package fixture")
        directory.chmod(0o555)
        original_unlink = file_cache.os.unlink

        def fail_one(name, **kwargs):
            if name == "source.go":
                raise PermissionError("fixture deletion denied")
            return original_unlink(name, **kwargs)

        try:
            with mock.patch.object(file_cache.os, "unlink", side_effect=fail_one):
                code, events = self.invoke_in_process(
                    "go", "--mod-cache", self.mod, "--apply"
                )
            self.assertEqual(code, 5, events)
            self.assertTrue(events[-1]["mutation_started"])
            self.assertEqual(events[-1]["status"], "partial-failure")
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o555)
            self.assertTrue((directory / "source.go").is_file())
        finally:
            directory.chmod(0o755)


if __name__ == "__main__":
    unittest.main()
