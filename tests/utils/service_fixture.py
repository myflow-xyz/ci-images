"""Run host commands with the shipped service's Unix identity/capability profile."""

import configparser
import pathlib


def service_command(args, job_gid):
    unit = configparser.ConfigParser(interpolation=None)
    unit.read(
        pathlib.Path(__file__).resolve().parents[2]
        / "scripts/examples/ci-utils/ci-docker-maintenance@.service"
    )
    service = unit["Service"]
    assert service["User"] == service["Group"] == "root"
    assert service["CapabilityBoundingSet"] == ""
    assert service.getboolean("NoNewPrivileges")
    groups = (
        service.get("SupplementaryGroups", "")
        .replace("REPLACE_WITH_JOB_GID", str(job_gid))
        .split()
    )
    return [
        "setpriv",
        "--reuid=0",
        "--regid=0",
        "--bounding-set=-all",
        "--inh-caps=-all",
        "--ambient-caps=-all",
        "--no-new-privs",
        "--groups=" + ",".join(groups) if groups else "--clear-groups",
        *args,
    ]
