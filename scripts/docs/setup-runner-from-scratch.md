# Runner directory bootstrap

`setup-runner-from-scratch.sh` creates the host directory skeleton for one
self-hosted GitHub Actions runner. Identity provisioning and recursive
permission policy are separate stages.

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
`shared/downloads` are owner-managed mode `0755` directories. `_work` and
`shared/cache` are initially group-owned mode `2770` directories. The separate
permission helper recursively normalizes those two managed trees and applies
their inherited ACLs.

The root-owned, read-only `.mfci-runner-root` marker records that this helper
created the runner root. Existing roots are accepted only with that marker,
making the helper safe to rerun without adopting arbitrary host directories.
Directory modes and owners at the eight explicit skeleton paths are normalized,
but their existing contents are not modified recursively. Symbolic links and
non-directory entries at any target path are rejected before the skeleton is
changed.

## Requirements and boundary

- Debian- or RHEL-family Linux with Bash and GNU account utilities;
- execution through `sudo`, including dry-run mode;
- an existing non-root runner owner and shared group;
- runner-owner membership in the shared group;
- an existing real parent directory for a runner root that has not yet been
  created.

The resolved runner root must be below `/opt`, `/var`, `/home`, or `/Users`.
The prefix allowlist applies after canonicalization, and an existing root must
carry the helper-owned marker. Broad, unapproved, or unmarked targets are
rejected before filesystem changes.

The helper does not create users or groups, change group membership, recurse
through existing contents, apply ACL policy, install system packages, download
or extract a GitHub Actions runner, register it with GitHub, configure
credentials, or manage its service. Run the
[identity helper](setup-runner-user.md) first for the standard host identity.

## Usage

Preview the resolved identities and eight directory targets without changing
the host:

```bash
sudo scripts/setup-runner-from-scratch.sh \
  --runner-root /opt/actions-runner \
  --owner ci-runner \
  --repository repo-example \
  --dry-run
```

Create and verify the structure using the default `mfci` shared group:

```bash
sudo scripts/setup-runner-from-scratch.sh \
  --runner-root /opt/actions-runner \
  --owner ci-runner \
  --repository repo-example
```

Use `--group GROUP|GID` for a different existing shared group. The canonical
`mfci` group must use GID `2001`. The owner may be a name or numeric ID. The
repository value is a single directory name, not a path.

If the owner is not in the resolved shared group, apply mode stops before
creating or normalizing the runner root. Dry-run reports the missing membership
without changing the host.

After creating the structure, apply and verify recursive permissions:

```bash
sudo scripts/setup-runner-permissions.sh \
  --runner-root /opt/actions-runner \
  --owner ci-runner \
  --group mfci
```

## Tests

- `tests/setup-runner-from-scratch_spec.sh` checks required inputs and the CLI
  contract through ShellSpec.
- `tests/setup-runner-from-scratch_integration.sh` verifies dry-run behavior,
  prerequisite membership, the complete directory structure, ownership and
  mode boundaries, non-recursive reruns, and unsafe target rejection in a
  disposable Linux tree.

The independent `Runner helper / Contract` workflow runs both suites without
accessing real runner host paths.
