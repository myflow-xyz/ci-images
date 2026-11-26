"""Exercise the per-user installer with a disposable account home and release assets."""

import json
import os
from pathlib import Path
import platform
import shutil
import tempfile
import sys

from install_integration import COMMANDS, INSTALL, run

sys.path.insert(0, str(INSTALL.parents[2] / "tests/utils"))
from api_fixture import APIFixture, daemon_routes


def qualify(assets, version, upgrade):
    if os.geteuid() == 0:
        sys.exit("run the per-user qualification as an ordinary user")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        # Expose the runner's client plugin without copying registry credentials.
        docker_config = root / "docker-config"
        plugins = docker_config / "cli-plugins"
        plugins.mkdir(parents=True)
        buildx = (
            Path(os.environ.get("DOCKER_CONFIG") or Path.home() / ".docker")
            / "cli-plugins/docker-buildx"
        )
        if buildx.is_file():
            (plugins / "docker-buildx").symlink_to(buildx.resolve())
        macos = sys.platform == "darwin"
        arch = {"x86_64": "amd64", "arm64": "arm64", "aarch64": "arm64"}[platform.machine()]
        commands = (
            ("ci-utils", "ci-utils-list", "ci-upgrade-images") if macos else COMMANDS
        )
        for account, override in (
            (root / "default", None),
            (root / "runner account", root / "custom data"),
        ):
            account.mkdir()
            public = account / ".local/bin"
            env = {
                **os.environ,
                "HOME": str(account),
                "DOCKER_CONFIG": str(docker_config),
            }
            startup = account / ".zprofile"
            startup.write_text("# runner-owned configuration\n")
            env.pop("XDG_DATA_HOME", None)
            data = override or account / ".local/share"
            if override:
                env["XDG_DATA_HOME"] = str(override)
            private = data / "ci-utils"
            for tag in (version, version, upgrade):
                message = run("/bin/sh", INSTALL, tag, "--from-dir", assets, env=env)
                assert {p.name for p in public.iterdir()} == set(commands)
                for name in commands:
                    assert (public / name).samefile(private / "current/bin" / name)
                build = json.loads((private / "current/lib/build.json").read_text())
                assert (build["os"], build["arch"]) == (sys.platform, arch)
                assert run(public / "ci-utils", "--version", env=env).strip() == (
                    f"ci-utils {tag} (revision {build['revision']})"
                )
                catalog = run(public / "ci-utils-list", env=env)
                assert "container image is deprecated" not in catalog
                for name in commands:
                    assert f"  {name} " in catalog
                if macos:
                    assert "ci-docker-maintenance" not in catalog
                    assert not os.path.lexists(private / "ci-docker-maintenance")
                    hint = next(
                        line
                        for line in message.splitlines()
                        if line.startswith("export PATH=")
                    )
                    assert run(
                        "bash", "-ec", hint + "\ncommand -v ci-upgrade-images", env=env
                    ).strip() == str(public / "ci-upgrade-images")
                assert startup.read_text() == "# runner-owned configuration\n"
            assert len(list((private / "releases").iterdir())) == 2
            # A failed download verification must leave the active release usable.
            bad = account / "bad"
            bad.mkdir()
            archive = f"ci-utils_{upgrade}_{sys.platform}_{build['arch']}.tar.gz"
            shutil.copy(assets / f"ci-utils_{upgrade}_SHA256SUMS", bad)
            (bad / archive).write_bytes(b"incomplete")
            run(
                "/bin/sh",
                INSTALL,
                upgrade,
                "--from-dir",
                bad,
                status=2,
                contains="checksum mismatch",
                env=env,
            )
            assert upgrade in run(public / "ci-utils", "--version", env=env)

        # Run the installed host client against an explicit Linux Engine API.
        routes = daemon_routes()
        routes["GET", "/v1.48/images/json?all=true"] = (200, [])
        with APIFixture(routes) as api:
            args = [public / "ci-upgrade-images", "--endpoint", api.endpoint]
            live = json.loads(run(*args, env=env).splitlines()[-1])
            assert (live["daemon_id"], live["exit_code"], live["mutation_started"]) == (
                "fixture-daemon",
                0,
                False,
            )
            run(
                *args,
                "--expected-daemon-id",
                "other-daemon",
                status=3,
                contains="does not match",
                env=env,
            )
            assert ("GET", "/v1.48/images/json?all=true") in api.requests
            assert all(method == "GET" for method, _ in api.requests)
    print(
        f"{sys.platform}/{build['arch']} per-user install, PATH, upgrade, checksum and Engine API checks passed"
    )


if __name__ == "__main__":
    qualify(Path(sys.argv[1]), *sys.argv[2:])
