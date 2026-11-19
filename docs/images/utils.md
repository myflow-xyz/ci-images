# CI utilities

`ghcr.io/myflow-xyz/ci-utils` provides reusable CI maintenance commands. It derives from `ci-base` and adds Docker Buildx, `ci-utils-list`, `ci-docker-cleanup`, `ci-upgrade-images`, `ci-remove-images`, `ci-go-cleanup`, and `ci-pnpm-cleanup`. It follows the suite's version and digest promotion rules.

The build reuses `ci-go` to compile Buildx and the internal capability checker. The final image copies those binaries into `ci-base`; it does not add the Go toolchain or the `ci-go` runtime environment. Buildx source and its required security fixes are pinned in `manifests/versions.json`. The upstream binary failed the image scan on fixed Go, `go-archive`, and `golang.org/x/net` vulnerabilities. The internal BuildKit probe checks the selected backend's advertised cache-space capability before cleanup. The cleanup policy and execution use Python's standard library.

## Commands

```sh
docker run --rm ghcr.io/myflow-xyz/ci-utils:<suite-version>
docker run --rm ghcr.io/myflow-xyz/ci-utils:<suite-version> ci-utils-list
docker run --rm ghcr.io/myflow-xyz/ci-utils:<suite-version> ci-docker-cleanup --help
docker run --rm ghcr.io/myflow-xyz/ci-utils:<suite-version> ci-docker-cleanup version
docker run --rm ghcr.io/myflow-xyz/ci-utils:<suite-version> ci-upgrade-images --help
docker run --rm ghcr.io/myflow-xyz/ci-utils:<suite-version> ci-remove-images --help
docker run --rm ghcr.io/myflow-xyz/ci-utils:<suite-version> ci-go-cleanup --help
docker run --rm ghcr.io/myflow-xyz/ci-utils:<suite-version> ci-pnpm-cleanup --help
docker run --rm ghcr.io/myflow-xyz/ci-utils:<suite-version> bash --version
```

The image default and `ci-utils-list` show the same supported maintenance commands, descriptions, and Docker tools without accessing a Docker daemon or caches. Commands are directly callable. Use `ci-go-cleanup -h` or `ci-pnpm-cleanup -h` for options, default paths, and example usages. `ci-docker-cleanup` defaults to `plan` and requires a valid policy and explicit local endpoint. It supports `check`, `plan`, `apply`, and `version`. Build identity uses the source revision; the shared suite tag and OCI digest identify the promoted artifact.

Use the [host maintenance adapter](../maintenance.md) for Docker cleanup apply. A direct Docker socket mount or a Boolean environment flag cannot authorize Docker deletion. The host must coordinate every participant that uses the selected daemon.

## Reset shared Go and pnpm caches

`ci-go-cleanup` and `ci-pnpm-cleanup` preview a complete reset of selected cache directories. With no cache options, they check the mfci shared cache locations below. Add `--apply` to remove their contents. They preserve each cache root's inode, owner, group, and permissions, including a bind-mounted root. They use Python's standard library and need no Go toolchain, pnpm runtime, network, or Docker socket.

| Command | Selection | Reset scope |
| --- | --- | --- |
| `ci-go-cleanup` | Both caches by default; `--build-cache [PATH]`, `--mod-cache [PATH]`, or both to select caches | All content in the selected Go build or module cache |
| `ci-pnpm-cleanup` | Default store or `--store-dir [PATH]` | All content in the pnpm store, including every store version |

| Option | Default path when PATH is omitted |
| --- | --- |
| `--build-cache` | `/opt/actions-runner/shared/cache/go/build` |
| `--mod-cache` | `/opt/actions-runner/shared/cache/go/mod` |
| `--store-dir` | `/opt/actions-runner/shared/cache/pnpm/store` |

For example, `ci-go-cleanup` previews both default Go caches, while `ci-go-cleanup --build-cache` previews only the default build cache. An explicit path overrides that cache's default. Once either Go cache flag is supplied, only the supplied flags select caches. Defaults are checked at these exact paths; missing paths fail without being created or replaced with another location.

These are full cache resets. They do not select by age or last use, and pnpm cleanup does not perform `pnpm store prune`'s unreferenced-package selection. Later jobs rebuild or download the removed data. Paths must be existing absolute paths ending in `go/build`, `go/mod`, or `pnpm/store`, as appropriate. Symlinked path components, overlapping selections, nested mounts, and special files such as sockets and FIFOs are rejected. Symlinks inside a cache are unlinked without following their targets. Go's read-only module directories can be removed when the executing user owns them; permissions on the cache root are never broadened.

The runner owner must stop admission and wait for **all consumers of these shared directories**, including native tools and jobs on other runner slots, to finish before apply. An idle snapshot is insufficient. The commands' directory locks coordinate only these cleanup commands; they do not block Go or pnpm processes. The Docker maintenance adapter does not coordinate these filesystem resets. Run them as separate administrator maintenance, outside ordinary jobs, with the existing `mfci` GID `2001` access. Permission errors stop cleanup and produce a nonzero result; inspect a partial reset before reopening admission.

For the standard mfci paths, preview with read-only cache mounts at the same paths inside the container so the defaults are visible. Set `utils_image` to a verified, pre-pulled digest that contains these commands:

```sh
utils_image='ghcr.io/myflow-xyz/ci-utils@sha256:REPLACE_WITH_VERIFIED_DIGEST'
docker run --rm --pull=never --network=none --read-only \
  --cap-drop=ALL --security-opt=no-new-privileges --group-add=2001 \
  --mount type=bind,src=/opt/actions-runner/shared/cache/go/build,dst=/opt/actions-runner/shared/cache/go/build,readonly \
  --mount type=bind,src=/opt/actions-runner/shared/cache/go/mod,dst=/opt/actions-runner/shared/cache/go/mod,readonly \
  "$utils_image" ci-go-cleanup

docker run --rm --pull=never --network=none --read-only \
  --cap-drop=ALL --security-opt=no-new-privileges --group-add=2001 \
  --mount type=bind,src=/opt/actions-runner/shared/cache/pnpm/store,dst=/opt/actions-runner/shared/cache/pnpm/store,readonly \
  "$utils_image" ci-pnpm-cleanup
```

After all consumers have stopped, remove `,readonly` from the selected cache mounts and append `--apply` to the same command. To retain downloaded Go modules, add `--build-cache` and omit the module-cache mount. For other container mount destinations, pass paths explicitly, such as `ci-go-cleanup --build-cache /var/cache/go/build` or `ci-pnpm-cleanup --store-dir /var/cache/pnpm/store`. Keep the container root read-only. Do not mount the shared cache's parent directory or a Docker socket.

JSON Lines report each selected path, entry counts, logical file bytes, and final success or failure. Logical bytes include hard-linked files and are not a physical-space reclamation estimate. Preview makes no changes. Missing or unreadable paths fail before deletion, and all selected caches are inspected before any reset. Exit codes are `0` success, `2` invalid selection or failed preflight, `4` another cleanup holds a lock, and `5` failed or interrupted reset, which may be partial.

## Refresh cached CI images

`ci-upgrade-images` refreshes each `ghcr.io/myflow-xyz/ci-*` repository already present on the selected daemon. A local tag or digest reference qualifies a repository. If only `ci-utils` is cached, it refreshes only that repository. Pull another suite image once to include it in later runs.

The helper matches the registry's `:latest` index digest to an exact version recorded in a published GitHub Release. It verifies the numeric tag against GHCR and pulls the immutable index. It then makes the verified `:X.Y.Z` and `:latest` available locally. Existing version tags are kept by default.

The command defaults to `unix:///var/run/docker.sock` and uses Docker CLI registry credentials. The utility container needs HTTPS access to `api.github.com` and `ghcr.io` for verification. The [one-off runner command](../../README.md#upgrade-runner-images) uses the cached image and supports temporary credentials for private packages. Mount a policy file and pass `--config` to protect additional images by ID, reference, or repository.

Each JSON Lines `pulled` event provides the following fields.

| Field | Meaning |
| --- | --- |
| `id` | Exact local result, such as `ghcr.io/myflow-xyz/ci-utils:0.0.26` |
| `source` | Moving registry alias used for discovery |
| `digest` | Verified registry index digest for the suite image |
| `image_id` | Docker image ID for the locally selected image |

Require a successful final `result` before using the reported references for future runs. A missing release match, registry mismatch, or conflicting local version fails the run. If the registry's `:latest` moves during the pull, retry to resolve the new release.

Pause new jobs and let active jobs finish before using `--prune-old-versions`. Retirement starts after all selected refreshes are verified. It considers only numeric version tags of the refreshed repositories, keeps aliases of the verified latest images, and preserves protected or in-use images. If a local latest tag changes before retirement, that repository is skipped. A failed refresh leaves old version tags in place.

## Keep a utility container running

On a Linux runner, use the utility image already pulled. Set `CI_UTILS_IMAGE` to its verified numeric tag or digest when available. The named container needs HTTPS access to `api.github.com` and `ghcr.io` for version lookup. Mounting the Docker socket grants access to the host daemon, including when the socket mount is marked read-only.

```bash
CI_UTILS_IMAGE=ghcr.io/myflow-xyz/ci-utils:latest
docker run --detach --name ci-utils --init --restart unless-stopped \
  --pull=never \
  --mount type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock,readonly \
  --group-add "$(stat -c %g /var/run/docker.sock)" \
  --tmpfs /var/tmp:mode=1777 \
  --env DOCKER_CONFIG=/var/tmp/ghcr \
  "$CI_UTILS_IMAGE" sleep infinity

docker exec ci-utils ci-utils-list
```

If the repositories require authentication, set `GHCR_USER` and load `GHCR_TOKEN` from your runner's secret store. Log in before the refresh and again after a container restart, which clears the temporary credentials.

```bash
printf '%s\n' "$GHCR_TOKEN" |
  docker exec -i ci-utils docker --host unix:///var/run/docker.sock \
    login ghcr.io --username "$GHCR_USER" --password-stdin
```

Run `docker exec ci-utils ci-upgrade-images` for each refresh. Add an alias in your shell startup file to invoke it by its command name.

```bash
alias ci-upgrade-images='docker exec -i ci-utils ci-upgrade-images'
```

Reuse `docker exec` for catalog, help, and image retirement previews. Docker cleanup plans need the selected socket and a policy, and cleanup apply uses the [guarded host adapter](../maintenance.md). Go and pnpm commands use [selected cache mounts](#reset-shared-go-and-pnpm-caches). Add those mounts when creating the container for cache maintenance.

Recreate the named container from the new utility tag or digest to use a newer helper version. Until the old container is removed, it keeps its original image in use.

## Remove local suite versions

`ci-remove-images` previews removal of older local suite versions. For each repository it retains the image tagged `:latest` and its version aliases. When the repository has no local `:latest` tag, it retains the highest numeric version and its image aliases. It uses local state from the daemon in the cleanup policy.

Use `--versions 0.0.1,0.0.2` to select exact numeric versions instead. The command matches `:X.Y.Z` and historical `:vX.Y.Z` tags for `ghcr.io/myflow-xyz/ci-{base,go,node,vite,playwright,postgres,utils,net}`. It trims whitespace and removes duplicate version requests. Ranges, wildcards, moving tags, and repository arguments are rejected.

The default dry-run makes no changes. `--apply` requires the [guarded host invocation](../maintenance.md#remove-local-suite-versions). Every container state reserves its image. Protection labels, configured image IDs, and protection through any tag, digest alias, or repository preserve the entire image. Apply rechecks identity, references, and protection before each non-forced tag removal. Unselected tags remain. Explicit retirement does not use routine cleanup's age, pressure, or image allowlist settings and does not remove containers, networks, volumes, or build cache.

JSON Lines report requested versions, matched references, would-remove/removed/skipped/failed counts, reasons, and versions not found locally. Missing versions are successful no-ops. Shared layers or retained tags can prevent disk space reclamation. Exit codes and uncertain-completion recovery use the existing maintenance contract.

## Cleanup policy

| Resource | Default selection |
| --- | --- |
| Containers | Explicitly owned, created or exited, creation age over `24h` |
| Networks | Owned, local, supported, unused, creation age over `24h` |
| Dangling images | Explicit scope, unreferenced; creation age over `168h` |
| Tagged images | Scoped, unused; creation age over `168h`; weekly pressure |
| Build cache | Last use over `24h`, then a separate `20gb` backend target |
| Volumes | Report only; never removed by host cleanup |

Ownership requires `xyz.myflow.ci.ephemeral=true`. Protection uses `xyz.myflow.cleanup.protect=true` or configured IDs/references/repositories. Protection through any image alias protects the whole local image. For routine `ci-docker-cleanup`, an empty image allowlist selects no images and multi-tag image deletion is conservatively skipped. Container creation age is not stop age; image creation age is not time since last use.

Cache modes are `scheduled`, `native`, and `off`. Only the selected local default builder with the `docker` driver is managed. Internal/frontend cache is excluded unless explicitly enabled. The budget stage can remove recent records. Its target is not a hard quota or a guaranteed physical-space saving. Native GC can continue independently in every mode.

Each stage sends its complete eligible ID selection to the Engine's BuildKit prune endpoint, so dependencies and eviction order remain under backend control. The form request is limited to 1 MiB; larger selections fail without submitting that stage. Requests are not split or retried after uncertain completion.

The budget and `cache_budget.remaining_bytes` use non-shared cache bytes, matching BuildKit. Usage observations report total, shared, and non-shared bytes separately.

Configuration precedence is defaults, JSON policy, documented `CLEANUP_*` scalar environment settings, then CLI overrides. Unknown settings fail. The supported environment names are `CLEANUP_CONTAINER_MIN_AGE`, `CLEANUP_NETWORK_MIN_AGE`, `CLEANUP_DANGLING_IMAGE_MIN_AGE`, `CLEANUP_UNUSED_IMAGE_MIN_AGE`, `CLEANUP_CACHE_MODE`, `CLEANUP_CACHE_MAX_UNUSED_AGE`, and `CLEANUP_CACHE_MAX_USED_SPACE`. Durations use positive integer `h`, `m`, and `s` components. Cache targets use positive integer `b`, `kb`, `mb`, `gb`, or `tb` binary units. Shell expressions are not accepted.

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
| Docker apply profile | Offline, read-only, non-root; see the host adapter |
| Filesystem cache apply | Only selected cache mounts writable; no Docker socket |

The reference deployment is native Linux, rootful Docker, with the host adapter in the daemon's PID namespace. Engine API `1.48` and the required BuildKit capabilities are checked. Rootless, remapped-user, SELinux-specific, remote, custom-builder, macOS, and VM-host adapters need separate qualification. An accepted version string is not live deployment evidence.

JSON Lines distinguish policy decisions, API/cache accounting, trusted host filesystem measurements, unknown values, and final completion. Application codes are `0` success/no eligible work, `2` invalid/unsupported configuration, `3` daemon access/identity failure, `4` unavailable guard, `5` partial/unexpected failure, and `6` unresolved completion. The host launcher uses `7` for its own Docker launch/transport failures. A skipped or uncertain run is not completed cleanup.
