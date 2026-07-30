# Runner permission setup

`setup-runner-permissions.sh` prepares host directories shared by self-hosted
GitHub Actions runners and MyFlow job containers.

## Managed boundary

The helper manages only these paths below the selected runner root:

```text
<runner-root>/*/_work
<runner-root>/shared/cache
```

It leaves the runner root, `shared`, and each runner installation directory
outside the writable group boundary. Before reporting success or changing a
managed path, it rejects effective group, other, or named-ACL write access on
those unmanaged parents. It never repairs them; the runner operator retains
their ownership and policy. Symbolic links are not followed. Existing named ACL
entries below managed paths are removed so only each entry's owner, the shared
group, and a no-access `other` entry remain. FIFOs, sockets, and device nodes are
rejected before any permission changes.

When `shared` is absent, the helper creates it as mode `0755`, owned by the
resolved runner owner and that account's primary group. The shared CI group
receives write access only from `shared/cache` downward.

Each managed `_work` or `shared/cache` root remains owned by the resolved runner
owner. Descendants created later by a job container may retain the container
UID. Directories remain `2770`; each regular file's group permissions mirror
its owner permissions. This preserves intentional read-only files such as Git
objects while the shared GID and inherited ACLs provide equivalent access to
both identities.

## Requirements

- Linux with Bash, GNU account utilities, and POSIX ACL tools;
- execution through `sudo` for planning or applying changes;
- an existing non-root runner owner and shared group;
- drained runners while existing trees are normalized.

The defaults are runner root `/opt/actions-runner`, owner `github-runner`, and
group `mfci`. `--runner-root`, `--owner`, and `--group` override them. Owner and
group values may be names or numeric IDs, but must resolve through the host
account database.

## Default host identity

GID `2001` is a MyFlow convention rather than a globally reserved value. Verify
that it is unused before creating `mfci`:

```bash
getent group 2001
sudo groupadd -g 2001 mfci
getent group mfci
sudo usermod -aG mfci github-runner
groups github-runner
```

The first lookup must return no group. The post-creation lookup must report GID
`2001`, and the runner account must include `mfci`. Restart an already-running
runner service after changing its supplementary groups.

## Usage

Preview the resolved identities and targets without changing the host:

```bash
sudo scripts/setup-runner-permissions.sh --dry-run
```

For a workflow that intentionally depends on these bind mounts, verify the
existing host state without root access or mutations. Run this directly from a
host-side step inherited from the runner service:

```bash
scripts/setup-runner-permissions.sh --check
```

`--check` requires the invoking UID to match the resolved runner owner. It
verifies both the account database and the current process's effective groups;
do not invoke it through `sudo`, `su`, or another fresh login that would receive
a new group list. On failure, stop the workflow. A runner operator must drain
the runner, apply the required host changes with `sudo`, restart the runner
service when reported, and then rerun the workflow.

Apply and verify the permission contract:

```bash
sudo scripts/setup-runner-permissions.sh
```

For a different layout or identity:

```bash
sudo scripts/setup-runner-permissions.sh \
  --runner-root /home/github-runner \
  --owner ci-user \
  --group ci-group
```

The apply run:

- adds the owner to the shared group when needed;
- creates a non-group-writable `shared` parent and `shared/cache` when absent;
- initially assigns the resolved owner and group recursively;
- enforces exact directory access and mirrors each file's owner permissions to
  the shared group while removing other and unexpected special-mode bits;
- replaces existing ACLs and configures setgid inheritance on directories;
- preserves creator-requested read-only, writable, and executable file modes;
- verifies managed-root ownership, descendant group ownership, modes, ACLs, and
  group membership;
- rejects unsafe write access on unmanaged parent directories without changing
  them.

If the result reports `restart-required=yes`, restart the runner service before
accepting another job.

Pre-create every exact cache bind source before Docker starts a job, then run
the helper so the new leaves are normalized. Docker may otherwise create a
missing source with unsuitable ownership.

See the
[image usage guide](../../docs/usage.md#self-hosted-bind-mount-permissions) for
the container-side GID contract and volume examples.

## Tests

The independent test project is rooted at `scripts/.shellspec`. It loads
`tests/spec_helper.sh`, whose precheck hook runs Bash syntax validation,
ShellCheck, and shfmt before the ShellSpec examples.

- `tests/setup-runner-permissions_spec.sh` checks the CLI contract through
  ShellSpec.
- `tests/setup-runner-permissions_integration.sh` checks recursive ownership,
  modes, ACL inheritance, group writes, Git read-only objects, dry-run behavior,
  and safety boundaries in disposable directories.

Run ShellSpec from the script project directory:

```bash
cd scripts
shellspec
```

The integration test requires root and the same Linux ACL tools as the helper:

```bash
sudo scripts/tests/setup-runner-permissions_integration.sh
```

The independent `Runner helper / Contract` workflow runs both suites against
disposable test directories. It does not inspect or change runner host paths.

ShellSpec DSL indentation is retained in the specification file because shfmt
does not model ShellSpec's block syntax.
