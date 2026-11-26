# Native CI utilities

Install a pinned release on a Linux amd64 or arm64 runner. The archive contains eight Bash commands, their Python standard-library implementation and a compiled BuildKit probe. Select a published version with native archives in its release assets. The example uses `0.0.31`.

Run this command in an administrator shell. It downloads the bootstrap from the matching Git tag and runs it after the download succeeds.

```bash
(set -eu; v=0.0.31; f=$(mktemp); trap 'rm -f "$f"' EXIT; curl -fsSL --proto '=https' --proto-redir '=https' "https://raw.githubusercontent.com/myflow-xyz/ci-images/v$v/scripts/ci-utils/install.sh" -o "$f"; sh "$f" "$v")
```

```bash
ci-docker-cleanup version
ci-utils-list
```

Verify the reported version and source revision. Follow the installation guide to migrate existing services or qualify a runner for guarded apply. [Installation and migration](../docs/ci-utils/install.md)

| Command | Operator reference |
| --- | --- |
| `ci-utils` | [Discover commands and help](../docs/ci-utils/ci-utils.md) |
| `ci-utils-list` | [List the suite offline](../docs/ci-utils/ci-utils-list.md) |
| `ci-go-cleanup` | [Preview or reset selected Go caches](../docs/ci-utils/ci-go-cleanup.md) |
| `ci-pnpm-cleanup` | [Preview or reset a pnpm store](../docs/ci-utils/ci-pnpm-cleanup.md) |
| `ci-upgrade-images` | [Refresh cached suite images](../docs/ci-utils/ci-upgrade-images.md) |
| `ci-remove-images` | [Preview or retire local suite tags](../docs/ci-utils/ci-remove-images.md) |
| `ci-docker-cleanup` | [Check, plan and apply a cleanup policy](../docs/ci-utils/ci-docker-cleanup.md) |
| `ci-docker-maintenance` | [Coordinate jobs, apply and recovery](../docs/ci-utils/ci-docker-maintenance.md) |
| Internal `ci-buildkit-probe` | [Verify the selected BuildKit worker](../docs/ci-utils/ci-buildkit-probe.md) |
