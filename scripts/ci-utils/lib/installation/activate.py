"""Activate an already checksum-verified release on the install filesystem."""

import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
import tempfile


def verify_probe(path, arch):
    with path.open("rb") as probe:
        header = probe.read(20)
    machine = {"amd64": 62, "arm64": 183}[arch]
    if (
        header[:6] != b"\x7fELF\x02\x01"
        or int.from_bytes(header[18:20], "little") != machine
    ):
        sys.exit(
            f"ci-utils: expected a Linux {arch} probe, detected a different binary"
        )


def activate(prefix, version, arch, digest, user_directory=None):
    bundle = Path(__file__).resolve().parents[2]
    build = json.loads((bundle / "lib/build.json").read_text())
    if (build.get("os", "linux"), build["version"], build["arch"]) != (
        sys.platform,
        version,
        arch,
    ) or not re.fullmatch(r"[a-f0-9]{40}", build["revision"]):
        sys.exit("ci-utils: release OS, version, revision or architecture mismatch")
    if sys.platform == "linux":
        verify_probe(bundle / "lib/maintenance/ci-buildkit-probe", arch)

    public = prefix / "bin"
    private = Path(user_directory) if user_directory else prefix / "libexec/ci-utils"
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
            current_bin = Path(os.path.relpath(private.resolve() / "current/bin", public.resolve()))
            old_bin = Path(os.path.relpath(private / "current/bin", public))
            links = {
                public / cmd.name: current_bin / cmd.name
                for cmd in (release / "bin").iterdir()
            }
            if sys.platform == "linux":
                links[private / "ci-docker-maintenance"] = Path(
                    "current/bin/ci-docker-maintenance"
                )
            for link, target in links.items():
                if link.is_symlink() and os.readlink(link) == str(target):
                    continue
                if link.parent == public and os.path.lexists(link):
                    if (link.is_symlink() and not link.exists()
                            and (private / "current").is_symlink()
                            and os.readlink(link) == str(old_bin / link.name)):
                        continue
                    sys.exit(f"ci-utils: public command path already in use: {link}")
            for link, target in [
                (private / "current", release.relative_to(private)),
                *links.items(),
            ]:
                if link.is_symlink() and os.readlink(link) == str(target):
                    continue
                # The bin directory may be on a different filesystem than libexec.
                with tempfile.TemporaryDirectory(dir=link.parent) as temp:
                    pending = Path(temp) / "link"
                    pending.symlink_to(target)
                    os.replace(pending, link)
    finally:
        os.close(lock)
    print(
        f"Installed ci-utils {version} ({sys.platform}/{arch}, revision {build['revision']}) in {public}"
    )
    if sys.platform == "darwin" and str(public) not in os.get_exec_path():
        print(
            "Add this line to your shell startup file and run it in your current shell."
        )
        print(f'export PATH={shlex.quote(str(public))}:"$PATH"')


if __name__ == "__main__":
    activate(Path(sys.argv[1]), *sys.argv[2:])
