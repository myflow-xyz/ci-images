# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS tsgolint-builder

ARG GO_SHA256_AMD64
ARG GO_SHA256_ARM64
ARG GO_VERSION
ARG OXLINT_TSGOLINT_COMMIT
ARG OXLINT_TSGOLINT_SOURCE
ARG TARGETARCH
ARG TYPESCRIPT_GO_COMMIT

USER root

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
    git init /tmp/tsgolint; \
    git -C /tmp/tsgolint remote add origin "${OXLINT_TSGOLINT_SOURCE}"; \
    git -C /tmp/tsgolint fetch \
      --depth 1 \
      origin \
      "${OXLINT_TSGOLINT_COMMIT}"; \
    git -C /tmp/tsgolint checkout --detach FETCH_HEAD; \
    git -C /tmp/tsgolint submodule update --init --depth 1; \
    test "$(git -C /tmp/tsgolint rev-parse HEAD)" \
      = "${OXLINT_TSGOLINT_COMMIT}"; \
    test "$(git -C /tmp/tsgolint/typescript-go rev-parse HEAD)" \
      = "${TYPESCRIPT_GO_COMMIT}"; \
    ( \
      cd /tmp/tsgolint/typescript-go; \
      git apply ../patches/*.patch \
    ); \
    install -d /tmp/tsgolint/internal/collections /out; \
    find /tmp/tsgolint/typescript-go/internal/collections \
      -type f \
      ! -name '*_test.go' \
      -exec cp {} /tmp/tsgolint/internal/collections/ \;; \
    cd /tmp/tsgolint; \
    CGO_ENABLED=0 \
    GOCACHE=/root/.cache/go-build \
    GOMODCACHE=/go/pkg/mod \
    GOPATH=/go \
    GOTOOLCHAIN=local \
      /usr/local/go/bin/go build \
        -buildvcs=false \
        -trimpath \
        -o /out/tsgolint \
        ./cmd/tsgolint

FROM ${BASE_IMAGE}

ARG BUILD_CREATED=unknown
ARG BUILD_REVISION=unknown
ARG MANIFEST_SHA=unknown
ARG OXFMT_VERSION
ARG OXLINT_TSGOLINT_VERSION
ARG OXLINT_VERSION
ARG TARGETARCH
ARG TYPESCRIPT_VERSION
ARG VITE_TOOLS_BUNDLE_VERSION
ARG VITE_VERSION
ARG VITEST_VERSION

USER root

COPY images/vite/npm/package.json images/vite/npm/package-lock.json \
  /tmp/vite-tools/
COPY --from=tsgolint-builder /out/tsgolint /tmp/tsgolint

RUN --mount=type=cache,target=/root/.npm \
    set -eu; \
    node --input-type=commonjs --eval "\
      const dependencies = require('/tmp/vite-tools/package.json').dependencies;\
      const expected = {\
        '@vitest/coverage-v8': '${VITEST_VERSION}',\
        'oxfmt': '${OXFMT_VERSION}',\
        'oxlint': '${OXLINT_VERSION}',\
        'oxlint-tsgolint': '${OXLINT_TSGOLINT_VERSION}',\
        'typescript': '${TYPESCRIPT_VERSION}',\
        'vite': '${VITE_VERSION}',\
        'vitest': '${VITEST_VERSION}'\
      };\
      for (const [name, version] of Object.entries(expected)) {\
        if (dependencies[name] !== version) throw new Error(name);\
      }"; \
    NPM_CONFIG_CACHE=/root/.npm npm ci \
      --fund=false \
      --no-audit \
      --omit=dev \
      --prefix /tmp/vite-tools; \
    case "${TARGETARCH}" in \
      amd64) tsgolint_package=linux-x64 ;; \
      arm64) tsgolint_package=linux-arm64 ;; \
      *) \
        printf 'unsupported target architecture: %s\n' "${TARGETARCH}" >&2; \
        exit 1 \
        ;; \
    esac; \
    install -m 0755 \
      /tmp/tsgolint \
      "/tmp/vite-tools/node_modules/@oxlint-tsgolint/${tsgolint_package}/tsgolint"; \
    rm -f /tmp/tsgolint; \
    install -d /opt/ci-tools/vite; \
    mv \
      /tmp/vite-tools \
      "/opt/ci-tools/vite/${VITE_TOOLS_BUNDLE_VERSION}"; \
    for command in \
      oxfmt \
      oxlint \
      tsc \
      tsgolint \
      tsserver \
      vite \
      vitest; do \
      test -x \
        "/opt/ci-tools/vite/${VITE_TOOLS_BUNDLE_VERSION}/node_modules/.bin/${command}"; \
      ln -s \
        "../vite/${VITE_TOOLS_BUNDLE_VERSION}/node_modules/.bin/${command}" \
        "/opt/ci-tools/bin/${command}"; \
    done

LABEL org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.description="MyFlow Vite CI job environment" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.source="https://github.com/myflow-xyz/ci-images" \
      org.opencontainers.image.title="MyFlow Vite CI" \
      org.myflow.ci.manifest-sha="${MANIFEST_SHA}"

USER ci
WORKDIR /workspace

CMD ["bash"]
