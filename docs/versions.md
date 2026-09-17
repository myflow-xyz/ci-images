# Image version inventory

This page provides one view of the explicitly pinned runtimes and first-order
tools owned by each image. Child-image sections do not repeat inherited tools.
Transitive dependencies and Debian packages resolved from the reviewed snapshot
are intentionally omitted. The [version manifest](../manifests/versions.json)
remains authoritative for source revisions, dependency overrides, checksums,
and upstream image digests.

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
