# Guarded Docker maintenance

Use `ci-utils` as a one-shot maintenance image. The native Linux host adapter
owns admission, storage observations, container launch, and recovery. Docker
socket access grants administrative control of the selected daemon; non-root
execution inside the container does not remove that authority.

## Deployment inputs

Review the [example policy and host settings](../scripts/examples/ci-utils/).
Replace all placeholders. Supply the expected daemon ID, local Unix socket,
verified pre-pulled image digest, trusted Docker CLI path, participant group,
complete daemon-user inventory, protected references, actual storage paths, and
job capacity reserve. Keep these files root-owned and outside job workspaces.

The reference adapter uses shared job leases and exclusive maintenance leases.
Every daemon user must participate, including native/containerized jobs, pulls,
builds, finalizers, manual tools, and background clients. The `participants` list
and `admission_evidence` record the reviewed deployment; they do not enforce an
external runner's lifecycle by themselves. Unadapted participants prevent apply
qualification. A cleanup-only lock or an idle snapshot is insufficient.

The host must share the Docker daemon's PID namespace so the lease can bind the
actual cleanup process returned by container inspection. The adapter has been
tested with Python 3.14.8. Qualify the intended host Python and service manager
before rollout. No host service is installed or enabled by building the image.

## Install the reviewed adapter

Install from the same reviewed revision as the image. The following commands are
operator steps, not actions performed by the image:

```sh
sudo install -d -m 0755 /usr/local/libexec/ci-utils /etc/ci-utils /var/lib/ci-utils
sudo install -m 0755 scripts/ci-docker-maintenance /usr/local/libexec/ci-utils/
sudo install -m 0644 scripts/ci_docker_*.py /usr/local/libexec/ci-utils/
sudo cp -R images/utils/ci_utils /usr/local/libexec/ci-utils/
sudo chmod -R go-w /usr/local/libexec/ci-utils
```

Install the reviewed `host.json` and `cleanup.json` into `/etc/ci-utils` as
root-owned regular files, mode `0644` or stricter. The Docker CLI path must also
be root-owned. The adapter rejects mutable configuration and symlinked trusted
paths. Pull and verify the approved image digest separately, before maintenance;
the launcher never pulls an image or reads registry credentials.

Provision the gate once:

```sh
sudo /usr/local/libexec/ci-utils/ci-docker-maintenance init
sudo /usr/local/libexec/ci-utils/ci-docker-maintenance status
sudo /usr/local/libexec/ci-utils/ci-docker-maintenance check
sudo /usr/local/libexec/ci-utils/ci-docker-maintenance plan --profile weekly
```

Existing gate state is never reset by initialization. Retain it across upgrades,
service restarts, and host reboots. Gate records and reconciliation audits are
under the configured gate directory. Scheduler logs need an operator-owned
retention policy.

## Admit a complete job lifecycle

The runner's trusted dispatcher invokes the wrapper before the first Docker
operation and keeps the entire job and teardown inside the command:

```sh
/usr/local/libexec/ci-utils/ci-docker-maintenance job \
  --participant runner-slot-1 --wait 15m --timeout 12h -- \
  /path/to/reviewed-complete-job-command
```

After all daemon operations have known completion, teardown has finished, and
all child clients have been joined, that command invokes:

```sh
/usr/local/libexec/ci-utils/ci-docker-maintenance job-complete
```

This writes an explicit finalization receipt. The parent also requires normal
process exit and no remaining process-group members. A test can return nonzero
after known teardown; its original exit code is preserved. Missing receipts,
signals, timeouts, wrapper crashes, or remaining clients leave admission blocked.
Receipt creation is the final lifecycle operation; it must not precede later
Docker work. Processes must not escape the supervised job into detached sessions.

The wrapper exports `CI_DOCKER_JOB_ID` as a collision-resistant per-admission token
and `CI_DOCKER_ENDPOINT` as the selected daemon endpoint. Use that token for
Compose project names. The [job example](../scripts/examples/ci-utils/job.sh)
shows scoped teardown for a reviewed project with disposable managed volumes.
Do not set fixed container names or shared explicit volume/network names. Mark
shared resources external and protected. The example treats every failed Docker
command as uncertain; a more specific adapter must establish completion before
issuing a receipt.

A generic pre/post-job hook is not automatically a qualified integration. Verify
that the actual runner includes container setup and its final teardown inside
the shared lease. The provided CLI does not claim that an unmodified GitHub
Actions runner has this boundary.

## Storage and pressure

The host measures the configured Docker/containerd backing directories and
deduplicates them by filesystem device. Its Docker path must match the daemon's
`DockerRootDir`. Containerd image-store deployments require their separate path;
classic `overlay2` deployments can explicitly use `null` for it. Review any other
storage roots. Inaccessible, incomplete, stale, mismatched, or unknown measurements
remain unknown. No container-root `df` result is substituted.

Set `pressure.reserve_bytes` from concurrent-job peak requirements and a margin.
Jobs are refused when measurements are unavailable, the reserve is absent or
insufficient, or the critical threshold is reached. Maintenance can still run
while capacity prevents new jobs. At the default 80% pressure threshold, weekly
tagged-image cleanup remains subject to its existing scope, age, and protection.
The default critical threshold is 90%. Pressure never authorizes volume deletion
or wider image scope.

Review native BuildKit GC with the operator. Scheduled pruning neither disables
native GC nor guarantees a 14-day minimum retention after the space-budget stage.
Keep backend accounting, host free space, and any VM physical-host measurements
separate. Logical reclamation is not proof that a VM disk image shrank.

## Schedule and run maintenance

`tests/utils-docker.sh` qualifies the packaged utility against a fresh,
digest-pinned Docker daemon. It checks guarded deletion, retained volume
contents, cache behavior, concurrent Compose projects, and explicit recovery.
The harness creates and removes its own test containers and volumes. Only the
test daemon is privileged; it receives no host Docker socket or host-root mount.
These tests do not replace qualification of the runner's complete job lifecycle.

CI runs both the default containerd image store and
`CI_UTILS_TEST_IMAGE_STORE=classic`. The dangling-image fixture uses classic
`overlay2`: the containerd store removes the fixture's old image metadata during
tag replacement, before cleanup runs. Other cases run against both stores.

After the rollout gates below pass, review and install the
[systemd examples](../scripts/examples/ci-utils/). They use the same adapter for
daily and weekly profiles. Adjust the selected Docker service/socket and the
writable state path to match the host settings. Check the unit files with the
host's `systemd-analyze verify` before enabling timers.

The service uses `Requisite=` so it does not start an inactive Docker service.
Its explicit start deadline bounds the one-shot process. Timers use persistent
calendar scheduling to catch up missed runs. See the Debian manuals for
[unit dependencies](https://manpages.debian.org/trixie/systemd/systemd.unit.5.en.html),
[service deadlines](https://manpages.debian.org/trixie/systemd/systemd.service.5.en.html),
and [timers](https://manpages.debian.org/trixie/systemd/systemd.timer.5.en.html).

Manual maintenance uses the same gate:

```sh
sudo /usr/local/libexec/ci-utils/ci-docker-maintenance apply --profile daily
sudo /usr/local/libexec/ci-utils/ci-docker-maintenance apply --profile weekly
```

The launcher passes a read-only policy snapshot and host observation, the selected
socket, and a narrowly scoped lease socket. It uses a non-root identity, actual
socket group, no network, read-only root, bounded scratch space, dropped
capabilities, and no-new-privileges. It removes its stopped container after known
completion without removing volumes. On uncertain completion it retains the
container identity for investigation. It never changes socket permissions,
relabels host paths, stops workloads, resets a builder, or restarts Docker.

## Reconcile uncertain completion

Disable new dispatch through every participant and inspect `status` plus the
retained job/maintenance record and logs. Establish that the selected daemon has
finished the relevant work. A dead client, an unlocked file, or a stopped
maintenance container alone does not prove that backend pruning/builds completed.
Keep admission blocked if that evidence is unavailable.

When completion is established, the administrator supplies a root-owned JSON
file containing current evidence for one exact record:

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

These assertions require actual operator evidence; do not generate them from
process exit alone. Then run:

```sh
sudo /usr/local/libexec/ci-utils/ci-docker-maintenance reconcile \
  --record-id <record-id> --evidence /path/to/root-owned-evidence.json
```

Recovery takes exclusive access, verifies the daemon and record, refuses an
active or indeterminate maintenance container, writes a durable audit, and clears
only that record. Evidence must be no older than 15 minutes. Reconcile every
unresolved record before resuming dispatch. Do not delete lock/state files or
blindly retry cleanup. The command does not kill processes or cancel daemon work.

## Rollout and rollback

Start with plan-only runs on a representative runner. Review ownership-label
adoption, protected inventories, exact Engine/BuildKit/Buildx versions, filesystem
mapping, and all participants' lifecycle coverage. Then perform a limited apply,
compare protected resources and volumes before/after, and confirm that jobs do
not overlap maintenance. Test cancellation/crash recovery. Enable weekly policy
only after those checks, and tune cache targets and resource limits from observed
job performance and daemon I/O.

Fixtures do not qualify a production runner. Native AMD64/ARM64 build, smoke,
vulnerability, SBOM/provenance, isolated real-daemon E2E, and representative-runner
rollout evidence are release/deployment gates. Rootless, remapped, SELinux-specific,
custom-builder, remote, and VM-host adapters remain separate qualification work.

To disable, stop the timers and dispatch path. Preserve any unresolved admission
block until reconciliation. Roll back to a previously verified pre-pulled digest
and compatible host adapter/configuration after reviewing protocol/schema
compatibility. Rollback changes future behavior; it cannot restore deleted data.
