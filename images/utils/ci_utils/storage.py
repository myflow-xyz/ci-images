"""Validate host storage observations without measuring the container root."""

import json
import os
import pathlib
import stat

from .policy import duration, timestamp


def load(path):
    """Read only a bounded root-owned observation from the host adapter."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        metadata = os.fstat(handle.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_mode & 0o022
        ):
            raise ValueError("storage observations must be immutable host-owned files")
        data = handle.read(65537)
        if len(data) > 65536:
            raise ValueError("storage observation exceeds 64 KiB")
        return json.loads(data)


def evaluate(observation, policy, daemon_id, run_id, now):
    def unknown(reason):
        return {
            "status": "unknown",
            "reason": reason,
            "pressured": None,
            "critical": None,
            "filesystems": None,
        }

    if observation is None:
        return unknown("missing-observation")
    if (
        not isinstance(observation, dict)
        or type(observation.get("schema_version")) is not int
        or observation["schema_version"] != 1
        or observation.get("source") != "linux-host"
        or observation.get("daemon_id") != daemon_id
        or observation.get("run_id") != run_id
        or observation.get("complete") is not True
    ):
        return unknown("untrusted-or-incomplete-observation")
    sampled = timestamp(observation.get("sampled_at"))
    if sampled is None or not -5 <= (now - sampled).total_seconds() <= duration(
        policy["pressure"]["max_sample_age"]
    ):
        return unknown("stale-or-invalid-observation-time")
    filesystems = observation.get("filesystems")
    if not isinstance(filesystems, list) or not 1 <= len(filesystems) <= 32:
        return unknown("missing-storage-filesystems")
    devices, roles = set(), set()
    pressured, critical = False, False
    settings = policy["pressure"]
    for item in filesystems:
        if not isinstance(item, dict):
            return unknown("invalid-filesystem-observation")
        device = item.get("device")
        paths, sources = item.get("paths"), item.get("roles")
        if (
            not isinstance(device, str)
            or not device.isascii()
            or not device.isdecimal()
            or len(device) > 32
            or device in devices
            or not isinstance(paths, list)
            or not paths
            or any(
                not isinstance(path, str)
                or not pathlib.PurePosixPath(path).is_absolute()
                for path in paths
            )
            or not isinstance(sources, list)
            or not sources
            or any(role not in ("docker", "containerd", "other") for role in sources)
        ):
            return unknown("invalid-or-duplicate-storage-source")
        devices.add(device)
        roles.update(sources)
        total, used, available = (
            item.get(key) for key in ("total_bytes", "used_bytes", "available_bytes")
        )
        if (
            any(
                type(value) is not int or not 0 <= value <= 2**63 - 1
                for value in (total, used, available)
            )
            or total == 0
            or used + available > total
        ):
            return unknown("invalid-filesystem-accounting")
        below_reserve = (
            settings["reserve_bytes"] is not None
            and available < settings["reserve_bytes"]
        )
        pressured |= used * 100 >= settings["used_percent"] * total or below_reserve
        critical |= used * 100 >= settings["critical_percent"] * total or below_reserve
    if "docker" not in roles:
        return unknown("missing-docker-storage-source")
    return {
        "status": "known",
        "sampled_at": observation["sampled_at"],
        "source": "linux-host",
        "pressured": pressured,
        "critical": critical,
        "filesystems": filesystems,
    }
