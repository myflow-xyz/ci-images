#!/usr/bin/env python3
"""Package the two CI-built Linux probes with the native command suite."""

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "scripts/ci-utils"


def package(version, revision, probes, output):
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    output.mkdir(parents=True, exist_ok=True)
    checksums = []
    for arch in ("amd64", "arm64"):
        base = f"ci-utils_{version}_linux_{arch}"
        path = output / (base + ".tar.gz")
        files = {
            str(source.relative_to(SUITE)): source.read_bytes()
            for pattern in ("bin/ci-*", "lib/*.py", "lib/ci_utils/*.py")
            for source in SUITE.glob(pattern)
        }
        files["LICENSE"] = (ROOT / "LICENSE").read_bytes()
        files["lib/ci-buildkit-probe"] = (probes / f"probe-{arch}").read_bytes()
        files["lib/build.json"] = (json.dumps(
            dict(version=version, revision=revision, arch=arch), sort_keys=True
        ) + "\n").encode()
        with path.open("wb") as raw, gzip.GzipFile(
            filename="", fileobj=raw, mode="wb", mtime=epoch
        ) as compressed, tarfile.open(fileobj=compressed, mode="w|") as archive:
            for name, data in sorted(files.items()):
                member = tarfile.TarInfo(f"{base}/{name}")
                member.size = len(data)
                member.mtime = epoch
                member.mode = 0o755 if name.startswith("bin/") or name == "lib/ci-buildkit-probe" else 0o644
                archive.addfile(member, io.BytesIO(data))
        checksums.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n")
    (output / f"ci-utils_{version}_SHA256SUMS").write_text("".join(checksums))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("revision")
    parser.add_argument("probes", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", args.version):
        parser.error("expected a pinned X.Y.Z version")
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        parser.error("expected a full source commit")
    package(args.version, args.revision, args.probes, args.output)
