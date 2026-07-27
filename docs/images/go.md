# `ci-go`

`ghcr.io/myflow-xyz/ci-go` extends [`ci-base`](base.md) for Go build,
generation, analysis, test, and release jobs.

## Included tools

The initial image contract includes:

- Go 1.26.5, installed from the official per-architecture archive after
  SHA-256 verification, with `GOTOOLCHAIN=local`;
- a C compiler, libc development headers, and native build prerequisites for
  race-enabled tests;
- Go's standard build, format, vet, test, and coverage commands;
- sqlc 1.31.1;
- Goose 3.27.1;
- golangci-lint 2.12.1;
- pinned `goimports` and `govulncheck` releases.

External Go executables are built from exact module versions into immutable
versioned directories. Stable links are exposed through
`/opt/ci-tools/bin`.

## Dependency authority and caches

The image does not package reusable application libraries such as pgx, Cobra,
or Goose libraries. Each repository's `go.mod` and `go.sum` remain
authoritative.

The writable cache contract is:

```text
GOMODCACHE=/cache/go/modules
GOCACHE=/cache/go/build
```

Consumers partition both paths by repository, architecture, Go version, and
`go.sum` hash. Jobs may bypass the caches without changing behavior.

## Consumers

- PMem uses this image for Go verification and release gates.
- MyFlow API Gateway uses it for pure Go and generation jobs.
- MyFlow Identity Service uses it for build, sqlc, Goose, lint, race, and test
  jobs.
- MyFlow Storage Service uses it for Go build, test, and migration jobs.

Add [`ci-postgres`](postgres.md) as a service when a job requires PostgreSQL.
Docker Compose conformance remains outside the ordinary job-image contract.
