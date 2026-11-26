"""Exercise shipped archives in a disposable Linux runner with no Docker socket."""

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

INSTALL = Path(__file__).resolve().parents[2] / "ci-utils/install.sh"
COMMANDS = (
    "ci-utils",
    "ci-utils-list",
    "ci-go-cleanup",
    "ci-pnpm-cleanup",
    "ci-upgrade-images",
    "ci-remove-images",
    "ci-docker-cleanup",
    "ci-docker-maintenance",
)


def run(*command, status=0, contains="", env=None):
    result = subprocess.run(
        command, env=env, text=True, capture_output=True, timeout=60
    )
    assert result.returncode == status and contains in result.stdout + result.stderr, (
        command,
        result.returncode,
        result.stdout,
        result.stderr,
    )
    return result.stdout


def qualify(root, assets, version, upgrade):
    prefix = root / "prefix"
    private = prefix / "libexec/ci-utils"
    compat = private / "ci-docker-maintenance"
    shim = root / "tools"
    shim.mkdir()
    tools = (
        "bash",
        "python3",
        "uname",
        "readlink",
        "docker",
        "curl",
        "sha256sum",
        "tar",
        "gzip",
        "mktemp",
        "cp",
        "rm",
    )
    for tool in tools:
        (shim / tool).symlink_to(shutil.which(tool))
    isolated = {**os.environ, "PATH": str(shim)}
    cli = {**os.environ, "PATH": f"{prefix}/bin:{os.environ['PATH']}"}

    def install(tag, *extra, source=assets, **kwargs):
        options = ["--from-dir", source] if source else []
        return run(
            "/bin/sh", INSTALL, tag, "--prefix", prefix, *options, *extra, **kwargs
        )

    def active(tag):
        for name in COMMANDS:
            assert shutil.which(name, path=cli["PATH"]) == str(prefix / "bin" / name)
            run(name, "--help", env=cli)
        identity = json.loads(run("ci-docker-cleanup", "version", env=cli))
        assert identity["version"] == tag and len(identity["revision"]) == 40, identity
        assert compat.samefile(prefix / "bin/ci-docker-maintenance")
        return identity

    def preflight():
        cases = [
            (name, None, message)
            for name, message in (
                ("bash", "Bash >= 5.0 (detected: missing)"),
                ("python3", "Python >= 3.9 (detected: missing)"),
                *(
                    (name, f"executable {name} (detected: missing)")
                    for name in tools
                    if name not in ("bash", "python3")
                ),
            )
        ]
        if Path("/opt/below/bin/bash").exists():
            cases += [
                ("bash", "/opt/below/bin/bash", "Bash >= 5.0 (detected: 4.4"),
                (
                    "python3",
                    "/opt/below/bin/python3",
                    "Python >= 3.9 (detected: Python 3.8",
                ),
            ]
        for name, replacement, message in cases:
            path = shim / name
            original = os.readlink(path)
            path.unlink()
            if replacement:
                path.symlink_to(replacement)
            install(upgrade, status=2, contains=message, env=isolated)
            path.unlink(missing_ok=True)
            path.symlink_to(original)
        (shim / "docker").unlink()
        (shim / "docker").write_text('#!/bin/sh\n[ "$1" = --version ]\n')
        (shim / "docker").chmod(0o755)
        install(upgrade, env=isolated, status=2, contains="requires Docker Buildx")
        # The operator has a personal plugin. The service's empty config cannot use it.
        (shim / "docker").write_text('#!/bin/sh\n[ "$1" = --version ] || [ "$1" = buildx ]\n')
        install(upgrade, env=isolated, status=2, contains="requires Docker Buildx")
        (shim / "docker").unlink()
        (shim / "docker").symlink_to(shutil.which("docker"))

    preflight()
    assert not prefix.exists()
    private.mkdir(parents=True)
    compat.write_text("# deployed adapter\n")
    install(version)
    before = active(version)
    guide = (INSTALL.parents[1] / "docs/ci-utils/install.md").read_text()
    checks = next(block.split("\n```", 1)[0] for block in guide.split("```bash\n")
                  if block.startswith("command -v ci-utils\n"))
    old_alias = "alias ci-upgrade-images='docker exec -i ci-utils ci-upgrade-images'"
    output = run("bash", "-O", "expand_aliases", "-ec",
                 f"{old_alias}\n{checks}\ncommand -v ci-upgrade-images", env=cli)
    assert output.splitlines()[-1] == str(prefix / "bin/ci-upgrade-images"), output
    # The release never owns operator settings or persistent gate records.
    config = Path("/etc/ci-utils/cleanup.json")
    gate = Path("/var/lib/ci-utils/gate/maintenance.json")
    for path in (config, gate):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as out:
            out.write("operator fixture\n")
    install(version)
    assert active(version)["revision"] == before["revision"]
    previous = (private / "current").resolve()
    assert len(list((private / "releases").iterdir())) == 1
    preflight()
    arch = {"x86_64": "amd64", "aarch64": "arm64"}[platform.machine()]
    archive = f"ci-utils_{upgrade}_linux_{arch}.tar.gz"
    sums = f"ci-utils_{upgrade}_SHA256SUMS"
    bad = root / "bad"
    bad.mkdir()
    shutil.copy(assets / archive, bad / archive)
    (bad / sums).write_text(f"{'0' * 64}  {archive}\n")
    install(upgrade, source=bad, status=2, contains="checksum mismatch")

    # A checksum-valid archive for the other CPU must still fail activation.
    other = "arm64" if arch == "amd64" else "amd64"
    shutil.copy(assets / archive.replace(arch, other), bad / archive)
    (bad / sums).write_text(
        f"{hashlib.sha256((bad / archive).read_bytes()).hexdigest()}  {archive}\n"
    )
    install(upgrade, source=bad, status=2, contains="architecture")
    curl = shim / "curl"
    curl.unlink()
    curl.write_text(
        '#!/bin/sh\nwhile [ "$1" != --output ]; do shift; done\n'
        'case "$3" in *SHA256SUMS) cp "$SUMS" "$2";; *) echo partial >"$2"; exit 18;; esac\n'
    )
    curl.chmod(0o755)
    install(
        upgrade, source=None, status=18, env={**isolated, "SUMS": str(assets / sums)}
    )
    assert previous == (private / "current").resolve()
    active(version)
    install(upgrade)
    identity = active(upgrade)
    for path in (config, gate):
        assert path.read_text() == "operator fixture\n"
    for command, parts, option in (
        ("ci-go-cleanup", "go/build", "--build-cache"),
        ("ci-pnpm-cleanup", "pnpm/store", "--store-dir"),
    ):
        cache = root / parts
        cache.mkdir(parents=True)
        (cache / "entry").touch()
        run(command, option, cache, env=cli, contains='"mode": "plan"')
        assert (cache / "entry").exists()
        run(command, option, cache, "--apply", env=cli)
        assert cache.is_dir() and not list(cache.iterdir())
    probe = private / "current/lib/ci-buildkit-probe"
    run(probe, status=2, contains="explicit local Unix endpoint")
    print(
        arch,
        run("bash", "-c", 'echo "$BASH_VERSION"').strip(),
        platform.python_version(),
        identity["version"],
        identity["revision"],
        "install, upgrade and preflight passed",
    )


if __name__ == "__main__":
    if not Path("/.dockerenv").exists() or Path("/var/run/docker.sock").exists():
        sys.exit("requires a disposable Linux container without a host Docker socket")
    with tempfile.TemporaryDirectory() as directory:
        qualify(Path(directory), Path(sys.argv[1]), *sys.argv[2:])
