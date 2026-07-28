# MyFlow CI Images

`ci-images` defines the reusable Linux job and service images used by MyFlow
GitHub Actions workflows. The images centralize stable runtimes and CI tooling
without making them authoritative for application dependencies.

## Image hierarchy

```text
debian:bookworm-slim@<digest>
└── ci-base
    ├── ci-go
    └── ci-node
        └── ci-vite
            └── ci-playwright

pgvector/pgvector:0.8.2-pg18-bookworm@<digest>
└── ci-postgres
```

`ci-node` imports its Node runtime from the digest-pinned
`node:24.18.0-bookworm-slim` image without adding Node to `ci-base`.

- `ghcr.io/myflow-xyz/ci-base`: operating-system utilities and
  runtime-independent repository policy tools.
- `ghcr.io/myflow-xyz/ci-go`: Go toolchain, native race-test prerequisites,
  and reusable Go CI executables.
- `ghcr.io/myflow-xyz/ci-node`: generic Node.js, Markdown, and OpenAPI jobs
  that do not require a frontend toolchain.
- `ghcr.io/myflow-xyz/ci-vite`: TypeScript, Vite, Vitest, Oxlint, and Oxfmt
  quality and build jobs.
- `ghcr.io/myflow-xyz/ci-playwright`: Vite jobs that also require a
  version-matched Chromium browser.
- `ghcr.io/myflow-xyz/ci-postgres`: PostgreSQL 18 service jobs requiring
  pgvector and PostgreSQL contrib extensions.

The five job images support GitHub Actions `jobs.<job_id>.container`.
`ci-postgres` is an independent service-image lineage and never inherits from a
job image.

## Repository structure

```text
.
├── docs/
│   ├── images/       # image contracts and included tools
│   ├── index.md      # architecture and design boundaries
│   ├── release.md    # versioning, promotion, and verification
│   └── usage.md      # authentication and consumer workflow guidance
├── images/           # Dockerfiles and immutable installation inputs
├── manifests/        # reviewed versions, digests, source pins, and checksums
├── tests/            # static contracts and image smoke tests
└── .github/
    └── workflows/    # verification and GHCR publication
```

Start with [the design overview](docs/index.md), use
[the consumer guide](docs/usage.md) to select and pin an image, and follow
[the release guide](docs/release.md) when publishing a stable suite version.

## Design boundaries

- Application lockfiles and Go modules remain authoritative.
- Published images and upstream base images are consumed by immutable digest.
- Direct downloads are checksum-verified. npm dependency graphs use committed
  lockfiles, and Go executables are built from exact module versions or source
  commits with reviewed security overrides.
- Images contain no application source, credentials, generated output, or
  mutable service data.
- Job images run as a non-root user and do not imply Docker daemon access.
- Writable caches are mounted explicitly and partitioned by repository, runtime,
  architecture, and dependency lock hash.

## License

This repository is licensed under the [GNU Affero General Public License
v3.0](LICENSE).
