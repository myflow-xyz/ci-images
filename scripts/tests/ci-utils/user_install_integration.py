"""Exercise the per-user installer with a disposable account home and release assets."""

import os
from pathlib import Path
import tempfile
import sys

from install_integration import COMMANDS, INSTALL, run


def qualify(assets, version, upgrade):
    if os.geteuid() == 0:
        sys.exit("run the per-user qualification as an ordinary user")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        for account, override in (
            (root / "default", None),
            (root / "custom", root / "custom data"),
        ):
            account.mkdir()
            public = account / ".local/bin"
            env = {**os.environ, "HOME": str(account)}
            env.pop("XDG_DATA_HOME", None)
            data = override or account / ".local/share"
            if override:
                env["XDG_DATA_HOME"] = str(override)
            private = data / "ci-utils"
            for tag in (version, version, upgrade):
                run("/bin/sh", INSTALL, tag, "--from-dir", assets, env=env)
                assert {p.name for p in public.iterdir()} == set(COMMANDS)
                for name in COMMANDS:
                    assert (public / name).samefile(private / "current/bin" / name)
                assert f'"version": "{tag}"' in run(
                    public / "ci-docker-cleanup", "version", env=env
                )
            assert len(list((private / "releases").iterdir())) == 2
    print("per-user install, repeat and upgrade passed")


if __name__ == "__main__":
    qualify(Path(sys.argv[1]), *sys.argv[2:])
