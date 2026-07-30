# Using the CI images

Select the narrowest image that satisfies a job. This reduces download size,
security surface, and accidental tool coupling.

## Image selection

- Use `ci-base` for repository policy, shell, Python standard-library
  automation, and documentation checks.
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

## Pulling and pinning

The current GHCR packages are private. For local access, authenticate with a
personal access token (classic) that has `read:packages` and an account that can
read the packages:

```bash
printf '%s\n' "$GHCR_TOKEN" |
  docker login ghcr.io --username <github-user> --password-stdin
```

Use a stable version to discover the release digest:

```bash
docker buildx imagetools inspect ghcr.io/myflow-xyz/ci-go:v0.1.0
```

Compare the reported OCI index digest with the digest table in the matching
GitHub Release. Then pull or configure the shared release tag pinned to that
index digest:

```bash
docker pull ghcr.io/myflow-xyz/ci-go:v0.1.0@sha256:<digest>
```

The container runtime selects AMD64 or ARM64 from the index automatically.
Architecture-specific suffix tags are not required. Use `vX.Y.Z` for stable
release discovery, `latest` only to inspect the current verified `main` suite,
and `edge` only for integration testing. Do not consume candidate or
run-specific tags.

For a private package in GitHub Actions, grant the consumer repository read
access to each package, set `packages: read`, and authenticate with its
`GITHUB_TOKEN`. Public packages can be pulled anonymously.

## Job-container example

Always replace the digest placeholders with promoted OCI index digests.
Container `run` steps default to `sh`, so jobs that require Bash select it
explicitly. Job images use UID `1001` so the non-root process can write the
workspace and file-command mounts created by standard Linux GitHub-hosted
runners.

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: read
    container:
      image: ghcr.io/myflow-xyz/ci-go:v0.1.0@sha256:<digest>
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
    permissions:
      contents: read
      packages: read
    container:
      image: ghcr.io/myflow-xyz/ci-go:v0.1.0@sha256:<digest>
      credentials:
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}
    services:
      postgres:
        image: ghcr.io/myflow-xyz/ci-postgres:v0.1.0@sha256:<digest>
        credentials:
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
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
/var/cache/go/build
/var/cache/go/mod
/var/cache/npm
/var/cache/pnpm/store
```

On GitHub-hosted runners, save and restore these paths with the repository's
cache action. On trusted self-hosted runners, they may instead be bind-mounted
from matching tool directories below `/opt/actions-runner/shared/cache`, such
as `go` mounted at `/var/cache/go` and `pnpm` mounted at
`/var/cache/pnpm`.

A cache-action key includes:

- repository or equivalent trust domain;
- operating system and architecture;
- exact runtime version;
- `go.sum` or package-manager lockfile hash;
- relevant compiler or tool configuration.

Never cache a repository workspace, `node_modules`, credentials, release
artifacts, or PostgreSQL data. Every workflow must support an uncached rebuild.
Temporary build artifacts belong below `/var/tmp` and are never restored as
caches.

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

## Self-hosted bind-mount permissions

This setup is needed only when a job intentionally bind-mounts host workspaces
or caches. Jobs without those mounts do not need the host group or permission
helper.

A bind mount retains its host ownership, modes, ACLs, and mount flags; the image
does not grant automatic access. The image defines its runtime identity and
container-side tool configuration. The runner operator enrolls only selected
bind sources in the shared-group contract, while workflows and host policy
remain responsible for every other mount.

Job images retain the fixed unprivileged `ci` identity with UID `1001` and
primary GID `2001`. A self-hosted runner grants access to bind-mounted
workspaces and caches through the dedicated host group `mfci` with GID `2001`.
The runner user's UID does not need to match the container UID.

Linux evaluates the numeric GID rather than the group name. The container group
is named `ci`, while the host group is named `mfci`; both use GID `2001`. Do not
use the host's `docker` group: it governs Docker daemon access and is outside
the filesystem-sharing boundary.

### Host setup

Reserve GID `2001` across the controlled runner fleet. This value is a MyFlow
convention, not a globally reserved Linux group, so verify that the lookup
returns no existing group before provisioning it. Do not repurpose an existing
group. Install the host's `acl` package and drain every affected runner before
changing an existing work tree.

The independent
[runner permission helper](../scripts/docs/setup-runner-permissions.md)
documents host provisioning, supported layouts, safety boundaries, and its
test contract. It manages only repository `_work` trees and `shared/cache`; it
does not make runner installation directories group-writable. Unsafe write
access on their unmanaged parents is rejected for the runner operator to fix.

An opt-in host preflight may run the helper with `--check` directly from a
host-side step inherited from the runner service. It verifies the invoking
runner process's effective shared-group membership in addition to the host
filesystem state. It must fail the job rather than repair a runner. The runner
operator applies changes and restarts the service separately before the
workflow is rerun.

The runner account owns each managed `_work` or `shared/cache` root. Files and
directories created below those roots may retain the container UID; the shared
GID and inherited permissions provide cross-UID access.

Pre-create every exact cache bind source before Docker starts a job. Docker may
otherwise create a missing source with unsuitable ownership.

Share a tool cache only among repositories in the same trust domain. For
mutually untrusted workloads, add a repository or trust-domain partition below
the tool directory and mount that partition instead.

### Job-container setup

The container's primary GID already matches `mfci`, so the recommended
configuration does not require `--group-add`. Mount only the directories the
job requires. The host setup must have created and normalized every bind source
before the job starts.

```yaml
jobs:
  test:
    runs-on: [self-hosted, linux]
    container:
      image: ghcr.io/myflow-xyz/ci-go:v0.1.0@sha256:<digest>
      volumes:
        - >-
          /opt/actions-runner/shared/cache/go:/var/cache/go
    defaults:
      run:
        shell: bash
    steps:
      - uses: actions/checkout@<commit-sha>
      - run: go test ./...
```

The same runtime contract for direct Docker invocation is:

```bash
docker run --rm \
  --mount type=bind,src=<host-directory>,dst=/workspace \
  ghcr.io/myflow-xyz/ci-base:v0.1.0@sha256:<digest>
```

### Existing host group

Docker can add any existing host GID to the image process as a supplementary
group. For example, if the runner account is `ci-user` and the writable mount
group is `ci-group`:

```bash
getent group ci-group
groups ci-user
```

Provision the runner account and writable trees with the independent
[runner permission helper](../scripts/docs/setup-runner-permissions.md), using
`ci-user` as its owner and `ci-group` as its group.

Use the numeric GID reported in the third field of `getent` output. Store that
value as the repository or organization variable `CI_GROUP_GID`, then pass it
when GitHub Actions creates the job container. Every runner selected by the job
must use the same GID for `ci-group`.

```yaml
jobs:
  test:
    runs-on: [self-hosted, linux]
    container:
      image: ghcr.io/myflow-xyz/ci-go:v0.1.0@sha256:<digest>
      options: --group-add ${{ vars.CI_GROUP_GID }}
    steps:
      - uses: actions/checkout@<commit-sha>
      - run: go test ./...
```

For direct Docker invocation, resolve and pass the same numeric GID:

```bash
ci_group_gid=$(getent group ci-group | cut -d: -f3)
test -n "$ci_group_gid"
docker run --rm \
  --group-add "$ci_group_gid" \
  --mount type=bind,src=<host-directory>,dst=/workspace \
  ghcr.io/myflow-xyz/ci-base:v0.1.0@sha256:<digest>
```

The mounted directory must use `ci-group` group ownership and group-write,
setgid, and default-ACL permissions equivalent to the recommended `mfci`
setup. Restart the runner service after changing `ci-user` group membership.
The image's primary `ci` GID remains `2001`; the host group name does not need
to exist in the container.

This contract covers rootful Linux Docker without user-namespace remapping.
Rootless Docker and `userns-remap` require mapping-aware host provisioning and
are outside the image contract. Do not replace the group contract with root,
world-writable directories, or a mounted Docker socket.

## References

- [GitHub Container registry authentication and pulling][container-registry]
- [GitHub Packages permissions][package-permissions]
- [GitHub job container options][job-container-options]
- [Docker supplementary groups][docker-supplementary-groups]

[container-registry]: https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
[docker-supplementary-groups]: https://docs.docker.com/engine/containers/run/#additional-groups
[job-container-options]: https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/run-jobs-in-a-container#setting-container-resource-options
[package-permissions]: https://docs.github.com/en/packages/learn-github-packages/about-permissions-for-github-packages
