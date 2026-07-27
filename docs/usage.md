# Using the CI images

Select the narrowest image that satisfies a job. This reduces download size,
security surface, and accidental tool coupling.

## Image selection

- Use `ci-base` for repository policy, shell, and documentation checks.
- Use `ci-go` for Go build, generation, lint, test, and release jobs.
- Use `ci-node` for generic Node tasks such as Redocly OpenAPI linting.
- Use `ci-vite` for TypeScript and Vite quality, test, and build jobs.
- Use `ci-playwright` only when a job launches Chromium.
- Use `ci-postgres` as a service beside a job image, never as the job image.

## Workload patterns

- Go verification and release jobs use `ci-go`.
- Database-backed Go jobs add `ci-postgres` as a service.
- Generic Node and OpenAPI jobs use `ci-node`.
- TypeScript and Vite quality, test, coverage, and build jobs use `ci-vite`.
- Browser smoke and E2E jobs use `ci-playwright`.
- Docker Compose conformance stays on a separately controlled host runner;
  ordinary job images do not receive the Docker socket.

Repository-specific dependencies, configuration, and migrations remain in the
consumer repository rather than the shared images.

## Job-container example

Always replace the digest placeholders with promoted OCI index digests.
Container `run` steps default to `sh`, so jobs that require Bash select it
explicitly.

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: read
    container:
      image: ghcr.io/myflow-xyz/ci-go@sha256:<digest>
      credentials:
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}
    defaults:
      run:
        shell: bash
    steps:
      - uses: actions/checkout@<commit-sha>
      - run: go test ./...
```

Pin actions by full commit SHA as well as pinning the container by digest.

## PostgreSQL service example

A containerized job reaches a service by its service label and container port;
it does not use `localhost` or publish a host port.

```yaml
jobs:
  integration:
    runs-on: ubuntu-latest
    container:
      image: ghcr.io/myflow-xyz/ci-go@sha256:<digest>
    services:
      postgres:
        image: ghcr.io/myflow-xyz/ci-postgres@sha256:<digest>
        env:
          POSTGRES_DB: app_test
          POSTGRES_USER: app
          POSTGRES_PASSWORD: test-only-password
        options: >-
          --health-cmd "pg_isready -U app -d app_test"
          --health-interval 2s
          --health-timeout 5s
          --health-retries 30
    env:
      DATABASE_URL: >-
        postgres://app:test-only-password@postgres:5432/app_test?sslmode=disable
```

The service image exposes `vector` and PostgreSQL contrib support, but does not
create extensions. Repository migrations remain responsible for statements
such as:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

## Dependency caches

The images define these writable container paths:

```text
/cache/go/build
/cache/go/modules
/cache/npm
/cache/pnpm
```

On GitHub-hosted runners, save and restore these paths with the repository's
cache action. On trusted self-hosted runners, they may instead be bind-mounted
from partitioned directories below `/opt/actions-runner/shared/cache`.

A cache key includes:

- repository or equivalent trust domain;
- operating system and architecture;
- exact runtime version;
- `go.sum` or package-manager lockfile hash;
- relevant compiler or tool configuration.

Never cache a repository workspace, `node_modules`, credentials, release
artifacts, or PostgreSQL data. Every workflow must support an uncached rebuild.

## Version compatibility

Jobs verify their declared runtime and critical tool versions before relying on
the image:

- Go jobs compare `go version` with `go.mod` and any `toolchain` directive.
- Node jobs compare `node --version` and `pnpm --version` with repository
  declarations.
- Vite jobs use repository-local tools and treat the bundled tool versions as a
  compatibility and smoke-test baseline.
- Playwright jobs compare their lockfile-managed Playwright version with
  `PLAYWRIGHT_VERSION` before launching the bundled browser.

Do not fall back to downloading a different runtime or browser during a job.
Update and republish the shared image, or select an older compatible digest.

## Self-hosted runner ownership

Job images use a fixed unprivileged user. Before enabling bind-mounted caches,
provision the host directories so the image user can write them. Verify
checkout, artifact staging, and cache writes on both AMD64 and ARM64.

Do not solve an ownership mismatch by running ordinary jobs as root. Reconcile
the runner and container numeric ownership contract instead.
