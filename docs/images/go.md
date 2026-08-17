# `ci-go`

`ghcr.io/myflow-xyz/ci-go` extends [`ci-base`](base.md) for Go build,
generation, analysis, test, and release jobs.

## Included tools

The initial image contract includes:

- Go 1.26.6, installed from the official per-architecture archive after
  SHA-256 verification, with local toolchain selection and the JSON v2
  experiment enabled;
- a C compiler, libc development headers, and native build prerequisites for
  race-enabled tests;
- Go's standard build, format, vet, test, and coverage commands;
- HTTP/API end-to-end testing with Hurl 8.0.1 and request formatting with
  `hurlfmt`;
- sqlc 1.31.1;
- Goose 3.27.3;
- golangci-lint 2.12.2;
- pinned `goimports` and `govulncheck` releases.

External Go executables are built from exact module versions into immutable
versioned directories. Stable links are exposed through
`/opt/ci-tools/bin`. Hurl executables are installed from checksum-pinned
upstream Linux archives for both supported architectures.

The manifest records narrow dependency overrides used to rebuild a tool when
its released dependency graph contains a fixed HIGH or CRITICAL vulnerability
or an upstream-retracted module version. The image smoke contract verifies
those resolved module versions; an override is removed when the upstream tool
release incorporates the fix.

## Runtime environment

The image adds this Go environment to the variables inherited from `ci-base`:

```text
GOBIN=/opt/ci-tools/bin
GOCACHE=/var/cache/go/build
GOEXPERIMENT=jsonv2
GOMODCACHE=/var/cache/go/mod
GOPATH=/var/lib/go
GOROOT=/usr/local/go
GOTMPDIR=/var/tmp/go
GOTOOLCHAIN=local
PATH=/usr/local/go/bin:/opt/ci-tools/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
```

`GOBIN` identifies the image-global command location. It remains image-managed;
ordinary jobs do not mutate the preinstalled tool set.

## Dependency authority and caches

The image does not package reusable application libraries such as pgx, Cobra,
or Goose libraries. Each repository's `go.mod` and `go.sum` remain
authoritative.

Consumers partition `GOMODCACHE` and `GOCACHE` by repository, architecture, Go
version, and `go.sum` hash. Jobs may bypass the caches without changing
behavior.

## Usage

Use `ci-go` for Go generation, build, lint, race, test, and release jobs.

Add [`ci-postgres`](postgres.md) as a service when a job requires PostgreSQL.
Docker Compose conformance remains outside the ordinary job-image contract.
