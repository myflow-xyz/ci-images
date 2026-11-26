#!/usr/bin/env python3
"""Package the Linux maintenance suite and the macOS runner client."""

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "scripts/ci-utils"
sys.path.insert(0, str(SUITE))
from lib.installation.activate import verify_probe

PLATFORMS = ("linux/amd64", "linux/arm64", "darwin/arm64")
MACOS_COMMANDS = ("bin/ci-utils", "bin/ci-utils-list", "bin/ci-upgrade-images")


def package(version, revision, probes, output, platforms=PLATFORMS):
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    output.mkdir(parents=True, exist_ok=True)
    checksums = []
    for platform in platforms:
        system, arch = platform.split("/")
        base = f"ci-utils_{version}_{system}_{arch}"
        path = output / (base + ".tar.gz")
        commands = ("bin/ci-*",) if system == "linux" else MACOS_COMMANDS
        files = {
            str(source.relative_to(SUITE)): source.read_bytes()
            for pattern in (*commands, "lib/*.py", "lib/*/*.py")
            for source in SUITE.glob(pattern)
            if system == "linux"
            or not (
                source.name.startswith("ci_docker_") or source.name == "file_cache.py"
            )
        }
        files["LICENSE"] = (ROOT / "LICENSE").read_bytes()
        if system == "linux":
            probe = probes / f"probe-{arch}"
            verify_probe(probe, arch)
            files["lib/maintenance/ci-buildkit-probe"] = probe.read_bytes()
        files["lib/build.json"] = (
            json.dumps(
                dict(version=version, revision=revision, os=system, arch=arch),
                sort_keys=True,
            )
            + "\n"
        ).encode()
        with (
            path.open("wb") as raw,
            gzip.GzipFile(
                filename="", fileobj=raw, mode="wb", mtime=epoch
            ) as compressed,
            tarfile.open(fileobj=compressed, mode="w|") as archive,
        ):
            for name, data in sorted(files.items()):
                member = tarfile.TarInfo(f"{base}/{name}")
                member.size = len(data)
                member.mtime = epoch
                member.mode = (
                    0o755
                    if name.startswith("bin/") or name == "lib/maintenance/ci-buildkit-probe"
                    else 0o644
                )
                archive.addfile(member, io.BytesIO(data))
        checksums.append(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
        )
    (output / f"ci-utils_{version}_SHA256SUMS").write_text("".join(checksums))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("revision")
    parser.add_argument("probes", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--platform", choices=PLATFORMS, help="package only this qualification target"
    )
    args = parser.parse_args()
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", args.version):
        parser.error("expected a pinned X.Y.Z version")
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        parser.error("expected a full source commit")
    package(
        args.version,
        args.revision,
        args.probes,
        args.output,
        (args.platform,) if args.platform else PLATFORMS,
    )
