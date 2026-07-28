# `ci-base`

`ghcr.io/myflow-xyz/ci-base` is the common parent of every job image. It is
intended for repository policy, shell, and documentation checks and supplies
the shared layer inherited by language-specific images.

## Base and runtime

The image starts from a digest-pinned
`node:24.18.0-bookworm-slim` OCI index. Node is present at this level because
the shared Markdown policy uses `markdownlint-cli2`.

The environment is non-interactive, UTF-8, glibc-based Debian Bookworm. Debian
packages are resolved from a reviewed, Debian-signed snapshot. The slim parent
omits CA certificates, so the snapshot bootstrap uses HTTP with apt's signature
verification; CA certificates are installed before any HTTPS source download.

## Included tools

The base image includes:

- shell and build utilities: `sh`, Bash, Make, coreutils, findutils, diffutils,
  grep, sed, awk, and `procps`;
- source and transfer utilities: Git, CA certificates, curl, wget, OpenSSL, tar,
  gzip, xz, zip, and unzip;
- structured-data and diagnosis tools: `jq`, `yq`, ripgrep, and GitHub CLI;
- shared policy tools: gitleaks, actionlint, shfmt, ShellCheck, ShellSpec, and
  `markdownlint-cli2`;
- Node.js 24.18.0 with npm and npx from a locked npm 12.0.1 package;
- `tini` for descendants that require subprocess reaping.

The npm runtime, its reviewed vulnerable-dependency replacement,
`markdownlint-cli2`, and their dependency trees are installed from committed
npm lockfiles. actionlint, gitleaks, shfmt, and yq are built from exact module
releases with Go 1.26.5; the reviewed gitleaks dependency override is recorded
in the version manifest. Tools are installed into immutable versioned
directories and exposed through stable links in `/opt/ci-tools/bin`. The Go
compiler is a build input and is not retained in this image.

## Runtime contract

Ordinary commands run as the unprivileged `ci` user. The image provides writable
home and temporary directories but does not assume that an arbitrary host bind
mount is writable.

The image intentionally excludes:

- Docker CLI and Docker socket access;
- application source and dependency trees;
- language runtimes other than the Node runtime required by common tools;
- repository-specific credentials, configuration, and generated output.

## Consumers

Use `ci-base` directly for shared documentation, workflow, shell, secret, and
repository policy gates. Go, generic Node, Vite, and browser jobs use a
descendant image instead.
