# `ci-postgres`

`ghcr.io/myflow-xyz/ci-postgres` is a GitHub Actions service image. It is built
from a digest-pinned
`pgvector/pgvector:0.8.2-pg18-bookworm` image and does not inherit from a job
image.

## Included service contract

The image provides:

- PostgreSQL 18 server and client utilities;
- `pg_isready`, `psql`, `pg_dump`, and `pg_restore`;
- pgvector 0.8.2 and the `vector` extension files;
- PostgreSQL contrib support required by `pgcrypto`;
- a health check driven by the runtime database name and user.

It preserves the upstream PostgreSQL entrypoint, user, data-directory, and
initialization behavior.

The derived layer refreshes Debian packages from the same reviewed,
Debian-signed snapshot as the job images while leaving the upstream PostgreSQL
repository disabled during that refresh. The service base omits CA
certificates, so the snapshot bootstrap uses HTTP with apt's signature
verification; the isolated builder installs CA certificates before fetching Go
over HTTPS. The image also replaces the upstream `gosu` executable with version
1.19 built from its exact source commit using Go 1.26.5. The replacement remains
at the canonical `/usr/local/bin/gosu` path and is exposed through
`/opt/ci-tools/bin`. Neither the Go compiler nor build sources are retained.

## Runtime environment

The effective runtime environment is:

```text
LANG=en_US.utf8
LC_ALL=en_US.utf8
PATH=/opt/ci-tools/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/lib/postgresql/18/bin
PGDATA=/var/lib/postgresql/18/docker
PG_MAJOR=18
PGVECTOR_VERSION=0.8.2
```

This independent service lineage defines the same locale as `ci-base`, adds the
`/opt/ci-tools/bin` prefix to the upstream `PATH`, preserves the upstream
`PGDATA`, and exposes the service's PostgreSQL major and pgvector feature
versions. Runtime values such as `POSTGRES_DB`, `POSTGRES_USER`, and
`POSTGRES_PASSWORD` are consumer inputs to the preserved upstream entrypoint,
not image defaults.

## Repository authority

The image does not create application roles, schemas, extensions, credentials,
or data. Repository workflows supply ephemeral credentials and repository
migrations remain responsible for:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

Database containers and data directories are job-scoped. Do not restore or
share PostgreSQL data directories as dependency caches.

## Consumers

- PMem uses this service for pgvector-backed tests.
- MyFlow Identity Service uses it for PostgreSQL and `pgcrypto` tests.
- MyFlow Storage Service uses it for PostgreSQL migration and integration
  tests.

Containerized jobs address the service by its workflow label on port 5432.
Host-executed jobs publish a dynamic host port instead.
