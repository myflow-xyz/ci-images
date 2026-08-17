# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

ARG BASE_IMAGE
FROM --platform=${BUILDPLATFORM} ${BASE_IMAGE} AS go-tools-builder

ARG BUILDARCH
ARG GO_SHA256_AMD64
ARG GO_SHA256_ARM64
ARG GO_VERSION
ARG OXLINT_TSGOLINT_COMMIT
ARG OXLINT_TSGOLINT_SOURCE
ARG OXLINT_TSGOLINT_X_TEXT_VERSION
ARG TARGETARCH
ARG TYPESCRIPT_GO_COMMIT
ARG TYPESCRIPT_GO_SOURCE
ARG TYPESCRIPT_X_TEXT_VERSION

USER root

RUN set -eu; \
    case "${BUILDARCH}" in \
      amd64) go_sha256="${GO_SHA256_AMD64}" ;; \
      arm64) go_sha256="${GO_SHA256_ARM64}" ;; \
      *) \
        printf 'unsupported build architecture: %s\n' "${BUILDARCH}" >&2; \
        exit 1 \
        ;; \
    esac; \
    /usr/local/libexec/ci/fetch-verified \
      "https://go.dev/dl/go${GO_VERSION}.linux-${BUILDARCH}.tar.gz" \
      "${go_sha256}" \
      /var/tmp/go.tar.gz; \
    tar -xzf /var/tmp/go.tar.gz -C /usr/local; \
    rm -f /var/tmp/go.tar.gz; \
    test "$(/usr/local/go/bin/go version | awk '{print $3}')" \
      = "go${GO_VERSION}"

RUN --mount=type=cache,target=/var/cache/go/mod,sharing=locked \
    --mount=type=cache,target=/var/cache/go/build,sharing=locked \
    set -eu; \
    install -d /out; \
    git init /var/tmp/typescript-go; \
    git -C /var/tmp/typescript-go remote add origin \
      "${TYPESCRIPT_GO_SOURCE}"; \
    git -C /var/tmp/typescript-go fetch \
      --depth 1 \
      origin \
      "${TYPESCRIPT_GO_COMMIT}"; \
    git -C /var/tmp/typescript-go checkout --detach FETCH_HEAD; \
    test "$(git -C /var/tmp/typescript-go rev-parse HEAD)" \
      = "${TYPESCRIPT_GO_COMMIT}"; \
    cd /var/tmp/typescript-go; \
    export \
      GOCACHE=/var/cache/go/build \
      GOMODCACHE=/var/cache/go/mod \
      GOPATH=/var/lib/go \
      GOTOOLCHAIN=local; \
    /usr/local/go/bin/go get \
      "golang.org/x/text@${TYPESCRIPT_X_TEXT_VERSION}"; \
    CGO_ENABLED=0 GOARCH="${TARGETARCH}" GOOS=linux \
      /usr/local/go/bin/go build \
      -buildvcs=false \
      -trimpath \
      -o /out/tsc \
      ./cmd/tsgo; \
    cd /; \
    git init /var/tmp/tsgolint; \
    git -C /var/tmp/tsgolint remote add origin "${OXLINT_TSGOLINT_SOURCE}"; \
    git -C /var/tmp/tsgolint fetch \
      --depth 1 \
      origin \
      "${OXLINT_TSGOLINT_COMMIT}"; \
    git -C /var/tmp/tsgolint checkout --detach FETCH_HEAD; \
    git -C /var/tmp/tsgolint submodule update --init --depth 1; \
    test "$(git -C /var/tmp/tsgolint rev-parse HEAD)" \
      = "${OXLINT_TSGOLINT_COMMIT}"; \
    test "$(git -C /var/tmp/tsgolint/typescript-go rev-parse HEAD)" \
      = "${TYPESCRIPT_GO_COMMIT}"; \
    git -C /var/tmp/tsgolint/typescript-go apply \
      /var/tmp/tsgolint/patches/*.patch; \
    install -d /var/tmp/tsgolint/internal/collections; \
    find /var/tmp/tsgolint/typescript-go/internal/collections \
      -type f \
      ! -name '*_test.go' \
      -exec cp {} /var/tmp/tsgolint/internal/collections/ \;; \
    cd /var/tmp/tsgolint; \
    export \
      GOCACHE=/var/cache/go/build \
      GOMODCACHE=/var/cache/go/mod \
      GOPATH=/var/lib/go \
      GOTOOLCHAIN=local; \
    /usr/local/go/bin/go get \
      "golang.org/x/text@${OXLINT_TSGOLINT_X_TEXT_VERSION}"; \
    CGO_ENABLED=0 GOARCH="${TARGETARCH}" GOOS=linux \
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
ARG TYPESCRIPT_LEGACY_COMPAT_PACKAGE_VERSION
ARG TYPESCRIPT_LEGACY_COMPILER_VERSION
ARG TYPESCRIPT_VERSION
ARG VITE_TOOLS_BUNDLE_VERSION
ARG VITE_VERSION
ARG VITEST_VERSION

USER root

COPY images/vite/npm/package.json images/vite/npm/package-lock.json \
  /var/tmp/vite-tools/
COPY --from=go-tools-builder /out/tsc /var/tmp/tsc
COPY --from=go-tools-builder /out/tsgolint /var/tmp/tsgolint

RUN --mount=type=cache,target=/var/cache/npm \
    set -eu; \
    node --input-type=commonjs --eval "\
      const dependencies = require('/var/tmp/vite-tools/package.json').dependencies;\
      const expected = {\
        '@typescript/native': 'npm:typescript@${TYPESCRIPT_VERSION}',\
        '@vitest/coverage-v8': '${VITEST_VERSION}',\
        'oxfmt': '${OXFMT_VERSION}',\
        'oxlint': '${OXLINT_VERSION}',\
        'oxlint-tsgolint': '${OXLINT_TSGOLINT_VERSION}',\
        'typescript': 'npm:@typescript/typescript6@${TYPESCRIPT_LEGACY_COMPAT_PACKAGE_VERSION}',\
        'vite': '${VITE_VERSION}',\
        'vitest': '${VITEST_VERSION}'\
      };\
      for (const [name, version] of Object.entries(expected)) {\
        if (dependencies[name] !== version) throw new Error(name);\
      }"; \
    NPM_CONFIG_CACHE=/var/cache/npm npm ci \
      --fund=false \
      --no-audit \
      --omit=dev \
      --prefix /var/tmp/vite-tools; \
    test "$(node --print \
      "require('/var/tmp/vite-tools/node_modules/@typescript/native/package.json').version")" \
      = "${TYPESCRIPT_VERSION}"; \
    test "$(node --print \
      "require('/var/tmp/vite-tools/node_modules/typescript/package.json').version")" \
      = "${TYPESCRIPT_LEGACY_COMPAT_PACKAGE_VERSION}"; \
    test "$(node --print \
      "require('/var/tmp/vite-tools/node_modules/@typescript/old/package.json').version")" \
      = "${TYPESCRIPT_LEGACY_COMPILER_VERSION}"; \
    test "$(/var/tmp/vite-tools/node_modules/.bin/tsc6 --version)" \
      = "Version ${TYPESCRIPT_LEGACY_COMPILER_VERSION}"; \
    test -x /var/tmp/vite-tools/node_modules/@typescript/old/bin/tsserver; \
    case "${TARGETARCH}" in \
      amd64) go_package=linux-x64 ;; \
      arm64) go_package=linux-arm64 ;; \
      *) \
        printf 'unsupported target architecture: %s\n' "${TARGETARCH}" >&2; \
        exit 1 \
        ;; \
    esac; \
    install -m 0755 \
      /var/tmp/tsc \
      "/var/tmp/vite-tools/node_modules/@typescript/typescript-${go_package}/lib/tsc"; \
    rm -f \
      /var/tmp/tsc \
      "/var/tmp/vite-tools/node_modules/@typescript/typescript-${go_package}/lib/tsc.sig"; \
    test "$(/var/tmp/vite-tools/node_modules/.bin/tsc --version)" \
      = "Version ${TYPESCRIPT_VERSION}"; \
    install -m 0755 \
      /var/tmp/tsgolint \
      "/var/tmp/vite-tools/node_modules/@oxlint-tsgolint/${go_package}/tsgolint"; \
    rm -f /var/tmp/tsgolint; \
    install -d /opt/ci-tools/vite; \
    mv \
      /var/tmp/vite-tools \
      "/opt/ci-tools/vite/${VITE_TOOLS_BUNDLE_VERSION}"; \
    for command in \
      oxfmt \
      oxlint \
      tsc \
      tsc6 \
      tsgolint \
      vite \
      vitest; do \
      test -x \
        "/opt/ci-tools/vite/${VITE_TOOLS_BUNDLE_VERSION}/node_modules/.bin/${command}"; \
      ln -s \
        "../vite/${VITE_TOOLS_BUNDLE_VERSION}/node_modules/.bin/${command}" \
        "/opt/ci-tools/bin/${command}"; \
    done; \
    ln -s \
      "../vite/${VITE_TOOLS_BUNDLE_VERSION}/node_modules/@typescript/old/bin/tsserver" \
      /opt/ci-tools/bin/tsserver

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
