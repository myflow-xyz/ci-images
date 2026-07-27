# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

ARG PGVECTOR_IMAGE
FROM ${PGVECTOR_IMAGE}

ARG BUILD_CREATED=unknown
ARG BUILD_REVISION=unknown
ARG MANIFEST_SHA=unknown
ARG PGVECTOR_VERSION
ARG POSTGRES_VERSION

LABEL org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.description="MyFlow PostgreSQL CI service with pgvector" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.source="https://github.com/myflow-xyz/ci-images" \
      org.opencontainers.image.title="MyFlow PostgreSQL CI service" \
      org.myflow.ci.manifest-sha="${MANIFEST_SHA}" \
      org.myflow.ci.pgvector-version="${PGVECTOR_VERSION}" \
      org.myflow.ci.postgres-version="${POSTGRES_VERSION}"

HEALTHCHECK \
  --interval=2s \
  --timeout=5s \
  --start-period=10s \
  --retries=30 \
  CMD pg_isready \
    --username="$${POSTGRES_USER:-postgres}" \
    --dbname="$${POSTGRES_DB:-$${POSTGRES_USER:-postgres}}" || exit 1
