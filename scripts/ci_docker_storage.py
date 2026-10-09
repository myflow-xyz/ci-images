"""Trusted native-host filesystem measurements for one Docker daemon."""

import datetime as dt
import os
import pathlib

from ci_docker_gate import GateError


def measure(info, sources, run_id):
    if (
        not isinstance(sources, dict)
        or set(sources) != {"docker", "containerd", "other"}
        or not isinstance(sources["other"], list)
        or len(sources["other"]) > 30
    ):
        raise GateError(
            2, "explicit Docker, containerd, and other storage paths are required"
        )
    status = info.get("DriverStatus")
    if not isinstance(status, list) or any(
        not isinstance(row, list)
        or len(row) != 2
        or any(not isinstance(value, str) for value in row)
        for row in status
    ):
        raise GateError(2, "cannot establish the daemon storage driver")
    containerd_store = any(
        key == "driver-type" and value == "io.containerd.snapshotter.v1"
        for key, value in status
    )
    if not containerd_store and info.get("Driver") != "overlay2":
        raise GateError(2, "storage layout requires separate qualification")
    if containerd_store and sources["containerd"] is None:
        raise GateError(
            2, "containerd image storage needs an explicit host backing path"
        )
    paths = [("docker", sources["docker"])]
    if sources["containerd"] is not None:
        paths.append(("containerd", sources["containerd"]))
    paths.extend(("other", path) for path in sources["other"])
    filesystems = {}
    try:
        docker_root = info.get("DockerRootDir")
        if (
            not isinstance(docker_root, str)
            or not pathlib.Path(docker_root).is_absolute()
        ):
            raise GateError(2, "daemon did not report an absolute DockerRootDir")
        if pathlib.Path(sources["docker"]).resolve(strict=True) != pathlib.Path(
            docker_root
        ).resolve(strict=True):
            raise GateError(2, "configured Docker storage does not match DockerRootDir")
        for role, value in paths:
            if not isinstance(value, str) or not pathlib.Path(value).is_absolute():
                raise GateError(2, "storage paths must be absolute host directories")
            path = pathlib.Path(value).resolve(strict=True)
            if not path.is_dir():
                raise GateError(2, "storage path is not a directory")
            descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                device = str(os.fstat(descriptor).st_dev)
                if device not in filesystems:
                    counts = os.fstatvfs(descriptor)
                    filesystems[device] = {
                        "device": device,
                        "paths": [],
                        "roles": [],
                        "total_bytes": counts.f_blocks * counts.f_frsize,
                        "used_bytes": (counts.f_blocks - counts.f_bfree)
                        * counts.f_frsize,
                        "available_bytes": counts.f_bavail * counts.f_frsize,
                    }
                entry = filesystems[device]
                if str(path) not in entry["paths"]:
                    entry["paths"].append(str(path))
                if role not in entry["roles"]:
                    entry["roles"].append(role)
            finally:
                os.close(descriptor)
    except (OSError, ValueError, TypeError) as error:
        raise GateError(
            2,
            "host storage measurement is unavailable; no partial pressure estimate is valid",
        ) from error
    return {
        "schema_version": 1,
        "source": "linux-host",
        "complete": True,
        "daemon_id": info["ID"],
        "run_id": run_id,
        "sampled_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "filesystems": list(filesystems.values()),
    }
