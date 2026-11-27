# ci-remove-images

Preview local suite tags eligible for retirement. For each repository the default keeps the image tagged `latest` and its aliases. If that tag is absent, it keeps the highest numeric version. Use `--versions X.Y.Z[,X.Y.Z]` for an explicit selection. Both numeric tags and their historical `v` aliases match.

```bash
ci-remove-images --config /etc/ci-utils/cleanup.json --versions 0.0.1
# After reviewing the preview and qualifying admission
sudo ci-docker-maintenance --config /etc/ci-utils/host.json remove-images --versions 0.0.1 --apply
```

`--config` defaults to `/etc/ci-utils/cleanup.json`. This **cleanup policy** selects the Unix endpoint, expected daemon ID and protected images. Override daemon selection for a preview with `--endpoint unix:///path/to/docker.sock` and `--expected-daemon-id ID`. Clear inherited Docker context, host, configuration, TLS and Buildx overrides. The CLI names the missing policy path. Use `-h` for help.

The adapter's **host settings** at `/etc/ci-utils/host.json` identify the trusted policy, Docker CLI, gate, participants and storage. Local preview requires read access to the policy and daemon. Apply requires a configured daemon identity and the administrator's exclusive lease. The adapter supplies `--apply`, `--run-id` and `--lease-socket` to its installed worker. The lease binds that process, release, selection, policy and daemon. Every container state and every protected alias reserves its image. Deletion targets exact tags without force. The operation uses local daemon state and needs no registry credentials. [Host coordination](../maintenance/ci-docker-maintenance.md)

JSON Lines identify `would-remove`, `removed`, `skipped` or `not-found` decisions and a final result. Exit 0 includes an empty selection, 2 indicates invalid policy or arguments, 3 indicates daemon access or identity failure, 4 indicates a denied lease, 5 indicates an operation failure and 6 requires reconciliation.

Run `(cd scripts && shellspec ci-utils/tests/images/ci-remove-images_spec.sh)` from the repository root.
