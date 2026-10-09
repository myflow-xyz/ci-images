"""Pure cleanup policy; no daemon, filesystem, or shell operations."""

import copy
import datetime as dt
import re
from dataclasses import dataclass

OWNERSHIP_LABEL = "xyz.myflow.ci.ephemeral"
PROTECTION_LABEL = "xyz.myflow.cleanup.protect"
OBJECT_ID = re.compile(r"[a-f0-9]{64}\Z")
IMAGE_ID = re.compile(r"sha256:[a-f0-9]{64}\Z")
DEFAULTS = {
    "schema_version": 1,
    "endpoint": None,
    "expected_daemon_id": None,
    "container_min_age": "24h",
    "network_min_age": "24h",
    "dangling_image_min_age": "24h",
    "tagged_image_min_age": "720h",
    "tagged_image_trigger": "pressure",
    "image_scope": {
        "mode": "allowlist",
        "repositories": [],
        "references": [],
        "ids": [],
        "daemon_wide_approved": False,
    },
    "protected": {
        "container_ids": [],
        "network_ids": [],
        "image_ids": [],
        "image_references": [],
        "image_repositories": [],
    },
    "cache": {
        "mode": "scheduled",
        "builder": "default",
        "max_unused_age": "336h",
        "max_used_space": "20gb",
        "include_internal": False,
    },
    "timeouts": {"run": "15m", "operation": "2m"},
    "pressure": {
        "used_percent": 80,
        "critical_percent": 90,
        "reserve_bytes": None,
        "max_sample_age": "5m",
    },
}
ENVIRONMENT = {
    "CLEANUP_CONTAINER_MIN_AGE": ("container_min_age",),
    "CLEANUP_NETWORK_MIN_AGE": ("network_min_age",),
    "CLEANUP_DANGLING_IMAGE_MIN_AGE": ("dangling_image_min_age",),
    "CLEANUP_UNUSED_IMAGE_MIN_AGE": ("tagged_image_min_age",),
    "CLEANUP_CACHE_MODE": ("cache", "mode"),
    "CLEANUP_CACHE_MAX_UNUSED_AGE": ("cache", "max_unused_age"),
    "CLEANUP_CACHE_MAX_USED_SPACE": ("cache", "max_used_space"),
}


class InvalidPolicy(ValueError):
    """A configuration cannot be applied safely."""


@dataclass(frozen=True)
class Decision:
    eligible: bool
    reason: str


def duration(value):
    """Accept positive, ordered integer hours/minutes/seconds, never expressions."""
    if not isinstance(value, str) or len(value) > 32:
        raise InvalidPolicy("duration must contain integer h/m/s components")
    match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", value)
    if not match:
        raise InvalidPolicy("duration must contain integer h/m/s components")
    seconds = sum(
        int(part or 0) * factor for part, factor in zip(match.groups(), (3600, 60, 1))
    )
    if not 0 < seconds <= 3155760000:
        raise InvalidPolicy("duration must be positive and at most 100 years")
    return seconds


def space_bytes(value):
    """Use the binary memory units accepted by Buildx's RAM size parser."""
    if not isinstance(value, str) or len(value) > 32:
        raise InvalidPolicy(
            "space target must be a positive integer with b/kb/mb/gb/tb units"
        )
    match = re.fullmatch(r"([1-9]\d*)(b|kb|mb|gb|tb)", value.lower())
    if not match:
        raise InvalidPolicy(
            "space target must be a positive integer with b/kb/mb/gb/tb units"
        )
    result = int(match[1]) * 1024 ** ("b", "kb", "mb", "gb", "tb").index(match[2])
    # Buildx's RAMInBytes parser passes through float64 before int64. Keep
    # every accepted byte count exact, including at the upper boundary.
    if result > 2**53 - 1:
        raise InvalidPolicy("space target exceeds exact backend parser range")
    return result


def repository(reference):
    """Normalize exact Docker repository names without prefix/glob matching."""
    if not isinstance(reference, str) or len(reference) > 512:
        raise InvalidPolicy("invalid image reference")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._:/@-]*", reference):
        raise InvalidPolicy("invalid image reference")
    base = reference.split("@", 1)[0]
    parts = base.split("/")
    parts[-1] = parts[-1].split(":", 1)[0]
    if not all(parts) or any(part in (".", "..") for part in parts):
        raise InvalidPolicy("invalid image repository")
    if len(parts) == 1 or not (
        "." in parts[0] or ":" in parts[0] or parts[0] == "localhost"
    ):
        parts.insert(0, "docker.io")
    if parts[0] == "index.docker.io":
        parts[0] = "docker.io"
    if parts[0] == "docker.io" and len(parts) == 2:
        parts.insert(1, "library")
    result = "/".join(parts)
    if result.lower() != result:
        raise InvalidPolicy("repository names must be lowercase")
    return result


def reference_name(reference):
    repo = repository(reference)
    if "@" in reference:
        digest = reference.split("@", 1)[1]
        if not IMAGE_ID.fullmatch(digest):
            raise InvalidPolicy("image digest must be a full sha256 digest")
        return repo + "@" + digest
    tail = reference.rsplit("/", 1)[-1]
    tag = tail.split(":", 1)[1] if ":" in tail else "latest"
    if not re.fullmatch(r"[\w][\w.-]{0,127}", tag, flags=re.ASCII):
        raise InvalidPolicy("invalid image tag")
    return repo + ":" + tag


def _merge(target, source, path=""):
    if not isinstance(source, dict):
        raise InvalidPolicy(f"{path or 'configuration'} must be an object")
    for key, value in source.items():
        if key not in target:
            raise InvalidPolicy(f"unknown setting: {path}{key}")
        if isinstance(target[key], dict):
            _merge(target[key], value, f"{path}{key}.")
        else:
            target[key] = copy.deepcopy(value)


def _list(value, predicate, label):
    if not isinstance(value, list) or any(
        not isinstance(x, str) or not predicate(x) for x in value
    ):
        raise InvalidPolicy(f"invalid {label}")
    if len(set(value)) != len(value):
        raise InvalidPolicy(f"duplicate {label}")


def _repository_only(value):
    # A port in the registry is permitted; a tag on the final component is not.
    return (
        "@" not in value
        and ":" not in value.rsplit("/", 1)[-1]
        and bool(repository(value))
    )


def configuration(value, environ=None, overrides=None):
    policy = copy.deepcopy(DEFAULTS)
    _merge(policy, value)
    for key, text in (environ or {}).items():
        if not key.startswith("CLEANUP_"):
            continue
        if key not in ENVIRONMENT:
            raise InvalidPolicy(f"unknown policy environment setting: {key}")
        path = ENVIRONMENT[key]
        if len(path) == 1:
            policy[path[0]] = text
        else:
            policy[path[0]][path[1]] = text
    _merge(policy, overrides or {})
    if type(policy["schema_version"]) is not int or policy["schema_version"] != 1:
        raise InvalidPolicy("schema_version must be 1")
    endpoint = policy["endpoint"]
    if (
        not isinstance(endpoint, str)
        or not endpoint.startswith("unix:///")
        or endpoint == "unix:///"
        or any(c in endpoint for c in "\x00\n\r?#")
    ):
        raise InvalidPolicy("endpoint must be an explicit absolute local Unix socket")
    daemon_id = policy["expected_daemon_id"]
    if daemon_id is not None and (
        not isinstance(daemon_id, str)
        or not re.fullmatch(r"[\w:.-]{1,256}", daemon_id, re.ASCII)
    ):
        raise InvalidPolicy("invalid expected_daemon_id")
    for key in (
        "container_min_age",
        "network_min_age",
        "dangling_image_min_age",
        "tagged_image_min_age",
    ):
        duration(policy[key])
    if policy["tagged_image_trigger"] not in ("pressure", "scheduled", "disabled"):
        raise InvalidPolicy("invalid tagged_image_trigger")
    scope = policy["image_scope"]
    if (
        scope["mode"] not in ("allowlist", "daemon-wide")
        or type(scope["daemon_wide_approved"]) is not bool
    ):
        raise InvalidPolicy("invalid image_scope")
    if scope["mode"] == "daemon-wide" and not scope["daemon_wide_approved"]:
        raise InvalidPolicy(
            "daemon-wide image cleanup requires dedicated-daemon approval"
        )
    _list(scope["repositories"], _repository_only, "image repositories")
    _list(scope["references"], reference_name, "image references")
    _list(scope["ids"], IMAGE_ID.fullmatch, "image IDs")
    protected = policy["protected"]
    for key in ("container_ids", "network_ids"):
        _list(protected[key], OBJECT_ID.fullmatch, key)
    _list(protected["image_ids"], IMAGE_ID.fullmatch, "protected image IDs")
    _list(protected["image_references"], reference_name, "protected image references")
    _list(
        protected["image_repositories"],
        _repository_only,
        "protected image repositories",
    )
    cache = policy["cache"]
    if (
        cache["mode"] not in ("scheduled", "native", "off")
        or cache["builder"] != "default"
    ):
        raise InvalidPolicy(
            "only the explicitly selected local default builder is supported"
        )
    if type(cache["include_internal"]) is not bool:
        raise InvalidPolicy("cache.include_internal must be a boolean")
    duration(cache["max_unused_age"])
    space_bytes(cache["max_used_space"])
    if duration(policy["timeouts"]["operation"]) > duration(policy["timeouts"]["run"]):
        raise InvalidPolicy("operation deadline exceeds run deadline")
    pressure = policy["pressure"]
    for key in ("used_percent", "critical_percent"):
        if type(pressure[key]) is not int or not 1 <= pressure[key] <= 100:
            raise InvalidPolicy(f"invalid pressure.{key}")
    if pressure["used_percent"] >= pressure["critical_percent"]:
        raise InvalidPolicy("critical pressure must exceed normal pressure threshold")
    reserve = pressure["reserve_bytes"]
    if reserve is not None and (type(reserve) is not int or reserve <= 0):
        raise InvalidPolicy("pressure reserve must be positive bytes or null")
    duration(pressure["max_sample_age"])
    return policy


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(dt.timezone.utc) if result.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def _age(item, age, now):
    created = timestamp(item.get("Created"))
    if created is None:
        return Decision(False, "indeterminate-creation-time")
    return Decision(created < now - dt.timedelta(seconds=duration(age)), "creation-age")


def _labels(item, nested=False):
    value = item.get("Config") if nested else item
    if not isinstance(value, dict):
        return None
    labels = value.get("Labels")
    if labels is None:
        return {}
    if not isinstance(labels, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in labels.items()
    ):
        return None
    return labels


def _owned(item, identifiers, nested=False):
    if (
        not isinstance(item, dict)
        or not isinstance(item.get("Id"), str)
        or not OBJECT_ID.fullmatch(item["Id"])
    ):
        return Decision(False, "indeterminate-identity")
    labels = _labels(item, nested)
    if labels is None:
        return Decision(False, "indeterminate-labels")
    if item["Id"] in identifiers or labels.get(PROTECTION_LABEL) == "true":
        return Decision(False, "protected")
    if labels.get(OWNERSHIP_LABEL) != "true":
        return Decision(False, "unmanaged")
    return None


def container_decision(item, policy, now):
    excluded = _owned(item, policy["protected"]["container_ids"], nested=True)
    if excluded:
        return excluded
    name = item.get("Name")
    labels = _labels(item, nested=True)
    if not isinstance(name, str):
        return Decision(False, "indeterminate-name")
    if (
        name.lstrip("/").startswith("buildx_buildkit_")
        or "com.docker.buildx.builder" in labels
    ):
        return Decision(False, "infrastructure")
    state = item.get("State")
    if not isinstance(state, dict) or state.get("Status") not in ("created", "exited"):
        return Decision(False, "excluded-state")
    return _age(item, policy["container_min_age"], now)


def network_decision(item, policy, now, referenced=()):
    excluded = _owned(item, policy["protected"]["network_ids"])
    if excluded:
        return excluded
    if not isinstance(item.get("Name"), str) or item["Name"] in (
        "bridge",
        "host",
        "none",
    ):
        return Decision(False, "system-or-unknown-network")
    if (
        item.get("Scope") != "local"
        or item.get("Driver") not in ("bridge", "macvlan", "ipvlan")
        or item.get("Ingress") is not False
    ):
        return Decision(False, "unsupported-network")
    if not isinstance(item.get("Containers"), dict):
        return Decision(False, "indeterminate-references")
    if item["Containers"] or item["Id"] in referenced:
        return Decision(False, "referenced")
    return _age(item, policy["network_min_age"], now)


def image_decision(item, policy, now, referenced=(), protected=()):
    if (
        not isinstance(item, dict)
        or not isinstance(item.get("Id"), str)
        or not IMAGE_ID.fullmatch(item["Id"])
    ):
        return Decision(False, "indeterminate-identity")
    labels = _labels(item, nested=True)
    if labels is None:
        return Decision(False, "indeterminate-labels")
    aliases = []
    for key in ("RepoTags", "RepoDigests"):
        if key not in item or (
            item[key] is not None and not isinstance(item[key], list)
        ):
            return Decision(False, "indeterminate-aliases")
        aliases.extend(item[key] or [])
    try:
        aliases = [
            reference_name(ref)
            for ref in aliases
            if ref not in ("<none>:<none>", "<none>@<none>")
        ]
    except InvalidPolicy:
        return Decision(False, "indeterminate-aliases")
    protection = policy["protected"]
    protected_refs = {reference_name(ref) for ref in protection["image_references"]}
    protected_repos = {repository(ref) for ref in protection["image_repositories"]}
    if (
        labels.get(PROTECTION_LABEL) == "true"
        or item["Id"] in protected
        or item["Id"] in protection["image_ids"]
        or any(
            ref in protected_refs or repository(ref) in protected_repos
            for ref in aliases
        )
    ):
        return Decision(False, "protected")
    if item["Id"] in referenced:
        return Decision(False, "referenced")
    scope = policy["image_scope"]
    if scope["mode"] != "daemon-wide" and item["Id"] not in scope["ids"]:
        repos = {repository(ref) for ref in scope["repositories"]}
        refs = {reference_name(ref) for ref in scope["references"]}
        # Removing an ID also affects its aliases. Require every alias in scope.
        if not aliases or not all(
            repository(ref) in repos or ref in refs for ref in aliases
        ):
            return Decision(False, "outside-image-scope")
    tagged = bool([ref for ref in item["RepoTags"] or [] if ref != "<none>:<none>"])
    return _age(
        item,
        policy["tagged_image_min_age" if tagged else "dangling_image_min_age"],
        now,
    )
