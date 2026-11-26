# Native CI utilities

Install the native commands on the runner and invoke them directly from your shell. Linux amd64 and arm64 receive the full suite and its BuildKit probe. Apple Silicon macOS receives the catalog and image refresh commands. [Install or upgrade ci-utils](docs/installation/install.md)

Put the command directory on `PATH` (`~/.local/bin` for a per-user install) and list the commands in your release.

```bash
ci-utils-list
```

Installation checks for Docker CLI and Buildx and can run with the daemon stopped. After installation, the catalog, version report and Linux Go and pnpm cache commands run offline. Image refresh, retirement and Docker resource cleanup need access to the selected Linux daemon.

| Command | Runner | Operator reference |
| --- | --- | --- |
| `ci-utils` | Linux, macOS | [Discover commands and help](docs/catalog/ci-utils.md) |
| `ci-utils-list` | Linux, macOS | [List the suite offline](docs/catalog/ci-utils-list.md) |
| `ci-upgrade-images` | Linux, macOS | [Refresh cached suite images](docs/images/ci-upgrade-images.md) |
| `ci-go-cleanup` | Linux | [Preview or reset selected Go caches](docs/caches/ci-go-cleanup.md) |
| `ci-pnpm-cleanup` | Linux | [Preview or reset a pnpm store](docs/caches/ci-pnpm-cleanup.md) |
| `ci-remove-images` | Linux | [Preview or retire local suite tags](docs/images/ci-remove-images.md) |
| `ci-docker-cleanup` | Linux | [Check, plan and apply a cleanup policy](docs/maintenance/ci-docker-cleanup.md) |
| `ci-docker-maintenance` | Linux | [Coordinate jobs, apply and recovery](docs/maintenance/ci-docker-maintenance.md) |
| Internal `ci-buildkit-probe` | Linux | [Verify the selected BuildKit worker](docs/maintenance/ci-buildkit-probe.md) |

The implementation, command references and tests are grouped by domain under `lib/`, `docs/` and `tests/`. Host settings, job hooks and service templates are in the maintenance examples. [Maintenance examples](examples/maintenance/)
