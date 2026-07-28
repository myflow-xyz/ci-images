# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

ARG PGVECTOR_IMAGE
FROM ${PGVECTOR_IMAGE} AS gosu-builder

ARG DEBIAN_SNAPSHOT
ARG GOSU_COMMIT
ARG GO_SHA256_AMD64
ARG GO_SHA256_ARM64
ARG GO_VERSION
ARG TARGETARCH

COPY images/common/fetch-verified /usr/local/libexec/ci/fetch-verified

RUN test -n "${DEBIAN_SNAPSHOT}" \
    && sed -ri \
      "s|URIs: http://deb.debian.org/debian$|URIs: http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/|" \
      /etc/apt/sources.list.d/debian.sources \
    && sed -ri \
      "s|URIs: http://deb.debian.org/debian-security$|URIs: http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}/|" \
      /etc/apt/sources.list.d/debian.sources \
    && sed -ri 's|^deb |# deb |' /etc/apt/sources.list.d/pgdg.list \
    && printf '%s\n' \
      'Acquire::Check-Valid-Until "false";' \
      'Acquire::Retries "5";' \
      > /etc/apt/apt.conf.d/99-ci-snapshot \
    && apt-get update \
    && apt-get install --yes --no-install-recommends \
      ca-certificates \
      curl \
    && rm -rf /var/lib/apt/lists/* \
    && chmod 0755 /usr/local/libexec/ci/fetch-verified

RUN set -eu; \
    case "${TARGETARCH}" in \
      amd64) go_sha256="${GO_SHA256_AMD64}" ;; \
      arm64) go_sha256="${GO_SHA256_ARM64}" ;; \
      *) \
        printf 'unsupported target architecture: %s\n' "${TARGETARCH}" >&2; \
        exit 1 \
        ;; \
    esac; \
    /usr/local/libexec/ci/fetch-verified \
      "https://go.dev/dl/go${GO_VERSION}.linux-${TARGETARCH}.tar.gz" \
      "${go_sha256}" \
      /var/tmp/go.tar.gz; \
    tar -xzf /var/tmp/go.tar.gz -C /usr/local; \
    rm -f /var/tmp/go.tar.gz; \
    test "$(/usr/local/go/bin/go version | awk '{print $3}')" \
      = "go${GO_VERSION}"

RUN --mount=type=cache,target=/var/cache/go/mod \
    --mount=type=cache,target=/var/cache/go/build \
    set -eu; \
    install -d /out; \
    CGO_ENABLED=0 \
    GOBIN=/out \
    GOCACHE=/var/cache/go/build \
    GOMODCACHE=/var/cache/go/mod \
    GOPATH=/var/lib/go \
    GOTOOLCHAIN=local \
      /usr/local/go/bin/go install \
        -buildvcs=false \
        -trimpath \
        "github.com/tianon/gosu@${GOSU_COMMIT}"

FROM ${PGVECTOR_IMAGE}

ARG BUILD_CREATED=unknown
ARG BUILD_REVISION=unknown
ARG DEBIAN_SNAPSHOT
ARG GOSU_VERSION
ARG MANIFEST_SHA=unknown
ARG PGVECTOR_VERSION
ARG POSTGRES_VERSION

ENV LANG=en_US.utf8 \
    LC_ALL=en_US.utf8 \
    PATH=/opt/ci-tools/bin:${PATH}

RUN test -n "${DEBIAN_SNAPSHOT}" \
    && sed -ri \
      "s|URIs: http://deb.debian.org/debian$|URIs: http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/|" \
      /etc/apt/sources.list.d/debian.sources \
    && sed -ri \
      "s|URIs: http://deb.debian.org/debian-security$|URIs: http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}/|" \
      /etc/apt/sources.list.d/debian.sources \
    && sed -ri 's|^deb |# deb |' /etc/apt/sources.list.d/pgdg.list \
    && printf '%s\n' \
      'Acquire::Check-Valid-Until "false";' \
      'Acquire::Retries "5";' \
      > /etc/apt/apt.conf.d/99-ci-snapshot \
    && apt-get update \
    && apt-get upgrade --yes --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && sed -ri 's|^# deb |deb |' /etc/apt/sources.list.d/pgdg.list

COPY --from=gosu-builder \
  /out/gosu \
  /opt/ci-tools/gosu/${GOSU_VERSION}/gosu

RUN set -eu; \
    install -d /opt/ci-tools/bin; \
    ln -s \
      "../gosu/${GOSU_VERSION}/gosu" \
      /opt/ci-tools/bin/gosu; \
    test "$(gosu --version | awk '{print $1}')" = "${GOSU_VERSION}"

LABEL org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.description="MyFlow PostgreSQL CI service with pgvector" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.source="https://github.com/myflow-xyz/ci-images" \
      org.opencontainers.image.title="MyFlow PostgreSQL CI service" \
      org.myflow.ci.gosu-version="${GOSU_VERSION}" \
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
