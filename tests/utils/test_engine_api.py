"""T-03, T-20, T-21, T-23, T-25: public Engine API boundary regressions."""

import pathlib
import sys
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "images/utils"))

from api_fixture import APIFixture, daemon_routes
from ci_utils.engine import APIError, Engine, Failure


class EngineAPITests(unittest.TestCase):
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
