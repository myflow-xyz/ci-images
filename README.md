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

`ci-base` builds CPython 3.14.7 from a checksum-pinned source release.
`ci-node` imports its Node runtime from the digest-pinned
`node:24.19.0-bookworm-slim` image without adding Node to `ci-base`.

- `ghcr.io/myflow-xyz/ci-base`: operating-system utilities, Python 3.14.7
  standard-library scripting, OSV-Scanner, Trivy, and runtime-independent
  repository policy tools.
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
│   ├── index.md      # documentation map
│   ├── release.md    # versioning, promotion, and verification
│   ├── versions.md   # version inventory by image
│   └── usage.md      # authentication and consumer workflow guidance
├── images/           # Dockerfiles and immutable installation inputs
├── manifests/        # reviewed versions, digests, source pins, and checksums
├── scripts/          # self-hosted runner administration helpers
├── tests/            # static contracts and image smoke tests
└── .github/
    └── workflows/    # verification and GHCR publication
```

Browse [the documentation index](docs/index.md) for detailed image contracts.
Use [the usage guide](docs/usage.md) to select and pin an image, and follow
[the release guide](docs/release.md) when publishing a stable suite version.

## Local image verification

After building a target with `tests/build-local-image.sh <target>`, use
`tests/scan-local-image.sh <target>` to scan its local `ci-<target>:test` image
before pushing. The helper requires Trivy in the developer environment,
restricts the image source to the local Docker daemon, and applies the publish
policy: fixed HIGH or CRITICAL operating-system and library vulnerabilities
fail the scan. Use `all` to scan all six local images. Local verification covers
the host platform; CI remains responsible for both published architectures.

## Design boundaries

- Application lockfiles and Go modules remain authoritative.
- Published images and upstream base images are consumed by immutable digest.
- Direct downloads are checksum-verified. npm dependency graphs use committed
  lockfiles, and Go executables are built from exact module versions or source
  commits with reviewed security overrides.
- Images contain no application source, credentials, generated output, or
  mutable service data.
- Job images run as the non-root `ci` user with UID `1001` for GitHub-hosted
  job-container compatibility and primary GID `2001`. Self-hosted bind mounts
  delegate write access through the dedicated host group `mfci` with GID
  `2001`, rather than matching the runner UID or using root.
- Job images do not imply Docker daemon access.
- Writable caches are mounted explicitly and partitioned by trust domain,
  runtime, architecture, and dependency lock hash.

## License

This repository is licensed under the [GNU Affero General Public License
v3.0](LICENSE).
