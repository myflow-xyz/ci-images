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
| `CPython` | `3.14.7` |
| `actionlint` | `1.7.12` |
| `gitleaks` | `8.30.1` |
| `osv-scanner` | `2.6.0` |
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
| `bash` | `5.2.15-2+b13` |
| `ca-certificates` | `20250419~deb12u1` |
| `coreutils` | `9.1-1` |
| `curl` | `7.88.1-10+deb12u15` |
| `dash` | `0.5.12-2` |
| `diffutils` | `1:3.8-4` |
| `findutils` | `4.9.0-4` |
| `gawk` | `1:5.2.1-2` |
| `gh` | `2.23.0+dfsg1-1` |
| `git` | `1:2.39.5-0+deb12u3` |
| `git-lfs` | `3.3.0-1+deb12u1` |
| `grep` | `3.8-5` |
| `gzip` | `1.12-1` |
| `jq` | `1.6-2.1+deb12u2` |
| `locales` | `2.36-9+deb12u14` |
| `make` | `4.3-4.1` |
| `media-types` | `10.0.0` |
| `netbase` | `6.4` |
| `openssl` | `3.0.20-1~deb12u2` |
| `procps` | `2:4.0.2-3` |
| `ripgrep` | `13.0.0-4+b2` |
| `sed` | `4.9-1+deb12u1` |
| `shellcheck` | `0.9.0-1` |
| `tar` | `1.34+dfsg-1.2+deb12u1` |
| `tini` | `0.19.0-1+b3` |
| `tzdata` | `2026b-0+deb12u1` |
| `unzip` | `6.0-28+deb12u1` |
| `wget` | `1.21.3-1+deb12u1` |
| `xz-utils` | `5.4.1-1+deb12u1` |
| `zip` | `3.0-13` |

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
