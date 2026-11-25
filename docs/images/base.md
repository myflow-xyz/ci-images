# `ci-base`

`ghcr.io/myflow-xyz/ci-base` is the common parent of every job image. It is intended for runtime-independent repository policy, shell checks, and small Python automation scripts. It supplies the shared layer inherited by language-specific images.

## Base and runtime

The image starts from a digest-pinned `debian:trixie-slim` OCI index.

The environment is non-interactive, UTF-8, glibc-based Debian Trixie. Debian packages are resolved from a reviewed, Debian-signed snapshot. Direct packages are installed at the exact architecture-specific revisions in `images/base/debian-packages.*.lock`, and smoke tests compare every locked revision with the built image. The slim parent omits CA certificates, so the snapshot bootstrap uses HTTP with apt's signature verification; CA certificates are installed before any HTTPS source download.

## Runtime environment

The image defines this repository-owned runtime environment:

```text
CI=true
DEBIAN_FRONTEND=noninteractive
HOME=/home/ci
LANG=en_US.utf8
LC_ALL=en_US.utf8
PATH=/opt/ci-tools/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
TMPDIR=/var/tmp
TZ=UTC
```

## Included tools

The base image includes:

- shell and build utilities: `sh`, Bash 5.3.20, Make, coreutils, findutils, diffutils, grep, sed, awk, and `procps`;
- Source and transfer tools include Git, Git LFS, CA certificates, curl, wget, OpenBSD netcat (`nc`), OpenSSL, tar, gzip, xz, zip, and unzip.
- CPython 3.15.2 and its standard-library modules for repository-owned CI automation;
- Docker CLI 29.10.1, Compose 5.8.0, and Buildx 0.39.1;
- structured-data and diagnosis tools: `jq`, `yq`, ripgrep, and GitHub CLI;
- shared policy tools: OSV-Scanner 2.7.1, Trivy 0.76.2, gitleaks, actionlint, shfmt, ShellCheck, and ShellSpec;
- `tini` for descendants that require subprocess reaping.

Python is built from its checksum-pinned official 3.15.2 source release. Its shared-library dependencies use pinned Debian packages. The Python XML parser uses the system Expat package, so a security update to that package also updates Python's parser. The runtime contains the interpreter and standard library.

Git is built from a checksum-pinned upstream source release so the protected system configuration can scope trust to GitHub's workspace tree. GitHub CLI, jq, ripgrep, and ShellCheck use checksum-pinned upstream release artifacts for each supported architecture. Git LFS, actionlint, gitleaks, OSV-Scanner, shfmt, and yq are built from exact module releases with Go 1.27.4. Trivy 0.76.2 uses the same toolchain with the `jsonv2` build mode required by that release. Narrow dependency overrides used to remove known vulnerabilities from released tools are recorded in the version manifest and verified by image smoke tests. Go tools are installed into immutable versioned directories and exposed through stable links in `/opt/ci-tools/bin`. Compilers are build inputs and are not retained in this image. Their pure-Go binaries are compiled on the native build platform for each target architecture. Publication uses native AMD64 and ARM64 runners for all image stages, avoiding emulated Git and Go compilation. Vulnerability data is not embedded in the image; online scans by OSV-Scanner and Trivy still query or download their external data sources.

Bash is built from the checksum-pinned GNU 5.3 source release with its twenty reviewed upstream patches. The image's `bash`, `/bin/bash`, `/usr/bin/bash`, and `ci` login shell use this build. Debian's Bash package remains installed for package management, with its binary diverted so later package upgrades do not replace the image-managed shell. Repository-owned Bash scripts require Bash 5.0 or newer; the base image exceeds that minimum.

## Docker client contract

Docker CLI and Compose are built from their exact upstream module releases with Go 1.27.4. Go authenticates module downloads through its checksum database. This gives the clients the current Go security fixes, which were absent from the previous image's upstream executables. Their upstream version metadata is retained. The image includes only the client executables; compilers remain in the build stages.
Buildx uses the same Go toolchain. The build verifies the pinned Buildx source commit and module checksum, then applies the dependency versions recorded in the [version manifest](../../manifests/versions.json).

The client is exposed through `/opt/ci-tools/bin/docker`. Compose and Buildx are installed under `/usr/local/lib/docker/cli-plugins`, a root-owned system-wide plugin location following [Docker's installation guidance][compose-install]. Both plugins are discoverable with a fresh private `DOCKER_CONFIG` and are inherited by all images derived from `ci-base`.

Version queries and offline Compose configuration need no daemon, socket, network, registry credentials, or startup installation. Daemon operations require an endpoint explicitly supplied by a trusted workflow. Installation never grants daemon access or changes host/socket permissions. Registry credentials remain job-scoped, preferably in a private client configuration.

The supported target range is Linux Docker Engine 28.x and 29.x, using normal API negotiation and the API overlap with Docker CLI 29.10.1 and Compose 5.8.0. [Docker documents negotiation as best effort][docker-api]; feature-specific consumer qualification is still required. This includes the 28.0.4 daemon listed in the [GitHub Ubuntu 24.04 runner inventory][runner-tools]; the image-managed client version does not require an identical host daemon. The integration check records the actual daemon/API/platform and verifies fixture startup, HTTP receipt, and owned container/network/volume cleanup after both successful and failed verification. Qualification of the whole version range is not implied by a passing check against one daemon. Older daemons, Windows daemons, rootless/user-namespace networking and remapped socket permissions need separate qualification.

Native AMD64 and ARM64 Actions run the integration check against their runner daemons. The preflight checks separately cover admission of 28.x and 29.x daemons, including 28.0.4, and rejection diagnostics.

[compose-install]: https://docs.docker.com/compose/install/linux/
[docker-api]: https://docs.docker.com/reference/api/engine/
[runner-tools]: https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md

## Runtime contract

Ordinary commands run as the unprivileged `ci` user. The image provides writable home, workspace, and `/var/tmp` directories but does not assume that an arbitrary host bind mount is writable. Descendants provision only the runtime-specific reusable caches they require below `/var/cache`.

The protected system Git configuration trusts the repository at `/workspace` for direct Docker use and repositories below `/__w` for GitHub job containers. It does not disable Git's ownership check elsewhere.

Self-hosted bind-mount permissions are defined in the [usage guide](../usage.md#self-hosted-bind-mount-permissions).

The image intentionally excludes:

- Docker daemon and implicit socket/API access;
- application source and dependency trees;
- application runtime toolchains and language package managers;
- third-party Python packages;
- user-scoped application configuration or state;
- repository-specific credentials, configuration, and generated output.

## Usage

Use `ci-base` directly for workflow, shell, Python automation, secret, and runtime-independent repository policy gates. Markdown, Go, generic Node, Vite, and browser jobs use the corresponding descendant image.
