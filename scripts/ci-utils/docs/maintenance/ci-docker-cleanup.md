# ci-docker-cleanup

Inspect or clean eligible containers, networks, images and local default-builder cache. `check` validates capabilities and reports inventory. `plan` is the default and reports decisions. `version` prints the active release identity offline. Use the host adapter to authorize `apply`.

```bash
ci-docker-cleanup plan --profile daily
# After reviewing the plan and qualifying admission
sudo ci-docker-maintenance apply --profile daily
```

Use `--config PATH` to override `/etc/ci-utils/cleanup.json`, `--profile daily|weekly` to select policy and `--endpoint` or `--expected-daemon-id` for explicit daemon selection. Age overrides are `--container-min-age` and `--network-min-age` (both default to `24h`), plus `--dangling-image-min-age` and `--tagged-image-min-age` (both default to `168h`). Policy values override those defaults. Use `-h` for help.

Online operations require policy read access and access to the local rootful Linux Docker 28.x or 29.x daemon with API 1.48. Clear inherited Docker and Buildx selection variables. Managed cache modes also need the existing local default builder, Buildx and the private probe. The host supplies `--observations` with trusted storage measurements and binds its worker through `--run-id` and `--lease-socket`. An exclusive authorized apply rechecks eligibility before deletion. Volumes, protected resources and in-use images are retained. The default image allowlist is empty.

JSON Lines report policy, observations and decisions. The terminal `result` reports counts, exit code, mutation and completion status. Exit 0 includes no eligible work, 2 indicates invalid policy or missing capabilities, 3 indicates daemon access or identity failure, 4 indicates an unavailable lease, 5 indicates partial failure and 6 requires reconciliation.

## Cleanup policy

| Resource | Default selection |
| --- | --- |
| Containers | Explicitly owned, created or exited, creation age over `24h` |
| Networks | Owned, local, supported, unused, creation age over `24h` |
| Dangling images | Explicitly scoped, unreferenced, creation age over `168h` |
| Tagged images | Scoped, unused, creation age over `168h`, weekly pressure |
| Build cache | Last use over `24h`, then a separate `20gb` backend target |
| Volumes | Report only |

Ownership requires `xyz.myflow.ci.ephemeral=true`. Protection uses `xyz.myflow.cleanup.protect=true` or configured IDs/references/repositories. Protection through any image alias protects the whole local image. For routine `ci-docker-cleanup`, an empty image allowlist selects no images and multi-tag image deletion is conservatively skipped. Container and image age use the creation timestamp.

Cache modes are `scheduled`, `native`, and `off`. Only the selected local default builder with the `docker` driver is managed. Internal/frontend cache is excluded unless explicitly enabled. The budget stage can remove recent records. Its target is not a hard quota or a guaranteed physical-space saving. Native GC can continue independently in every mode.

Each stage sends its complete eligible ID selection to the Engine's BuildKit prune endpoint, so dependencies and eviction order remain under backend control. The form request is limited to 1 MiB. Larger selections fail before submission. Requests are not split or retried after uncertain completion.

The budget and `cache_budget.remaining_bytes` use non-shared cache bytes, matching BuildKit. Usage observations report total, shared, and non-shared bytes separately.

Configuration precedence is defaults, JSON policy, documented `CLEANUP_*` scalar environment settings, then CLI overrides. Unknown settings fail. The supported environment names are `CLEANUP_CONTAINER_MIN_AGE`, `CLEANUP_NETWORK_MIN_AGE`, `CLEANUP_DANGLING_IMAGE_MIN_AGE`, `CLEANUP_UNUSED_IMAGE_MIN_AGE`, `CLEANUP_CACHE_MODE`, `CLEANUP_CACHE_MAX_UNUSED_AGE`, and `CLEANUP_CACHE_MAX_USED_SPACE`. Durations use positive integer `h`, `m`, and `s` components. Cache targets use positive integer `b`, `kb`, `mb`, `gb`, or `tb` binary units. Shell expressions are not accepted.

Run `(cd scripts && shellspec ci-utils/tests/maintenance/ci-docker-cleanup_spec.sh)` from the repository root.
