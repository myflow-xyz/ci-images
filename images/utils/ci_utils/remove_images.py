"""Retire explicit local suite tags under the existing host maintenance lease."""

import hashlib
import json
import os
import re
import signal
import sys

from .cleanup import (
    Inventory,
    Parser,
    Report,
    build_metadata,
    check_environment,
    interrupted,
    load_policy,
)
from .engine import APIError, Engine, Failure
from .guard import LeaseGuard
from .policy import IMAGE_ID, InvalidPolicy, duration, image_safety

PROFILE = "remove-images"
REPOSITORIES = tuple(
    "ghcr.io/myflow-xyz/ci-" + name
    for name in (
        "base",
        "go",
        "node",
        "vite",
        "playwright",
        "postgres",
        "utils",
        "net",
    )
)


def versions(value):
    selected = [part.strip() for part in value.split(",")]
    if any(
        not re.fullmatch(
            r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", part
        )
        for part in selected
    ):
        raise InvalidPolicy(
            "versions must be comma-separated numeric X.Y.Z values"
        )
    return sorted(set(selected))


def scope_hash(policy, selected):
    # A lease for routine cleanup or different versions cannot authorize this run.
    scope = {"operation": PROFILE, "versions": selected, "policy": policy}
    return hashlib.sha256(
        json.dumps(scope, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def container_images(inventory):
    inventory.refresh("containers")
    result = set()
    for item in inventory.objects["containers"]:
        identifier = item.get("Image")
        if not isinstance(identifier, str) or not IMAGE_ID.fullmatch(
            identifier
        ):
            raise Failure(5, "cannot establish container image reference")
        result.add(identifier)
    return result


def remove_versions(inventory, selected, apply, guard, report):
    engine = inventory.engine
    wanted = {
        f"{repository}:{prefix}{version}": version
        for repository in REPOSITORIES
        for version in selected
        for prefix in ("", "v")
    }
    inventory.refresh("images")
    referenced = container_images(inventory)
    inventory.resolve_protections()
    matches = {}
    for item in inventory.objects["images"]:
        tags = item.get("RepoTags")
        if tags is not None and (
            not isinstance(tags, list)
            or any(not isinstance(tag, str) for tag in tags)
        ):
            raise Failure(5, "cannot establish image tags")
        for tag in tags or []:
            if tag in wanted:
                if tag in matches:
                    raise Failure(
                        5, "image reference has conflicting identities"
                    )
                matches[tag] = item
    report.counts["images.matched"] = len(matches)
    found = {wanted[reference] for reference in matches}
    for version in selected:
        if version not in found:
            report.action("not-found", "versions", version)
    for reference, initial in sorted(matches.items()):
        item = initial
        if apply:
            guard.check()
            engine.preflight(inventory.policy["expected_daemon_id"])
            referenced = container_images(inventory)
            inventory.resolve_protections()
            try:
                item = engine.inspect("images", reference)
            except APIError as error:
                if error.status != 404:
                    raise
                report.action(
                    "skipped", "images", reference, reason="disappeared"
                )
                continue
            if not isinstance(item, dict) or item.get("Id") != initial["Id"]:
                report.action(
                    "skipped", "images", reference, reason="reference-changed"
                )
                continue
        choice = image_safety(
            item, inventory.policy, referenced, inventory.protected_images
        )
        if not choice.eligible:
            report.action("skipped", "images", reference, reason=choice.reason)
            continue
        if reference not in (item["RepoTags"] or []):
            report.action(
                "skipped", "images", reference, reason="reference-changed"
            )
            continue
        if not apply:
            report.action(
                "would-remove", "images", reference, image_id=item["Id"]
            )
            continue
        try:
            reply = engine.remove("images", reference, guard.check)
            if (
                not isinstance(reply, list)
                or not reply
                or any(
                    not isinstance(entry, dict)
                    or not entry
                    or any(
                        key not in ("Deleted", "Untagged")
                        or not isinstance(value, str)
                        for key, value in entry.items()
                    )
                    for entry in reply
                )
                or not any(
                    entry.get("Untagged") == reference for entry in reply
                )
            ):
                raise Failure(
                    6,
                    "image removal reply is indeterminate; reconciliation is required",
                )
        except APIError as error:
            if error.status in (404, 409):
                report.action(
                    "skipped",
                    "images",
                    reference,
                    reason="disappeared"
                    if error.status == 404
                    else "reference-or-state-conflict",
                    http_status=error.status,
                )
                continue
            report.action(
                "failed", "images", reference, http_status=error.status
            )
            raise
        except Failure as error:
            report.action("failed", "images", reference, reason=str(error))
            raise
        report.action("removed", "images", reference, image_id=item["Id"])


def arguments(argv):
    parser = Parser(
        prog="ci-remove-images",
        description="Remove exact local MyFlow CI suite tags. Defaults to dry-run.",
    )
    parser.add_argument(
        "--versions",
        required=True,
        help="numeric X.Y.Z values, separated by commas",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="remove eligible tags; requires a host maintenance lease",
    )
    parser.add_argument("--config", default="/etc/ci-utils/cleanup.json")
    parser.add_argument("--endpoint")
    parser.add_argument("--expected-daemon-id")
    parser.add_argument("--run-id")
    parser.add_argument("--lease-socket")
    return parser.parse_args(argv)


def main(argv=None):
    report = Report()
    code, engine, old_signals = 0, None, {}
    try:
        args = arguments(argv)
        selected = versions(args.versions)
        if args.run_id is not None:
            if not re.fullmatch(r"[a-f0-9]{32}", args.run_id):
                raise InvalidPolicy("run-id must be the host lease identifier")
            report.run_id = args.run_id
        report.context = {
            "mode": "apply" if args.apply else "plan",
            "profile": PROFILE,
            "versions": selected,
            **build_metadata(),
            "image_digest": os.environ.get("CI_UTILS_IMAGE_DIGEST"),
        }
        policy = load_policy(
            args.config,
            os.environ,
            {
                key: value
                for key in ("endpoint", "expected_daemon_id")
                if (value := getattr(args, key)) is not None
            },
        )
        check_environment()
        if args.apply and not policy["expected_daemon_id"]:
            raise InvalidPolicy("apply requires expected_daemon_id")
        report.context["policy_hash"] = scope_hash(policy, selected)
        for signum in (signal.SIGTERM, signal.SIGINT):
            old_signals[signum] = signal.signal(signum, interrupted)
        engine = Engine(
            policy["endpoint"],
            duration(policy["timeouts"]["operation"]),
            duration(policy["timeouts"]["run"]),
        )
        info = engine.preflight(policy["expected_daemon_id"])
        report.context["daemon_id"] = info["ID"]
        guard = LeaseGuard(
            engine,
            args.lease_socket,
            args.run_id,
            info["ID"],
            report.context["policy_hash"],
            PROFILE,
            report.context["image_digest"],
        )
        if args.apply:
            guard.check()
        remove_versions(
            Inventory(engine, policy, report),
            selected,
            args.apply,
            guard,
            report,
        )
        if args.apply:
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
