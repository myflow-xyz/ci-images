"""T-24/32: storage identity, freshness, capacity, and unknown accounting."""

import copy
import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "images/utils"))

from ci_utils.storage import evaluate
from test_policy import NOW, configured

RUN = "a" * 32


def observation():
    return {
        "schema_version": 1,
        "source": "linux-host",
        "daemon_id": "fixture-daemon",
        "run_id": RUN,
        "sampled_at": NOW.isoformat(),
        "complete": True,
        "filesystems": [
            {
                "device": "1",
                "paths": ["/var/lib/docker", "/var/lib/containerd"],
                "roles": ["docker", "containerd"],
                "total_bytes": 1000,
                "used_bytes": 810,
                "available_bytes": 150,
            }
        ],
    }


class StorageTests(unittest.TestCase):
    def evaluate(self, value, **settings):
        return evaluate(
            value, configured(pressure=settings), "fixture-daemon", RUN, NOW
        )

    def test_pressure_uses_actual_used_bytes_and_separate_available_reserve(self):
        value = observation()
        result = self.evaluate(value)
        self.assertEqual(result["status"], "known")
        self.assertTrue(result["pressured"])
        self.assertFalse(result["critical"])
        result = self.evaluate(value, reserve_bytes=151)
        self.assertTrue(result["critical"])
        value["filesystems"][0]["used_bytes"] = 900
        value["filesystems"][0]["available_bytes"] = 50
        self.assertTrue(self.evaluate(value)["critical"])

    def test_fresh_below_threshold_is_distinct_from_unknown(self):
        value = observation()
        value["filesystems"][0].update(used_bytes=100, available_bytes=850)
        result = self.evaluate(value)
        self.assertIs(result["pressured"], False)
        self.assertIs(result["critical"], False)
        self.assertIsNone(self.evaluate(None)["pressured"])
        self.assertIsNone(self.evaluate(None)["filesystems"])

    def test_stale_wrong_daemon_wrong_run_and_incomplete_sources_are_unknown(self):
        for patch in [
            {"sampled_at": (NOW - dt.timedelta(seconds=301)).isoformat()},
            {"sampled_at": (NOW + dt.timedelta(seconds=6)).isoformat()},
            {"daemon_id": "other"},
            {"run_id": "b" * 32},
            {"source": "container-root"},
            {"complete": False},
            {"schema_version": True},
            {"filesystems": []},
        ]:
            with self.subTest(patch=patch):
                result = self.evaluate({**observation(), **patch})
                self.assertIsNone(result["pressured"])
                self.assertIsNone(result["filesystems"])

    def test_duplicate_filesystems_and_invalid_or_missing_metrics_are_unknown(self):
        for patch in [
            {"total_bytes": 0},
            {"available_bytes": -1},
            {"used_bytes": 1001},
            {"total_bytes": True},
            {"device": None},
            {"paths": ["relative"]},
            {"roles": []},
        ]:
            with self.subTest(patch=patch):
                value = observation()
                value["filesystems"][0].update(patch)
                self.assertIsNone(self.evaluate(value)["pressured"])
        value = observation()
        value["filesystems"].append(copy.deepcopy(value["filesystems"][0]))
        self.assertIsNone(self.evaluate(value)["pressured"])


if __name__ == "__main__":
    unittest.main()
