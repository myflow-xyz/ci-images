# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG BUILD_CREATED=unknown
ARG BUILD_REVISION=unknown
ARG GOLANGCI_LINT_VERSION
ARG GOIMPORTS_VERSION
ARG GOOSE_VERSION
ARG GOVULNCHECK_VERSION
ARG GO_SHA256_AMD64
ARG GO_SHA256_ARM64
ARG GO_VERSION
ARG MANIFEST_SHA=unknown
ARG SQLC_VERSION
ARG TARGETARCH

USER root

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
      gcc \
      g++ \
      libc6-dev \
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
      /tmp/go.tar.gz; \
    tar -xzf /tmp/go.tar.gz -C /usr/local; \
    rm -f /tmp/go.tar.gz; \
    test "$(/usr/local/go/bin/go version | awk '{print $3}')" \
      = "go${GO_VERSION}"

RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    set -eu; \
    install_tool() { \
      name=$1; \
      package=$2; \
      version=$3; \
      output_directory="/opt/ci-tools/${name}/${version#v}"; \
      install -d "${output_directory}"; \
      CGO_ENABLED=0 \
      GOBIN="${output_directory}" \
      GOCACHE=/root/.cache/go-build \
      GOMODCACHE=/go/pkg/mod \
      GOPATH=/go \
        /usr/local/go/bin/go install \
          -buildvcs=false \
          -trimpath \
          "${package}@${version}"; \
    }; \
    install_tool \
      sqlc \
      github.com/sqlc-dev/sqlc/cmd/sqlc \
      "${SQLC_VERSION}"; \
    install_tool \
      goose \
      github.com/pressly/goose/v3/cmd/goose \
      "${GOOSE_VERSION}"; \
    install_tool \
      golangci-lint \
      github.com/golangci/golangci-lint/v2/cmd/golangci-lint \
      "${GOLANGCI_LINT_VERSION}"; \
    install_tool \
      goimports \
      golang.org/x/tools/cmd/goimports \
      "${GOIMPORTS_VERSION}"; \
    install_tool \
      govulncheck \
      golang.org/x/vuln/cmd/govulncheck \
      "${GOVULNCHECK_VERSION}"

ENV GOCACHE=/cache/go/build \
    GOMODCACHE=/cache/go/modules \
    GOPATH=/home/ci/go \
    GOTOOLCHAIN=local \
    PATH=/opt/ci-tools/bin:/usr/local/go/bin:/home/ci/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

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
      /cache/go/build \
      /cache/go/modules \
      /home/ci/go/bin

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
