# Install or upgrade ci-utils

Use a published Git tag with the archive for your runner and its checksum file. The pinned example uses `v0.0.31`. Earlier image-only releases have no native assets. Run the bootstrap from that same tag under your runner account. Use a Linux administrator shell for the system-wide maintenance service.

```bash
(set -eu; v=0.0.31; f=$(mktemp); trap 'rm -f "$f"' EXIT; curl -fsSL --proto '=https' --proto-redir '=https' "https://raw.githubusercontent.com/myflow-xyz/ci-images/v$v/scripts/ci-utils/install.sh" -o "$f"; sh "$f" "$v")
```

The bootstrap uses the runner's OS and CPU to select `linux_amd64`, `linux_arm64` or `darwin_arm64`. It downloads `ci-utils_<version>_SHA256SUMS` and the selected `.tar.gz` over HTTPS from the pinned GitHub release. It requires one matching SHA-256 entry and verifies the archive before extraction. Activation checks the embedded OS, architecture, version and source revision. Linux archives include a probe built from the release source for the selected CPU and activation checks its ELF machine type. The macOS archive contains the Bash and Python client for catalog and refresh.

## Dependencies

| Dependency | Minimum or required capability | Why |
| --- | --- | --- |
| `/bin/sh`, `/usr/bin/env`, Bash | Bash 5.0 | The repository sets this floor for Bash entry points. On macOS, put a supported Bash on PATH before invoking the bootstrap. |
| `python3` and its standard library | Python 3.9 | Image selection uses `str.removeprefix`. Cache selection uses `Path.is_relative_to`. Linux file descriptors, locks, Unix sockets, TLS, JSON and SHA-256 are required. |
| Transfer and extraction | HTTPS-capable `curl`, Linux `sha256sum` or macOS `shasum -a 256` with `--check --status`, `tar --no-same-owner -xzf`, `gzip` | Download from GitHub, verify the release checksum and extract a verified archive. |
| Runner utilities | `uname`, `readlink -f`, `mktemp -d`, `cp`, `rm` | Select the platform, resolve installed entry points, stage files and remove temporary data. |
| Docker CLI with Buildx | `docker --version` and `docker buildx version` must succeed | Linux maintenance needs Buildx with an empty Docker configuration. The macOS client checks Buildx in the runner account's configuration, which it also uses for refresh. |

Python 3.9 is both the source lower bound and the qualified minimum for this package. Linux qualification exercised Bash 5.0.3 with Python 3.9.23 and Bash 5.3.20 with Python 3.15.2. It also exercised rejection of Bash 4.4 and Python 3.8. The probe is a static Go binary. The release supplies the binary. The Python commands use the standard library.

Preflight runs before installation writes. It checks the Docker CLI and Buildx versions and can run with the daemon stopped. For example, `requires Docker Buildx (detected: missing or unusable with a clean Docker configuration)` means the plugin could not report its version without personal Docker settings. Install the system-wide Docker Buildx CLI plugin on Linux and repeat the pinned command. The installed catalog and filesystem cache commands work offline. Image and Docker resource operations check the selected daemon when invoked.

### Shipped runtime inventory

All eight Bash entry points resolve their release with `readlink -f` and execute `python3 -IB`. The catalog uses `catalog.py`. The Go and pnpm commands use `file_cache.py`. Docker operations share `engine.py`, `policy.py`, `guard.py`, `storage.py`, `cache.py` and the report logic in `cleanup.py`. Image refresh and retirement use `upgrade_images.py` and `remove_images.py`. The adapter uses the `ci_docker_maintenance`, `ci_docker_gate`, `ci_docker_job`, `ci_docker_storage` and `ci_docker_reconcile` modules.

| Runtime boundary | Direct standard-library imports or child programs |
| --- | --- |
| Parsing, policy and reporting | `argparse`, `collections`, `copy`, `dataclasses`, `datetime`, `functools`, `hashlib`, `json`, `math`, `re`, `sys`, `time`, `uuid` |
| Files, processes and admission | `contextlib`, `fcntl`, `os`, `pathlib`, `shutil`, `signal`, `socket`, `socketserver`, `stat`, `struct`, `subprocess`, `tempfile`, `threading` |
| Engine and release requests | `http.client`, `urllib.parse`, `urllib.request` and TLS support from `ssl` |
| External commands | Refresh invokes Docker image pull/tag and Buildx imagetools inspect. Managed cache invokes Docker, Buildx and the bundled probe. The adapter starts the installed Python worker and the job lifecycle command supplied by the operator. Catalog, filesystem reset and image retirement use no further child programs. |

## Paths, repeat installation and migration

The installer accepts `X.Y.Z [--prefix ABSOLUTE_PATH] [--from-dir TRUSTED_RELEASE_DIRECTORY]`. On Linux, an administrator installation defaults to `/usr/local` for the trusted maintenance service. On macOS and under an ordinary Linux runner account, the installer creates `~/.local/bin` for public links and `${XDG_DATA_HOME:-$HOME/.local/share}/ci-utils` for releases. An explicit prefix selects its `bin/` and `libexec/ci-utils/` instead. Use `--from-dir` with a trusted offline copy of the checksum file and selected archive. Obtain the checksum file from the authenticated release or an independently verified mirror.

On macOS, follow the installer's PATH hint if the command directory is missing. For the default layout, add the following line to your shell startup file and run it in the current shell. The installer leaves shell configuration under your control. On Linux, the installer provisions the selected directories and links directly. A service can use its existing absolute entry point.

```bash
export PATH="$HOME/.local/bin:$PATH"
```

| Linux system installation path | Role |
| --- | --- |
| `/usr/local/bin/ci-*` | Eight Bash entry points on the runner's PATH. |
| `/usr/local/libexec/ci-utils/releases/` | Complete release directories keyed by version and archive digest. |
| `/usr/local/libexec/ci-utils/current` | Atomically selected release. Its `lib/` directory holds the Python implementation, release metadata and prebuilt probe. |
| `/usr/local/libexec/ci-utils/ci-docker-maintenance` | Compatibility entry point for deployed service units and job finalizers. |
| `/etc/ci-utils/host.json` and `cleanup.json` | Operator-owned host settings and cleanup policy. |
| `/var/lib/ci-utils/gate` | Example persistent admission state. The actual directory comes from `host.json`. |

Install success prints the version, architecture, source revision and prefix and exits 0. Usage and preflight failures exit 2. Download, extraction and filesystem errors return nonzero. A failed prerequisite, download or checksum leaves the active release usable. Repeat installation of the same archive reuses its release directory. To upgrade or select a previous verified native release, run its pinned bootstrap. Existing configuration, job records and reconciliation evidence survive activation.

Remove any `ci-upgrade-images` alias from your Bash startup file (such as `~/.bashrc` or `~/.bash_profile`). Clear the active alias in each existing shell. Verify that `type -a` lists the installed executable first.

```bash
command -v ci-utils
if alias ci-upgrade-images >/dev/null 2>&1; then unalias ci-upgrade-images; fi
type -a ci-upgrade-images
ci-utils --version
ci-utils-list
```

Compare the reported version and revision with the selected release. The active release stores its verified checksum in `current/lib/archive.sha256`. On Linux, `ci-docker-cleanup version` also reports the digest in JSON. For a new Linux maintenance host, review the policy, host settings, service, timers and job wrapper before provisioning the gate. On an existing host, drain participants, resolve outstanding maintenance and record the active release before switching. The installer replaces the old absolute adapter entry point. The adapter authorizes the installed release by archive digest. Keep the existing gate and run `status`, `check` and `plan` before the first apply. [Configuration and service examples](../../examples/ci-utils/) · [Maintenance and recovery](../../../docs/maintenance.md)

From the repository root, run `(cd scripts && shellspec tests/ci-utils/install_spec.sh)`. The Linux installation and daemon qualification entry point is `tests/ci-utils-native.sh`.
