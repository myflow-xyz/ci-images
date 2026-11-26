# ci-upgrade-images

Refresh MyFlow suite images already cached on the selected daemon. The command reads the GitHub release digest table and pulls the approved index by digest for the Linux platform reported by that daemon. It checks the local image OS and architecture before updating the numeric and `:latest` tags. A runner's cross-build setting for `DOCKER_DEFAULT_PLATFORM` does not change this selection. Refresh runs immediately and retains older versions by default.

```bash
ci-upgrade-images --endpoint unix:///var/run/docker.sock
```

The default endpoint is `unix:///var/run/docker.sock`. Use `--expected-daemon-id ID` to require a specific daemon, `--config PATH` for an optional cleanup policy and its image protections, and `-h` for help. The account needs access to a rootful Linux Docker 28.x or 29.x daemon supporting API 1.48, Docker CLI with Buildx, and HTTPS to `api.github.com` and `ghcr.io`. Supply Docker registry credentials for restricted repositories. Only cached suite repositories are refreshed.

The `--prune-old-versions` option retires eligible old versions after all refreshes verify. Drain all daemon participants before using it. A digest mismatch stops the refresh before retirement. A later failure can leave earlier pulls or tags in place.

JSON Lines include `pulled` events with the versioned reference, OCI digest and local image ID, followed by a `result`. Exit 0 means success or no cached suite images, 2 means invalid input or unsupported daemon, 3 means daemon access or identity failed, 5 means lookup, verification or refresh failed and 6 means completion is uncertain.

Run `(cd scripts && shellspec tests/ci-utils/ci-upgrade-images_spec.sh)` from the repository root. The isolated registry and Engine scenario runs in `tests/ci-utils-native.sh`.
