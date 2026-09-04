# `ci-node`

`ghcr.io/myflow-xyz/ci-node` extends [`ci-base`](base.md) for generic Node.js
CI tasks that do not require the Vite frontend toolchain.

## Included tools

The initial image contract includes:

- Node.js 24.20.0 imported from the digest-pinned official Node image;
- npm and npx 12.0.2 from a hash-verified release artifact;
- pnpm 12.3.1 from hash-verified native Linux release artifacts;
- `markdownlint-cli2` 0.23.2;
- Redocly CLI 2.51.1 for OpenAPI validation;
- explicit npm and pnpm cache paths.

The npm release artifact is hash-verified, and its reviewed bundled dependency
replacements are installed from a committed lockfile. The architecture-matched
pnpm archive is installed independently of npm and includes its native
executable. Other Node tool dependency trees are installed from committed
lockfiles into immutable versioned directories. Stable command links are
exposed through `/opt/ci-tools/bin`.

## Runtime environment

This image adds these variables to the
[`ci-base` environment](base.md#runtime-environment):

```text
NODE_VERSION=24.20.0
NPM_CONFIG_CACHE=/var/cache/npm
PNPM_CONFIG_STORE_DIR=/var/cache/pnpm/store
```

Image-managed npm, pnpm, and Markdown commands remain in
`/opt/ci-tools/bin`.

The native pnpm executable uses the glibc Linux build. On this Debian-based
image, `libatomic1` supplies its required `libatomic.so.1` runtime library.

## Dependency authority and caches

Repository lockfiles remain authoritative. Application-owned binaries are run
through package scripts or `pnpm exec`, which must resolve the repository-local
dependency before an image-global tool.

The writable cache contract is:

```text
npm cache=/var/cache/npm
pnpm store=/var/cache/pnpm/store
```

pnpm creates a store-format directory below the configured store root. pnpm
12.3.1 retains the compatible `v11` store format; the manifest records the CLI
and store-format versions independently. The caches contain package content
only. Do not persist `node_modules`, build output, or a repository workspace.

## Usage

Use `ci-node` for generic Node maintenance, Markdown policy, and OpenAPI jobs.

Frontend projects use [`ci-vite`](vite.md). Browser jobs use
[`ci-playwright`](playwright.md).
