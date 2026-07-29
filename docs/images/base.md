# `ci-base`

`ghcr.io/myflow-xyz/ci-base` is the common parent of every job image. It is
intended for runtime-independent repository policy and shell checks and
supplies the shared layer inherited by language-specific images.

## Base and runtime

The image starts from a digest-pinned `debian:bookworm-slim` OCI index. Debian
Bookworm preserves the existing glibc and apt package contract without carrying
a language runtime.

The environment is non-interactive, UTF-8, glibc-based Debian Bookworm. Debian
packages are resolved from a reviewed, Debian-signed snapshot. The slim parent
omits CA certificates, so the snapshot bootstrap uses HTTP with apt's signature
verification; CA certificates are installed before any HTTPS source download.

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

- shell and build utilities: `sh`, Bash, Make, coreutils, findutils, diffutils,
  grep, sed, awk, and `procps`;
- source and transfer utilities: Git, CA certificates, curl, wget, OpenSSL, tar,
  gzip, xz, zip, and unzip;
- structured-data and diagnosis tools: `jq`, `yq`, ripgrep, and GitHub CLI;
- shared policy tools: gitleaks, actionlint, shfmt, ShellCheck, and ShellSpec;
- `tini` for descendants that require subprocess reaping.

actionlint, gitleaks, shfmt, and yq are built from exact module releases with
Go 1.26.5; the reviewed gitleaks dependency override is recorded in the version
manifest. Tools are installed into immutable versioned directories and exposed
through stable links in `/opt/ci-tools/bin`. The Go compiler is a build input
and is not retained in this image.

## Runtime contract

Ordinary commands run as the unprivileged `ci` user. The image provides writable
home, workspace, and `/var/tmp` directories but does not assume that an
arbitrary host bind mount is writable. Descendants provision only the
runtime-specific reusable caches they require below `/var/cache`.

The image intentionally excludes:

- Docker CLI and Docker socket access;
- application source and dependency trees;
- language runtimes and language package managers;
- user-scoped application configuration or state;
- repository-specific credentials, configuration, and generated output.

## Usage

Use `ci-base` directly for workflow, shell, secret, and runtime-independent
repository policy gates. Markdown, Go, generic Node, Vite, and browser jobs use
the corresponding descendant image.
