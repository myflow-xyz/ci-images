"""One-shot cleanup command."""

import argparse
import collections
import copy
import datetime as dt
import hashlib
import json
import os
import pathlib
import signal
import sys
import time
import uuid

from .engine import APIError, Engine, Failure
from .policy import (
    IMAGE_ID,
    OBJECT_ID,
    Decision,
    InvalidPolicy,
    configuration,
    container_decision,
    duration,
    image_decision,
    network_decision,
)


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidPolicy("duplicate JSON setting")
        result[key] = value
    return result


def reject_constant(value):
    raise InvalidPolicy("nonfinite JSON values are not permitted")


def load_policy(path, environ, overrides):
    try:
        with open(path, "rb") as handle:
            data = handle.read(65537)
        if len(data) > 65536:
            raise InvalidPolicy("policy exceeds 64 KiB")
        value = json.loads(
            data, object_pairs_hook=strict_object, parse_constant=reject_constant
        )
    except (OSError, ValueError, UnicodeError) as error:
        raise InvalidPolicy("cannot read a valid JSON policy") from error
    return configuration(value, environ, overrides)


def build_metadata():
    try:
        value = json.loads(
            pathlib.Path("/opt/ci-tools/ci-utils/build.json").read_text()
        )
        return {
            key: str(value.get(key, "unknown"))[:128] for key in ("revision", "version")
        }
    except (OSError, ValueError, AttributeError):
        return {"revision": "unbuilt", "version": "unbuilt"}


class Report:
    def __init__(self):
        self.run_id = str(uuid.uuid4())
        self.started = time.monotonic()
        self.context = {}
        self.counts = collections.Counter()
        self.details = collections.Counter()

    def emit(self, event, **fields):
        record = {
            "event": event,
            "run_id": self.run_id,
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            **self.context,
            **fields,
        }
        print(
            json.dumps(record, sort_keys=True, ensure_ascii=True, allow_nan=False),
            flush=True,
        )

    def decision(self, kind, item, decision, dependent=False):
        outcome = "candidate" if decision.eligible else "excluded"
        if dependent:
            outcome = "dependent-candidate"
        self.counts[f"{kind}.{outcome}"] += 1
        self.counts[f"reasons.{decision.reason}"] += 1
        if self.details[kind] < 200:
            self.emit(
                "decision",
                kind=kind,
                id=item["Id"],
                outcome=outcome,
                reason=decision.reason,
            )
            self.details[kind] += 1

    def finish(self, code):
        self.emit(
            "result",
            status={0: "success", 4: "skipped", 6: "reconciliation-required"}.get(
                code, "failed"
            ),
            exit_code=code,
            counts=dict(self.counts),
            duration_seconds=round(time.monotonic() - self.started, 6),
            detail_limit_per_kind=200,
        )


class Inventory:
    def __init__(self, engine, policy, report):
        self.engine = engine
        self.policy = policy
        self.report = report
        self.protected_images = set(policy["protected"]["image_ids"])
        self.objects = {}

    def load(self):
        for kind, path in (
            ("containers", "/containers/json?all=true"),
            ("networks", "/networks"),
            ("images", "/images/json?all=true"),
        ):
            records = self.engine.get(path)
            if not isinstance(records, list):
                raise Failure(5, f"cannot establish {kind} inventory")
            identifiers = set()
            for record in records:
                identifier = record.get("Id") if isinstance(record, dict) else None
                pattern = IMAGE_ID if kind == "images" else OBJECT_ID
                if not isinstance(identifier, str) or not pattern.fullmatch(identifier):
                    raise Failure(5, f"cannot establish {kind} identity")
                identifiers.add(identifier)
            self.objects[kind] = []
            for identifier in sorted(identifiers):
                try:
                    item = self.engine.inspect(kind, identifier)
                except APIError as error:
                    if error.status == 404:
                        self.report.emit(
                            "skip", kind=kind, id=identifier, reason="disappeared"
                        )
                        continue
                    raise
                if not isinstance(item, dict) or item.get("Id") != identifier:
                    raise Failure(5, f"cannot establish {kind} metadata")
                self.objects[kind].append(item)
        self.references()
        for reference in self.policy["protected"]["image_references"]:
            try:
                item = self.engine.inspect("images", reference)
            except APIError as error:
                if error.status == 404:
                    self.report.emit("protection", reference=reference, status="absent")
                    continue
                raise
            identifier = item.get("Id") if isinstance(item, dict) else None
            if not isinstance(identifier, str) or not IMAGE_ID.fullmatch(identifier):
                raise Failure(2, "cannot establish protected image identity")
            self.protected_images.add(identifier)

    def references(self, exclude=()):
        image_ids, network_ids = set(), set()
        for item in self.objects["containers"]:
            if item["Id"] in exclude:
                continue
            identifier = item.get("Image")
            settings = item.get("NetworkSettings")
            networks = settings.get("Networks") if isinstance(settings, dict) else None
            if (
                not isinstance(identifier, str)
                or not IMAGE_ID.fullmatch(identifier)
                or not isinstance(networks, dict)
            ):
                raise Failure(5, "cannot establish container image/network references")
            image_ids.add(identifier)
            for network in networks.values():
                if not isinstance(network, dict):
                    raise Failure(5, "cannot establish container network references")
                # A created but never attached container can have an empty NetworkID.
                network_id = network.get("NetworkID")
                if network_id:
                    if not isinstance(network_id, str) or not OBJECT_ID.fullmatch(
                        network_id
                    ):
                        raise Failure(5, "invalid container network reference")
                    network_ids.add(network_id)
                elif network_id is None:
                    raise Failure(5, "cannot establish container network identity")
        return image_ids, network_ids


def accounting(engine):
    try:
        data = engine.get("/system/df")
        size = data.get("LayersSize") if isinstance(data, dict) else None
        if type(size) is not int or size < 0:
            return None
        volumes = data.get("Volumes")
        return {
            "image_layer_bytes": size,
            "volume_count": len(volumes) if isinstance(volumes, list) else None,
        }
    except Failure as error:
        if error.code == 6:
            raise
        return None


def image_profile(item, policy, profile):
    tagged = bool(item.get("RepoTags"))
    if tagged and (profile != "weekly" or policy["tagged_image_trigger"] == "disabled"):
        return Decision(False, "tagged-image-profile-disabled")
    if tagged and policy["tagged_image_trigger"] == "pressure":
        return Decision(False, "pressure-observation-unavailable")
    return None


def plan(inventory, now, profile, report):
    policy = inventory.policy
    removable_containers = set()
    for item in inventory.objects["containers"]:
        inventory.engine.remaining()
        choice = container_decision(item, policy, now)
        report.decision("containers", item, choice)
        if choice.eligible:
            removable_containers.add(item["Id"])
    image_refs, network_refs = inventory.references()
    later_image_refs, later_network_refs = inventory.references(removable_containers)
    for item in inventory.objects["networks"]:
        inventory.engine.remaining()
        choice = network_decision(item, policy, now, network_refs)
        after = copy.deepcopy(item)
        if isinstance(after.get("Containers"), dict):
            after["Containers"] = {
                key: value
                for key, value in after["Containers"].items()
                if key not in removable_containers
            }
        later = network_decision(after, policy, now, later_network_refs)
        report.decision(
            "networks", item, choice, dependent=not choice.eligible and later.eligible
        )
    for item in inventory.objects["images"]:
        inventory.engine.remaining()
        disabled = image_profile(item, policy, profile)
        choice = image_decision(
            item, policy, now, image_refs, inventory.protected_images
        )
        later = image_decision(
            item, policy, now, later_image_refs, inventory.protected_images
        )
        if disabled:
            choice = disabled if choice.eligible else choice
            later = disabled if later.eligible else later
        report.decision(
            "images", item, choice, dependent=not choice.eligible and later.eligible
        )
    report.emit(
        "plan_limitations",
        snapshot_only=True,
        revalidation_required=True,
        exact_reclaimed_bytes=None,
        volumes="report-only",
    )


def arguments(argv):
    parser = argparse.ArgumentParser(
        prog="ci-docker-cleanup",
        description="Inspect and maintain explicitly owned CI resources.",
    )
    parser.add_argument(
        "operation",
        nargs="?",
        default="plan",
        choices=("check", "plan", "apply", "version"),
    )
    parser.add_argument("--config", default="/etc/ci-utils/cleanup.json")
    parser.add_argument("--profile", choices=("daily", "weekly"), default="daily")
    parser.add_argument("--endpoint")
    parser.add_argument("--expected-daemon-id")
    for name in (
        "container-min-age",
        "network-min-age",
        "dangling-image-min-age",
        "tagged-image-min-age",
    ):
        parser.add_argument("--" + name)
    return parser.parse_args(argv)


def interrupted(signum, frame):
    raise Failure(
        6, "cleanup interrupted; reconcile daemon completion before reopening admission"
    )


def main(argv=None):
    report = Report()
    code = 0
    old_signals = {}
    try:
        args = arguments(argv)
        if args.operation == "version":
            report.emit("version", **build_metadata(), policy_schema=1)
            return 0
        report.context = {
            "mode": args.operation,
            "profile": args.profile,
            **build_metadata(),
            "image_digest": os.environ.get("CI_UTILS_IMAGE_DIGEST"),
        }
        overrides = {
            key: value
            for key, value in vars(args).items()
            if value is not None and key not in ("operation", "config", "profile")
        }
        policy = load_policy(args.config, os.environ, overrides)
        for key in (
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_API_VERSION",
            "DOCKER_CONFIG",
            "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH",
            "BUILDX_BUILDER",
            "BUILDX_CONFIG",
        ):
            if os.environ.get(key):
                raise InvalidPolicy(
                    f"inherited {key} conflicts with explicit maintenance configuration"
                )
        if args.operation == "apply" and not policy["expected_daemon_id"]:
            raise InvalidPolicy("apply requires expected_daemon_id")
        policy_hash = hashlib.sha256(
            json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        report.context["policy_hash"] = policy_hash
        now = dt.datetime.now(dt.timezone.utc)
        report.emit("policy", effective=policy, cutoff_timestamp=now.isoformat())
        for signum in (signal.SIGTERM, signal.SIGINT):
            old_signals[signum] = signal.signal(signum, interrupted)
        engine = Engine(
            policy["endpoint"],
            duration(policy["timeouts"]["operation"]),
            duration(policy["timeouts"]["run"]),
        )
        info = engine.preflight(policy["expected_daemon_id"])
        report.context["daemon_id"] = info["ID"]
        report.emit(
            "daemon",
            server_version=engine.version["Version"],
            server_api=engine.version["ApiVersion"],
            client_api="1.48",
        )
        if args.operation == "apply":
            raise Failure(4, "apply requires the trusted host integration")
        if policy["cache"]["mode"] != "off":
            raise Failure(
                2, "the configured cache adapter is unavailable in this build"
            )
        report.emit("cache", builder="default", mode="off", status="unmanaged")
        inventory = Inventory(engine, policy, report)
        inventory.load()
        report.emit(
            "observations",
            docker=accounting(engine),
            filesystems=None,
            cache=None,
            reclaimed_bytes=None,
        )
        if args.operation == "plan":
            plan(inventory, now, args.profile, report)
    except InvalidPolicy as error:
        code = 2
        report.emit("error", message=str(error), exit_code=code)
        print(json.dumps(str(error)), file=sys.stderr)
    except Failure as error:
        code = error.code
        report.emit("error", message=str(error), exit_code=code)
        print(json.dumps(str(error)), file=sys.stderr)
    finally:
        for signum, handler in old_signals.items():
            signal.signal(signum, handler)
    report.finish(code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
