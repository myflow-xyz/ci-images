"""Activate an already checksum-verified release on the install filesystem."""

import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile


def activate(prefix, version, arch, digest):
    bundle = Path(__file__).resolve().parents[1]
    build = json.loads((bundle / "lib/build.json").read_text())
    if (build["version"], build["arch"]) != (version, arch) or not re.fullmatch(
        r"[a-f0-9]{40}", build["revision"]
    ):
        sys.exit("ci-utils: release version, revision or architecture mismatch")
    with (bundle / "lib/ci-buildkit-probe").open("rb") as probe:
        header = probe.read(20)
    if header[:6] != b"\x7fELF\x02\x01" or int.from_bytes(header[18:20], "little") != {
        "amd64": 62, "arm64": 183,
    }[arch]:
        sys.exit(f"ci-utils: expected a Linux {arch} probe, detected a different binary")

    public = prefix / "bin"
    private = prefix / "libexec/ci-utils"
    releases = private / "releases"
    release = releases / f"{version}-{digest}"
    releases.mkdir(parents=True, exist_ok=True)
    public.mkdir(parents=True, exist_ok=True)
    # Serialize concurrent installs. The one current link selects the entire suite.
    lock = os.open(private, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with tempfile.TemporaryDirectory(dir=private) as stage:
            staging = Path(stage)
            if not release.exists():
                tree = staging / "bundle"
                shutil.copytree(bundle, tree)
                (tree / "lib/archive.sha256").write_text(digest + "\n")
                tree.rename(release)
            links = {
                public / cmd.name: Path("../libexec/ci-utils/current/bin") / cmd.name
                for cmd in (release / "bin").iterdir()
            }
            links[private / "ci-docker-maintenance"] = Path("current/bin/ci-docker-maintenance")
            for link, target in links.items():
                if link.is_symlink() and os.readlink(link) == str(target):
                    continue
                if link.parent == public and os.path.lexists(link):
                    sys.exit(f"ci-utils: public command path already in use: {link}")
            for link, target in [(private / "current", release.relative_to(private)), *links.items()]:
                if link.is_symlink() and os.readlink(link) == str(target):
                    continue
                # The bin directory may be on a different filesystem than libexec.
                with tempfile.TemporaryDirectory(dir=link.parent) as temp:
                    pending = Path(temp) / "link"
                    pending.symlink_to(target)
                    os.replace(pending, link)
    finally:
        os.close(lock)
    print(f"Installed ci-utils {version} ({arch}, revision {build['revision']}) in {prefix}")


if __name__ == "__main__":
    activate(Path(sys.argv[1]), *sys.argv[2:])
