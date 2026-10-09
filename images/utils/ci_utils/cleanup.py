"""One-shot cleanup command."""

import argparse
import collections
import copy
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import signal
import sys
import time
import uuid

from . import storage
from .cache import BuildCache
from .engine import APIError, Engine, Failure
from .guard import LeaseGuard
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

    def action(self, event, kind, identifier, **fields):
        self.counts[f"{kind}.{event}"] += 1
        if "reason" in fields:
            self.counts[f"reasons.{fields['reason']}"] += 1
        if self.details[kind] < 200:
            self.emit(event, kind=kind, id=identifier, **fields)
            self.details[kind] += 1

    def finish(self, code, mutation_started=False):
        self.emit(
            "result",
            status={
                0: "success",
                4: "skipped",
                5: "partial-failure",
                6: "reconciliation-required",
            }.get(code, "failed"),
            exit_code=code,
            mutation_started=mutation_started,
            completion_known=code != 6,
            counts=dict(self.counts),
            duration_seconds=round(time.monotonic() - self.started, 6),
            detail_limit_per_kind=200,
        )


class Inventory:
    def __init__(self, engine, policy, report, observation=None):
        self.engine = engine
        self.policy = policy
        self.report = report
        self.protected_images = set(policy["protected"]["image_ids"])
        self.objects = {}
        self.observation = observation

    def pressure(self):
        return storage.evaluate(
            self.observation,
            self.policy,
            self.report.context["daemon_id"],
            self.report.run_id,
            dt.datetime.now(dt.timezone.utc),
        )

    def load(self):
        for kind in ("containers", "networks", "images"):
            self.refresh(kind)
        self.references()
        self.resolve_protections()

    def refresh(self, kind):
        path = {
            "containers": "/containers/json?all=true",
            "networks": "/networks",
            "images": "/images/json?all=true",
        }[kind]
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
            item = self.inspect(kind, identifier)
            if item is not None:
                self.objects[kind].append(item)

    def inspect(self, kind, identifier):
        try:
            item = self.engine.inspect(kind, identifier)
        except APIError as error:
            if error.status == 404:
                self.report.action(
                    "skip", kind, identifier, reason="disappeared", http_status=404
                )
                return None
            raise
        if not isinstance(item, dict) or item.get("Id") != identifier:
            raise Failure(5, f"cannot establish {kind} metadata")
        return item

    def resolve_protections(self):
        for reference in self.policy["protected"]["image_references"]:
            try:
                item = self.engine.inspect("images", reference)
            except APIError as error:
                if error.status == 404:
                    if self.report.details["protection"] < 200:
                        self.report.emit(
                            "protection", reference=reference, status="absent"
                        )
                        self.report.details["protection"] += 1
                    continue
                raise
            identifier = item.get("Id") if isinstance(item, dict) else None
            if not isinstance(identifier, str) or not IMAGE_ID.fullmatch(identifier):
                raise Failure(2, "cannot establish protected image identity")
            self.protected_images.add(identifier)

    def references(self, exclude=()):
        image_ids, network_ids = set(), set()

        def reserve_network(reference):
            if not isinstance(reference, str):
                raise Failure(5, "cannot establish container network reservation")
            if not reference or reference.startswith("container:"):
                return
            if reference == "default":
                reference = "bridge"
            # Before an endpoint exists, Docker retains only a name or ID prefix.
            # Duplicate names reserve every matching network conservatively.
            for network in self.objects["networks"]:
                if network.get("Name") == reference or network["Id"].startswith(
                    reference
                ):
                    network_ids.add(network["Id"])

        for item in self.objects["containers"]:
            if item["Id"] in exclude:
                continue
            identifier = item.get("Image")
            settings = item.get("NetworkSettings")
            networks = settings.get("Networks") if isinstance(settings, dict) else None
            host = item.get("HostConfig")
            if (
                not isinstance(identifier, str)
                or not IMAGE_ID.fullmatch(identifier)
                or not isinstance(networks, dict)
                or not isinstance(host, dict)
                or not isinstance(host.get("NetworkMode"), str)
            ):
                raise Failure(5, "cannot establish container image/network references")
            image_ids.add(identifier)
            reserve_network(host["NetworkMode"])
            for name, network in networks.items():
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
                elif network_id == "":
                    reserve_network(name)
                else:
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


def is_tagged(item):
    tags = item.get("RepoTags")
    # Unknown aliases must reach the policy's exclusion path without crashing.
    return tags is not None and (
        not isinstance(tags, list) or any(tag != "<none>:<none>" for tag in tags)
    )


def image_profile(item, policy, profile, pressure):
    tagged = is_tagged(item)
    if tagged and (profile != "weekly" or policy["tagged_image_trigger"] == "disabled"):
        return Decision(False, "tagged-image-profile-disabled")
    if tagged and policy["tagged_image_trigger"] == "pressure":
        if pressure["pressured"] is None:
            return Decision(False, "pressure-observation-unavailable")
        if not pressure["pressured"]:
            return Decision(False, "below-pressure-threshold")
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
        disabled = image_profile(item, policy, profile, inventory.pressure())
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


def apply(inventory, cache, guard, now, profile, report):
    policy = inventory.policy
    engine = inventory.engine
    for stage, kind in (
        ("containers", "containers"),
        ("networks", "networks"),
        ("dangling-images", "images"),
        ("cache", None),
        ("tagged-images", "images"),
    ):
        started = time.monotonic()
        completed = False
        try:
            guard.check()
            engine.preflight(policy["expected_daemon_id"])
            if kind is None:
                cache.prune(now, guard.check)
            else:
                inventory.load()
                for initial in inventory.objects[kind]:
                    engine.remaining()
                    if kind == "images" and is_tagged(initial) != (
                        stage == "tagged-images"
                    ):
                        continue
                    guard.check()
                    if kind != "containers":
                        inventory.refresh("containers")
                    if kind == "images":
                        inventory.resolve_protections()
                    item = inventory.inspect(kind, initial["Id"])
                    if item is None:
                        continue
                    if kind == "containers":
                        choice = container_decision(item, policy, now)
                    else:
                        image_refs, network_refs = inventory.references()
                        if kind == "networks":
                            choice = network_decision(item, policy, now, network_refs)
                        else:
                            choice = image_decision(
                                item,
                                policy,
                                now,
                                image_refs,
                                inventory.protected_images,
                            )
                            if choice.eligible:
                                disabled = image_profile(
                                    item, policy, profile, inventory.pressure()
                                )
                                if disabled:
                                    choice = disabled
                                elif is_tagged(item) != (stage == "tagged-images"):
                                    choice = Decision(False, "image-stage-changed")
                                elif len(item.get("RepoTags") or []) > 1:
                                    choice = Decision(
                                        False, "multi-tag-image-unsupported"
                                    )
                    report.decision(kind, item, choice)
                    if not choice.eligible:
                        continue
                    try:
                        reply = engine.remove(kind, item["Id"], guard.check)
                    except APIError as error:
                        if error.status not in (404, 409):
                            raise
                        report.action(
                            "skip",
                            kind,
                            item["Id"],
                            reason="disappeared"
                            if error.status == 404
                            else "reference-or-state-conflict",
                            http_status=error.status,
                        )
                        continue
                    if kind == "images" and (
                        not isinstance(reply, list)
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
                    ):
                        raise Failure(
                            6,
                            "image removal reply is indeterminate; reconciliation is required",
                        )
                    report.action("removed", kind, item["Id"])
            completed = True
        finally:
            report.emit(
                "stage",
                stage=stage,
                completed=completed,
                duration_seconds=round(time.monotonic() - started, 6),
            )


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise InvalidPolicy(message)


def arguments(argv):
    parser = Parser(
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
    parser.add_argument("--run-id")
    parser.add_argument("--lease-socket")
    parser.add_argument("--observations")
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
    engine = None
    try:
        args = arguments(argv)
        if args.operation == "version":
            report.emit("version", **build_metadata(), policy_schema=1, host_protocol=1)
            return 0
        if args.run_id is not None:
            if not re.fullmatch(r"[a-f0-9]{32}", args.run_id):
                raise InvalidPolicy("run-id must be the host lease identifier")
            report.run_id = args.run_id
        report.context = {
            "mode": args.operation,
            "profile": args.profile,
            **build_metadata(),
            "image_digest": os.environ.get("CI_UTILS_IMAGE_DIGEST"),
        }
        overrides = {
            key: value
            for key, value in vars(args).items()
            if value is not None
            and key
            not in (
                "operation",
                "config",
                "profile",
                "run_id",
                "lease_socket",
                "observations",
            )
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
        guard = LeaseGuard(
            engine,
            args.lease_socket,
            args.run_id,
            info["ID"],
            policy_hash,
            args.profile,
            report.context["image_digest"],
        )
        if args.operation == "apply":
            guard.check()
        with BuildCache(engine, policy, info["ID"], report) as cache:
            cache.preflight()
            observation = None
            if args.observations:
                try:
                    observation = storage.load(args.observations)
                except (OSError, ValueError):
                    report.emit(
                        "storage_observation",
                        status="unknown",
                        reason="unreadable-or-untrusted-host-sample",
                    )
            inventory = Inventory(engine, policy, report, observation)
            inventory.load()
            pressure = inventory.pressure()
            report.emit(
                "observations",
                docker=accounting(engine),
                filesystems=pressure["filesystems"],
                pressure=pressure,
                cache=cache.observe(),
                reclaimed_bytes=None,
            )
            if args.operation == "plan":
                plan(inventory, now, args.profile, report)
                cache.plan(now)
            elif args.operation == "apply":
                apply(inventory, cache, guard, now, args.profile, report)
                guard.check()
                report.emit(
                    "final_observations",
                    docker=accounting(engine),
                    cache=cache.observe(),
                    filesystems=None,
                    reclaimed_bytes=None,
                )
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
    report.finish(code, engine is not None and engine.mutation_started)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
