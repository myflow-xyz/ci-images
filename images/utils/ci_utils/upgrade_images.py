"""Refresh cached CI repositories and optionally retire old release tags."""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time

from .cleanup import Inventory, Parser, Report, interrupted, load_policy, strict_object
from .engine import Engine, Failure
from .guard import LeaseGuard
from .policy import IMAGE_ID, InvalidPolicy, duration
from .remove_images import CI_REPOSITORY, remove_versions, scope_hash

PROFILE = "upgrade-images"


def pull_image(engine, reference, docker_cli="docker", environment=None):
    env = dict(os.environ if environment is None else environment)
    for key in (
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
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
                docker_cli,
                "--config",
                config,
                "--host",
                engine.endpoint,
                "image",
                "pull",
                reference,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            timeout=timeout,
            check=False,
        )
    except OSError as error:
        raise Failure(
            5, "unable to start the Docker client for image refresh"
        ) from error
    except subprocess.TimeoutExpired as error:
        raise Failure(6, f"Docker pull timed out for {reference}") from error
    if result.returncode < 0:
        raise Failure(6, f"Docker pull was interrupted for {reference}")
    if result.returncode:
        raise Failure(
            5,
            f"Docker pull failed for {reference}. Check GHCR access and connectivity.",
        )


def refresh_images(
    inventory, report, *, docker_cli="docker", environment=None, guard=None
):
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
                if CI_REPOSITORY.fullmatch(repository):
                    repositories.add(repository)
    report.counts["repositories.matched"] = len(repositories)

    refreshed = {}
    daemon_id = report.context["daemon_id"]
    for repository in sorted(repositories):
        reference = f"{repository}:latest"
        engine.preflight(daemon_id)
        if guard is not None:
            guard.check()
        engine.mutation_started = True
        pull_image(engine, reference, docker_cli, environment)
        engine.preflight(daemon_id)
        item = engine.inspect("images", reference)
        identifier = item.get("Id") if isinstance(item, dict) else None
        tags = item.get("RepoTags") if isinstance(item, dict) else None
        if (
            not isinstance(identifier, str)
            or not IMAGE_ID.fullmatch(identifier)
            or not isinstance(tags, list)
            or reference not in tags
        ):
            raise Failure(5, f"cannot verify the image pulled for {reference}")
        refreshed[repository] = identifier
        report.action("pulled", "images", reference, image_id=identifier)
    return refreshed


def refreshed_images(path):
    try:
        with open(path, "rb") as handle:
            data = handle.read(65537)
        if len(data) > 65536:
            raise ValueError("snapshot size")
        images = json.loads(data, object_pairs_hook=strict_object)
        if not isinstance(images, dict) or any(
            not CI_REPOSITORY.fullmatch(repo)
            or not isinstance(identifier, str)
            or not IMAGE_ID.fullmatch(identifier)
            for repo, identifier in images.items()
        ):
            raise ValueError("snapshot shape")
        return images
    except (OSError, ValueError) as error:
        raise InvalidPolicy("cannot read a valid refreshed image snapshot") from error


def arguments(argv):
    parser = Parser(
        prog="ci-upgrade-images",
        description="Pull :latest for cached MyFlow CI images. Keep old versions by default.",
    )
    parser.add_argument(
        "--prune-old-versions",
        action="store_true",
        help="retire eligible old versions after a successful pull using the host adapter",
    )
    parser.add_argument("--config", default="/etc/ci-utils/cleanup.json")
    parser.add_argument("--endpoint")
    parser.add_argument("--expected-daemon-id")
    parser.add_argument("--run-id")
    parser.add_argument("--lease-socket")
    parser.add_argument("--refreshed-images", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv=None):
    report = Report()
    code, engine, old_signals = 0, None, {}
    try:
        args = arguments(argv)
        if args.run_id is not None:
            if not re.fullmatch(r"[a-f0-9]{32}", args.run_id):
                raise InvalidPolicy("run-id must be the host lease identifier")
            report.run_id = args.run_id
        report.context = {
            "mode": "apply",
            "profile": PROFILE,
            "image_digest": os.environ.get("CI_UTILS_IMAGE_DIGEST"),
        }
        if args.refreshed_images and not args.prune_old_versions:
            raise InvalidPolicy(
                "a refreshed image snapshot requires --prune-old-versions"
            )
        refreshed = (
            refreshed_images(args.refreshed_images) if args.refreshed_images else None
        )
        policy = load_policy(
            args.config,
            os.environ,
            {
                key: value
                for key in ("endpoint", "expected_daemon_id")
                if (value := getattr(args, key)) is not None
            },
        )
        if args.prune_old_versions and not policy["expected_daemon_id"]:
            raise InvalidPolicy("retirement requires expected_daemon_id")
        policy_hash = scope_hash(policy, refreshed, profile=PROFILE)
        report.context["policy_hash"] = policy_hash
        for signum in (signal.SIGTERM, signal.SIGINT):
            old_signals[signum] = signal.signal(signum, interrupted)
        engine = Engine(
            policy["endpoint"],
            duration(policy["timeouts"]["operation"]),
            duration(policy["timeouts"]["run"]),
        )
        info = engine.preflight(policy["expected_daemon_id"])
        report.context["daemon_id"] = info["ID"]
        inventory = Inventory(engine, policy, report)
        guard = None
        if args.prune_old_versions:
            guard = LeaseGuard(
                engine,
                args.lease_socket,
                args.run_id,
                info["ID"],
                policy_hash,
                PROFILE,
                report.context["image_digest"],
            )
            guard.check()
        if refreshed is None:
            refreshed = refresh_images(inventory, report, guard=guard)
        if args.prune_old_versions:
            remove_versions(inventory, None, True, guard, report, refreshed=refreshed)
            guard.check()
    except (InvalidPolicy, Failure) as error:
        code = error.code if isinstance(error, Failure) else 2
        report.emit("error", message=str(error), exit_code=code)
        print(json.dumps(str(error)), file=sys.stderr)
    finally:
        for signum, handler in old_signals.items():
            signal.signal(signum, handler)
    report.finish(code, engine is not None and engine.mutation_started)
    return code
