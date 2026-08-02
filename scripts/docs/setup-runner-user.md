# Runner identity setup

`setup-runner-user.sh` creates or verifies the fixed host identity used by the
self-hosted GitHub Actions runner:

```text
user              ci-runner
home              /opt/actions-runner
login shell       /bin/bash
primary group     ci-runner
shared group      mfci (GID 2001)
additional groups docker, mfci
```

The account's home field is set to `/opt/actions-runner`, but this helper does
not create that directory. The directory helper owns the runner-root filesystem
boundary and creates it in the next provisioning stage.

## Requirements and boundary

- Debian- or RHEL-family Linux with Bash and GNU account utilities;
- execution through `sudo`, including dry-run mode;
- an existing `docker` group;
- no conflicting `ci-runner` account, private group, `mfci` group, or GID
  `2001` assignment.

The `docker` group grants control of the Docker daemon and is effectively
root-equivalent on a typical rootful Docker host. Add only the dedicated runner
account, and do not reuse `docker` as the bind-mount permission group.

When `mfci` is absent, the helper creates it with GID `2001` only if that GID is
unused. A new `ci-runner` gets a private primary group, `/bin/bash`, the fixed
home metadata, and supplementary membership in `docker` and `mfci`. An existing
account is accepted only when those fixed identity fields already match; any
missing supplementary memberships are appended without removing other groups.

The helper does not create the home directory, install Docker, create the
`docker` group, install packages, download or register a runner, configure
credentials, or manage a service.

## Usage

Preview the identity plan without changing the host:

```bash
sudo scripts/setup-runner-user.sh --dry-run
```

Create or verify the identity:

```bash
sudo scripts/setup-runner-user.sh
```

If the helper adds supplementary membership to an account whose runner service
is already running, restart that service before accepting jobs.

Continue with the
[runner directory helper](setup-runner-from-scratch.md), then apply the
[runner permission helper](setup-runner-permissions.md).

## Tests

- `tests/setup-runner-user_spec.sh` checks the fixed CLI contract through
  ShellSpec.
- `tests/setup-runner-user_integration.sh` verifies dry-run behavior, exact
  identity creation, group membership, home-directory separation, and
  idempotent reruns on Linux.
