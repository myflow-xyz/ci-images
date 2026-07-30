# Runner directory bootstrap

`setup-runner-from-scratch.sh` creates the host directory skeleton for one
self-hosted GitHub Actions runner and then delegates writable mount policy to
`setup-runner-permissions.sh`.

## Created structure

For repository name `repo-example`, the helper creates:

```text
<runner-root>/
├── .mfci-runner-root
├── workspace/
│   └── repo-example/
│       └── _work/
└── shared/
    ├── bin/
    ├── cache/
    └── downloads/
```

The runner root, `workspace`, repository directory, `shared`, `shared/bin`, and
`shared/downloads` are owner-managed mode `0755` directories. Only `_work` and
`shared/cache` enter the shared-group permission contract; the permission
helper normalizes them to group-owned mode `2770` trees with inherited ACLs.

The root-owned, read-only `.mfci-runner-root` marker records that this helper
created the runner root. Existing roots are accepted only with that marker,
making the helper safe to rerun without adopting arbitrary host directories.
Directory modes and owners at the explicit skeleton paths are normalized, but
contents below `shared/bin` and `shared/downloads` are not modified. Existing
`_work` and `shared/cache` contents are normalized recursively by the delegated
permission helper. Symbolic links and non-directory entries at any target path
are rejected before the skeleton is changed.

## Requirements and boundary

- Linux with Bash, GNU account utilities, and POSIX ACL tools;
- execution through `sudo`, including dry-run mode;
- an existing non-root runner owner;
- an existing real parent directory for a runner root that has not yet been
  created;
- the adjacent executable `setup-runner-permissions.sh`.

The resolved runner root must be below `/opt`, `/var`, `/home`, or `/Users`.
The prefix allowlist applies after canonicalization, and an existing root must
carry the helper-owned marker. Broad, unapproved, or unmarked targets are
rejected before identity or filesystem changes.

The helper may create only the canonical `mfci` group with GID `2001`. It does
not create accounts or arbitrary groups, install system packages, download or
extract a GitHub Actions runner, register it with GitHub, configure credentials,
or manage its service. Those operations remain the runner operator's
responsibility.

## Usage

Preview the resolved identities and eight directory targets without changing
the host:

```bash
sudo scripts/setup-runner-from-scratch.sh \
  --runner-root /opt/actions-runner \
  --owner github-runner \
  --repository repo-example \
  --dry-run
```

Create and verify the structure using the default `mfci` shared group:

```bash
sudo scripts/setup-runner-from-scratch.sh \
  --runner-root /opt/actions-runner \
  --owner github-runner \
  --repository repo-example
```

When `mfci` is absent, the helper creates it only if GID `2001` is unused. It
fails instead of repurposing another group at that GID or accepting `mfci` with
a different GID. Use `--group GROUP|GID` for a different shared group; explicit
alternatives must already resolve through the host account database. The owner
may be a name or numeric ID. The repository value is a single directory name,
not a path.

The bootstrap adds the owner to the resolved shared group when needed. If its
output reports `restart-required=yes`, restart the runner service before
accepting a job. Dry-run reports planned group creation and membership changes
without applying them.

## Tests

- `tests/setup-runner-from-scratch_spec.sh` checks required inputs and the CLI
  contract through ShellSpec.
- `tests/setup-runner-from-scratch_integration.sh` verifies dry-run behavior,
  canonical group creation, owner enrollment, the complete directory structure,
  ownership and mode boundaries, permission delegation, reruns, and unsafe
  target rejection in a disposable Linux tree.

The independent `Runner helper / Contract` workflow runs both suites without
accessing real runner host paths.
