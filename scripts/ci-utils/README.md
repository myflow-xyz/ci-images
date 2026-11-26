# Native CI utilities

Linux amd64 and arm64 runners receive eight Bash commands, their Python implementation and the compiled BuildKit probe. Apple Silicon macOS runners receive three native client commands for discovery and image refresh against a Linux Docker daemon. Select a published version with an archive for your runner. The example uses `0.0.31`.

Run this command as the runner account for a per-user install, or as a Linux administrator to provision the system commands for guarded maintenance. It downloads the bootstrap from the matching Git tag and runs it after the download succeeds.

```bash
(set -eu; v=0.0.31; f=$(mktemp); trap 'rm -f "$f"' EXIT; curl -fsSL --proto '=https' --proto-redir '=https' "https://raw.githubusercontent.com/myflow-xyz/ci-images/v$v/scripts/ci-utils/install.sh" -o "$f"; sh "$f" "$v")
```

For a per-user install, the commands are in `~/.local/bin` and the release is under `${XDG_DATA_HOME:-$HOME/.local/share}/ci-utils`. On macOS, apply the printed PATH hint if needed before running these checks.

```bash
ci-utils --version
ci-utils-list
```

Compare the reported version and source revision with the pinned release. [Installation and migration](../docs/ci-utils/install.md)

| Command | Runner | Operator reference |
| --- | --- | --- |
| `ci-utils` | Linux, macOS | [Discover commands and help](../docs/ci-utils/ci-utils.md) |
| `ci-utils-list` | Linux, macOS | [List the suite offline](../docs/ci-utils/ci-utils-list.md) |
| `ci-upgrade-images` | Linux, macOS | [Refresh cached suite images](../docs/ci-utils/ci-upgrade-images.md) |
| `ci-go-cleanup` | Linux | [Preview or reset selected Go caches](../docs/ci-utils/ci-go-cleanup.md) |
| `ci-pnpm-cleanup` | Linux | [Preview or reset a pnpm store](../docs/ci-utils/ci-pnpm-cleanup.md) |
| `ci-remove-images` | Linux | [Preview or retire local suite tags](../docs/ci-utils/ci-remove-images.md) |
| `ci-docker-cleanup` | Linux | [Check, plan and apply a cleanup policy](../docs/ci-utils/ci-docker-cleanup.md) |
| `ci-docker-maintenance` | Linux | [Coordinate jobs, apply and recovery](../docs/ci-utils/ci-docker-maintenance.md) |
| Internal `ci-buildkit-probe` | Linux | [Verify the selected BuildKit worker](../docs/ci-utils/ci-buildkit-probe.md) |
