# ci-buildkit-probe

`ci-docker-cleanup` calls this internal, CI-built binary to verify the capabilities of the selected Docker driver's BuildKit worker. The installed caller resolves it from its own release directory. To inspect a runner with its reviewed daemon ID, run the same private binary directly.

```bash
/usr/local/libexec/ci-utils/current/lib/ci-buildkit-probe \
  --host unix:///var/run/docker.sock --expected-daemon-id "$DAEMON_ID" --timeout 30s
```

`--host` requires an explicit local Unix socket and `--expected-daemon-id` requires the expected identity. `--timeout` defaults to 30 seconds and accepts positive Go durations up to 15 minutes. The caller needs socket access, a rootful Linux daemon and exactly one local BuildKit worker. The handshake can create internal session metadata. It submits no build workload or prune request.

Exit 0 prints a JSON object with the daemon ID, builder, driver, worker ID, BuildKit versions and `gc_space_filters` capability. Invalid input, mismatched identity or unavailable capabilities produce a JSON error on stderr and exit 2.

Run `(cd scripts && shellspec tests/ci-utils/ci-buildkit-probe_spec.sh)` from the repository root. The live cases use the packaged probe and the disposable daemon started by `tests/ci-utils-native.sh`.
