"""Stage the native release layout for isolated CLI and lease tests."""

import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[4]
DIGEST = "sha256:" + "a" * 64


def stage_release(root, probe=None):
    release = Path(root) / "release"
    source = ROOT / "scripts/ci-utils"
    lib = release / "lib"
    shutil.copytree(source / "lib", lib, ignore=shutil.ignore_patterns("__pycache__", "buildkit-probe"))
    shutil.copytree(source / "bin", release / "bin")
    (lib / "build.json").write_text(json.dumps({"version": "1.0.0", "revision": "1" * 40, "arch": "test"}))
    (lib / "archive.sha256").write_text(DIGEST[7:])
    if probe:
        shutil.copy2(probe, lib / "maintenance/ci-buildkit-probe")
    return lib / "installation/run.py"
