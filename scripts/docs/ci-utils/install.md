# Install or upgrade ci-utils

Use a published Git tag with both Linux archives and a checksum file. The pinned example uses `v0.0.31`. Earlier image-only releases have no native assets. In an administrator shell, run the bootstrap from that same tag.

```bash
(set -eu; v=0.0.31; f=$(mktemp); trap 'rm -f "$f"' EXIT; curl -fsSL --proto '=https' --proto-redir '=https' "https://raw.githubusercontent.com/myflow-xyz/ci-images/v$v/scripts/ci-utils/install.sh" -o "$f"; sh "$f" "$v")
```

The bootstrap selects `linux_amd64` for `x86_64` and `linux_arm64` for `aarch64` or `arm64`. It downloads `ci-utils_<version>_SHA256SUMS` and the selected `.tar.gz` over HTTPS from the pinned GitHub release. It requires exactly one matching SHA-256 entry and verifies the archive before extraction. Activation checks the embedded version, source revision format, architecture and probe ELF machine type. CI packages the probe already compiled for that platform from the verified utility image index.

## Dependencies

| Dependency | Minimum or required capability | Why |
| --- | --- | --- |
| Linux, `/bin/sh`, `/usr/bin/env`, Bash | Bash 5.0 | The repository sets this floor for Bash entry points. The bootstrap starts under POSIX sh so it can diagnose an absent or older Bash. |
| `python3` and its standard library | Python 3.9 | Image selection uses `str.removeprefix`. Cache selection uses `Path.is_relative_to`. Linux file descriptors, locks, Unix sockets, TLS, JSON and SHA-256 are required. |
| Transfer and extraction | HTTPS-capable `curl`, `sha256sum --check --status`, `tar --no-same-owner -xzf`, `gzip` | Download from GitHub, verify the release checksum and extract a verified archive. |
| Linux utilities | `uname`, `readlink -f`, `mktemp -d`, `cp`, `rm` | Select the platform, resolve installed entry points, stage files and remove temporary data. |
| Docker CLI with Buildx | `docker --version` and `docker buildx version` must succeed | Refresh inspects OCI indexes. Cleanup selects the local default builder. Install the plugin where the maintenance service can discover it with an empty Docker configuration. |

Python 3.9 is both the source lower bound and the qualified minimum for this package. Linux qualification exercised Bash 5.0.3 with Python 3.9.23 and Bash 5.3.20 with Python 3.15.2. It also exercised rejection of Bash 4.4 and Python 3.8. The probe is a static Go binary. Runners need no Go compiler, pip packages or utility container.

Preflight runs before installation writes. For example, `requires Docker Buildx (detected: missing or unusable with a clean Docker configuration)` means the plugin could not report its version without personal Docker settings. Install the system-wide Docker Buildx CLI plugin and repeat the pinned command. Live daemon identity, registry access and cache permissions are checked by the commands that use them.

### Shipped runtime inventory

All eight Bash entry points resolve their release with `readlink -f` and execute `python3 -IB`. The catalog uses `catalog.py`. The Go and pnpm commands use `file_cache.py`. Docker operations share `engine.py`, `policy.py`, `guard.py`, `storage.py`, `cache.py` and the report logic in `cleanup.py`. Image refresh and retirement use `upgrade_images.py` and `remove_images.py`. The adapter uses the `ci_docker_maintenance`, `ci_docker_gate`, `ci_docker_job`, `ci_docker_storage` and `ci_docker_reconcile` modules.

| Runtime boundary | Direct standard-library imports or child programs |
| --- | --- |
| Parsing, policy and reporting | `argparse`, `collections`, `copy`, `dataclasses`, `datetime`, `functools`, `hashlib`, `json`, `math`, `re`, `sys`, `time`, `uuid` |
| Files, processes and admission | `contextlib`, `fcntl`, `os`, `pathlib`, `shutil`, `signal`, `socket`, `socketserver`, `stat`, `struct`, `subprocess`, `tempfile`, `threading` |
| Engine and release requests | `http.client`, `urllib.parse`, `urllib.request` and TLS support from `ssl` |
| External commands | Refresh invokes Docker image pull/tag and Buildx imagetools inspect. Managed cache invokes Docker, Buildx and the bundled probe. The adapter starts the installed Python worker and the job lifecycle command supplied by the operator. Catalog, filesystem reset and image retirement use no further child programs. |

## Paths, repeat installation and migration

The installer accepts `X.Y.Z [--prefix ABSOLUTE_PATH] [--from-dir TRUSTED_RELEASE_DIRECTORY]`. The default prefix is `/usr/local`. Use `--from-dir` with a trusted offline copy of the checksum file and selected archive. The checksum file is the trust input. Obtain it from the authenticated release or an independently verified mirror. A writable private prefix also supports unprivileged installation for offline commands.

| Path at the default prefix | Role |
| --- | --- |
| `/usr/local/bin/ci-*` | Eight Bash entry points on the runner's PATH. |
| `/usr/local/libexec/ci-utils/releases/` | Complete release directories keyed by version and archive digest. |
| `/usr/local/libexec/ci-utils/current` | Atomically selected release. Its `lib/` directory holds the Python implementation, release metadata and prebuilt probe. |
| `/usr/local/libexec/ci-utils/ci-docker-maintenance` | Compatibility entry point for deployed service units and job finalizers. |
| `/etc/ci-utils/host.json` and `cleanup.json` | Operator-owned host settings and cleanup policy. |
| `/var/lib/ci-utils/gate` | Example persistent admission state. The actual directory comes from `host.json`. |

Install success prints the version, architecture, source revision and prefix and exits 0. Usage and preflight failures exit 2. Download, extraction and filesystem errors return nonzero. A failed prerequisite, download or checksum leaves the active release usable. Repeat installation of the same archive reuses its release directory. To upgrade or select a previous verified native release, run its pinned bootstrap. Existing configuration, job records and reconciliation evidence survive activation.

```bash
command -v ci-utils
ci-docker-cleanup version
ci-utils-list
```

The version event reports the numeric release, full revision and verified archive digest. Compare them with the selected tag and checksum. For a new host, review the policy, host settings, service, timers and job wrapper before provisioning the gate. On an existing host, drain participants, resolve outstanding maintenance and record the active release before switching. The installer replaces the old absolute adapter entry point. Its native replacement accepts the deployed `image` setting and authorizes the installed release by archive digest. Keep the existing gate and run `status`, `check` and `plan` before the first apply. [Configuration and service examples](../../examples/ci-utils/) · [Maintenance and recovery](../../../docs/maintenance.md)

From the repository root, run `(cd scripts && shellspec tests/ci-utils/install_spec.sh)`. The Linux installation and daemon qualification entry point is `tests/ci-utils-native.sh`.
