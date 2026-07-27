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
