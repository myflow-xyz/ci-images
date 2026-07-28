# `ci-node`

`ghcr.io/myflow-xyz/ci-node` extends [`ci-base`](base.md) for generic Node.js
CI tasks that do not require the Vite frontend toolchain.

## Included tools

The initial image contract includes:

- Node.js 24.18.0 with npm and npx 12.0.1 inherited from `ci-base`;
- pnpm 11.15.1;
- Redocly CLI 2.38.0 for OpenAPI validation;
- explicit npm and pnpm cache paths.

The Node tool dependency tree is installed from a committed npm lockfile into an
immutable versioned directory. Stable command links are exposed through
`/opt/ci-tools/bin`.

## Runtime environment

The effective environment is the [`ci-base` environment](base.md#runtime-environment)
plus:

```text
PNPM_HOME=/home/ci/.local/share/pnpm
```

`PNPM_HOME` is the user-level pnpm home; image-managed commands remain in
`/opt/ci-tools/bin`. The npm cache setting is inherited unchanged from
`ci-base`.

## Dependency authority and caches

Repository lockfiles remain authoritative. Application-owned binaries are run
through package scripts or `pnpm exec`, which must resolve the repository-local
dependency before an image-global tool.

The writable cache contract is:

```text
npm cache=/var/cache/npm
pnpm store=/var/cache/pnpm
```

The caches contain package content only. Do not persist `node_modules`, build
output, or a repository workspace.

## Consumers

Use `ci-node` for generic Node maintenance and OpenAPI jobs. MyFlow Storage
Service uses it for Redocly linting.

Frontend projects use [`ci-vite`](vite.md). Browser jobs use
[`ci-playwright`](playwright.md).
