"""Check the refresh scope and the boundary between pulling and retirement."""

import contextlib
import io
import json
import os
import pathlib
import sys
import time
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "images/utils"))

from ci_utils.engine import Failure
from ci_utils.upgrade_images import main, pull_image
from test_remove_images import ALIAS, IID, PREFIX, REF, VersionAPI

GO_LATEST = PREFIX + "go:latest"
VITE_LATEST = PREFIX + "vite:latest"
NEW_ID = "sha256:" + "4" * 64


class UpgradeImagesTests(unittest.TestCase):
    def invoke(self, api, pull, *args):
        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(output))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            stack.enter_context(mock.patch.dict(os.environ, {}, clear=True))
            stack.enter_context(
                mock.patch("ci_utils.upgrade_images.DEFAULT_ENDPOINT", api.endpoint)
            )
            stack.enter_context(
                mock.patch("ci_utils.upgrade_images.pull_image", side_effect=pull)
            )
            code = main(args)
        return code, [json.loads(line) for line in output.getvalue().splitlines()]

    def test_pulls_cached_tags_and_digests_only_and_keeps_old_versions(self):
        other = "ghcr.io/other/ci-base:0.0.1"
        with VersionAPI([REF, other], {NEW_ID: [ALIAS]}) as api:
            api.objects["images"][IID]["RepoDigests"] = [PREFIX + "vite@" + IID]
            for reference in (GO_LATEST, VITE_LATEST):
                api.add_reference(reference)
            requests = []

            def fetch(engine, reference):
                requests.append(reference)
                api.objects["images"][NEW_ID]["RepoTags"].append(reference)

            code, events = self.invoke(api, fetch)
            self.assertEqual(code, 0, events)
            self.assertEqual(requests, [GO_LATEST, VITE_LATEST])
            self.assertEqual(api.objects["images"][IID]["RepoTags"], [REF, other])
            self.assertTrue(all(method == "GET" for method, _ in api.requests))

    def test_prunes_only_after_success_and_preserves_latest_alias(self):
        new_version = PREFIX + "go:0.0.2"
        with VersionAPI([REF, ALIAS], {NEW_ID: [new_version]}) as api:
            api.add_reference(GO_LATEST)

            def fetch(engine, reference):
                self.assertEqual(reference, GO_LATEST)
                api.objects["images"][NEW_ID]["RepoTags"].append(reference)

            code, events = self.invoke(api, fetch, "--prune-old-versions")
            self.assertEqual(code, 0, events)
            self.assertEqual(api.objects["images"][IID]["RepoTags"], [ALIAS])
            self.assertEqual(
                api.objects["images"][NEW_ID]["RepoTags"], [new_version, GO_LATEST]
            )
            self.assertEqual(
                [e["id"] for e in events if e["event"] == "removed"], [REF]
            )

    def test_failed_pull_keeps_versions_even_if_another_pull_succeeded(self):
        old_vite = PREFIX + "vite:0.0.1"
        with VersionAPI([REF, old_vite], {NEW_ID: [ALIAS]}) as api:
            api.add_reference(GO_LATEST)

            def fetch(engine, reference):
                if reference == VITE_LATEST:
                    raise Failure(5, "fixture pull failed")
                api.objects["images"][NEW_ID]["RepoTags"].append(reference)

            code, events = self.invoke(api, fetch, "--prune-old-versions")
            self.assertEqual(code, 5, events)
            self.assertEqual(api.objects["images"][IID]["RepoTags"], [REF, old_vite])
            self.assertTrue(all(method == "GET" for method, _ in api.requests))

    def test_retirement_skips_a_latest_tag_that_changed_after_pull(self):
        with VersionAPI([REF], {NEW_ID: [GO_LATEST]}) as api:

            def move_latest(kind, identifier):
                if identifier == REF:
                    api.objects["images"][NEW_ID]["RepoTags"].remove(GO_LATEST)
                    api.objects["images"][IID]["RepoTags"].append(GO_LATEST)

            api.before_inspect = move_latest
            code, events = self.invoke(api, mock.Mock(), "--prune-old-versions")
            self.assertEqual(code, 0, events)
            self.assertTrue(
                any(e.get("reason") == "latest-selection-changed" for e in events)
            )
            self.assertTrue(all(method == "GET" for method, _ in api.requests))

    def test_retirement_stops_if_daemon_identity_changes_before_deletion(self):
        with VersionAPI([REF], {NEW_ID: [GO_LATEST]}) as api:

            def change_daemon(kind, identifier):
                if identifier == REF:
                    _, info = api.routes[("GET", "/v1.48/info")]
                    info["ID"] = "other-daemon"

            api.before_inspect = change_daemon
            code, events = self.invoke(api, mock.Mock(), "--prune-old-versions")
            self.assertEqual(code, 3, events)
            self.assertTrue(all(method == "GET" for method, _ in api.requests))

    def test_without_matching_images_prune_is_a_no_op(self):
        with VersionAPI([ALIAS]) as api:
            pull = mock.Mock()
            code, events = self.invoke(api, pull, "--prune-old-versions")
            self.assertEqual(code, 0, events)
            pull.assert_not_called()
            self.assertTrue(all(method == "GET" for method, _ in api.requests))

    def test_docker_client_uses_explicit_socket_and_local_registry_config(self):
        engine = SimpleNamespace(
            endpoint="unix:///runner/docker.sock", deadline=time.monotonic() + 10
        )
        environment = {
            "DOCKER_HOST": "tcp://remote:2375",
            "DOCKER_CONFIG": "/fixture/docker",
        }
        with (
            mock.patch.dict(os.environ, environment, clear=True),
            mock.patch("ci_utils.upgrade_images.subprocess.run") as run,
        ):
            run.return_value.returncode = 0
            pull_image(engine, GO_LATEST)
        self.assertEqual(
            run.call_args.args[0],
            [
                "docker",
                "--config",
                "/fixture/docker",
                "--host",
                engine.endpoint,
                "image",
                "pull",
                GO_LATEST,
            ],
        )
        self.assertNotIn("DOCKER_HOST", run.call_args.kwargs["env"])
