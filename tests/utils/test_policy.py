"""T-02, T-06–13, T-23: deterministic safety and retention regressions."""

import copy
import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "images/utils"))

from ci_utils.policy import (
    InvalidPolicy,
    configuration,
    container_decision,
    duration,
    image_decision,
    network_decision,
    space_bytes,
)

NOW = dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)
OLD = "2026-08-01T00:00:00Z"
CID = "1" * 64
NID = "2" * 64
IID = "sha256:" + "3" * 64
OWNED = {"xyz.myflow.ci.ephemeral": "true"}


def configured(**values):
    return configuration(
        {"schema_version": 1, "endpoint": "unix:///test/docker.sock", **values}, {}
    )


def container():
    return {
        "Id": CID,
        "Created": OLD,
        "Config": {"Labels": dict(OWNED)},
        "State": {"Status": "exited"},
        "Name": "/fixture",
        "Image": IID,
    }


def network():
    return {
        "Id": NID,
        "Created": OLD,
        "Labels": dict(OWNED),
        "Name": "fixture",
        "Scope": "local",
        "Driver": "bridge",
        "Ingress": False,
        "Containers": {},
    }


def image():
    return {
        "Id": IID,
        "Created": OLD,
        "Config": {"Labels": {}},
        "RepoTags": ["ci.example/fixture:old"],
        "RepoDigests": [],
    }


class ConfigurationTests(unittest.TestCase):
    def test_duration_is_exact_and_rejects_expressions(self):
        self.assertEqual(duration("720h"), 2592000)
        self.assertEqual(duration("2h30m5s"), 9005)
        for value in [
            "",
            "0h",
            "-1h",
            "1d",
            "1e3h",
            "1h;touch /tmp/no",
            True,
            10,
            "NaNh",
            "1h1h",
            "1.5h",
        ]:
            with self.subTest(value=value), self.assertRaises(InvalidPolicy):
                duration(value)

    def test_defaults_preserve_explicit_scope(self):
        policy = configured()
        self.assertEqual(policy["container_min_age"], "24h")
        self.assertEqual(policy["tagged_image_min_age"], "720h")
        self.assertEqual(policy["cache"]["max_unused_age"], "336h")
        self.assertEqual(policy["cache"]["max_used_space"], "20gb")
        self.assertEqual(policy["image_scope"]["mode"], "allowlist")
        self.assertEqual(policy["image_scope"]["repositories"], [])

    def test_space_target_matches_buildx_binary_units(self):
        self.assertEqual(space_bytes("20gb"), 20 * 1024**3)
        self.assertEqual(space_bytes("1MB"), 1024**2)
        for value in ["0gb", "-1gb", "inf", 20, "9" * 30 + "tb"]:
            with self.subTest(value=value), self.assertRaises(InvalidPolicy):
                space_bytes(value)

    def test_unknown_keys_and_unsafe_configuration_fail(self):
        for change in [
            {"surprise": 1},
            {"volume_cleanup": True},
            {"schema_version": True},
            {"endpoint": "tcp://localhost:2375"},
            {"endpoint": "unix://relative"},
            {"container_min_age": "0h"},
            {"cache": {"mode": "automatic"}},
            {"cache": {"builder": "unmanaged"}},
            {"cache": {"max_used_space": "-1gb"}},
            {"cache": {"include_internal": "false"}},
            {"image_scope": {"mode": "daemon-wide"}},
            {"image_scope": {"repositories": ["ci.example/*"]}},
            {"protected": {"image_ids": ["not-an-id"]}},
            {"timeouts": {"operation": "2h", "run": "1h"}},
        ]:
            with self.subTest(change=change), self.assertRaises(InvalidPolicy):
                configured(**change)

    def test_configuration_precedence_and_no_mutation(self):
        value = {
            "schema_version": 1,
            "endpoint": "unix:///test/docker.sock",
            "container_min_age": "48h",
        }
        original = copy.deepcopy(value)
        env = {"CLEANUP_CONTAINER_MIN_AGE": "72h"}
        self.assertEqual(configuration(value, env)["container_min_age"], "72h")
        self.assertEqual(
            configuration(value, env, {"container_min_age": "96h"})[
                "container_min_age"
            ],
            "96h",
        )
        self.assertEqual(value, original)
        with self.assertRaises(InvalidPolicy):
            configuration(value, {"CLEANUP_UNKNOWN": "true"})


class ContainerTests(unittest.TestCase):
    def test_old_finished_owned_container_is_eligible(self):
        for state in ["created", "exited"]:
            obj = container()
            obj["State"]["Status"] = state
            self.assertTrue(container_decision(obj, configured(), NOW).eligible)

    def test_all_other_states_survive(self):
        for state in [
            "running",
            "paused",
            "restarting",
            "removing",
            "dead",
            "unknown",
            None,
        ]:
            obj = container()
            obj["State"]["Status"] = state
            self.assertFalse(container_decision(obj, configured(), NOW).eligible)

    def test_positive_ownership_and_protection_override(self):
        for labels in [{}, None, {**OWNED, "xyz.myflow.cleanup.protect": "true"}]:
            obj = container()
            obj["Config"]["Labels"] = labels
            self.assertFalse(container_decision(obj, configured(), NOW).eligible)
        policy = configured(protected={"container_ids": [CID]})
        self.assertFalse(container_decision(container(), policy, NOW).eligible)

    def test_infrastructure_and_unknown_metadata_survive(self):
        for patch in [
            {"Name": "/buildx_buildkit_default"},
            {"Config": None},
            {"Created": None},
            {"Id": None},
            {"Id": "short"},
            {"State": None},
        ]:
            obj = {**container(), **patch}
            self.assertFalse(container_decision(obj, configured(), NOW).eligible)

    def test_creation_age_is_not_stop_age_and_cutoff_is_strict(self):
        obj = container()
        obj["State"]["FinishedAt"] = NOW.isoformat()
        self.assertTrue(container_decision(obj, configured(), NOW).eligible)
        for created, eligible in [
            ("2026-09-30T00:00:00Z", False),
            ("2026-09-29T23:59:59Z", True),
            ("2026-09-30T00:00:01Z", False),
            ("2026-09-30T01:00:00+01:00", False),
            ("2026-09-30T00:00:00", False),
            ("nonsense", False),
        ]:
            obj["Created"] = created
            with self.subTest(created=created):
                self.assertEqual(
                    container_decision(obj, configured(), NOW).eligible, eligible
                )


class NetworkTests(unittest.TestCase):
    def test_owned_old_empty_local_network_is_eligible(self):
        self.assertTrue(network_decision(network(), configured(), NOW).eligible)

    def test_references_systems_protection_and_unknowns_survive(self):
        for patch in [
            {"Containers": {CID: {}}},
            {"Containers": None},
            {"Name": "bridge"},
            {"Name": "host"},
            {"Name": "none"},
            {"Driver": "overlay"},
            {"Scope": "swarm"},
            {"Ingress": True},
            {"Labels": {}},
            {"Labels": {**OWNED, "xyz.myflow.cleanup.protect": "true"}},
            {"Created": None},
        ]:
            self.assertFalse(
                network_decision({**network(), **patch}, configured(), NOW).eligible
            )
        self.assertFalse(network_decision(network(), configured(), NOW, {NID}).eligible)


class ImageTests(unittest.TestCase):
    def test_empty_allowlist_does_not_select_any_image(self):
        self.assertFalse(image_decision(image(), configured(), NOW).eligible)

    def test_exact_repository_scope_and_old_creation_age(self):
        policy = configured(image_scope={"repositories": ["ci.example/fixture"]})
        self.assertTrue(image_decision(image(), policy, NOW).eligible)
        self.assertFalse(
            image_decision(
                {**image(), "RepoTags": ["ci.example/fixture-evil:old"]}, policy, NOW
            ).eligible
        )

    def test_alias_protection_and_mixed_scope_never_untag(self):
        obj = image()
        obj["RepoTags"].append("ci.example/protected:old")
        policy = configured(
            image_scope={"mode": "daemon-wide", "daemon_wide_approved": True},
            protected={"image_repositories": ["ci.example/protected"]},
        )
        self.assertFalse(image_decision(obj, policy, NOW).eligible)
        policy = configured(image_scope={"repositories": ["ci.example/fixture"]})
        self.assertFalse(image_decision(obj, policy, NOW).eligible)
        self.assertFalse(image_decision(image(), policy, NOW, protected={IID}).eligible)

    def test_container_references_preserve_tagged_and_dangling_images(self):
        policy = configured(
            image_scope={"mode": "daemon-wide", "daemon_wide_approved": True}
        )
        for tags in [[], image()["RepoTags"]]:
            obj = {**image(), "RepoTags": tags}
            self.assertFalse(
                image_decision(obj, policy, NOW, referenced={IID}).eligible
            )

    def test_dangling_scope_and_missing_metadata_fail_closed(self):
        obj = {**image(), "RepoTags": []}
        self.assertFalse(image_decision(obj, configured(), NOW).eligible)
        policy = configured(image_scope={"ids": [IID]})
        self.assertTrue(image_decision(obj, policy, NOW).eligible)
        for patch in [
            {"Created": None},
            {"RepoTags": "invalid"},
            {"Config": None},
            {"Config": {"Labels": {"xyz.myflow.cleanup.protect": "true"}}},
        ]:
            self.assertFalse(image_decision({**obj, **patch}, policy, NOW).eligible)


if __name__ == "__main__":
    unittest.main()
