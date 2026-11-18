"""Refresh cached CI repositories and optionally retire old release tags."""

import json
import os
import signal
import subprocess
import sys
import time
from functools import partial

from .cleanup import Inventory, Parser, Report, load_policy
from .engine import Engine, Failure
from .policy import IMAGE_ID, InvalidPolicy, configuration, duration
from .remove_images import CI_REPOSITORY, remove_versions

PROFILE = "upgrade-images"
DEFAULT_ENDPOINT = "unix:///var/run/docker.sock"


def pull_image(engine, reference):
    env = dict(os.environ)
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
                "docker",
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
                if CI_REPOSITORY.fullmatch(repository):
                    repositories.add(repository)
    report.counts["repositories.matched"] = len(repositories)

    refreshed = {}
    daemon_id = inventory.policy["expected_daemon_id"]
    for repository in sorted(repositories):
        reference = f"{repository}:latest"
        engine.preflight(daemon_id)
        engine.mutation_started = True
        pull_image(engine, reference)
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


def arguments(argv):
    parser = Parser(
        prog="ci-upgrade-images",
        description="Pull :latest for cached MyFlow CI images. Keep old versions by default.",
    )
    parser.add_argument(
        "--prune-old-versions",
        action="store_true",
        help="Retire eligible old versions after all :latest pulls succeed. Drain runner jobs first.",
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
