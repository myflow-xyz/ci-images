# CI utilities

`ghcr.io/myflow-xyz/ci-utils` provides reusable CI maintenance commands. It derives
from `ci-base` and adds Docker Buildx and `ci-docker-cleanup`. There is no separate
cleanup image. It follows the suite's existing version and digest promotion rules.

The build reuses `ci-go` to compile Buildx and the internal capability checker.
The final image copies those binaries into `ci-base`; it does not add the Go
toolchain or the `ci-go` runtime environment. Buildx source and its required
security fix are pinned in `manifests/versions.json`. The upstream binary failed
the image scan on fixed Go and `go-archive` vulnerabilities. The internal BuildKit
probe checks the selected backend's advertised cache-space capability before
cleanup. The cleanup policy and execution use Python's standard library.

## Commands

```sh
docker run --rm ghcr.io/myflow-xyz/ci-utils:<suite-version>
docker run --rm ghcr.io/myflow-xyz/ci-utils:<suite-version> ci-docker-cleanup --help
docker run --rm ghcr.io/myflow-xyz/ci-utils:<suite-version> ci-docker-cleanup version
docker run --rm ghcr.io/myflow-xyz/ci-utils:<suite-version> bash --version
```

The image default prints its tool catalog without a Docker daemon. Commands are
directly callable. `ci-docker-cleanup` defaults to `plan` and requires a valid
policy and explicit local endpoint. It supports `check`, `plan`, `apply`, and
`version`. Build identity uses the source revision; the shared suite tag and OCI
digest identify the promoted artifact.

Use the [host maintenance adapter](../maintenance.md) for apply. A direct Docker
socket mount or a Boolean environment flag cannot authorize deletion. The host
must coordinate every participant that uses the selected daemon.

## Cleanup policy

| Resource | Default selection |
| --- | --- |
| Containers | Explicitly owned, created or exited, creation age over `24h` |
| Networks | Owned, local, supported, unused; creation age over `24h` |
| Dangling images | Explicit scope, unreferenced; creation age over `24h` |
| Tagged images | Scoped, unused; creation age over `720h`; weekly pressure |
| Build cache | Last use over `336h`, then a separate `20gb` backend target |
| Volumes | Report only; never removed by host cleanup |

Ownership requires `xyz.myflow.ci.ephemeral=true`. Protection uses
`xyz.myflow.cleanup.protect=true` or configured IDs/references/repositories.
Protection through any image alias protects the whole local image. An empty
image allowlist selects no images. Multi-tag image deletion is conservatively
skipped. Container creation age is not stop age; image creation age is not time
since last use.

Cache modes are `scheduled`, `native`, and `off`. Only the selected local default
builder with the `docker` driver is managed. Internal/frontend cache is excluded
unless explicitly enabled. The budget stage can remove recent records. Its
target is not a hard quota or a guaranteed physical-space saving. Native GC can
continue independently in every mode.

Configuration precedence is defaults, JSON policy, documented `CLEANUP_*` scalar
environment settings, then CLI overrides. Unknown settings fail. The supported
environment names are `CLEANUP_CONTAINER_MIN_AGE`, `CLEANUP_NETWORK_MIN_AGE`,
`CLEANUP_DANGLING_IMAGE_MIN_AGE`, `CLEANUP_UNUSED_IMAGE_MIN_AGE`, `CLEANUP_CACHE_MODE`,
`CLEANUP_CACHE_MAX_UNUSED_AGE`, and `CLEANUP_CACHE_MAX_USED_SPACE`. Durations use
positive integer `h`, `m`, and `s` components. Cache targets use positive integer
`b`, `kb`, `mb`, `gb`, or `tb` binary units. Shell expressions are not accepted.

## Runtime environment

| Property | Contract |
| --- | --- |
| Parent | Verified `ci-base` from the same suite build |
| User | Inherited `ci`, UID `1001`, GID `2001` |
| Working directory | `/workspace` |
| Home | `/home/ci` |
| Temporary files | `/var/tmp`; bounded private scratch space during apply |
| Commands | Root-owned programs under `/opt/ci-tools`; stable links on `PATH` |
| Default command | `ci-utils`, which prints help |
| Docker access | Explicit Unix endpoint; no daemon or credentials included |
| Apply profile | Offline, read-only, non-root; see the host adapter |

The reference deployment is native Linux, rootful Docker, with the host adapter
in the daemon's PID namespace. Engine API `1.48` and the required BuildKit
capabilities are checked. Rootless, remapped-user, SELinux-specific, remote,
custom-builder, macOS, and VM-host adapters need separate qualification. An
accepted version string is not live deployment evidence.

JSON Lines distinguish policy decisions, API/cache accounting, trusted host
filesystem measurements, unknown values, and final completion. Application codes
are `0` success/no eligible work, `2` invalid/unsupported configuration, `3` daemon
access/identity failure, `4` unavailable guard, `5` partial/unexpected failure,
and `6` unresolved completion. The host launcher uses `7` for its own Docker
launch/transport failures. A skipped or uncertain run is not completed cleanup.
