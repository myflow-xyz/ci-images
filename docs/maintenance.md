# Guarded Docker maintenance

The installed Linux adapter coordinates jobs, measures daemon storage and runs the verified maintenance worker on the runner. Docker socket access grants administrative control of the selected daemon. [Native installation and command guide](../scripts/ci-utils/README.md)

## Deployment inputs

Review the cleanup policy, host settings, job wrapper and service templates. Replace the placeholders with the expected daemon ID, local Unix socket, trusted Docker CLI path, participant group, complete daemon-user inventory, protected references, actual storage paths and job capacity reserve. Keep the files root-owned and outside job workspaces. [Configuration examples](../scripts/ci-utils/examples/maintenance/)

The reference adapter uses shared job leases and exclusive maintenance leases. Every daemon user must participate, including native/containerized jobs, pulls, builds, finalizers, manual tools, and background clients. The `participants` list and `admission_evidence` record the reviewed deployment; they do not enforce an external runner's lifecycle by themselves. Unadapted participants prevent apply qualification. A cleanup-only lock or an idle snapshot is insufficient.

## Install the reviewed adapter

Install the pinned release system-wide as a Linux administrator. The public command at `/usr/local/bin/ci-docker-maintenance` and the absolute path used by services and job hooks select the same installed worker. The issuer checks its Linux peer PID and release identity. [Install or upgrade ci-utils](../scripts/ci-utils/docs/installation/install.md)

Create `/etc/ci-utils` and `/var/lib/ci-utils` as root-owned directories. Install the reviewed `host.json` and `cleanup.json` into `/etc/ci-utils` as root-owned regular files, mode `0644` or stricter. The Docker CLI path must also be root-owned. The adapter rejects mutable configuration and symlinked trusted paths.

Provision the gate once and verify the installation with the public command.

```sh
sudo ci-docker-maintenance init
sudo ci-docker-maintenance status
sudo ci-docker-maintenance check
sudo ci-docker-maintenance plan --profile weekly
```

Existing gate state is never reset by initialization. Retain it across upgrades, service restarts, and host reboots. Gate records and reconciliation audits are under the configured gate directory. Scheduler logs need an operator-owned retention policy.

## Admit a complete job lifecycle

The runner's trusted dispatcher invokes the wrapper before the first Docker operation and keeps the entire job and teardown inside the command:

```sh
/usr/local/libexec/ci-utils/ci-docker-maintenance job \
  --participant runner-slot-1 --wait 15m --timeout 12h -- \
  /path/to/reviewed-complete-job-command
```

After all daemon operations have known completion, teardown has finished, and all child clients have been joined, that command invokes:

```sh
/usr/local/libexec/ci-utils/ci-docker-maintenance job-complete
```

This writes an explicit finalization receipt. The parent also requires normal process exit and no remaining process-group members. A test can return nonzero after known teardown; its original exit code is preserved. Missing receipts, signals, timeouts, wrapper crashes, or remaining clients leave admission blocked. Receipt creation is the final lifecycle operation; it must not precede later Docker work. Processes must not escape the supervised job into detached sessions.

The wrapper exports `CI_DOCKER_JOB_ID` as a collision-resistant per-admission token and `CI_DOCKER_ENDPOINT` as the selected daemon endpoint. Use that token for Compose project names. The [job example](../scripts/ci-utils/examples/maintenance/job.sh) shows scoped teardown for a reviewed project with disposable managed volumes. Do not set fixed container names or shared explicit volume/network names. Mark shared resources external and protected. The example treats every failed Docker command as uncertain; a more specific adapter must establish completion before issuing a receipt.

A generic pre/post-job hook is not automatically a qualified integration. Verify that the actual runner includes container setup and its final teardown inside the shared lease. The provided CLI does not claim that an unmodified GitHub Actions runner has this boundary.

## Storage and pressure

The host measures the configured Docker/containerd backing directories and deduplicates them by filesystem device. Its Docker path must match the daemon's `DockerRootDir`. Containerd image-store deployments require their separate path; classic `overlay2` deployments can explicitly use `null` for it. Review any other storage roots. Inaccessible, incomplete, stale, mismatched, or unknown measurements remain unknown. No container-root `df` result is substituted.

Set `pressure.reserve_bytes` from concurrent-job peak requirements and a margin. Jobs are refused when measurements are unavailable, the reserve is absent or insufficient, or the critical threshold is reached. Maintenance can still run while capacity prevents new jobs. At the default 80% pressure threshold, weekly tagged-image cleanup remains subject to its existing scope, age, and protection. The default critical threshold is 90%. Pressure never authorizes volume deletion or wider image scope.

Review native BuildKit GC with the operator. Scheduled pruning neither disables native GC nor guarantees a seven-day minimum retention after the space-budget stage. Keep backend accounting, host free space, and any VM physical-host measurements separate. Logical reclamation is not proof that a VM disk image shrank.

The native Go and pnpm cache commands operate on the runner's filesystem. Drain all consumers of the selected directories before a reset, including jobs outside the Docker admission gate. [Go cache reset](../scripts/ci-utils/docs/caches/ci-go-cleanup.md) · [pnpm store reset](../scripts/ci-utils/docs/caches/ci-pnpm-cleanup.md)

## Schedule and run maintenance

`scripts/ci-utils/tests/installation/qualify.sh` builds the native archives and tests the installed commands on isolated Linux engines. Coverage includes both containerd and classic overlay2 stores, BuildKit cache policy, job coordination, protection of in-use resources and recovery after interruption. Qualify the complete job lifecycle on the target runner before enabling scheduled apply.

### Install maintenance scheduling

After the rollout gates below pass, review and install the [systemd examples](../scripts/ci-utils/examples/maintenance/). They use the same adapter for daily and weekly profiles. Adjust the selected Docker service/socket and the writable state path to match the host settings. Check the unit files with the host's `systemd-analyze verify` before enabling timers.

Replace `REPLACE_WITH_JOB_GID` in the service's `SupplementaryGroups=` with the numeric `job_gid` from the reviewed `host.json`. The service drops all capabilities, so its root identity needs this group membership to read participant-owned `0640` gate records. Qualify interrupted-job recovery with this same group and capability profile before enabling scheduling. Retain the empty `CapabilityBoundingSet=` and the existing gate permissions.

The service uses `Requisite=` so it does not start an inactive Docker service. Its explicit start deadline bounds the one-shot process. Timers use persistent calendar scheduling to catch up missed runs. See the Debian manuals for [unit dependencies](https://manpages.debian.org/trixie/systemd/systemd.unit.5.en.html), [service deadlines](https://manpages.debian.org/trixie/systemd/systemd.service.5.en.html), and [timers](https://manpages.debian.org/trixie/systemd/systemd.timer.5.en.html).

Manual maintenance uses the same gate:

```sh
sudo ci-docker-maintenance apply --profile daily
sudo ci-docker-maintenance apply --profile weekly
```

The native launcher passes a read-only policy snapshot, storage observations and the selected Unix socket to the installed process. Apply also receives a process-bound lease. The adapter checks the worker's terminal JSON result before releasing admission. A lost result retains the gate record for reconciliation.

## Refresh cached CI images

Run `ci-upgrade-images` during the runner's maintenance window. Allow HTTPS access to the release metadata and registry. Supply Docker credentials for restricted packages. [Refresh options and output](../scripts/ci-utils/docs/images/ci-upgrade-images.md)

Keep the exact references in the JSON Lines log. Use the final result and exit status to detect failure. Investigate a failed refresh and keep existing job pins until a successful retry. Update version- or digest-pinned job references separately using the [release digests](usage.md#pulling-and-pinning).

The default keeps old versions. To retire eligible tags after refresh, add `--prune-old-versions` after pausing job admission and waiting for active jobs to finish. The host adapter coordinates job admission for lease-gated Docker cleanup and standalone version retirement.

## Remove local suite versions

Use the installed adapter and its trusted host configuration for version retirement. Preview the selection before applying it.

```sh
sudo ci-docker-maintenance remove-images
sudo ci-docker-maintenance remove-images --apply
```

The default retains each repository's local `latest` image, or its highest numeric version if `latest` is absent. To select exact versions, add the same `--versions 0.0.1,0.0.2` to both commands. For an alternate host configuration, pass `--config PATH` before `remove-images`.

The adapter launches the installed `ci-remove-images` worker. Apply waits for the exclusive maintenance lease (`--wait 15m` by default), bound to the selected daemon, policy, archive digest, process and retirement selection. It removes only eligible exact suite tags, preserves images referenced by any container or protected through any alias, and leaves unselected tags intact. Retirement selects versions independently of age and disk pressure. Unknown completion retains the admission block and requires the recovery below. [Retirement options and protections](../scripts/ci-utils/docs/images/ci-remove-images.md)

## Reconcile uncertain completion

Disable new dispatch through every participant and inspect `status` plus the retained job/maintenance record and logs. Establish that the selected daemon has finished the relevant work. Backend pruning or builds can continue after the worker exits and its locks are released. Keep admission blocked if completion is unknown.

For a native apply, read `worker-<record-id>.jsonl` in the configured gate directory as root. It contains the events the worker emitted before interruption, including confirmed removals. Save a copy if needed for your incident record. The gate removes the report after verified completion or accepted reconciliation.

When completion is established, the administrator supplies a root-owned JSON file containing current evidence for one exact record:

```json
{
  "schema_version": 1,
  "record_id": "REPLACE_WITH_UNRESOLVED_RECORD_ID",
  "daemon_id": "REPLACE_WITH_EXPECTED_DAEMON_ID",
  "observed_at": "REPLACE_WITH_CURRENT_UTC_TIMESTAMP",
  "observer": "REPLACE_WITH_OPERATOR",
  "evidence": "REPLACE_WITH_COMPLETION_OBSERVATIONS_OR_INCIDENT_REFERENCE",
  "participants_drained": true,
  "daemon_operations_complete": true
}
```

These assertions require actual operator evidence; do not generate them from process exit alone. Then run:

```sh
sudo ci-docker-maintenance reconcile \
  --record-id <record-id> --evidence /path/to/root-owned-evidence.json
```

Recovery takes exclusive access and verifies the daemon and record. If an unresolved record identifies a container, recovery verifies its state before releasing admission. After verification, recovery writes a durable audit and clears only that record. Evidence must be no older than 15 minutes. Reconcile every unresolved record before resuming dispatch. Do not delete lock/state files or blindly retry cleanup. The command does not kill processes or cancel daemon work.

## Rollout and rollback

Start with plan-only runs on a representative runner. Review ownership-label adoption, protected inventories, exact Engine/BuildKit/Buildx versions, filesystem mapping, and all participants' lifecycle coverage. Then perform a limited apply, compare protected resources and volumes before/after, and confirm that jobs do not overlap maintenance. Test cancellation/crash recovery. Enable weekly policy only after those checks, and tune cache targets and resource limits from observed job performance and daemon I/O.

Fixtures do not qualify a production runner. Native AMD64/ARM64 build, smoke, vulnerability, SBOM/provenance, isolated real-daemon E2E, and representative-runner rollout evidence are release/deployment gates. Rootless, remapped, SELinux-specific, custom-builder, remote, and VM-host adapters remain separate qualification work.

To disable, stop the timers and dispatch path. Preserve any unresolved admission block until reconciliation. Reinstall a previously verified native release after reviewing protocol and configuration compatibility. Rollback changes future behavior; it cannot restore deleted data.
