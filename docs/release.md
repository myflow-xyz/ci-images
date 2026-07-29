# Releasing the CI images

A release assigns one semantic version to the verified six-image suite. It
promotes existing OCI index digests; it does not rebuild or rescan images.

## Preconditions

The release workflow accepts only the current `main` commit. The CI images
workflow for that commit must have completed successfully and promoted all six
images to both:

- `sha-<full-commit>` for immutable source identity;
- `latest` for the current verified `main` suite.

The `sha-<full-commit>` and `latest` tags must resolve to the same digest for
every image. This prevents a release from combining images from different
source revisions.

## Version selection

Run the **Release CI images** workflow on `main` and select one bump:

| Selection | Previous stable version | Next version |
| --- | --- | --- |
| `patch` | `v1.2.3` | `v1.2.4` |
| `minor` | `v1.2.3` | `v1.3.0` |
| `major` | `v1.2.3` | `v2.0.0` |

`patch` is the default. If the repository has no stable version tag, the
baseline is `v0.0.0`; select `minor` for an initial `v0.1.0` release or `major`
for `v1.0.0`.

One version always covers `ci-base`, `ci-go`, `ci-node`, `ci-vite`,
`ci-playwright`, and `ci-postgres`. Individual images do not advance versions
independently.

## Release transaction

The workflow:

1. verifies that the selected revision is the current `main` commit;
2. calculates the next version from stable Git tags;
3. resolves and compares every immutable revision tag and `latest` tag;
4. rejects a version tag that already identifies another digest;
5. assigns the version tag to each verified OCI index and verifies the result;
6. creates the Git tag and GitHub Release at the source revision, including the
   six index digests.

The Git tag is created only after registry promotion succeeds. A version tag
that already identifies the expected digest is accepted so a partially
completed registry promotion can be retried safely.

## Tag policy

| Tag | Created by | Contract |
| --- | --- | --- |
| `candidate-<run>-<attempt>` | image publication | Internal only. |
| `sha-<full-commit>` | verified publication | Immutable source revision. |
| `edge` | verified `develop` push | Moving integration pointer. |
| `latest` | verified `main` push | Moving stable-branch pointer. |
| `run-<run>` | manual image publication | Ad hoc verification pointer. |
| `vX.Y.Z` | manual release | Immutable suite release. |

Consumers use the shared `vX.Y.Z` tag and pin its OCI index digest in workflow
configuration. The container runtime selects the compatible platform manifest;
architecture-specific suffix tags are not part of the release contract.
Neither `edge` nor `latest` is a reproducible consumer pin.

## Verification

A release is successful only when:

- the Release CI images workflow completed successfully;
- the GitHub Release and Git tag point to the intended `main` commit;
- all six release tags exist in GHCR;
- each release tag resolves to the digest recorded in the GitHub Release;
- that digest also matches the commit's immutable revision tag.

The source image workflow already verified that every index contains
`linux/amd64` and `linux/arm64` manifests, per-platform attestations, smoke
tests, standard GitHub-hosted job-container write compatibility, and
vulnerability policy before creating the immutable revision tags. The release
workflow verifies and retags those exact indexes rather than repeating the
build.

See [the usage guide](usage.md#pulling-and-pinning) for registry authentication,
digest inspection, and pull examples.

## Failure and rollback

If registry promotion stops after assigning only some version tags, rerun the
same bump. The absent Git tag causes the same version to be calculated, and
matching existing registry tags are preserved.

If an existing version tag has a different digest, the workflow fails before
promotion. Investigate the registry state; do not overwrite or delete the
stable tag to force a release.

Published versions are never moved. Roll back a consumer by restoring a
previous recorded digest. Publish a new version for any corrected image suite.

## References

- [GitHub Actions manual workflow inputs][workflow-inputs]
- [GitHub CLI release creation][release-create]

[release-create]: https://cli.github.com/manual/gh_release_create
[workflow-inputs]: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatchinputs
