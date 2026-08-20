# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG BUILD_CREATED=unknown
ARG BUILD_REVISION=unknown
ARG GOLANGCI_LINT_VERSION
ARG GOLANGCI_LINT_X_TEXT_VERSION
ARG GOIMPORTS_X_MOD_VERSION
ARG GOIMPORTS_VERSION
ARG GOOSE_VERSION
ARG GOOSE_X_CRYPTO_VERSION
ARG GOOSE_GRPC_VERSION
ARG GOOSE_MODERNC_LIBC_VERSION
ARG GOOSE_X_NET_VERSION
ARG GOVULNCHECK_X_MOD_VERSION
ARG GOVULNCHECK_VERSION
ARG GO_SHA256_AMD64
ARG GO_SHA256_ARM64
ARG GO_VERSION
ARG HURL_SHA256_AMD64
ARG HURL_SHA256_ARM64
ARG HURL_VERSION
ARG MANIFEST_SHA=unknown
ARG SQLC_VERSION
ARG SQLC_GRPC_VERSION
ARG SQLC_X_NET_VERSION
ARG TARGETARCH

USER root

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
      gcc \
      g++ \
      libc6-dev \
      libxml2 \
      pkg-config \
    && rm -rf /var/lib/apt/lists/*

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

RUN set -eu; \
    case "${TARGETARCH}" in \
      amd64) \
        hurl_arch=x86_64; \
        hurl_sha256="${HURL_SHA256_AMD64}" \
        ;; \
      arm64) \
        hurl_arch=aarch64; \
        hurl_sha256="${HURL_SHA256_ARM64}" \
        ;; \
      *) \
        printf 'unsupported target architecture: %s\n' "${TARGETARCH}" >&2; \
        exit 1 \
        ;; \
    esac; \
    hurl_distribution="hurl-${HURL_VERSION}-${hurl_arch}-unknown-linux-gnu"; \
    install -d "/opt/ci-tools/hurl/${HURL_VERSION}"; \
    /usr/local/libexec/ci/fetch-verified \
      "https://github.com/Orange-OpenSource/hurl/releases/download/${HURL_VERSION}/${hurl_distribution}.tar.gz" \
      "${hurl_sha256}" \
      /var/tmp/hurl.tar.gz; \
    tar -xzf /var/tmp/hurl.tar.gz \
      --strip-components=2 \
      -C "/opt/ci-tools/hurl/${HURL_VERSION}" \
      "${hurl_distribution}/bin/hurl" \
      "${hurl_distribution}/bin/hurlfmt"; \
    ln -s \
      "../hurl/${HURL_VERSION}/hurl" \
      /opt/ci-tools/bin/hurl; \
    ln -s \
      "../hurl/${HURL_VERSION}/hurlfmt" \
      /opt/ci-tools/bin/hurlfmt; \
    hurl --version | grep --fixed-strings "hurl ${HURL_VERSION}" >/dev/null; \
    hurlfmt --version | grep --fixed-strings "hurlfmt ${HURL_VERSION}" >/dev/null; \
    rm -f /var/tmp/hurl.tar.gz

RUN --mount=type=cache,target=/var/cache/go/mod,sharing=locked \
    --mount=type=cache,target=/var/cache/go/build,sharing=locked \
    set -eu; \
    build_tool() { \
      name=$1; \
      package=$2; \
      version=$3; \
      shift 3; \
      build_directory="/var/tmp/build/${name}"; \
      output_directory="/opt/ci-tools/${name}/${version#v}"; \
      install -d "${build_directory}" "${output_directory}"; \
      cd "${build_directory}"; \
      /usr/local/go/bin/go mod init "ci.invalid/${name}"; \
      /usr/local/go/bin/go get "${package}@${version}"; \
      for dependency in "$@"; do \
        /usr/local/go/bin/go get "${dependency}"; \
      done; \
      CGO_ENABLED=0 /usr/local/go/bin/go build \
          -buildvcs=false \
          -trimpath \
          -o "${output_directory}/${name}" \
          "${package}"; \
    }; \
    export \
      GOCACHE=/var/cache/go/build \
      GOMODCACHE=/var/cache/go/mod \
      GOPATH=/var/lib/go \
      GOTOOLCHAIN=local; \
    build_tool \
      sqlc \
      github.com/sqlc-dev/sqlc/cmd/sqlc \
      "${SQLC_VERSION}" \
      "golang.org/x/net@${SQLC_X_NET_VERSION}" \
      "google.golang.org/grpc@${SQLC_GRPC_VERSION}"; \
    build_tool \
      goose \
      github.com/pressly/goose/v3/cmd/goose \
      "${GOOSE_VERSION}" \
      "golang.org/x/crypto@${GOOSE_X_CRYPTO_VERSION}" \
      "golang.org/x/net@${GOOSE_X_NET_VERSION}" \
      "google.golang.org/grpc@${GOOSE_GRPC_VERSION}" \
      "modernc.org/libc@${GOOSE_MODERNC_LIBC_VERSION}"; \
    build_tool \
      golangci-lint \
      github.com/golangci/golangci-lint/v2/cmd/golangci-lint \
      "${GOLANGCI_LINT_VERSION}" \
      "golang.org/x/text@${GOLANGCI_LINT_X_TEXT_VERSION}"; \
    build_tool \
      goimports \
      golang.org/x/tools/cmd/goimports \
      "${GOIMPORTS_VERSION}" \
      "golang.org/x/mod@${GOIMPORTS_X_MOD_VERSION}"; \
    build_tool \
      govulncheck \
      golang.org/x/vuln/cmd/govulncheck \
      "${GOVULNCHECK_VERSION}" \
      "golang.org/x/mod@${GOVULNCHECK_X_MOD_VERSION}"

ENV GOBIN=/opt/ci-tools/bin \
    GOCACHE=/var/cache/go/build \
    GOMODCACHE=/var/cache/go/mod \
    GOPATH=/var/lib/go \
    GOROOT=/usr/local/go \
    GOTMPDIR=/var/tmp/go \
    GOTOOLCHAIN=local \
    PATH=/usr/local/go/bin:/opt/ci-tools/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN set -eu; \
    ln -s \
      "../sqlc/${SQLC_VERSION#v}/sqlc" \
      /opt/ci-tools/bin/sqlc; \
    ln -s \
      "../goose/${GOOSE_VERSION#v}/goose" \
      /opt/ci-tools/bin/goose; \
    ln -s \
      "../golangci-lint/${GOLANGCI_LINT_VERSION#v}/golangci-lint" \
      /opt/ci-tools/bin/golangci-lint; \
    ln -s \
      "../goimports/${GOIMPORTS_VERSION#v}/goimports" \
      /opt/ci-tools/bin/goimports; \
    ln -s \
      "../govulncheck/${GOVULNCHECK_VERSION#v}/govulncheck" \
      /opt/ci-tools/bin/govulncheck; \
    install -d -o ci -g ci \
      /var/cache/go/build \
      /var/cache/go/mod \
      /var/lib/go \
      /var/tmp/go

LABEL org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.description="MyFlow Go CI job environment" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.source="https://github.com/myflow-xyz/ci-images" \
      org.opencontainers.image.title="MyFlow Go CI" \
      org.myflow.ci.go-version="${GO_VERSION}" \
      org.myflow.ci.manifest-sha="${MANIFEST_SHA}"

USER ci
WORKDIR /workspace

CMD ["bash"]
