# MyFlow CI Images

`ci-images` defines the reusable Linux job and service images used by MyFlow GitHub Actions workflows. The images centralize stable runtimes and CI tooling without making them authoritative for application dependencies.

## Image hierarchy

```text
debian:trixie-slim@<digest>
└── ci-base
    ├── ci-go
    ├── ci-utils
    ├── ci-net
    └── ci-node
        └── ci-vite
            └── ci-playwright

pgvector/pgvector:0.8.7-pg18-trixie@<digest>
└── ci-postgres
```

`ci-base` builds CPython 3.15.2 from its checksum-pinned official source release with the reviewed Debian snapshot. `ci-node` installs Node 26.13.1 from checksum-pinned official Linux binary archives.

- `ghcr.io/myflow-xyz/ci-base`: operating-system utilities, Python 3.15.2 standard-library scripting, Docker CLI with Compose and Buildx, and shared policy tools including OSV-Scanner and Trivy.
- `ghcr.io/myflow-xyz/ci-go`: Go toolchain, native race-test prerequisites, and reusable Go CI executables.
- `ghcr.io/myflow-xyz/ci-utils`: runner image refresh, guarded Docker cleanup, and explicit Go and pnpm cache resets. Its runtime inherits `ci-base`.
- `ghcr.io/myflow-xyz/ci-net`: network diagnostics and isolated network tests, with explicit namespace and capability constraints in its [image contract](docs/images/net.md).
- `ghcr.io/myflow-xyz/ci-node`: generic Node.js, Markdown, and OpenAPI jobs that do not require a frontend toolchain.
- `ghcr.io/myflow-xyz/ci-vite`: TypeScript, Vite, Vitest, Oxlint, and Oxfmt quality and build jobs.
- `ghcr.io/myflow-xyz/ci-playwright`: Vite jobs that also require a version-matched Chromium browser.
- `ghcr.io/myflow-xyz/ci-postgres`: PostgreSQL 18 service jobs requiring pgvector and PostgreSQL contrib extensions.

The seven job images support GitHub Actions `jobs.<job_id>.container`. `ci-postgres` is an independent service-image lineage and never inherits from a job image.

Repository-owned Bash scripts require Bash 5.0 or newer. `ci-base` and its job image descendants provide Bash 5.3.20.

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

Browse [the documentation index](docs/index.md) for detailed image contracts. Use [the usage guide](docs/usage.md) to select and pin an image, and follow [the release guide](docs/release.md) when publishing a stable suite version.

## Upgrade runner images

On the Linux runner, set `CI_UTILS_IMAGE` to a locally cached utility image that includes the version-aware upgrade helper. Use its numeric tag or digest if available. Omit registry credentials for publicly readable images. For private packages, set `GHCR_USER` and a classic `GHCR_TOKEN` with `read:packages` access.

```bash
CI_UTILS_IMAGE=ghcr.io/myflow-xyz/ci-utils:latest
docker run --rm --pull=never --network=none "$CI_UTILS_IMAGE" ci-utils-list

printf '%s\n' "${GHCR_TOKEN:-}" |
  docker run \
    --rm \
    --interactive \
    --pull=never \
    --mount type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock,readonly \
    --group-add "$(stat -c %g /var/run/docker.sock)" \
    --tmpfs /var/tmp:mode=1777 \
    --env DOCKER_CONFIG=/var/tmp/ghcr \
    --env "GHCR_USER=${GHCR_USER:-}" \
    "$CI_UTILS_IMAGE" sh -ec '
      if [ -n "$GHCR_USER" ]; then
        docker --host unix:///var/run/docker.sock login ghcr.io \
          --username "$GHCR_USER" \
          --password-stdin
      fi
      exec ci-upgrade-images
    '
```

The refresh container needs HTTPS access to `api.github.com` and `ghcr.io` to verify release tags. With only the utility image cached, the command refreshes `ci-utils` itself. Pull each other suite image once to include it in future runs.

The report names the exact version and the default keeps old tags. Copy the reported reference to confirm that it and the local `:latest` resolve to the same image ID.

```bash
docker image inspect --format '{{.Id}}' \
  ghcr.io/myflow-xyz/ci-utils:0.0.26 \
  ghcr.io/myflow-xyz/ci-utils:latest
```

Use the reported version in place of `0.0.26`. See [image upgrade details](docs/images/utils.md#refresh-cached-ci-images) and [scheduled maintenance](docs/maintenance.md#refresh-cached-ci-images).

## Local image verification

After building a target with `tests/build-local-image.sh <target>`, use `tests/scan-local-image.sh <target>` to scan its local `ci-<target>:test` image before pushing. The helper requires Trivy in the developer environment, restricts the image source to the local Docker daemon, and applies the publish policy: fixed HIGH or CRITICAL operating-system and library vulnerabilities fail the scan. Use `all` to scan all eight local images. Local verification covers the host platform; CI remains responsible for both published architectures.

## Design boundaries

- Application lockfiles and Go modules remain authoritative.
- Published images and upstream base images are consumed by immutable digest.
- Direct downloads are checksum-verified. Direct Debian packages and npm dependency graphs use committed lockfiles, and Go executables are built from exact module versions or source commits with reviewed security overrides.
- Images contain no application source, credentials, generated output, or mutable service data.
- Job images run as the non-root `ci` user with UID `1001` for GitHub-hosted job-container compatibility and primary GID `2001`. Self-hosted bind mounts delegate write access through the dedicated host group `mfci` with GID `2001`, rather than matching the runner UID or using root.
- Job images do not imply Docker daemon access.
- Writable caches are mounted explicitly and partitioned by trust domain, runtime, architecture, and dependency lock hash.

## License

This repository is licensed under the [GNU Affero General Public License v3.0](LICENSE).
