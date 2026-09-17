# Image version inventory

This page provides one view of the explicitly pinned runtimes and first-order
tools owned by each image. Child-image sections do not repeat inherited tools.
Direct Debian packages are listed; transitive packages resolved from the
reviewed snapshot are intentionally omitted. The
[version manifest](../manifests/versions.json) and its referenced lockfiles
remain authoritative for source revisions, dependency overrides, package
revisions, checksums, and upstream image digests.

## `ci-base`

| Component | Version |
| --- | --- |
| `Git` | `2.55.0` |
| `Git LFS` | `3.8.0` |
| `GitHub CLI` | `2.101.0` |
| `CPython` | `3.14.7` |
| `actionlint` | `1.7.12` |
| `gitleaks` | `8.30.1` |
| `jq` | `1.8.2` |
| `osv-scanner` | `2.6.0` |
| `ripgrep` | `15.2.0` |
| `ShellCheck` | `0.11.0` |
| `shellspec` | `0.28.1` |
| `shfmt` | `3.14.1` |
| `Trivy` | `0.74.0` |
| `yq` | `4.53.6` |

### Direct Debian packages

These packages are installed at exact revisions from the pinned Debian
snapshot. Transitive packages remain snapshot-controlled and are covered by
the image vulnerability scan. The Debian `git` package supplies system
integration files; the exposed Git executable is the source-built version
listed above.

| Package | Version |
| --- | --- |
| `bash` | `5.2.37-2+b10` |
| `ca-certificates` | `20250419` |
| `coreutils` | `9.7-3` |
| `curl` | `8.14.1-2+deb13u5` |
| `dash` | `0.5.12-12` |
| `diffutils` | `1:3.10-4` |
| `findutils` | `4.10.0-3` |
| `gawk` | `1:5.2.1-2+b1 (amd64) / 1:5.2.1-2+b2 (arm64)` |
| `git` | `1:2.47.3-0+deb13u1` |
| `grep` | `3.11-4 (amd64) / 3.11-4+b1 (arm64)` |
| `gzip` | `1.13-1+deb13u1` |
| `locales` | `2.41-12+deb13u4` |
| `make` | `4.4.1-2` |
| `media-types` | `13.0.0` |
| `netbase` | `6.5` |
| `openssl` | `3.5.7-1~deb13u2` |
| `procps` | `2:4.0.4-9` |
| `sed` | `4.9-2+deb13u1` |
| `tar` | `1.35+dfsg-3.1` |
| `tini` | `0.19.0-3+b8` |
| `tzdata` | `2026c-0+deb13u1` |
| `unzip` | `6.0-29+deb13u1` |
| `wget` | `1.25.0-2` |
| `xz-utils` | `5.8.1-1+deb13u1` |
| `zip` | `3.0-15+deb13u1` |

## `ci-go`

| Component | Version |
| --- | --- |
| `Go` | `1.27.1` |
| `Hurl` | `8.0.1` |
| `sqlc` | `1.31.1` |
| `goose` | `3.28.0` |
| `golangci-lint` | `2.13.2` |
| `goimports` | `0.50.0` |
| `govulncheck` | `1.8.0` |

## `ci-node`

| Component | Version |
| --- | --- |
| `Node.js` | `24.21.0` |
| `npm` | `12.0.2` |
| `pnpm` | `12.4.2` |
| `markdownlint-cli2` | `0.23.2` |
| `@redocly/cli` | `2.53.3` |

## `ci-vite`

| Component | Version |
| --- | --- |
| `@typescript/native` | `7.0.2` |
| `TypeScript compatibility package` | `6.0.2` |
| `TypeScript legacy compiler` | `6.0.3` |
| `vite` | `8.3.0` |
| `vitest` | `5.0.1` |
| `@vitest/coverage-v8` | `5.0.1` |
| `oxlint` | `1.83.0` |
| `oxlint-tsgolint` | `7.0.2001` |
| `oxfmt` | `0.68.0` |

## `ci-playwright`

| Component | Version |
| --- | --- |
| `@playwright/test` | `1.63.0` |

## `ci-postgres`

| Component | Version |
| --- | --- |
| `PostgreSQL` | `18` |
| `pgvector` | `0.8.6` |
| `gosu` | `1.19` |
