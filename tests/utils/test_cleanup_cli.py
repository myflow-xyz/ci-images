"""T-01/02/03/11/23/26/32: CLI to Unix API end-to-end contracts."""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

from api_fixture import APIFixture, daemon_routes
from cache_fixture import CacheTools
from test_policy import CID, IID, NID, container, image, network

ROOT = pathlib.Path(__file__).resolve().parents[2]


def routes():
    obj = container()
    obj["NetworkSettings"] = {"Networks": {"fixture": {"NetworkID": NID}}}
    net = network()
    net["Containers"] = {CID: {}}
    return daemon_routes() | {
        ("GET", "/v1.48/containers/json?all=true"): (200, [{"Id": CID}]),
        ("GET", "/v1.48/containers/" + CID + "/json"): (200, obj),
        ("GET", "/v1.48/networks"): (200, [{"Id": NID}]),
        ("GET", "/v1.48/networks/" + NID): (200, net),
        ("GET", "/v1.48/images/json?all=true"): (200, [{"Id": IID}]),
        ("GET", "/v1.48/images/sha256%3A" + "3" * 64 + "/json"): (200, image()),
        ("GET", "/v1.48/system/df"): (200, {"LayersSize": 123, "Volumes": []}),
    }


class CleanupCLITests(unittest.TestCase):
    def invoke(self, api, *args, config=None, env=None):
        policy = {
            "schema_version": 1,
            "endpoint": api.endpoint,
            "cache": {"mode": "off"},
            "tagged_image_trigger": "scheduled",
            "image_scope": {"mode": "daemon-wide", "daemon_wide_approved": True},
        }
        policy.update(config or {})
        with tempfile.TemporaryDirectory(prefix="ci-utils-cli-", dir="/tmp") as root:
            path = pathlib.Path(root) / "policy.json"
            path.write_text(json.dumps(policy))
            environment = {
                key: os.environ[key]
                for key in ("PATH", "HOME", "TMPDIR")
                if key in os.environ
            }
            environment["PYTHONPATH"] = str(ROOT / "images/utils")
            environment.update(env or {})
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(ROOT / "images/utils/bin/ci-docker-cleanup"),
                    *args,
                    "--config",
                    str(path),
                ],
                env=environment,
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
            return result, [json.loads(line) for line in result.stdout.splitlines()]

    def test_default_plan_has_dependent_candidates_and_no_mutations(self):
        with APIFixture(routes()) as api:
            result, events = self.invoke(api, "--profile", "weekly")
            self.assertEqual(result.returncode, 0, result.stderr)
            decisions = {
                event["kind"]: event for event in events if event["event"] == "decision"
            }
            self.assertEqual(decisions["containers"]["outcome"], "candidate")
            self.assertEqual(decisions["networks"]["outcome"], "dependent-candidate")
            self.assertEqual(decisions["images"]["outcome"], "dependent-candidate")
            self.assertEqual(events[-1]["status"], "success")
            self.assertEqual(events[-1]["mode"], "plan")
            self.assertTrue(all(method == "GET" for method, path in api.requests))

    def test_check_validates_without_selecting_or_deleting(self):
        with APIFixture(routes()) as api:
            result, events = self.invoke(api, "check")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(any(event["event"] == "decision" for event in events))
            self.assertTrue(all(method == "GET" for method, path in api.requests))

    def test_created_container_reservations_preserve_networks_without_endpoints(self):
        for networks, mode in [
            ({"fixture": {"NetworkID": ""}}, "fixture"),
            ({NID: {"NetworkID": ""}}, NID),
            ({}, "fixture"),
            ({}, NID[:12]),
        ]:
            with self.subTest(networks=networks, mode=mode):
                data = routes()
                obj = data[("GET", "/v1.48/containers/" + CID + "/json")][1]
                obj["State"]["Status"] = "created"
                obj["Config"]["Labels"] = {}
                obj["HostConfig"] = {"NetworkMode": mode}
                obj["NetworkSettings"] = {"Networks": networks}
                data[("GET", "/v1.48/networks/" + NID)][1]["Containers"] = {}
                with APIFixture(data) as api:
                    result, events = self.invoke(api)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    decision = next(
                        e
                        for e in events
                        if e["event"] == "decision" and e["kind"] == "networks"
                    )
                    self.assertEqual(decision["outcome"], "excluded")
                    self.assertEqual(decision["reason"], "referenced")
                    self.assertTrue(all(method == "GET" for method, _ in api.requests))

    def test_invalid_config_and_conflicting_environment_precede_daemon_access(self):
        for config, env in [
            ({"unknown": True}, {}),
            ({}, {"DOCKER_CONTEXT": "other"}),
            ({}, {"DOCKER_HOST": "unix:///wrong.sock"}),
        ]:
            with APIFixture(routes()) as api:
                result, events = self.invoke(api, config=config, env=env)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(events[-1]["exit_code"], 2)
                self.assertEqual(api.requests, [])

    def test_apply_cannot_bypass_identity_or_host_integration(self):
        for daemon, code in [(None, 2), ("fixture-daemon", 4)]:
            with APIFixture(routes()) as api:
                result, events = self.invoke(
                    api, "apply", config={"expected_daemon_id": daemon}
                )
                self.assertEqual(result.returncode, code)
                self.assertEqual(events[-1]["exit_code"], code)
                self.assertFalse(
                    any(method == "DELETE" for method, path in api.requests)
                )

    def test_wrong_daemon_is_a_preflight_failure(self):
        with APIFixture(routes()) as api:
            result, events = self.invoke(
                api, "check", config={"expected_daemon_id": "wrong"}
            )
            self.assertEqual(result.returncode, 3)
            self.assertEqual(events[-1]["exit_code"], 3)

    def test_protected_alias_is_resolved_locally_without_pull(self):
        data = routes()
        data[("GET", "/v1.48/containers/json?all=true")] = (200, [])
        data[("GET", "/v1.48/images/ci.example%2Frollback%3Akeep/json")] = (
            200,
            image(),
        )
        with APIFixture(data) as api:
            result, events = self.invoke(
                api,
                "plan",
                "--profile",
                "weekly",
                config={
                    "protected": {"image_references": ["ci.example/rollback:keep"]}
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            decision = next(
                e for e in events if e["event"] == "decision" and e["kind"] == "images"
            )
            self.assertEqual(decision["reason"], "protected")
            self.assertTrue(all(method == "GET" for method, path in api.requests))

    def test_unreadable_protection_prevents_any_deletion(self):
        data = routes() | {
            ("GET", "/v1.48/images/ci.example%2Fkeep%3Atag/json"): (500, {})
        }
        with APIFixture(data) as api:
            result, events = self.invoke(
                api,
                "plan",
                config={"protected": {"image_references": ["ci.example/keep:tag"]}},
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(events[-1]["exit_code"], 5)
            self.assertFalse(any(method == "DELETE" for method, path in api.requests))

    def test_unavailable_accounting_is_unknown_and_not_zero(self):
        data = routes() | {("GET", "/v1.48/system/df"): (500, {})}
        with APIFixture(data) as api:
            result, events = self.invoke(api)
            self.assertEqual(result.returncode, 0, result.stderr)
            accounting = next(e for e in events if e["event"] == "observations")
            self.assertIsNone(accounting["docker"])
            self.assertIsNone(accounting["filesystems"])

    def test_cache_capability_failure_precedes_all_resource_mutations(self):
        with CacheTools() as tools, APIFixture(routes() | tools.routes()) as api:
            tools.state["capabilities"]["gc_space_filters"] = False
            tools.save()
            result, events = self.invoke(
                api,
                config={"cache": {"mode": "scheduled"}},
                env={"PATH": str(tools.path)},
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(events[-1]["exit_code"], 2)
            self.assertFalse(any(method == "DELETE" for method, path in api.requests))
            self.assertFalse(
                any("prune" in call and "--help" not in call for call in tools.calls())
            )

    def test_cache_plan_reports_budget_limitations_without_pruning(self):
        with CacheTools() as tools, APIFixture(routes() | tools.routes()) as api:
            result, events = self.invoke(
                api,
                config={"cache": {"mode": "scheduled"}},
                env={"PATH": str(tools.path)},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            planned = next(event for event in events if event["event"] == "cache_plan")
            self.assertTrue(planned["budget_may_remove_recent_records"])
            self.assertEqual(planned["age_candidates"], 1)
            self.assertIn(("GET", "/v1.48/system/df?type=build-cache"), api.requests)
            self.assertFalse(planned["exact_native_candidates"])
            self.assertIsNone(planned["exact_reclaimed_bytes"])
            self.assertFalse(
                any("prune" in call and "--help" not in call for call in tools.calls())
            )


if __name__ == "__main__":
    unittest.main()
