"""T-06–13/18–21/25/26/32: CLI apply through a real host lease and API fixture."""

import hashlib
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "images/utils")]

from api_fixture import APIFixture, daemon_routes
from cache_fixture import CacheTools
from ci_docker_gate import Gate, LeaseServer
from ci_utils.policy import configuration
from test_policy import CID, IID, NID, container, image, network

DIGEST = "sha256:" + "a" * 64
DANGLING = "sha256:" + "4" * 64


class StatefulAPI(APIFixture):
    def __init__(self):
        obj = container()
        obj["NetworkSettings"] = {"Networks": {"fixture": {"NetworkID": NID}}}
        self.objects = {
            "containers": {CID: obj},
            "networks": {NID: network()},
            "images": {
                IID: image(),
                DANGLING: {**image(), "Id": DANGLING, "RepoTags": []},
            },
        }
        self.errors = {}
        self.before_inspect = lambda kind, identifier: None
        self.after_remove = lambda kind, identifier: None
        routes = daemon_routes()
        for kind, listing in (
            ("containers", "/containers/json?all=true"),
            ("networks", "/networks"),
            ("images", "/images/json?all=true"),
        ):
            routes[("GET", "/v1.48" + listing)] = lambda kind=kind: (
                200,
                [{"Id": key} for key in self.objects[kind]],
            )
            for identifier in self.objects[kind]:
                path = "/v1.48/" + kind + "/" + urllib.parse.quote(identifier, safe="")
                routes[("GET", path + ("" if kind == "networks" else "/json"))] = (
                    lambda kind=kind, identifier=identifier: self.inspect(
                        kind, identifier
                    )
                )
                query = {
                    "containers": "?force=false&v=false",
                    "images": "?force=false&noprune=true",
                    "networks": "",
                }[kind]
                routes[("DELETE", path + query)] = (
                    lambda kind=kind, identifier=identifier: self.remove(
                        kind, identifier
                    )
                )
        routes[("GET", "/v1.48/system/df")] = (
            200,
            {"LayersSize": 123, "Volumes": [{}]},
        )
        super().__init__(routes)

    def inspect(self, kind, identifier):
        self.before_inspect(kind, identifier)
        value = self.objects[kind].get(identifier)
        return (200, value) if value else (404, {})

    def remove(self, kind, identifier):
        error = self.errors.get((kind, identifier))
        if error:
            return error() if callable(error) else (error, {})
        self.objects[kind].pop(identifier, None)
        self.after_remove(kind, identifier)
        return (200, [{"Deleted": identifier}]) if kind == "images" else (204, b"")


@unittest.skipUnless(
    hasattr(socket, "SO_PEERCRED") and os.geteuid() == 0,
    "apply protocol E2E requires an isolated Linux root controller",
)
class ApplyCLITests(unittest.TestCase):
    def invoke(self, api, config=None, profile="weekly", environ=None, revoke=False):
        policy = configuration(
            {
                "schema_version": 1,
                "endpoint": api.endpoint,
                "expected_daemon_id": "fixture-daemon",
                "cache": {"mode": "off"},
                "tagged_image_trigger": "scheduled",
                "image_scope": {"mode": "daemon-wide", "daemon_wide_approved": True},
                **(config or {}),
            }
        )
        policy_hash = hashlib.sha256(
            json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with tempfile.TemporaryDirectory(prefix="cu-apply-", dir="/tmp") as root:
            gate = Gate(pathlib.Path(root) / "gate")
            gate.initialize()
            path = pathlib.Path(root) / "policy.json"
            path.write_text(json.dumps(policy))
            with gate.maintenance("fixture-daemon", policy_hash) as lease:
                with LeaseServer(gate, lease, profile, DIGEST) as server:
                    if revoke:
                        api.after_remove = lambda *args: lease.complete()
                    process = subprocess.Popen(
                        [
                            sys.executable,
                            "-B",
                            str(ROOT / "images/utils/bin/ci-docker-cleanup"),
                            "apply",
                            "--profile",
                            profile,
                            "--config",
                            str(path),
                            "--run-id",
                            lease.id,
                            "--lease-socket",
                            str(server.path),
                        ],
                        env={
                            "PATH": os.environ["PATH"],
                            "TMPDIR": "/tmp",
                            "CI_UTILS_IMAGE_DIGEST": DIGEST,
                            **(environ or {}),
                        },
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    server.bind_client(process.pid)
                    stdout, stderr = process.communicate(timeout=15)
                # The fixture has no asynchronous backend operations to reconcile.
                lease.complete()
            return (
                process.returncode,
                [json.loads(line) for line in stdout.splitlines()],
                stderr,
            )

    def test_ordered_cleanup_and_repeated_apply_preserve_volumes(self):
        with StatefulAPI() as api:
            code, events, stderr = self.invoke(api)
            self.assertEqual(code, 0, stderr)
            self.assertEqual(
                [e["stage"] for e in events if e["event"] == "stage"],
                ["containers", "networks", "dangling-images", "cache", "tagged-images"],
            )
            removals = [path for method, path in api.requests if method == "DELETE"]
            self.assertEqual(len(removals), 4)
            self.assertIn("containers/", removals[0])
            self.assertIn("networks/", removals[1])
            self.assertIn(urllib.parse.quote(DANGLING, safe=""), removals[2])
            self.assertIn(urllib.parse.quote(IID, safe=""), removals[3])
            self.assertFalse(any("/volumes" in path for _, path in api.requests))
            self.assertTrue(events[-1]["completion_known"])
            api.requests.clear()
            code, _, stderr = self.invoke(api)
            self.assertEqual(code, 0, stderr)
            self.assertFalse(any(method == "DELETE" for method, _ in api.requests))

    def test_daily_profile_preserves_tagged_images(self):
        with StatefulAPI() as api:
            code, _, stderr = self.invoke(api, profile="daily")
            self.assertEqual(code, 0, stderr)
            self.assertIn(IID, api.objects["images"])
            self.assertNotIn(DANGLING, api.objects["images"])

    def test_unknown_alias_metadata_and_multiple_tags_are_preserved(self):
        for tags in (42, ["ci.example/fixture:old", "ci.example/fixture:second"]):
            with self.subTest(tags=tags), StatefulAPI() as api:
                api.objects["images"][IID]["RepoTags"] = tags
                code, _, stderr = self.invoke(api)
                self.assertEqual(code, 0, stderr)
                self.assertIn(IID, api.objects["images"])

    def test_new_protected_alias_between_stage_inventory_and_remove_is_preserved(self):
        with StatefulAPI() as api:
            inspections = 0

            def change(kind, identifier):
                nonlocal inspections
                if kind == "images" and identifier == IID:
                    inspections += 1
                    if inspections == 6:
                        api.objects[kind][identifier]["RepoTags"].append(
                            "ci.example/keep:rollback"
                        )

            api.before_inspect = change
            code, _, stderr = self.invoke(
                api, config={"protected": {"image_repositories": ["ci.example/keep"]}}
            )
            self.assertEqual(code, 0, stderr)
            self.assertEqual(inspections, 6)
            self.assertIn(IID, api.objects["images"])

    def test_reinspection_preserves_changed_state_and_protected_alias(self):
        with StatefulAPI() as api:
            inspections = 0

            def change(kind, identifier):
                nonlocal inspections
                if kind == "containers":
                    inspections += 1
                    if inspections >= 3:
                        api.objects[kind][identifier]["State"]["Status"] = "running"
                if kind == "images" and identifier == DANGLING:
                    api.objects[kind][identifier]["RepoTags"] = [
                        "ci.example/keep:rollback"
                    ]

            api.before_inspect = change
            code, events, stderr = self.invoke(
                api, config={"protected": {"image_repositories": ["ci.example/keep"]}}
            )
            self.assertEqual(code, 0, stderr)
            self.assertEqual([e for e in events if e["event"] == "removed"], [])
            self.assertFalse(any(method == "DELETE" for method, _ in api.requests))

    def test_conflict_and_disappearance_are_skips(self):
        for status in (404, 409):
            with self.subTest(status=status), StatefulAPI() as api:
                api.errors[("containers", CID)] = status
                code, events, stderr = self.invoke(api)
                self.assertEqual(code, 0, stderr)
                self.assertTrue(
                    any(
                        e["event"] == "skip" and e.get("http_status") == status
                        for e in events
                    )
                )
                self.assertIn(NID, api.objects["networks"])
                self.assertIn(IID, api.objects["images"])

    def test_unexpected_error_stops_later_destructive_stages(self):
        with StatefulAPI() as api:
            api.errors[("containers", CID)] = 500
            code, events, stderr = self.invoke(api)
            self.assertEqual(code, 5, stderr)
            self.assertEqual(len([r for r in api.requests if r[0] == "DELETE"]), 1)
            self.assertEqual(events[-1]["status"], "partial-failure")

    def test_timeout_is_not_retried_and_requires_reconciliation(self):
        with StatefulAPI() as api:

            def slow():
                time.sleep(1.2)
                return 204, b""

            api.errors[("containers", CID)] = slow
            code, events, stderr = self.invoke(
                api, config={"timeouts": {"operation": "1s", "run": "10s"}}
            )
            self.assertEqual(code, 6, stderr)
            self.assertFalse(events[-1]["completion_known"])
            self.assertEqual(len([r for r in api.requests if r[0] == "DELETE"]), 1)

    def test_lease_loss_stops_after_the_first_mutation(self):
        with StatefulAPI() as api:
            code, events, stderr = self.invoke(api, revoke=True)
            self.assertEqual(code, 6, stderr)
            self.assertFalse(events[-1]["completion_known"])
            self.assertEqual(len([r for r in api.requests if r[0] == "DELETE"]), 1)

    def test_cache_preflight_failure_prevents_every_resource_deletion(self):
        with StatefulAPI() as api, CacheTools() as tools:
            tools.state["capabilities"]["gc_space_filters"] = False
            tools.save()
            code, _, stderr = self.invoke(
                api,
                config={"cache": {"mode": "scheduled"}},
                environ={"PATH": str(tools.path)},
            )
            self.assertEqual(code, 2, stderr)
            self.assertFalse(any(method == "DELETE" for method, _ in api.requests))
            self.assertTrue(
                any(call[0] == "ci-buildkit-probe" for call in tools.calls())
            )


if __name__ == "__main__":
    unittest.main()
