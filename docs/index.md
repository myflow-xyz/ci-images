# Documentation

The [repository README](../README.md) owns the project overview, image
hierarchy, repository structure, and high-level design boundaries. This page
routes to the detailed operational and image contracts without repeating that
overview.

## Operator guides

- [Using the CI images](usage.md), including
  [self-hosted bind-mount permissions](usage.md#self-hosted-bind-mount-permissions)
- [Releasing the CI images](release.md)

## Image contracts

- [`ci-base`](images/base.md)
- [`ci-go`](images/go.md)
- [`ci-node`](images/node.md)
- [`ci-vite`](images/vite.md)
- [`ci-playwright`](images/playwright.md)
- [`ci-postgres`](images/postgres.md)

## Source authorities

- [`manifests/versions.json`](../manifests/versions.json) records reviewed
  versions, digests, source revisions, dependency overrides, and checksums.
- [`images/`](../images) contains the immutable image build definitions and
  installation inputs.
- [Image verification and publication](../.github/workflows/images.yml) defines
  the build, smoke-test, scan, and promotion policy.
- [Release promotion](../.github/workflows/release.yml) defines stable suite
  releases.
- [Runner directory bootstrap](../scripts/docs/setup-runner-from-scratch.md)
  documents creation of the independent self-hosted runner skeleton.
- [Runner permission setup](../scripts/docs/setup-runner-permissions.md)
  documents the independent self-hosted helper.
- [`scripts/tests/`](../scripts/tests) verifies the runner helpers independently
  from the image contracts in [`tests/`](../tests).
