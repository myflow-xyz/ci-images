# `ci-base`

`ghcr.io/myflow-xyz/ci-base` is the common parent of every job image. It is
intended for runtime-independent repository policy, shell checks, and small
Python automation scripts. It supplies the shared layer inherited by
language-specific images.

## Base and runtime

The image starts from a digest-pinned `debian:trixie-slim` OCI index.

The environment is non-interactive, UTF-8, glibc-based Debian Trixie. Debian
packages are resolved from a reviewed, Debian-signed snapshot. Direct packages
are installed at the exact architecture-specific revisions in
`images/base/debian-packages.*.lock`, and smoke tests compare every locked
revision with the built image. The slim parent omits CA certificates, so the
snapshot bootstrap uses HTTP with apt's signature verification; CA certificates
are installed before any HTTPS source download.

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

- shell and build utilities: `sh`, Bash 5.3.20, Make, coreutils, findutils, diffutils,
  grep, sed, awk, and `procps`;
- source and transfer utilities: Git, Git LFS, CA certificates, curl, wget,
  OpenSSL, tar, gzip, xz, zip, and unzip;
- CPython 3.14.8 and its standard-library modules for repository-owned CI
  automation;
- Docker CLI 29.9.0 and the Compose 5.6.0 CLI plugin;
- structured-data and diagnosis tools: `jq`, `yq`, ripgrep, and GitHub CLI;
- shared policy tools: OSV-Scanner 2.6.0, Trivy 0.75.0, gitleaks, actionlint,
  shfmt, ShellCheck, and ShellSpec;
- `tini` for descendants that require subprocess reaping.

Python is built from its checksum-pinned official 3.14.8 source release
using the reviewed Debian snapshot. This includes the current security fixes
because the matching official slim image was unavailable at selection. Its
shared-library dependencies are installed from the same snapshot. The runtime
is limited to the interpreter and standard library: the image does not include
pip, virtual-environment support, development headers, or third-party Python
packages.

Git is built from a checksum-pinned upstream source release so the protected
system configuration can scope trust to GitHub's workspace tree. jq, ripgrep,
and ShellCheck use checksum-pinned upstream release artifacts for each supported
architecture. GitHub CLI, Git LFS, actionlint, gitleaks, OSV-Scanner, shfmt,
and yq are built from exact module releases with Go 1.27.2. Trivy 0.75.0 uses
the same toolchain with the `jsonv2` build mode required by that release.
Narrow dependency overrides used to remove known vulnerabilities from released
tools are recorded in the version manifest and verified by image smoke tests.
Go tools are installed into immutable versioned directories and exposed through
stable links in `/opt/ci-tools/bin`. Compilers are build inputs and are not
retained in this image. Their pure-Go binaries are compiled on the native build
platform for each target architecture. Publication uses native AMD64 and ARM64
runners for all image stages, avoiding emulated Git and Go compilation.
Vulnerability data is not embedded in the
image; online scans by OSV-Scanner and Trivy still query or download their
external data sources.

Bash is built from the checksum-pinned GNU 5.3 source release with its twenty
reviewed upstream patches. The image's `bash`, `/bin/bash`, `/usr/bin/bash`, and
`ci` login shell use this build. Debian's Bash package remains installed for
package management, with its binary diverted so later package upgrades do not
replace the image-managed shell. Repository-owned Bash scripts require Bash 5.0
or newer; the base image exceeds that minimum.

## Docker client contract

Docker CLI and Compose are built from their exact upstream module releases with
Go 1.27.2. Go authenticates module downloads through its checksum database.
This gives the clients the current Go security fixes, which were absent from
the previous image's upstream executables. Their upstream version metadata is
retained. The image includes only the client executables; compilers remain in
the build stages.

The client is exposed through `/opt/ci-tools/bin/docker`. Compose is exposed at
`/usr/local/lib/docker/cli-plugins/docker-compose`, a root-owned system-wide
plugin location following [Docker's installation guidance][compose-install].
It remains discoverable with a fresh private `DOCKER_CONFIG`. The tools are
inherited by `ci-go`, `ci-node`, `ci-vite`, and `ci-playwright`; independently
based `ci-postgres` excludes them.

Version queries and offline Compose configuration need no daemon, socket,
network, registry credentials, or startup installation. Daemon operations
require an endpoint explicitly supplied by a trusted workflow. Installation
never grants daemon access or changes host/socket permissions. Registry
credentials remain job-scoped, preferably in a private client configuration.

The supported target range is Linux Docker Engine 28.x and 29.x,
using normal API negotiation and the API overlap with Docker CLI 29.9.0 and
Compose 5.6.0. [Docker documents negotiation as best effort][docker-api];
feature-specific consumer qualification is still required. This includes the
28.0.4 daemon listed in the [GitHub Ubuntu 24.04 runner inventory][runner-tools];
the image-managed client version does not require an identical host daemon.
The integration check records the actual daemon/API/platform and verifies
fixture startup, HTTP receipt, and owned container/network/volume cleanup after
both successful
and failed verification. Qualification of the whole version range is not
implied by a passing check against one daemon. Older daemons, Windows daemons,
rootless/user-namespace networking and remapped socket permissions need
separate qualification.

Local qualification used a Linux ARM64 client against Docker Engine 29.4.0
with API 1.54. Native AMD64/ARM64 Actions repeat the checks against their
runner daemons. Other versions in the target range have not been directly
qualified by this local run. The preflight regression covers admission of
28.x and 29.x daemons, including 28.0.4, and explicit rejection diagnostics;
it does not replace live integration qualification of those versions.

[compose-install]: https://docs.docker.com/compose/install/linux/
[docker-api]: https://docs.docker.com/reference/api/engine/
[runner-tools]: https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md

## Runtime contract

Ordinary commands run as the unprivileged `ci` user. The image provides writable
home, workspace, and `/var/tmp` directories but does not assume that an
arbitrary host bind mount is writable. Descendants provision only the
runtime-specific reusable caches they require below `/var/cache`.

The protected system Git configuration trusts the repository at `/workspace`
for direct Docker use and repositories below `/__w` for GitHub job containers.
It does not disable Git's ownership check elsewhere.

Self-hosted bind-mount permissions are defined in the
[usage guide](../usage.md#self-hosted-bind-mount-permissions).

The image intentionally excludes:

- Docker daemon, implicit socket/API access, and runtime Buildx;
- application source and dependency trees;
- application runtime toolchains and language package managers;
- third-party Python packages;
- user-scoped application configuration or state;
- repository-specific credentials, configuration, and generated output.

## Usage

Use `ci-base` directly for workflow, shell, Python automation, secret, and
runtime-independent repository policy gates. Markdown, Go, generic Node, Vite,
and browser jobs use the corresponding descendant image.
