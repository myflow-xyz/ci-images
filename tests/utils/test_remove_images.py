"""Explicit suite retirement must preserve unrelated and protected references."""

import contextlib
import copy
import io
import json
import os
import pathlib
import sys
import unittest
import urllib.parse
from unittest import mock

from test_apply_cli import StatefulAPI
from test_policy import CID, IID, container, image

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "images/utils")]
PREFIX = "ghcr.io/myflow-xyz/ci-"
REF = PREFIX + "go:0.0.1"
ALIAS = "example.test/retained:latest"


class VersionAPI(StatefulAPI):
    def __init__(self, tags=None):
        super().__init__(
            {
                "containers": {},
                "networks": {},
                "images": {IID: {**image(), "RepoTags": tags or [REF, ALIAS]}},
            }
        )
        for reference in self.objects["images"][IID]["RepoTags"]:
            self.add_reference(reference)

    def add_reference(self, reference):
        path = "/v1.48/images/" + urllib.parse.quote(reference, safe="")
        self.routes[("GET", path + "/json")] = lambda: self.inspect(
            "images", reference
        )
        self.routes[("DELETE", path + "?force=false&noprune=true")] = lambda: (
            self.remove("images", reference)
        )

    def inspect(self, kind, identifier):
        self.before_inspect(kind, identifier)
        for item in self.objects[kind].values():
            if identifier == item["Id"] or identifier in (
                (item.get("RepoTags") or []) + (item.get("RepoDigests") or [])
            ):
                return 200, item
        return 404, {}

    def remove(self, kind, identifier):
        error = self.errors.get((kind, identifier))
        if error:
            return error() if callable(error) else (error, {})
        status, item = self.inspect(kind, identifier)
        if status != 200:
            return status, item
        item["RepoTags"].remove(identifier)
        result = [{"Untagged": identifier}]
        if not item["RepoTags"]:
            self.objects[kind].pop(item["Id"])
            result.append({"Deleted": item["Id"]})
        self.after_remove(kind, identifier)
        return 200, result


class RemoveImagesTests(unittest.TestCase):
    def invoke(self, api, *args, config=None, trusted=False, env=None):
        self.assertTrue(
            (ROOT / "images/utils/bin/ci-remove-images").is_file(),
            "ci-utils does not yet provide its version removal command",
        )
        from ci_utils.remove_images import main

        policy = {
            "schema_version": 1,
            "endpoint": api.endpoint,
            "expected_daemon_id": "fixture-daemon",
            **(config or {}),
        }
        path = pathlib.Path(api.root.name) / "policy.json"
        path.write_text(json.dumps(policy))
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(output))
            stack.enter_context(contextlib.redirect_stderr(errors))
            stack.enter_context(
                mock.patch.dict(os.environ, env or {}, clear=True)
            )
            if trusted:
                # Authorization itself is covered by the real Linux host fixture.
                stack.enter_context(
                    mock.patch("ci_utils.remove_images.LeaseGuard.check")
                )
            code = main(["--config", str(path), *args])
        return code, [
            json.loads(line) for line in output.getvalue().splitlines()
        ]

    def test_default_dry_run_exact_suite_tags_and_historical_versions(self):
        selected = [
            PREFIX + name + ":0.0.1"
            for name in (
                "base",
                "go",
                "node",
                "vite",
                "playwright",
                "postgres",
                "utils",
                "net",
            )
        ] + [PREFIX + "go:v0.0.2"]
        excluded = [
            ALIAS,
            PREFIX + "go:0.0.10",
            PREFIX + "other:0.0.1",
            "example.test/ci-go:0.0.1",
            PREFIX + "go:latest",
        ]
        with VersionAPI(selected + excluded) as api:
            before = copy.deepcopy(api.objects)
            code, events = self.invoke(api, "--versions", "0.0.2, 0.0.1,0.0.2")
            self.assertEqual(code, 0, events)
            self.assertEqual(
                {e["id"] for e in events if e["event"] == "would-remove"},
                set(selected),
            )
            self.assertEqual(events[-1]["versions"], ["0.0.1", "0.0.2"])
            self.assertEqual(
                events[-1]["counts"]["images.matched"], len(selected)
            )
            self.assertEqual(api.objects, before)
            self.assertTrue(all(method == "GET" for method, _ in api.requests))

    def test_invalid_versions_and_environment_fail_before_daemon_access(self):
        for value in (
            None,
            "",
            "0.0.1,",
            ",0.0.1",
            "0.0.1,,0.0.2",
            "latest",
            "v0.0.1",
            "0.*",
            "0.0.1-0.0.3",
            "1.2",
            "1.2.3;true",
        ):
            with self.subTest(value=value), VersionAPI() as api:
                args = [] if value is None else ["--versions", value]
                code, _ = self.invoke(api, *args, "--apply")
                self.assertEqual(code, 2)
                self.assertEqual(api.requests, [])
        with VersionAPI() as api:
            code, _ = self.invoke(
                api,
                "--versions",
                "0.0.1",
                env={"DOCKER_HOST": "unix:///other.sock"},
            )
            self.assertEqual(code, 2)
            self.assertEqual(api.requests, [])

    def test_apply_removes_only_selected_references_and_repeat_is_noop(self):
        legacy = PREFIX + "node:v0.0.2"
        with VersionAPI([REF, legacy, ALIAS]) as api:
            code, events = self.invoke(
                api, "--versions", "0.0.1,0.0.2", "--apply", trusted=True
            )
            self.assertEqual(code, 0, events)
            self.assertEqual(api.objects["images"][IID]["RepoTags"], [ALIAS])
            self.assertEqual(events[-1]["counts"]["images.removed"], 2)
            mutations = [
                (method, path)
                for method, path in api.requests
                if method != "GET"
            ]
            self.assertEqual(len(mutations), 2)
            for method, path in mutations:
                self.assertEqual(method, "DELETE")
                self.assertTrue(path.endswith("?force=false&noprune=true"))
                self.assertNotIn("sha256", path)
            api.requests.clear()
            code, events = self.invoke(
                api, "--versions", "0.0.1,0.0.2", "--apply", trusted=True
            )
            self.assertEqual(code, 0, events)
            self.assertEqual(events[-1]["counts"]["versions.not-found"], 2)
            self.assertTrue(all(method == "GET" for method, _ in api.requests))

    def test_all_container_states_reserve_the_whole_image(self):
        for state in ("running", "exited", "created"):
            with self.subTest(state=state), VersionAPI() as api:
                obj = container()
                obj["State"]["Status"] = state
                api.objects["containers"][CID] = obj
                api.routes[("GET", "/v1.48/containers/" + CID + "/json")] = (
                    200,
                    obj,
                )
                code, events = self.invoke(
                    api, "--versions", "0.0.1", "--apply", trusted=True
                )
                self.assertEqual(code, 0, events)
                self.assertTrue(
                    any(e.get("reason") == "referenced" for e in events)
                )
                self.assertTrue(
                    all(method == "GET" for method, _ in api.requests)
                )

    def test_protection_through_any_alias_or_id_preserves_selected_tag(self):
        digest = "example.test/retained@sha256:" + "f" * 64
        for protection in (
            {"image_ids": [IID]},
            {"image_references": [ALIAS]},
            {"image_references": [digest]},
            {"image_repositories": ["example.test/retained"]},
            {},
        ):
            with self.subTest(protection=protection), VersionAPI() as api:
                item = api.objects["images"][IID]
                item["RepoDigests"] = [digest]
                api.add_reference(digest)
                if not protection:
                    item["Config"]["Labels"]["xyz.myflow.cleanup.protect"] = (
                        "true"
                    )
                code, events = self.invoke(
                    api,
                    "--versions",
                    "0.0.1",
                    "--apply",
                    trusted=True,
                    config={"protected": protection},
                )
                self.assertEqual(code, 0, events)
                self.assertTrue(
                    any(e.get("reason") == "protected" for e in events)
                )
                self.assertTrue(
                    all(method == "GET" for method, _ in api.requests)
                )

    def test_missing_guard_or_wrong_daemon_never_deletes(self):
        for config, expected in (
            ({}, 4),
            ({"expected_daemon_id": "wrong"}, 3),
            ({"expected_daemon_id": None}, 2),
        ):
            with self.subTest(config=config), VersionAPI() as api:
                code, _ = self.invoke(
                    api, "--versions", "0.0.1", "--apply", config=config
                )
                self.assertEqual(code, expected)
                self.assertTrue(
                    all(method == "GET" for method, _ in api.requests)
                )

    def test_retargeted_reference_is_skipped(self):
        with VersionAPI() as api:

            def retarget(kind, identifier):
                if identifier == REF:
                    api.objects["images"][IID]["Id"] = "sha256:" + "9" * 64

            api.before_inspect = retarget
            code, events = self.invoke(
                api, "--versions", "0.0.1", "--apply", trusted=True
            )
            self.assertEqual(code, 0, events)
            self.assertTrue(
                any(e.get("reason") == "reference-changed" for e in events)
            )
            self.assertTrue(all(method == "GET" for method, _ in api.requests))

    def test_new_container_reference_is_rechecked_before_deletion(self):
        with VersionAPI() as api:
            obj = container()
            api.routes[("GET", "/v1.48/containers/" + CID + "/json")] = (
                200,
                obj,
            )
            reads = 0

            def reservations():
                nonlocal reads
                reads += 1
                return 200, [] if reads == 1 else [{"Id": CID}]

            api.routes[("GET", "/v1.48/containers/json?all=true")] = (
                reservations
            )
            code, events = self.invoke(
                api, "--versions", "0.0.1", "--apply", trusted=True
            )
            self.assertEqual(code, 0, events)
            self.assertTrue(
                any(e.get("reason") == "referenced" for e in events)
            )
            self.assertTrue(all(method == "GET" for method, _ in api.requests))

    def test_new_protection_or_unreadable_alias_blocks_deletion(self):
        with VersionAPI() as api:

            def protect(kind, identifier):
                if identifier == REF:
                    api.objects["images"][IID]["Config"]["Labels"].update(
                        {"xyz.myflow.cleanup.protect": "true"}
                    )

            api.before_inspect = protect
            code, events = self.invoke(
                api, "--versions", "0.0.1", "--apply", trusted=True
            )
            self.assertEqual(code, 0, events)
            self.assertTrue(any(e.get("reason") == "protected" for e in events))
            self.assertTrue(all(method == "GET" for method, _ in api.requests))
        with VersionAPI() as api:
            path = (
                "/v1.48/images/" + urllib.parse.quote(ALIAS, safe="") + "/json"
            )
            api.routes[("GET", path)] = (500, {})
            code, _ = self.invoke(
                api,
                "--versions",
                "0.0.1",
                "--apply",
                trusted=True,
                config={"protected": {"image_references": [ALIAS]}},
            )
            self.assertEqual(code, 5)
            self.assertTrue(all(method == "GET" for method, _ in api.requests))

    def test_daemon_identity_change_stops_before_deletion(self):
        with VersionAPI() as api:
            original = api.routes[("GET", "/v1.48/info")][1]
            reads = 0

            def info():
                nonlocal reads
                reads += 1
                return 200, original if reads == 1 else {
                    **original,
                    "ID": "other",
                }

            api.routes[("GET", "/v1.48/info")] = info
            code, _ = self.invoke(
                api, "--versions", "0.0.1", "--apply", trusted=True
            )
            self.assertEqual(code, 3)
            self.assertTrue(all(method == "GET" for method, _ in api.requests))

    def test_api_errors_are_reported_without_retry(self):
        for response, expected in (
            (404, 0),
            (409, 0),
            (500, 5),
            (lambda: (200, b"malformed"), 6),
        ):
            with self.subTest(response=response), VersionAPI() as api:
                api.errors[("images", REF)] = response
                code, events = self.invoke(
                    api, "--versions", "0.0.1", "--apply", trusted=True
                )
                self.assertEqual(code, expected, events)
                self.assertEqual(
                    sum(method == "DELETE" for method, _ in api.requests), 1
                )
                self.assertEqual(events[-1]["completion_known"], expected != 6)


class HostRemoveImagesArgumentsTests(unittest.TestCase):
    def test_host_exposes_explicit_versions_and_defaults_to_dry_run(self):
        from ci_docker_maintenance import arguments

        args = arguments(["remove-images", "--versions", "0.0.1,0.0.2"])
        self.assertEqual(args.operation, "remove-images")
        self.assertFalse(args.apply)


if __name__ == "__main__":
    unittest.main()
