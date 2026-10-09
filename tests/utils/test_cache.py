"""T-14–17: cache preflight, ownership, modes, and truthful accounting."""

import datetime as dt
import os
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "images/utils"))

from api_fixture import APIFixture, daemon_routes
from cache_fixture import CacheTools
from ci_utils.cache import BuildCache
from ci_utils.engine import Engine, Failure
from test_policy import configured


class Events:
    def __init__(self):
        self.items = []

    def emit(self, event, **data):
        self.items.append({"event": event, **data})


class CacheTests(unittest.TestCase):
    def test_unknown_post_prune_state_stops_budget_and_reports_unknown(self):
        with (
            CacheTools() as tools,
            APIFixture(daemon_routes() | tools.routes()) as api,
            patch.dict(os.environ, {"PATH": str(tools.path)}),
        ):
            tools.state["after_age"] = [{**tools.state["records"][0], "Size": None}]
            tools.save()
            engine = Engine(api.endpoint)
            engine.preflight()
            events = Events()
            with BuildCache(engine, configured(), "fixture-daemon", events) as cache:
                cache.preflight()
                with self.assertRaises(Failure) as raised:
                    cache.prune(dt.datetime.now(dt.timezone.utc), lambda: None)
                self.assertEqual(raised.exception.code, 5)
            calls = [
                call
                for call in tools.calls()
                if "prune" in call and "--help" not in call
            ]
            self.assertEqual(len(calls), 1)
            outcome = next(
                event for event in events.items if event["event"] == "cache_budget"
            )
            self.assertEqual(outcome["status"], "unknown")
            self.assertIsNone(outcome["remaining_bytes"])

    def test_age_cleanup_can_achieve_target_without_budget_deletion(self):
        with (
            CacheTools() as tools,
            APIFixture(daemon_routes() | tools.routes()) as api,
            patch.dict(os.environ, {"PATH": str(tools.path)}),
        ):
            engine = Engine(api.endpoint)
            engine.preflight()
            events = Events()
            with BuildCache(engine, configured(), "fixture-daemon", events) as cache:
                cache.preflight()
                cache.prune(dt.datetime.now(dt.timezone.utc), lambda: None)
            calls = [
                call
                for call in tools.calls()
                if "prune" in call and "--help" not in call
            ]
            self.assertEqual(len(calls), 1)
            self.assertNotIn("--max-used-space", calls[0])
            budget = next(
                event for event in events.items if event["event"] == "cache_budget"
            )
            self.assertEqual(budget["status"], "achieved")
            self.assertIsNone(budget["reclaimed_bytes"])

    def test_capability_is_checked_before_any_prune(self):
        for changed in [
            {"gc_space_filters": False},
            {"daemon_id": "wrong"},
            {"driver": "docker-container"},
        ]:
            with (
                CacheTools() as tools,
                APIFixture(daemon_routes() | tools.routes()) as api,
                patch.dict(os.environ, {"PATH": str(tools.path)}),
            ):
                tools.state["capabilities"].update(changed)
                tools.save()
                engine = Engine(api.endpoint)
                engine.preflight()
                with (
                    BuildCache(
                        engine, configured(), "fixture-daemon", Events()
                    ) as cache,
                    self.assertRaises(Failure),
                ):
                    cache.preflight()
                self.assertFalse(
                    any(
                        "prune" in call and "--help" not in call
                        for call in tools.calls()
                    )
                )

    def test_exact_cache_accounting_is_separate_from_physical_reclamation(self):
        with (
            CacheTools() as tools,
            APIFixture(daemon_routes() | tools.routes()) as api,
            patch.dict(os.environ, {"PATH": str(tools.path)}),
        ):
            engine = Engine(api.endpoint)
            engine.preflight()
            with BuildCache(engine, configured(), "fixture-daemon", Events()) as cache:
                cache.preflight()
                sample = cache.observe()
                self.assertEqual(sample["reported_bytes"], 512)
                self.assertEqual(sample["reclaimable_records"], 1)
                self.assertIsNone(sample["physical_reclaimed_bytes"])

    def test_engine_cache_records_preserve_exact_bytes_and_last_use(self):
        now = dt.datetime(2026, 10, 9, tzinfo=dt.timezone.utc)
        with (
            CacheTools() as tools,
            APIFixture(daemon_routes() | tools.routes()) as api,
            patch.dict(os.environ, {"PATH": str(tools.path)}),
        ):
            tools.state["records"][0].update(
                Size=1234567891,
                Shared=True,
                LastUsedAt="2026-10-08T23:59:59.123456789Z",
            )
            tools.save()
            events = Events()
            with BuildCache(
                Engine(api.endpoint), configured(), "fixture-daemon", events
            ) as cache:
                cache.preflight()
                sample = cache.observe()
                cache.plan(now)
            self.assertEqual(sample["reported_bytes"], 1234567891)
            self.assertEqual(sample["shared_reported_bytes"], 1234567891)
            self.assertEqual(events.items[-1]["age_candidates"], 0)
            self.assertEqual(events.items[-1]["indeterminate_last_use"], 0)
            self.assertIn(("GET", "/v1.48/system/df?type=build-cache"), api.requests)
            self.assertFalse(any("du" in call for call in tools.calls()))

    def test_indeterminate_cache_accounting_is_rejected(self):
        for changed in (
            {"Size": True},
            {"Size": "512B"},
            {"Size": -1},
            {"Size": 2**63},
            {"InUse": None},
        ):
            with (
                self.subTest(changed=changed),
                CacheTools() as tools,
                APIFixture(daemon_routes() | tools.routes()) as api,
                patch.dict(os.environ, {"PATH": str(tools.path)}),
            ):
                tools.state["records"][0].update(changed)
                tools.save()
                with (
                    BuildCache(
                        Engine(api.endpoint), configured(), "fixture-daemon", Events()
                    ) as cache,
                    self.assertRaises(Failure) as raised,
                ):
                    cache.preflight()
                self.assertEqual(raised.exception.code, 2)

    def test_native_and_off_modes_do_not_prune(self):
        for mode in ("native", "off"):
            with (
                CacheTools() as tools,
                APIFixture(daemon_routes() | tools.routes()) as api,
                patch.dict(os.environ, {"PATH": str(tools.path)}),
            ):
                engine = Engine(api.endpoint)
                engine.preflight()
                with BuildCache(
                    engine, configured(cache={"mode": mode}), "fixture-daemon", Events()
                ) as cache:
                    cache.preflight()
                    cache.prune(
                        dt.datetime.now(dt.timezone.utc),
                        lambda: self.fail("guard should not be needed"),
                    )
                self.assertFalse(
                    any(
                        "prune" in call and "--help" not in call
                        for call in tools.calls()
                    )
                )

    def test_missing_cache_inventory_is_not_an_empty_backend(self):
        for usage in (None, {}, {"BuildCache": None}, {"BuildCache": {}}):
            with (
                self.subTest(usage=usage),
                CacheTools() as tools,
                APIFixture(
                    daemon_routes()
                    | {("GET", "/v1.48/system/df?type=build-cache"): (200, usage)}
                ) as api,
                patch.dict(os.environ, {"PATH": str(tools.path)}),
            ):
                with (
                    BuildCache(
                        Engine(api.endpoint), configured(), "fixture-daemon", Events()
                    ) as cache,
                    self.assertRaises(Failure) as raised,
                ):
                    cache.preflight()
                self.assertEqual(raised.exception.code, 2)

    def test_age_then_budget_reports_an_unmet_target(self):
        with (
            CacheTools() as tools,
            APIFixture(daemon_routes() | tools.routes()) as api,
            patch.dict(os.environ, {"PATH": str(tools.path)}),
        ):
            tools.state["after_age"] = [
                {
                    **tools.state["records"][0],
                    "ID": "new",
                    "Size": 5000,
                    "InUse": False,
                }
            ]
            tools.state["after_budget"] = tools.state["after_age"]
            tools.save()
            engine = Engine(api.endpoint)
            engine.preflight()
            events = Events()
            with BuildCache(
                engine,
                configured(cache={"max_used_space": "1kb"}),
                "fixture-daemon",
                events,
            ) as cache:
                cache.preflight()
                guard_calls = []
                cache.prune(
                    dt.datetime.now(dt.timezone.utc), lambda: guard_calls.append(1)
                )
            calls = [
                call
                for call in tools.calls()
                if "prune" in call and "--help" not in call
            ]
            self.assertEqual(len(calls), 2)
            self.assertIn("--filter", calls[0])
            self.assertIn("--max-used-space", calls[1])
            self.assertEqual(guard_calls, [1, 1])
            budget = next(
                event for event in events.items if event["event"] == "cache_budget"
            )
            self.assertEqual(budget["status"], "target-unmet")
            self.assertEqual(budget["remaining_bytes"], 5000)

    def test_unknown_age_or_type_and_internal_records_remain_untouched(self):
        for change in [
            {"LastUsedAt": None},
            {"Type": "unknown"},
            {"Type": "internal"},
            {"InUse": True},
        ]:
            with (
                CacheTools() as tools,
                APIFixture(daemon_routes() | tools.routes()) as api,
                patch.dict(os.environ, {"PATH": str(tools.path)}),
            ):
                tools.state["records"][0].update({"Size": 5000, **change})
                tools.save()
                engine = Engine(api.endpoint)
                engine.preflight()
                events = Events()
                with BuildCache(
                    engine,
                    configured(cache={"max_used_space": "1kb"}),
                    "fixture-daemon",
                    events,
                ) as cache:
                    cache.preflight()
                    cache.prune(
                        dt.datetime.now(dt.timezone.utc),
                        lambda: self.fail("no eligible record"),
                    )
                self.assertFalse(
                    any(
                        "prune" in call and "--help" not in call
                        for call in tools.calls()
                    )
                )
                budget = next(
                    event for event in events.items if event["event"] == "cache_budget"
                )
                self.assertEqual(budget["status"], "no-eligible-records")
                self.assertFalse(budget["target_met"])


if __name__ == "__main__":
    unittest.main()
