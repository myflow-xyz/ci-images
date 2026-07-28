# CI image design

This repository owns the reusable Linux execution environments for MyFlow
GitHub Actions jobs. It separates image lifecycle and security maintenance from
application repositories while keeping application dependency manifests
authoritative.

## Architecture

```text
node:24.18.0-bookworm-slim@<digest>
└── ci-base
    ├── ci-go
    └── ci-node
        └── ci-vite
            └── ci-playwright

pgvector/pgvector:0.8.2-pg18-bookworm@<digest>
└── ci-postgres
```

The inheritance graph reflects actual reuse:

- `ci-base` carries Node because shared policy tools include Node applications.
- `ci-go` adds Go without inheriting the `ci-node` or frontend tool bundles.
- `ci-node` adds package-management and generic Node CI tools.
- `ci-vite` adds the frontend quality and build tool bundle.
- `ci-playwright` adds the browser matched to the repository Playwright release.
- `ci-postgres` preserves its upstream PostgreSQL entrypoint and filesystem
  contract on a separate service-image lineage.

See [the image catalog](#image-catalog) for each detailed contract.

## Image catalog

- [`ci-base`](images/base.md) provides common operating-system, policy, and
  diagnostic tools.
- [`ci-go`](images/go.md) provides the Go toolchain and reusable Go CI
  executables.
- [`ci-node`](images/node.md) provides pnpm and generic Node/OpenAPI tooling.
- [`ci-vite`](images/vite.md) provides the Vite ecosystem quality and build
  bundle.
- [`ci-playwright`](images/playwright.md) provides version-matched Chromium.
- [`ci-postgres`](images/postgres.md) provides PostgreSQL 18 and pgvector as a
  service.

## Design rules

### Reproducible inputs

- Upstream images are selected by immutable OCI digest.
- Directly downloaded archives are verified against reviewed SHA-256 values.
- Node tool dependency trees are committed as npm lockfiles.
- Go executables are source-built with the pinned Go toolchain from exact
  module versions or source commits. Reviewed dependency overrides are recorded
  in the version manifest.
- Debian packages are resolved from a reviewed snapshot rather than a moving
  package mirror.
- Published images carry source revision, version-manifest, SBOM, and provenance
  metadata.

The version manifest is the review surface for updating upstream images,
runtimes, source revisions, security overrides, and direct downloads. Native
lock data remains beside the build input that consumes it.

### Repository authority

The images accelerate jobs; they do not replace repository dependency
management:

- `go.mod` and `go.sum` own Go library versions.
- `package.json` and the frozen package-manager lockfile own application and
  frontend package versions.
- Repository scripts invoke local Node executables through package scripts or
  `pnpm exec`.
- A version mismatch fails visibly instead of silently substituting an
  image-global executable.

### Runtime isolation

Job images run as an unprivileged CI user. They contain no Docker socket,
credentials, application source, generated output, or service state.

Writable dependency caches are external inputs. Consumers partition them by
repository or equivalent trust domain, architecture, runtime version, and
dependency lock hash. Jobs must retain a cache-bypass path because restored
caches are untrusted.

`ci-postgres` runs as its upstream database user. A new service container is
created for each job; schemas, roles, extensions, and test data remain
repository-owned.

### Platform support

Every published image name resolves to one OCI index containing:

- `linux/amd64` for GitHub-hosted Linux jobs;
- `linux/arm64` for MyFlow self-hosted Linux jobs.

Consumer workflows pin the platform-independent index digest. A publication is
not promoted unless both platform images pass their image-specific smoke tests.

## Build and release model

Parent changes rebuild every descendant:

1. `ci-base` is built and verified.
2. `ci-go` and `ci-node` consume the resulting `ci-base` digest.
3. `ci-vite` consumes the resulting `ci-node` digest.
4. `ci-playwright` consumes the resulting `ci-vite` digest.
5. `ci-postgres` builds independently from its pgvector base.

Publication produces immutable digests and descriptive tags. Tags are discovery
aids; consumers use digests. A promoted digest must have:

- image-specific smoke results;
- an SBOM and build provenance;
- vulnerability scans with no fixed HIGH or CRITICAL finding in either
  platform image;
- a retained previous digest for rollback.

Read [the usage guide](usage.md) for job-container and service-container
contracts.

## Scope boundaries

This repository does not:

- package application runtimes for production deployment;
- own application dependencies or database migrations;
- provide a privileged Docker-in-Docker environment;
- replace macOS tooling for jobs that cannot run in Linux containers;
- package repository-specific Redis, Tyk, Nginx, Grafana, or Prometheus
  services.

Docker Compose conformance jobs remain on a separately controlled runner unless
a dedicated privileged image contract is designed.

## References

- [GitHub Actions: running jobs in a container][job-containers]
- [GitHub Actions: service containers][service-containers]
- [GitHub Actions: dependency caching][dependency-caching]
- [Playwright Docker guidance][playwright-docker]
- [pgvector Docker images][pgvector-docker]

[dependency-caching]: https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching
[job-containers]: https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/run-jobs-in-a-container
[pgvector-docker]: https://github.com/pgvector/pgvector#docker
[playwright-docker]: https://playwright.dev/docs/docker
[service-containers]: https://docs.github.com/en/actions/tutorials/use-containerized-services/use-docker-service-containers
