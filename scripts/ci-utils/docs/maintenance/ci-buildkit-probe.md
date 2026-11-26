# ci-buildkit-probe

BuildKit keeps intermediate build results in a cache. Before `ci-docker-cleanup` manages that cache, this Linux helper verifies the selected daemon and worker. Scheduled cleanup also requires the worker to advertise support for space-based pruning. With cache mode `off`, cleanup skips the probe. Image refresh, image retirement and filesystem cache resets use their own commands.

The probe is built into the Linux release and only queries the worker. To inspect a runner, use the installed helper with the reviewed daemon ID.

```bash
/usr/local/libexec/ci-utils/current/lib/maintenance/ci-buildkit-probe \
  --host unix:///var/run/docker.sock --expected-daemon-id "$DAEMON_ID" --timeout 30s
```

`--host` requires an explicit local Unix socket and `--expected-daemon-id` requires the expected identity. `--timeout` defaults to 30 seconds and accepts positive Go durations up to 15 minutes. The caller needs socket access, a rootful Linux daemon and exactly one local BuildKit worker. The handshake can create internal session metadata. It submits no build workload or prune request.

Exit 0 prints a JSON object with the daemon ID, builder, driver, worker ID, BuildKit versions and `gc_space_filters` capability. Invalid input, mismatched identity or unavailable capabilities produce a JSON error on stderr and exit 2.

Run `(cd scripts && shellspec ci-utils/tests/maintenance/ci-buildkit-probe_spec.sh)` from the repository root. The live cases use the packaged probe and the disposable daemon started by `scripts/ci-utils/tests/installation/qualify.sh`.
