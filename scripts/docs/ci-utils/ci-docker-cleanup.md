# ci-docker-cleanup

Inspect or clean eligible containers, networks, images and local default-builder cache. `check` validates capabilities and reports inventory. `plan` is the default and reports decisions. `version` prints the active release identity offline. Use the host adapter to authorize `apply`.

```bash
ci-docker-cleanup plan --profile daily
# After reviewing the plan and qualifying admission
sudo ci-docker-maintenance apply --profile daily
```

Use `--config PATH` to override `/etc/ci-utils/cleanup.json`, `--profile daily|weekly` to select policy and `--endpoint` or `--expected-daemon-id` for explicit daemon selection. Age overrides are `--container-min-age` and `--network-min-age` (both default to `24h`), plus `--dangling-image-min-age` and `--tagged-image-min-age` (both default to `168h`). Policy values override those defaults. Use `-h` for help.

Online operations require policy read access and access to the local rootful Linux Docker 28.x or 29.x daemon with API 1.48. Clear inherited Docker and Buildx selection variables. Managed cache modes also need the existing local default builder, Buildx and the private probe. The host supplies `--observations` with trusted storage measurements and binds its worker through `--run-id` and `--lease-socket`. An exclusive authorized apply rechecks eligibility before deletion. Volumes, protected resources and in-use images are retained. The default image allowlist is empty. [Cleanup policy](../../../docs/images/utils.md#cleanup-policy)

JSON Lines report policy, observations and decisions. The terminal `result` reports counts, exit code, mutation and completion status. Exit 0 includes no eligible work, 2 indicates invalid policy or missing capabilities, 3 indicates daemon access or identity failure, 4 indicates an unavailable lease, 5 indicates partial failure and 6 requires reconciliation.

Run `(cd scripts && shellspec tests/ci-utils/ci-docker-cleanup_spec.sh)` from the repository root.
