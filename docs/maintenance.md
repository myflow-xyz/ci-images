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

### Test a published utility image

Open **Actions → Isolated utility tests → Run workflow**. This separate workflow
(`utils-test.yml`) pulls an existing image and runs both disposable-daemon stores.
It does not build or publish images, install host services, or qualify maintenance
against the runner's shared daemon. Normal `CI images` runs retain both stores.
The workflow must first exist on the default branch for
[manual dispatch](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).

Set `utils_runner` to an additional self-hosted runner label that uniquely selects
the target host, such as `utils-lab-01`. A runner name must also be a registered
label. In the repository or organization **Settings → Actions →
Runners**, open the runner and inspect or assign its
[labels](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/apply-labels).
The runner needs Bash, Python 3, Git, and Docker CLI access to a local Unix socket
for a Linux `amd64` or `arm64` daemon. A macOS runner with Linux Docker can run
these isolated tests; the native Linux host adapter needs separate qualification.
Runs using the same target label are serialized across source branches, with
concurrency separate from normal image CI.

`utils_image` is optional and always selects `ghcr.io/myflow-xyz/ci-utils`:

| Input | Selection |
| --- | --- |
| Omitted, blank, whitespace only, or `latest` | Published `latest` alias |
| `0.0.17` | Published version `X.Y.Z`; omit the Git-tag `v` prefix |
| `sha256:<64 lowercase hex characters>` | Published index digest |
| `<64 lowercase hex characters>` | Same index digest, with `sha256:` added |
| `ghcr.io/myflow-xyz/ci-utils@sha256:<64 hex>` | Full-reference form |

Use exactly 64 characters from `0-9` and `a-f` for the digest. `sha256:abc...` and
`abc...` only illustrate the shapes; an ellipsis is not valid input. Supply the
registry's OCI index or Docker manifest-list digest, not a per-platform manifest,
local image/config ID, or layer digest. The index must contain the runner's
platform. Other repositories and embedded whitespace/control characters are
rejected. Leading and trailing spaces around a valid selector are ignored.

`latest` means the published stable alias, not a candidate tag, the highest
discovered version, or the selected Git branch. The workflow resolves a tag once,
then pulls and tests that immutable index digest in both stores. A missing tag,
denied access, registry error, or unavailable platform stops the run without
fallback. If `latest` is absent, select an existing version/digest or wait for
release publication.

**Use workflow from** selects the workflow, tests, and repository maintenance
helpers. The image input independently selects the published container. For
ordinary qualification, use `main` with blank input or a fixed version/digest.
For harness or compatibility work, select the branch containing those changes
and keep a fixed image. Selecting `0.0.17` does not switch checkout to `v0.0.17`.
The result qualifies the selected source-and-image combination.

The run summary records the requested selector, normalized reference, immutable
index/reference, platform and child digest, workflow ref, actual checkout commit,
and image source-revision label when available. An absent image label is reported
as `null`. The checkout commit is never substituted for it.

Equivalent CLI examples follow. Replace the runner label and version with
registered and published values:

```sh
gh workflow run utils-test.yml --repo myflow-xyz/ci-images --ref main \
  -f utils_runner=utils-lab-01
gh workflow run utils-test.yml --repo myflow-xyz/ci-images --ref main \
  -f utils_runner=utils-lab-01 -f utils_image=0.0.17
```

### Verify workflow changes locally

The workflow contract tests and controlled registry API tests run in normal CI:

```sh
npm ci --fund=false --ignore-scripts --no-audit --prefix images/node/markdownlint
node --test tests/utils-workflow.mjs
python3 -B -m unittest discover -s tests/qualification -p 'test_*.py'
```

For opt-in live registry and Docker API checks, choose a published selector and
an explicit local Docker endpoint. The registry checks verify immutable digest
forms, provenance, and rejection of child/missing digests. The runtime suites then
exercise guarded cleanup inside disposable daemons; they remove their own
fixtures. Run these commands from the repository root:

```sh
set -eu
utils_image_selector='0.0.17' # Replace with an existing version or index digest.
export DOCKER_HOST="$(docker context inspect --format '{{.Endpoints.docker.Host}}')"
unset DOCKER_CONTEXT
qualification_report=$(mktemp)
trap 'rm -f "$qualification_report"' EXIT
python3 -B tests/qualification/registry_e2e.py \
  --image="$utils_image_selector" --output "$qualification_report"
CI_UTILS_TEST_IMAGE=$(jq -r '.resolved_reference' "$qualification_report")
export CI_UTILS_TEST_IMAGE
tests/utils-docker.sh
CI_UTILS_TEST_IMAGE_STORE=classic tests/utils-docker.sh
```

### Install maintenance scheduling

After the rollout gates below pass, review and install the
[systemd examples](../scripts/examples/ci-utils/). They use the same adapter for
daily and weekly profiles. Adjust the selected Docker service/socket and the
writable state path to match the host settings. Check the unit files with the
host's `systemd-analyze verify` before enabling timers.

Replace `REPLACE_WITH_JOB_GID` in the service's `SupplementaryGroups=` with the
numeric `job_gid` from the reviewed `host.json`. The service drops all
capabilities, so its root identity needs this group membership to read
participant-owned `0640` gate records. Qualify interrupted-job recovery with this
same group and capability profile before enabling scheduling. Retain the empty
`CapabilityBoundingSet=` and the existing gate permissions.

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
