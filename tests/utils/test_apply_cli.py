"""T-06–13/18–21/25/26/32: CLI apply through a real host lease and API fixture."""

import datetime as dt
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
from test_storage import observation

DIGEST = "sha256:" + "a" * 64
DANGLING = "sha256:" + "4" * 64


class StatefulAPI(APIFixture):
    def __init__(self, objects=None):
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
        if objects is not None:
            self.objects = objects
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
    def invoke(
        self,
        api,
        config=None,
        profile="weekly",
        environ=None,
        revoke=False,
        storage=None,
    ):
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
                    extra = []
                    if storage is not None:
                        sample = {
                            **observation(),
                            "run_id": lease.id,
                            "sampled_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                            **storage,
                        }
                        storage_path = pathlib.Path(root) / "storage.json"
                        storage_path.write_text(json.dumps(sample))
                        storage_path.chmod(0o644)
                        extra = ["--observations", str(storage_path)]
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
                            *extra,
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

    def test_multitag_plan_apply_parity_without_reference_refresh(self):
        from test_cleanup_cli import CleanupCLITests

        reference_reads = []
        for count in (0, 25):
            objects = {"containers": {}, "networks": {}, "images": {}}
            for index in range(count):
                identifier = f"sha256:{index:064x}"
                objects["images"][identifier] = {
                    **image(),
                    "Id": identifier,
                    "RepoTags": [
                        f"ci.example/fixture:old-{index}",
                        f"ci.example/fixture:alias-{index}",
                    ],
                }
            with self.subTest(images=count), StatefulAPI(objects) as api:
                config = {"image_scope": {"repositories": ["ci.example/fixture"]}}
                planned, plan_events = CleanupCLITests().invoke(
                    api, "plan", "--profile", "weekly", config=config
                )
                self.assertEqual(planned.returncode, 0, planned.stderr)
                self.assertTrue(all(method == "GET" for method, _ in api.requests))
                api.requests.clear()
                code, apply_events, stderr = self.invoke(api, config=config)
                self.assertEqual(code, 0, stderr)
                reference_reads.append(
                    api.requests.count(("GET", "/v1.48/containers/json?all=true"))
                )
                self.assertFalse(any(method == "DELETE" for method, _ in api.requests))
                self.assertEqual(len(api.objects["images"]), count)
                for events in (plan_events, apply_events):
                    decisions = [
                        e
                        for e in events
                        if e["event"] == "decision" and e["kind"] == "images"
                    ]
                    self.assertEqual(len(decisions), count)
                    self.assertEqual(
                        {(e["outcome"], e["reason"]) for e in decisions},
                        {("excluded", "multi-tag-image-unsupported")}
                        if count
                        else set(),
                    )
        self.assertEqual(reference_reads[0], reference_reads[1])

    def test_excluded_inventory_reads_scale_linearly(self):
        containers, images = 20, 100
        # Allow complete stage snapshots, not a container scan for every image.
        read_limit = 6 * (containers + images + 10)
        for profile, scope in (
            ("daily", {"mode": "daemon-wide", "daemon_wide_approved": True}),
            ("weekly", {"mode": "allowlist"}),
        ):
            objects = {"containers": {}, "networks": {}, "images": {}}
            for index in range(containers):
                identifier = f"{index:064x}"
                objects["containers"][identifier] = {
                    **container(),
                    "Id": identifier,
                    "Config": {"Labels": {}},
                    "NetworkSettings": {"Networks": {}},
                    "HostConfig": {"NetworkMode": "none"},
                }
            for index in range(images):
                identifier = f"sha256:{index:064x}"
                objects["images"][identifier] = {**image(), "Id": identifier}
            with self.subTest(profile=profile), StatefulAPI(objects) as api:
                inspect = api.inspect

                def bounded_inspect(kind, identifier):
                    if len(api.requests) > read_limit:
                        return 500, {"message": "test inventory read budget exceeded"}
                    return inspect(kind, identifier)

                api.inspect = bounded_inspect
                code, events, stderr = self.invoke(
                    api, profile=profile, config={"image_scope": scope}
                )
                reads = sum(method == "GET" for method, _ in api.requests)
                self.assertLessEqual(reads, read_limit)
                self.assertEqual(code, 0, stderr)
                self.assertTrue(events[-1]["completion_known"])
                self.assertFalse(any(method == "DELETE" for method, _ in api.requests))
                self.assertEqual(len(objects["images"]), images)
                self.assertEqual(len(objects["containers"]), containers)

    def test_pressure_trigger_needs_fresh_host_evidence_and_keeps_protection(self):
        for sample, removed in [
            (None, False),
            ({}, True),
            ({"sampled_at": "2000-01-01T00:00:00Z"}, False),
            ({"daemon_id": "other"}, False),
            ({"source": "container-root"}, False),
        ]:
            with self.subTest(sample=sample), StatefulAPI() as api:
                code, _, stderr = self.invoke(
                    api, config={"tagged_image_trigger": "pressure"}, storage=sample
                )
                self.assertEqual(code, 0, stderr)
                self.assertEqual(IID not in api.objects["images"], removed)
        with StatefulAPI() as api:
            code, _, stderr = self.invoke(
                api,
                config={
                    "tagged_image_trigger": "pressure",
                    "protected": {"image_ids": [IID]},
                },
                storage={},
            )
            self.assertEqual(code, 0, stderr)
            self.assertIn(IID, api.objects["images"])

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

    def test_scheduled_cache_uses_engine_accounting_before_and_after_prune(self):
        with StatefulAPI() as api, CacheTools() as tools:
            tools.state["records"] = [
                {**tools.state["records"][0], "ID": f"record-{i}"} for i in range(105)
            ]
            tools.save()
            api.routes.update(tools.routes())
            code, events, stderr = self.invoke(
                api,
                config={"cache": {"mode": "scheduled"}},
                environ={"PATH": str(tools.path)},
            )
            self.assertEqual(code, 0, stderr)
            self.assertTrue(any(method == "DELETE" for method, _ in api.requests))
            self.assertGreaterEqual(
                api.requests.count(("GET", "/v1.48/system/df?type=build-cache")), 2
            )
            budget = next(e for e in events if e["event"] == "cache_budget")
            self.assertEqual(budget["remaining_bytes"], 0)
            self.assertEqual(budget["status"], "achieved")
            self.assertFalse(any("du" in call for call in tools.calls()))
            self.assertEqual(len(tools.prunes), 1)
            age = next(e for e in events if e["event"] == "cache_stage")
            self.assertEqual(age["submitted_candidates"], 105)
            self.assertIn(("POST", "/v1.48/build/prune"), api.requests)

    def test_uncertain_cache_completion_stops_later_cleanup(self):
        for response in ((200, b"bad-json"), (500, {})):
            with (
                self.subTest(response=response),
                StatefulAPI() as api,
                CacheTools() as tools,
            ):
                api.routes.update(tools.routes())
                api.routes[("POST", "/v1.48/build/prune")] = response
                code, events, stderr = self.invoke(
                    api,
                    config={"cache": {"mode": "scheduled"}},
                    environ={"PATH": str(tools.path)},
                )
                self.assertEqual(code, 6, stderr)
                self.assertFalse(events[-1]["completion_known"])
                request = ("POST", "/v1.48/build/prune")
                self.assertEqual(api.requests.count(request), 1)
                self.assertFalse(
                    any(
                        method in ("POST", "DELETE")
                        for method, _ in api.requests[api.requests.index(request) + 1 :]
                    )
                )

    def test_shared_cache_does_not_trigger_budget_pruning(self):
        with StatefulAPI() as api, CacheTools() as tools:
            tools.state["records"][0].update(
                Shared=True,
                Size=4096,
                LastUsedAt=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
            tools.state["after_budget"] = tools.state["records"]
            tools.save()
            api.routes.update(tools.routes())
            code, events, stderr = self.invoke(
                api,
                config={"cache": {"mode": "scheduled", "max_used_space": "1kb"}},
                environ={"PATH": str(tools.path)},
            )
            self.assertEqual(code, 0, stderr)
            budget = next(e for e in events if e["event"] == "cache_budget")
            self.assertTrue(budget["target_met"])
            self.assertEqual(budget["remaining_bytes"], 0)
            self.assertEqual(tools.prunes, [])
            self.assertIn(("GET", "/v1.48/system/df?type=build-cache"), api.requests)

    def test_missing_cache_accounting_prevents_every_resource_deletion(self):
        with StatefulAPI() as api, CacheTools() as tools:
            api.routes[("GET", "/v1.48/system/df?type=build-cache")] = (200, {})
            code, _, stderr = self.invoke(
                api,
                config={"cache": {"mode": "scheduled"}},
                environ={"PATH": str(tools.path)},
            )
            self.assertEqual(code, 2, stderr)
            self.assertFalse(any(method == "DELETE" for method, _ in api.requests))
            self.assertEqual(tools.prunes, [])

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
