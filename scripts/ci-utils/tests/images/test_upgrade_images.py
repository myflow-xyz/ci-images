"""Check the refresh scope and the boundary between pulling and retirement."""

import contextlib
import io
import json
import os
import time
import unittest
from types import SimpleNamespace
from unittest import mock


from lib.maintenance.engine import Failure
from lib.images.upgrade_images import (
    main,
    published_version_tags,
    pull_image,
    registry_index_digest,
)
from tests.images.test_remove_images import ALIAS, IID, PREFIX, REF, VersionAPI

GO_LATEST = PREFIX + "go:latest"
VITE_LATEST = PREFIX + "vite:latest"
GO_VERSION = PREFIX + "go:0.0.2"
VITE_VERSION = PREFIX + "vite:0.0.2"
GO_INDEX = "sha256:" + "6" * 64
VITE_INDEX = "sha256:" + "7" * 64
GO_PINNED = PREFIX + "go@" + GO_INDEX
VITE_PINNED = PREFIX + "vite@" + VITE_INDEX
NEW_ID = "sha256:" + "4" * 64
INDEXES = {
    GO_LATEST: GO_INDEX,
    GO_VERSION: GO_INDEX,
    VITE_LATEST: VITE_INDEX,
    VITE_VERSION: VITE_INDEX,
}


def release(tag, images, *, draft=False, prerelease=False):
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "body": "\n".join(f"| {reference} | {digest} |" for reference, digest in images),
    }


def add_pulled_digest(api, pinned):
    digests = api.objects["images"][NEW_ID].setdefault("RepoDigests", [])
    if pinned not in digests:
        digests.append(pinned)


class UpgradeImagesTests(unittest.TestCase):
    def invoke(self, api, pull, *args, indexes=None, releases=None):
        if indexes is None:
            indexes = INDEXES
        if releases is None:
            releases = [
                release("v0.0.2", [(GO_VERSION, GO_INDEX), (VITE_VERSION, VITE_INDEX)])
            ]
        for reference in (*INDEXES, GO_PINNED, VITE_PINNED):
            api.add_reference(reference)

        def tag(_engine, source, reference):
            status, target = api.inspect("images", source)
            self.assertEqual(status, 200)
            for item in api.objects["images"].values():
                if reference in item["RepoTags"]:
                    item["RepoTags"].remove(reference)
            target["RepoTags"].append(reference)

        output = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(output))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            stack.enter_context(mock.patch.dict(os.environ, {}, clear=True))
            stack.enter_context(
                mock.patch("lib.images.upgrade_images.DEFAULT_ENDPOINT", api.endpoint)
            )
            stack.enter_context(
                mock.patch("lib.images.upgrade_images.pull_image", side_effect=pull)
            )
            stack.enter_context(
                mock.patch("lib.images.upgrade_images.tag_image", side_effect=tag)
            )
            stack.enter_context(
                mock.patch(
                    "lib.images.upgrade_images.registry_index_digest",
                    side_effect=lambda _engine, reference: indexes[reference],
                )
            )
            stack.enter_context(
                mock.patch(
                    "lib.images.upgrade_images.urllib.request.urlopen",
                    return_value=io.StringIO(json.dumps(releases)),
                )
            )
            code = main(args)
        return code, [json.loads(line) for line in output.getvalue().splitlines()]

    def test_pulls_cached_tags_and_digests_only_and_keeps_old_versions(self):
        other = "ghcr.io/other/ci-base:0.0.1"
        with VersionAPI([REF, other], {NEW_ID: [ALIAS]}) as api:
            api.objects["images"][IID]["RepoDigests"] = [PREFIX + "vite@" + IID]
            requests = []

            def fetch(engine, reference, platform):
                requests.append((reference, platform))
                add_pulled_digest(api, reference)

            code, events = self.invoke(api, fetch)
            self.assertEqual(code, 0, events)
            self.assertEqual(requests, [(GO_PINNED, "linux/amd64"), (VITE_PINNED, "linux/amd64")])
            self.assertEqual(api.objects["images"][IID]["RepoTags"], [REF, other])
            self.assertEqual(
                api.objects["images"][NEW_ID]["RepoTags"],
                [ALIAS, GO_VERSION, GO_LATEST, VITE_VERSION, VITE_LATEST],
            )
            pulls = [event for event in events if event["event"] == "pulled"]
            self.assertEqual(
                [(e["id"], e["source"], e["digest"], e["image_id"]) for e in pulls],
                [
                    (GO_VERSION, GO_LATEST, GO_INDEX, NEW_ID),
                    (VITE_VERSION, VITE_LATEST, VITE_INDEX, NEW_ID),
                ],
            )
            self.assertTrue(all(method == "GET" for method, _ in api.requests))

    def test_prunes_only_after_success_and_preserves_latest_alias(self):
        with VersionAPI([REF, ALIAS], {NEW_ID: []}) as api:

            def fetch(engine, reference, platform):
                self.assertEqual(reference, GO_PINNED)
                add_pulled_digest(api, reference)

            code, events = self.invoke(api, fetch, "--prune-old-versions")
            self.assertEqual(code, 0, events)
            self.assertEqual(api.objects["images"][IID]["RepoTags"], [ALIAS])
            self.assertEqual(
                api.objects["images"][NEW_ID]["RepoTags"], [GO_VERSION, GO_LATEST]
            )
            self.assertEqual(
                [e["id"] for e in events if e["event"] == "removed"], [REF]
            )

    def test_failed_pull_keeps_versions_even_if_another_pull_succeeded(self):
        old_vite = PREFIX + "vite:0.0.1"
        with VersionAPI([REF, old_vite], {NEW_ID: [ALIAS]}) as api:
            def fetch(engine, reference, platform):
                if reference == VITE_PINNED:
                    raise Failure(5, "fixture pull failed")
                add_pulled_digest(api, reference)

            code, events = self.invoke(api, fetch, "--prune-old-versions")
            self.assertEqual(code, 5, events)
            self.assertEqual(api.objects["images"][IID]["RepoTags"], [REF, old_vite])
            self.assertTrue(all(method == "GET" for method, _ in api.requests))

    def test_retirement_skips_a_latest_tag_that_changed_after_tagging(self):
        with VersionAPI([REF], {NEW_ID: []}) as api:

            def move_latest(kind, identifier):
                if identifier == REF:
                    api.objects["images"][NEW_ID]["RepoTags"].remove(GO_LATEST)
                    api.objects["images"][IID]["RepoTags"].append(GO_LATEST)

            api.before_inspect = move_latest
            code, events = self.invoke(
                api,
                lambda _, pinned, _platform: add_pulled_digest(api, pinned),
                "--prune-old-versions",
            )
            self.assertEqual(code, 0, events)
            self.assertTrue(
                any(e.get("reason") == "latest-selection-changed" for e in events)
            )
            self.assertTrue(all(method == "GET" for method, _ in api.requests))

    def test_retirement_stops_if_daemon_identity_changes_before_deletion(self):
        with VersionAPI([REF], {NEW_ID: []}) as api:

            def change_daemon(kind, identifier):
                if identifier == REF:
                    _, info = api.routes[("GET", "/v1.48/info")]
                    info["ID"] = "other-daemon"

            api.before_inspect = change_daemon
            code, events = self.invoke(
                api,
                lambda _, pinned, _platform: add_pulled_digest(api, pinned),
                "--prune-old-versions",
            )
            self.assertEqual(code, 3, events)
            self.assertTrue(all(method == "GET" for method, _ in api.requests))

    def test_without_matching_images_prune_is_a_no_op(self):
        with VersionAPI([ALIAS, PREFIX + "retired:0.0.1"]) as api:
            pull = mock.Mock()
            code, events = self.invoke(api, pull, "--prune-old-versions")
            self.assertEqual(code, 0, events)
            pull.assert_not_called()
            self.assertTrue(all(method == "GET" for method, _ in api.requests))

    def test_repeat_refresh_reuses_the_correct_exact_tag(self):
        with VersionAPI([REF], {NEW_ID: [GO_VERSION, GO_LATEST]}) as api:
            for _ in range(2):
                code, events = self.invoke(
                    api, lambda _, pinned, _platform: add_pulled_digest(api, pinned)
                )
                self.assertEqual(code, 0, events)
            self.assertEqual(
                api.objects["images"][NEW_ID]["RepoTags"], [GO_VERSION, GO_LATEST]
            )
            self.assertIn(REF, api.objects["images"][IID]["RepoTags"])

    def test_missing_release_keeps_all_tags_and_does_not_pull(self):
        with VersionAPI([REF, GO_LATEST]) as api:
            pull = mock.Mock()
            code, events = self.invoke(api, pull, "--prune-old-versions", releases=[])
            self.assertEqual(code, 5, events)
            self.assertIn("no published numeric release", events[0]["message"])
            pull.assert_not_called()
            self.assertEqual(api.objects["images"][IID]["RepoTags"], [REF, GO_LATEST])

    def test_remote_version_tag_must_still_match_the_release_digest(self):
        with VersionAPI([REF, GO_LATEST]) as api:
            pull = mock.Mock()
            code, events = self.invoke(
                api,
                pull,
                "--prune-old-versions",
                indexes=INDEXES | {GO_VERSION: VITE_INDEX},
            )
            self.assertEqual(code, 5, events)
            self.assertIn("does not match its published image index", events[0]["message"])
            pull.assert_not_called()
            self.assertEqual(api.objects["images"][IID]["RepoTags"], [REF, GO_LATEST])

    def test_moved_remote_latest_leaves_local_tags_and_prevents_retirement(self):
        with VersionAPI([REF, GO_LATEST], {NEW_ID: []}) as api:
            indexes = dict(INDEXES)

            def fetch(_engine, pinned, _platform):
                add_pulled_digest(api, pinned)
                indexes[GO_LATEST] = VITE_INDEX

            code, events = self.invoke(api, fetch, "--prune-old-versions", indexes=indexes)
            self.assertEqual(code, 5, events)
            self.assertIn("changed during refresh", events[0]["message"])
            self.assertEqual(api.objects["images"][NEW_ID]["RepoTags"], [])
            self.assertEqual(api.objects["images"][IID]["RepoTags"], [REF, GO_LATEST])

    def test_conflicting_local_version_is_preserved(self):
        with VersionAPI([REF, GO_LATEST, GO_VERSION], {NEW_ID: []}) as api:
            code, events = self.invoke(
                api, lambda _, pinned, _platform: add_pulled_digest(api, pinned), "--prune-old-versions"
            )
            self.assertEqual(code, 5, events)
            self.assertIn("points to a different image", events[0]["message"])
            self.assertEqual(api.objects["images"][NEW_ID]["RepoTags"], [])
            self.assertEqual(
                api.objects["images"][IID]["RepoTags"], [REF, GO_LATEST, GO_VERSION]
            )

    def test_foreign_platform_pull_preserves_both_tags_and_old_versions(self):
        with VersionAPI([REF, GO_LATEST], {NEW_ID: []}) as api:
            api.objects["images"][NEW_ID].update(Os="linux", Architecture="arm64")
            code, events = self.invoke(
                api, lambda _, pinned, _platform: add_pulled_digest(api, pinned), "--prune-old-versions"
            )
            self.assertEqual(code, 5, events)
            self.assertIn("linux/amd64", next(e["message"] for e in events if e["event"] == "error"))
            self.assertEqual(api.objects["images"][IID]["RepoTags"], [REF, GO_LATEST])
            self.assertEqual(api.objects["images"][NEW_ID]["RepoTags"], [])
            self.assertFalse(any(method == "DELETE" for method, _ in api.requests))

    def test_unsupported_daemon_architecture_fails_before_pull(self):
        with VersionAPI([REF, GO_LATEST]) as api:
            api.routes[("GET", "/version")][1]["Arch"] = "riscv64"
            pull = mock.Mock()
            code, events = self.invoke(api, pull, "--prune-old-versions")
            self.assertEqual(code, 2, events)
            pull.assert_not_called()
            self.assertFalse(events[-1]["mutation_started"])
            self.assertEqual(api.objects["images"][IID]["RepoTags"], [REF, GO_LATEST])

    def test_docker_client_uses_explicit_socket_and_local_registry_config(self):
        engine = SimpleNamespace(
            endpoint="unix:///runner/docker.sock", deadline=time.monotonic() + 10
        )
        environment = {
            "DOCKER_HOST": "tcp://remote:2375",
            "DOCKER_CONFIG": "/fixture/docker",
            "DOCKER_DEFAULT_PLATFORM": "linux/amd64",
        }
        with (
            mock.patch.dict(os.environ, environment, clear=True),
            mock.patch("lib.images.upgrade_images.subprocess.run") as run,
        ):
            run.return_value.returncode = 0
            pull_image(engine, GO_LATEST, "linux/arm64")
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
                "--platform",
                "linux/arm64",
                GO_LATEST,
            ],
        )
        self.assertNotIn("DOCKER_HOST", run.call_args.kwargs["env"])
        self.assertNotIn("DOCKER_DEFAULT_PLATFORM", run.call_args.kwargs["env"])


class ReleaseLookupTests(unittest.TestCase):
    def test_registry_inspection_uses_the_selected_socket_and_account_config(self):
        engine = SimpleNamespace(endpoint="unix:///runner/docker.sock", deadline=time.monotonic() + 10)
        env = {"DOCKER_CONFIG": "/fixture/docker", "BUILDX_BUILDER": "other-context"}
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch("lib.images.upgrade_images.subprocess.run") as run,
        ):
            run.return_value.returncode = 0
            run.return_value.stdout = f"application/vnd.oci.image.index.v1+json {GO_INDEX}"
            self.assertEqual(registry_index_digest(engine, GO_LATEST), GO_INDEX)
        self.assertEqual(run.call_args.args[0][:10], [
            "docker", "--config", env["DOCKER_CONFIG"], "--host", engine.endpoint,
            "buildx", "--builder", "default", "imagetools", "inspect",
        ])

    def test_matches_each_index_across_pages_and_ignores_unpublished_releases(self):
        newest_go = PREFIX + "go:0.0.3"
        newest_vite = PREFIX + "vite:0.0.3"
        pages = [
            [
                release("v0.0.4", [(PREFIX + "go:0.0.4", GO_INDEX)], draft=True),
                release("v0.0.3", [(newest_go, VITE_INDEX), (newest_vite, VITE_INDEX)]),
            ],
            [release("v0.0.2", [(GO_VERSION, GO_INDEX)])],
        ]
        with (
            mock.patch("lib.images.upgrade_images.RELEASE_PAGE_SIZE", 2),
            mock.patch(
                "lib.images.upgrade_images.urllib.request.urlopen",
                side_effect=[io.StringIO(json.dumps(page)) for page in pages],
            ) as request,
        ):
            versions = published_version_tags(
                SimpleNamespace(remaining=lambda: 10),
                {PREFIX + "go": GO_INDEX, PREFIX + "vite": VITE_INDEX},
            )
        self.assertEqual(
            versions, {PREFIX + "go": GO_VERSION, PREFIX + "vite": newest_vite}
        )
        self.assertTrue(request.call_args.args[0].full_url.endswith("per_page=2&page=2"))

    def test_registry_descriptor_requires_an_index(self):
        with mock.patch(
            "lib.images.upgrade_images.docker_command",
            return_value=f"application/vnd.oci.image.manifest.v1+json {GO_INDEX}",
        ):
            with self.assertRaisesRegex(Failure, "did not return a valid image index"):
                registry_index_digest(mock.Mock(), GO_LATEST)
