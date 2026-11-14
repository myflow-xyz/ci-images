# `ci-go`

`ghcr.io/myflow-xyz/ci-go` extends [`ci-base`](base.md) for Go build, generation, analysis, test, and release jobs.

## Included tools

The initial image contract includes:

- Go 1.27.4, installed from the official per-architecture archive after SHA-256 verification, with local toolchain selection and the JSON v2 implementation enabled by default;
- a C compiler, libc development headers, and native build prerequisites for race-enabled tests;
- Go's standard build, format, vet, test, and coverage commands;
- HTTP/API end-to-end testing with Hurl 8.1.0 and request formatting with `hurlfmt`;
- sqlc 1.31.1;
- Goose 3.30.1;
- golangci-lint 2.15.0;
- `goimports` 0.52.0 and `govulncheck` 1.9.0.

External Go executables are built from exact module versions into immutable versioned directories. Stable links are exposed through `/opt/ci-tools/bin`.

Hurl and `hurlfmt` are built from checksum-pinned 8.1.0 source and a reviewed Cargo lockfile. Their private library directory contains patched Brotli, curl, OpenSSL, nghttp3, and ngtcp2 builds. HTTP/3 support and the system CA certificate paths are retained. The manifest pins the source archives and Rust compiler. Build compilers are excluded from the runtime image; the Go image's existing C compiler remains available for Go jobs.

The image pins Debian `linux-libc-dev` 6.12.115-2 from the signed security archive, ahead of the general package snapshot. Its source package contains fixes for CVE-2026-98432 and CVE-2026-99083. These userspace headers do not update the [runner's kernel](../usage.md#workload-patterns).

The manifest records narrow dependency overrides used to rebuild a tool when its released dependency graph contains a known vulnerability with a fixed version or an upstream-retracted module version. The image smoke contract verifies those resolved module versions; an override is removed when the upstream tool release incorporates the fix.

## Runtime environment

The image adds this Go environment to the variables inherited from `ci-base`:

```text
GOBIN=/opt/ci-tools/bin
GOCACHE=/var/cache/go/build
GOMODCACHE=/var/cache/go/mod
GOPATH=/var/lib/go
GOROOT=/usr/local/go
GOTMPDIR=/var/tmp/go
GOTOOLCHAIN=local
PATH=/usr/local/go/bin:/opt/ci-tools/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
```

`GOBIN` identifies the image-global command location. It remains image-managed; ordinary jobs do not mutate the preinstalled tool set.

## Dependency authority and caches

The image does not package reusable application libraries such as pgx, Cobra, or Goose libraries. Each repository's `go.mod` and `go.sum` remain authoritative.

Consumers partition `GOMODCACHE` and `GOCACHE` by repository, architecture, Go version, and `go.sum` hash. Jobs may bypass the caches without changing behavior.

## Usage

Use `ci-go` for Go generation, build, lint, race, test, and release jobs.

Add [`ci-postgres`](postgres.md) as a service when a job requires PostgreSQL. Docker CLI and Compose are inherited from `ci-base`. Trusted fixture jobs explicitly supply a qualified daemon endpoint under the [base client contract](base.md#docker-client-contract).
