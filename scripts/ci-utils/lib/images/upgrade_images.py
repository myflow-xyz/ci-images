"""Refresh cached CI repositories and optionally retire old release tags."""

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from functools import partial

from lib.maintenance.cleanup import Inventory, Parser, Report, load_policy
from lib.maintenance.engine import APIError, Engine, Failure
from lib.maintenance.policy import IMAGE_ID, InvalidPolicy, configuration, duration
from .remove_images import REPOSITORIES, VERSION, remove_versions

PROFILE = "upgrade-images"
DEFAULT_ENDPOINT = "unix:///var/run/docker.sock"
RELEASES_API = "https://api.github.com/repos/myflow-xyz/ci-images/releases"
RELEASE_PAGE_SIZE = 30
INDEX_MEDIA_TYPES = (
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
)


def docker_command(engine, arguments, operation, *, capture=False):
    env = dict(os.environ)
    for key in (
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_DEFAULT_PLATFORM",
        "DOCKER_API_VERSION",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
    ):
        env.pop(key, None)
    config = env.get("DOCKER_CONFIG") or os.path.join(env.get("HOME", ""), ".docker")
    timeout = engine.deadline - time.monotonic()
    if timeout <= 0:
        raise Failure(6, "image refresh deadline exceeded")
    try:
        result = subprocess.run(
            [
                "docker",
                "--config",
                config,
                "--host",
                engine.endpoint,
                *arguments,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            timeout=timeout,
            check=False,
            text=True,
        )
    except OSError as error:
        raise Failure(
            5, "unable to start the Docker client for image refresh"
        ) from error
    except subprocess.TimeoutExpired as error:
        raise Failure(6, f"{operation} timed out") from error
    if result.returncode < 0:
        raise Failure(6, f"{operation} was interrupted")
    if result.returncode:
        raise Failure(5, f"{operation} failed. Check Docker and GHCR access.")
    return result.stdout


def pull_image(engine, reference, platform):
    docker_command(
        engine, ["image", "pull", "--platform", platform, reference],
        f"Docker pull for {reference}",
    )


def tag_image(engine, source, reference):
    docker_command(
        engine, ["image", "tag", source, reference], f"Docker tag for {reference}"
    )


def registry_index_digest(engine, reference):
    fields = docker_command(
        engine,
        [
            "buildx",
            "--builder",
            "default",
            "imagetools",
            "inspect",
            "--format",
            "{{.Manifest.MediaType}} {{.Manifest.Digest}}",
            reference,
        ],
        f"GHCR inspection for {reference}",
        capture=True,
    ).split()
    if (
        len(fields) != 2
        or fields[0] not in INDEX_MEDIA_TYPES
        or not IMAGE_ID.fullmatch(fields[1])
    ):
        raise Failure(5, f"GHCR did not return a valid image index for {reference}")
    return fields[1]


def published_version_tags(engine, digests):
    pending = dict(digests)
    versions = {}
    page = 1
    while pending:
        request = urllib.request.Request(
            f"{RELEASES_API}?per_page={RELEASE_PAGE_SIZE}&page={page}",
            headers={"Accept": "application/vnd.github+json"},
        )
        try:
            with urllib.request.urlopen(
                request, timeout=engine.remaining()
            ) as response:
                releases = json.load(response)
        except (OSError, ValueError) as error:
            raise Failure(
                5,
                "cannot read published CI image releases. Check HTTPS access to api.github.com.",
            ) from error
        if not isinstance(releases, list) or any(
            not isinstance(record, dict) for record in releases
        ):
            raise Failure(5, "GitHub returned invalid CI image release records")
        for release in releases:
            tag = release.get("tag_name")
            body = release.get("body")
            if (
                release.get("draft") is not False
                or release.get("prerelease") is not False
                or not isinstance(tag, str)
                or not tag.startswith("v")
                or not VERSION.fullmatch(tag[1:])
                or not isinstance(body, str)
            ):
                continue
            rows = {line.strip() for line in body.splitlines()}
            for repository, digest in tuple(pending.items()):
                reference = f"{repository}:{tag[1:]}"
                # The release workflow records each versioned reference and index digest.
                if f"| {reference} | {digest} |" in rows:
                    versions[repository] = reference
                    del pending[repository]
        if len(releases) < RELEASE_PAGE_SIZE:
            break
        page += 1
    if pending:
        missing = ", ".join(
            f"{repo}@{digest}" for repo, digest in sorted(pending.items())
        )
        raise Failure(5, f"no published numeric release found for {missing}")
    return versions


def local_image_id(engine, reference, platform, *, allow_missing=False):
    try:
        item = engine.inspect("images", reference)
    except APIError as error:
        if allow_missing and error.status == 404:
            return None
        raise
    identifier = item.get("Id") if isinstance(item, dict) else None
    if not isinstance(identifier, str) or not IMAGE_ID.fullmatch(identifier):
        raise Failure(5, f"cannot verify the local image for {reference}")
    if f"{item.get('Os')}/{item.get('Architecture')}" != platform:
        raise Failure(
            5, f"local image {reference} does not match daemon platform {platform}"
        )
    return identifier


def refresh_images(inventory, report):
    engine = inventory.engine
    inventory.refresh("images")
    repositories = set()
    for item in inventory.objects["images"]:
        for field, separator in (("RepoTags", ":"), ("RepoDigests", "@")):
            aliases = item.get(field)
            if aliases is None:
                continue
            if not isinstance(aliases, list) or any(
                not isinstance(ref, str) for ref in aliases
            ):
                raise Failure(5, "cannot establish local image aliases")
            for reference in aliases:
                repository, _, _ = reference.rpartition(separator)
                if repository in REPOSITORIES:
                    repositories.add(repository)
    report.counts["repositories.matched"] = len(repositories)

    digests = {
        repository: registry_index_digest(engine, f"{repository}:latest")
        for repository in sorted(repositories)
    }
    versions = published_version_tags(engine, digests)
    daemon_id = inventory.policy["expected_daemon_id"]
    refreshed = {}
    for repository, digest in digests.items():
        latest = f"{repository}:latest"
        reference = versions[repository]
        pinned = f"{repository}@{digest}"
        if registry_index_digest(engine, reference) != digest:
            raise Failure(5, f"{reference} does not match its published image index")

        engine.preflight(daemon_id)
        platform = f"{engine.version.get('Os')}/{engine.version.get('Arch')}"
        if platform not in ("linux/amd64", "linux/arm64"):
            raise Failure(2, f"unsupported Docker daemon platform: {platform}")
        engine.mutation_started = True
        pull_image(engine, pinned, platform)
        if registry_index_digest(engine, latest) != digest:
            raise Failure(5, f"{latest} changed during refresh")

        engine.preflight(daemon_id)
        identifier = local_image_id(engine, pinned, platform)
        existing = local_image_id(engine, reference, platform, allow_missing=True)
        if existing is not None and existing != identifier:
            raise Failure(5, f"local tag {reference} points to a different image")
        if existing is None:
            tag_image(engine, pinned, reference)
        tag_image(engine, pinned, latest)
        if (
            local_image_id(engine, reference, platform) != identifier
            or local_image_id(engine, latest, platform) != identifier
        ):
            raise Failure(5, f"cannot verify refreshed tags {reference} and {latest}")
        refreshed[repository] = identifier
        report.action(
            "pulled", "images", reference, source=latest, digest=digest, image_id=identifier
        )
    return refreshed


def arguments(argv):
    parser = Parser(
        prog="ci-upgrade-images",
        description="Refresh cached MyFlow CI images and keep their verified version tags.",
    )
    parser.add_argument(
        "--prune-old-versions",
        action="store_true",
        help="Retire eligible old versions after all refreshes are verified. Drain runner jobs first.",
    )
    parser.add_argument("--config", help="optional JSON policy with image protections")
    parser.add_argument(
        "--endpoint", help=f"Docker socket (default: {DEFAULT_ENDPOINT})"
    )
    parser.add_argument("--expected-daemon-id")
    return parser.parse_args(argv)


def interrupted(signum, frame):
    raise Failure(
        6, "Image maintenance interrupted. Check runner images before retrying."
    )


def main(argv=None):
    report = Report()
    code, engine, old_signals = 0, None, {}
    try:
        args = arguments(argv)
        report.context = {
            "mode": "apply",
            "profile": PROFILE,
        }
        overrides = {
            key: value
            for key in ("endpoint", "expected_daemon_id")
            if (value := getattr(args, key)) is not None
        }
        if args.config is None:
            policy = configuration(
                {"endpoint": DEFAULT_ENDPOINT}, os.environ, overrides
            )
        else:
            policy = load_policy(args.config, os.environ, overrides)
        for signum in (signal.SIGTERM, signal.SIGINT):
            old_signals[signum] = signal.signal(signum, interrupted)
        engine = Engine(
            policy["endpoint"],
            duration(policy["timeouts"]["operation"]),
            duration(policy["timeouts"]["run"]),
        )
        info = engine.preflight(policy["expected_daemon_id"])
        report.context["daemon_id"] = info["ID"]
        policy["expected_daemon_id"] = info["ID"]
        inventory = Inventory(engine, policy, report)
        refreshed = refresh_images(inventory, report)
        if args.prune_old_versions and refreshed:
            remove_versions(
                inventory,
                None,
                True,
                partial(engine.preflight, info["ID"]),
                report,
                refreshed=refreshed,
            )
    except (InvalidPolicy, Failure) as error:
        code = error.code if isinstance(error, Failure) else 2
        report.emit("error", message=str(error), exit_code=code)
        print(json.dumps(str(error)), file=sys.stderr)
    finally:
        for signum, handler in old_signals.items():
            signal.signal(signum, handler)
    report.finish(code, engine is not None and engine.mutation_started)
    return code
