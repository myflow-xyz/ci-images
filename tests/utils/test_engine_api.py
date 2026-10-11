"""T-03, T-20, T-21, T-23, T-25: public Engine API boundary regressions."""

import pathlib
import json
import re
import sys
import time
import unittest
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "images/utils"))

from api_fixture import APIFixture, daemon_routes
from ci_utils.engine import APIError, Engine, Failure


class EngineAPITests(unittest.TestCase):
    def test_cache_prune_uses_one_body_for_a_large_exact_selection(self):
        identifiers = [f"record-{i}-" + "x" * 150 for i in range(1000)]
        routes = daemon_routes() | {
            ("POST", "/v1.48/build/prune"): (
                200,
                {"SpaceReclaimed": 0, "CachesDeleted": None},
            )
        }
        with APIFixture(routes) as api:
            engine = Engine(api.endpoint)
            engine.preflight()
            guarded = []
            engine.prune_cache(
                identifiers,
                lambda: guarded.append(len(api.posts)),
                include_internal=True,
                max_used_space=1024,
            )
            self.assertEqual(guarded, [0])
            self.assertEqual(len(api.posts), 1)
            post = api.posts[0]
            self.assertEqual(post["path"], "/v1.48/build/prune")
            self.assertEqual(post["content_type"], "application/x-www-form-urlencoded")
            self.assertGreater(len(post["body"]), 128 * 1024)
            fields = urllib.parse.parse_qs(post["body"].decode())
            self.assertEqual(fields["max-used-space"], ["1024"])
            self.assertEqual(fields["all"], ["true"])
            filters = json.loads(fields["filters"][0])
            self.assertEqual(set(filters), {"id"})
            self.assertEqual(len(filters["id"]), 1)
            pattern = re.compile(filters["id"][0])
            self.assertTrue(all(pattern.fullmatch(key) for key in identifiers))
            self.assertIsNone(pattern.search("prefix-" + identifiers[0]))
            self.assertIsNone(pattern.search(identifiers[0] + "-suffix"))

    def test_cache_prune_rejects_unbounded_or_unguarded_mutations(self):
        def denied():
            raise Failure(4, "no guard")

        for identifiers, verified, guard, code in (
            ([], True, lambda: None, 2),
            (["unsafe.*"], True, lambda: None, 2),
            ([str(i) + "x" * 250 for i in range(5000)], True, lambda: None, 2),
            (["record"], False, lambda: None, 3),
            (["record"], True, denied, 4),
        ):
            with (
                self.subTest(code=code, count=len(identifiers)),
                APIFixture(daemon_routes()) as api,
            ):
                engine = Engine(api.endpoint)
                if verified:
                    engine.preflight()
                with self.assertRaises(Failure) as raised:
                    engine.prune_cache(
                        identifiers, guard, include_internal=False, unused=3600
                    )
                self.assertEqual(raised.exception.code, code)
                self.assertEqual(api.posts, [])
                self.assertFalse(engine.mutation_started)

    def test_cache_prune_uncertain_completion_is_not_retried(self):
        def slow(form):
            time.sleep(0.15)
            return 200, {"SpaceReclaimed": 0, "CachesDeleted": None}

        for response in (
            (200, b"bad-json"),
            (200, {}),
            (200, {"SpaceReclaimed": 0, "CachesDeleted": "invalid"}),
            (500, {"message": "backend failed after partial pruning"}),
            slow,
        ):
            with (
                self.subTest(response=response),
                APIFixture(
                    daemon_routes() | {("POST", "/v1.48/build/prune"): response}
                ) as api,
            ):
                engine = Engine(api.endpoint, operation_timeout=0.05)
                engine.preflight()
                with self.assertRaises(Failure) as raised:
                    engine.prune_cache(
                        ["record"], lambda: None, include_internal=False, unused=3600
                    )
                self.assertEqual(raised.exception.code, 6)
                self.assertEqual(len(api.posts), 1)
                self.assertTrue(engine.mutation_started)

    def test_daemon_identity_is_bounded_valid_data(self):
        for identifier in (
            None,
            "",
            "has whitespace",
            "x" * 257,
            "name\nlog-injection",
        ):
            routes = daemon_routes()
            routes[("GET", "/v1.48/info")][1]["ID"] = identifier
            with APIFixture(routes) as api:
                with self.assertRaises(Failure) as raised:
                    Engine(api.endpoint).preflight()
                self.assertEqual(raised.exception.code, 3)

    def test_preflight_validates_local_daemon_without_mutation(self):
        with APIFixture(daemon_routes()) as api:
            info = Engine(api.endpoint).preflight("fixture-daemon")
            self.assertEqual(info["ID"], "fixture-daemon")
            self.assertTrue(all(method == "GET" for method, path in api.requests))

    def test_mismatch_and_unsupported_daemons_are_rejected(self):
        for change, expected in [
            (None, 3),
            ({"OSType": "windows"}, 2),
            ({"SecurityOptions": ["name=rootless"]}, 2),
        ]:
            routes = daemon_routes()
            if change:
                routes[("GET", "/v1.48/info")][1].update(change)
            with APIFixture(routes) as api:
                with self.assertRaises(Failure) as raised:
                    Engine(api.endpoint).preflight(
                        "wrong" if change is None else "fixture-daemon"
                    )
                self.assertEqual(raised.exception.code, expected)
                self.assertTrue(all(method == "GET" for method, path in api.requests))

    def test_removed_container_never_requests_force_or_volume_deletion(self):
        path = "/v1.48/containers/" + "1" * 64 + "?force=false&v=false"
        routes = daemon_routes() | {("DELETE", path): (204, b"")}
        with APIFixture(routes) as api:
            engine = Engine(api.endpoint)
            engine.preflight("fixture-daemon")
            guarded = []
            engine.remove("containers", "1" * 64, lambda: guarded.append("checked"))
            self.assertEqual(guarded, ["checked"])
            self.assertEqual(api.requests[-1], ("DELETE", path))

    def test_failed_guard_prevents_api_mutation(self):
        def unavailable():
            raise Failure(4, "no guard")

        with APIFixture(daemon_routes()) as api:
            engine = Engine(api.endpoint)
            engine.preflight("fixture-daemon")
            with self.assertRaises(Failure):
                engine.remove("containers", "1" * 64, unavailable)
            self.assertFalse(any(method == "DELETE" for method, path in api.requests))

    def test_volume_removal_is_not_an_available_operation(self):
        with APIFixture(daemon_routes()) as api:
            with self.assertRaises(Failure):
                Engine(api.endpoint).remove("volumes", "fixture", lambda: None)
            self.assertEqual(api.requests, [])

    def test_conflicts_and_disappearance_keep_typed_http_status(self):
        for status in [404, 409, 500]:
            path = "/v1.48/containers/" + "1" * 64 + "?force=false&v=false"
            routes = daemon_routes() | {
                ("DELETE", path): (status, {"message": "secret-sentinel\nmalicious"})
            }
            with APIFixture(routes) as api:
                engine = Engine(api.endpoint)
                engine.preflight()
                with self.assertRaises(APIError) as raised:
                    engine.remove("containers", "1" * 64, lambda: None)
                self.assertEqual(raised.exception.status, status)
                self.assertNotIn("secret-sentinel", str(raised.exception))

    def test_mutation_timeout_is_ambiguous_and_not_retried(self):
        def slow():
            time.sleep(0.15)
            return 204, b""

        path = "/v1.48/containers/" + "1" * 64 + "?force=false&v=false"
        with APIFixture(daemon_routes() | {("DELETE", path): slow}) as api:
            engine = Engine(api.endpoint, operation_timeout=0.05)
            engine.preflight()
            with self.assertRaises(Failure) as raised:
                engine.remove("containers", "1" * 64, lambda: None)
            self.assertEqual(raised.exception.code, 6)
            self.assertEqual(
                sum(method == "DELETE" for method, path in api.requests), 1
            )

    def test_bad_json_and_api_version_fail_before_cleanup(self):
        for payload in [
            b"{invalid",
            {"ApiVersion": "1.20", "MinAPIVersion": "1.10", "Version": "19.0"},
        ]:
            routes = daemon_routes() | {("GET", "/version"): (200, payload)}
            with APIFixture(routes) as api:
                with self.assertRaises(Failure):
                    Engine(api.endpoint).preflight()
                self.assertFalse(
                    any(method == "DELETE" for method, path in api.requests)
                )

    def test_slow_stream_cannot_extend_the_operation_deadline(self):
        routes = daemon_routes() | {
            ("GET", "/v1.48/slow"): (200, b'{"value":"slow response"}', 0.02)
        }
        with APIFixture(routes) as api:
            engine = Engine(api.endpoint, operation_timeout=0.08)
            engine.preflight()
            started = time.monotonic()
            with self.assertRaises(Failure) as raised:
                engine.get("/slow")
            self.assertEqual(raised.exception.code, 3)
            self.assertLess(time.monotonic() - started, 0.3)

    def test_malformed_mutation_response_requires_reconciliation(self):
        path = "/v1.48/images/sha256%3A" + "1" * 64 + "?force=false&noprune=true"
        with APIFixture(
            daemon_routes() | {("DELETE", path): (200, b"bad-json")}
        ) as api:
            engine = Engine(api.endpoint)
            engine.preflight()
            with self.assertRaises(Failure) as raised:
                engine.remove("images", "sha256:" + "1" * 64, lambda: None)
            self.assertEqual(raised.exception.code, 6)
            self.assertEqual(api.requests[-1], ("DELETE", path))


if __name__ == "__main__":
    unittest.main()
