# syntax=docker/dockerfile:1.28.0@sha256:bb22d9815c728170f72750f4e5b0d672e06176142e1d602c7e66c050100b7e5b
# check=skip=InvalidDefaultArgInFrom

ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS node-runtime

ARG NODE_ASSET_URL_AMD64
ARG NODE_ASSET_URL_ARM64
ARG NODE_SHA256_AMD64
ARG NODE_SHA256_ARM64
ARG NODE_VERSION
ARG TARGETARCH

USER root

RUN set -eu; \
    case "${TARGETARCH}" in \
      amd64) node_asset_url="${NODE_ASSET_URL_AMD64}"; node_sha256="${NODE_SHA256_AMD64}" ;; \
      arm64) node_asset_url="${NODE_ASSET_URL_ARM64}"; node_sha256="${NODE_SHA256_ARM64}" ;; \
      *) exit 1 ;; \
    esac; \
    /usr/local/libexec/ci/fetch-verified \
      "${node_asset_url}" "${node_sha256}" /var/tmp/node.tar.xz; \
    tar --no-same-owner -xJf /var/tmp/node.tar.xz --strip-components=1 -C /usr/local; \
    rm -f /var/tmp/node.tar.xz; \
    install -d /usr/local/share/doc/node; \
    cp /usr/local/LICENSE /usr/local/CHANGELOG.md /usr/local/README.md \
      /usr/local/share/doc/node/; \
    test -x /usr/local/bin/node

FROM ${BASE_IMAGE}

ARG BUILD_CREATED=unknown
ARG BUILD_REVISION=unknown
ARG MANIFEST_SHA=unknown
ARG MARKDOWNLINT_CLI2_VERSION
ARG MARKDOWNLINT_SMOL_TOML_VERSION
ARG MARKDOWNLINT_KATEX_VERSION
ARG NODE_TOOLS_BUNDLE_VERSION
ARG NODE_VERSION
ARG NPM_ASSET_URL
ARG NPM_BRACE_EXPANSION_VERSION
ARG NPM_HTTP_CACHE_SEMANTICS_VERSION
ARG NPM_IP_ADDRESS_VERSION
ARG NPM_POSTCSS_SELECTOR_PARSER_VERSION
ARG NPM_SHA256
ARG NPM_TAR_VERSION
ARG NPM_UNDICI_VERSION
ARG NPM_VERSION
ARG PNPM_ASSET_URL_AMD64
ARG PNPM_ASSET_URL_ARM64
ARG PNPM_SHA256_AMD64
ARG PNPM_SHA256_ARM64
ARG PNPM_VERSION
ARG REDOCLY_VERSION
ARG TARGETARCH

USER root

ENV NODE_VERSION=${NODE_VERSION} \
    NPM_CONFIG_CACHE=/var/cache/npm \
    PNPM_CONFIG_STORE_DIR=/var/cache/pnpm/store

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
      libatomic1 \
      libgcc-s1 \
      libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node-runtime /usr/local/LICENSE /usr/local/LICENSE
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/include/node/ /usr/local/include/node/
COPY --from=node-runtime /usr/local/share/doc/node/ /usr/local/share/doc/node/
COPY --from=node-runtime /usr/local/share/man/man1/node.1 \
  /usr/local/share/man/man1/node.1

RUN set -eu; \
    ln -s node /usr/local/bin/nodejs; \
    test "$(node --version)" = "v${NODE_VERSION}"

RUN set -eu; \
    case "${TARGETARCH}" in \
      amd64) \
        pnpm_asset_url="${PNPM_ASSET_URL_AMD64}"; \
        pnpm_sha256="${PNPM_SHA256_AMD64}" \
        ;; \
      arm64) \
        pnpm_asset_url="${PNPM_ASSET_URL_ARM64}"; \
        pnpm_sha256="${PNPM_SHA256_ARM64}" \
        ;; \
      *) \
        printf 'unsupported target architecture: %s\n' "${TARGETARCH}" >&2; \
        exit 1 \
        ;; \
    esac; \
    pnpm_directory="/opt/ci-tools/pnpm/${PNPM_VERSION}"; \
    install -d "${pnpm_directory}"; \
    /usr/local/libexec/ci/fetch-verified \
      "${pnpm_asset_url}" \
      "${pnpm_sha256}" \
      /var/tmp/pnpm.tar.gz; \
    tar -xzf /var/tmp/pnpm.tar.gz \
      -C "${pnpm_directory}"; \
    rm -f /var/tmp/pnpm.tar.gz; \
    chmod 0755 "${pnpm_directory}/pnpm"; \
    test "$("${pnpm_directory}/pnpm" --version)" = "${PNPM_VERSION}"; \
    ln -s \
      "../pnpm/${PNPM_VERSION}/pnpm" \
      /opt/ci-tools/bin/pnpm; \
    ln -s \
      "../pnpm/${PNPM_VERSION}/pnpm" \
      /opt/ci-tools/bin/pnpx

COPY images/node/npm-runtime/package.json \
  images/node/npm-runtime/package-lock.json \
  /var/tmp/npm-runtime/

RUN --mount=from=node-runtime,source=/usr/local/lib/node_modules/npm,target=/usr/local/lib/node_modules/npm,ro \
    --mount=type=cache,target=/var/cache/npm \
    set -eu; \
    /usr/local/libexec/ci/fetch-verified \
      "${NPM_ASSET_URL}" \
      "${NPM_SHA256}" \
      /var/tmp/npm.tgz; \
    install -d /var/tmp/npm-package; \
    tar -xzf /var/tmp/npm.tgz \
      --strip-components=1 \
      -C /var/tmp/npm-package; \
    rm -f /var/tmp/npm.tgz; \
    test "$(node --print \
      "require('/var/tmp/npm-package/package.json').version")" \
      = "${NPM_VERSION}"; \
    node /usr/local/lib/node_modules/npm/bin/npm-cli.js ci \
      --fund=false \
      --ignore-scripts \
      --no-audit \
      --omit=dev \
      --prefix /var/tmp/npm-runtime; \
    test "$(node --print \
      "require('/var/tmp/npm-runtime/node_modules/brace-expansion/package.json').version")" \
      = "${NPM_BRACE_EXPANSION_VERSION}"; \
    test "$(node --print \
      "require('/var/tmp/npm-runtime/node_modules/http-cache-semantics/package.json').version")" \
      = "${NPM_HTTP_CACHE_SEMANTICS_VERSION}"; \
    test "$(node --print \
      "require('/var/tmp/npm-runtime/node_modules/ip-address/package.json').version")" \
      = "${NPM_IP_ADDRESS_VERSION}"; \
    test "$(node --print \
      "require('/var/tmp/npm-runtime/node_modules/postcss-selector-parser/package.json').version")" \
      = "${NPM_POSTCSS_SELECTOR_PARSER_VERSION}"; \
    test "$(node --print \
      "require('/var/tmp/npm-runtime/node_modules/tar/package.json').version")" \
      = "${NPM_TAR_VERSION}"; \
    test "$(node --print \
      "require('/var/tmp/npm-runtime/node_modules/undici/package.json').version")" \
      = "${NPM_UNDICI_VERSION}"; \
    rm -rf \
      /var/tmp/npm-package/node_modules/brace-expansion \
      /var/tmp/npm-package/node_modules/http-cache-semantics \
      /var/tmp/npm-package/node_modules/ip-address \
      /var/tmp/npm-package/node_modules/postcss-selector-parser \
      /var/tmp/npm-package/node_modules/tar \
      /var/tmp/npm-package/node_modules/undici; \
    mv \
      /var/tmp/npm-runtime/node_modules/brace-expansion \
      /var/tmp/npm-package/node_modules/brace-expansion; \
    mv \
      /var/tmp/npm-runtime/node_modules/http-cache-semantics \
      /var/tmp/npm-package/node_modules/http-cache-semantics; \
    mv \
      /var/tmp/npm-runtime/node_modules/ip-address \
      /var/tmp/npm-package/node_modules/ip-address; \
    mv \
      /var/tmp/npm-runtime/node_modules/postcss-selector-parser \
      /var/tmp/npm-package/node_modules/postcss-selector-parser; \
    mv \
      /var/tmp/npm-runtime/node_modules/tar \
      /var/tmp/npm-package/node_modules/tar; \
    mv \
      /var/tmp/npm-runtime/node_modules/undici \
      /var/tmp/npm-package/node_modules/undici; \
    install -d /opt/ci-tools/npm; \
    mv \
      /var/tmp/npm-package \
      "/opt/ci-tools/npm/${NPM_VERSION}"; \
    ln -s \
      "../npm/${NPM_VERSION}/bin/npm-cli.js" \
      /opt/ci-tools/bin/npm; \
    ln -s \
      "../npm/${NPM_VERSION}/bin/npx-cli.js" \
      /opt/ci-tools/bin/npx; \
    rm -rf /var/tmp/npm-runtime; \
    test "$(/opt/ci-tools/bin/npm --version)" = "${NPM_VERSION}"; \
    test "$(node --print \
      "require('/opt/ci-tools/npm/${NPM_VERSION}/node_modules/brace-expansion/package.json').version")" \
      = "${NPM_BRACE_EXPANSION_VERSION}"; \
    test "$(node --print \
      "require('/opt/ci-tools/npm/${NPM_VERSION}/node_modules/ip-address/package.json').version")" \
      = "${NPM_IP_ADDRESS_VERSION}"; \
    test "$(node --print \
      "require('/opt/ci-tools/npm/${NPM_VERSION}/node_modules/tar/package.json').version")" \
      = "${NPM_TAR_VERSION}"; \
    test "$(node --print \
      "require('/opt/ci-tools/npm/${NPM_VERSION}/node_modules/undici/package.json').version")" \
      = "${NPM_UNDICI_VERSION}"

COPY images/node/markdownlint/package.json \
  images/node/markdownlint/package-lock.json \
  /var/tmp/markdownlint-tools/

RUN --mount=type=cache,target=/var/cache/npm \
    set -eu; \
    test "$(node --print \
      "require('/var/tmp/markdownlint-tools/package.json').dependencies['markdownlint-cli2']")" \
      = "${MARKDOWNLINT_CLI2_VERSION}"; \
    npm ci \
      --fund=false \
      --ignore-scripts \
      --no-audit \
      --omit=dev \
      --prefix /var/tmp/markdownlint-tools; \
    test "$(node --print \
      "require('/var/tmp/markdownlint-tools/node_modules/markdownlint-cli2/package.json').version")" \
      = "${MARKDOWNLINT_CLI2_VERSION}"; \
    test "$(node --print \
      "require('/var/tmp/markdownlint-tools/node_modules/smol-toml/package.json').version")" \
      = "${MARKDOWNLINT_SMOL_TOML_VERSION}"; \
    test "$(node --print \
      "require('/var/tmp/markdownlint-tools/node_modules/katex/package.json').version")" \
      = "${MARKDOWNLINT_KATEX_VERSION}"; \
    install -d /opt/ci-tools/markdownlint-cli2; \
    mv \
      /var/tmp/markdownlint-tools \
      "/opt/ci-tools/markdownlint-cli2/${MARKDOWNLINT_CLI2_VERSION}"; \
    ln -s \
      "../markdownlint-cli2/${MARKDOWNLINT_CLI2_VERSION}/node_modules/.bin/markdownlint-cli2" \
      /opt/ci-tools/bin/markdownlint-cli2

COPY images/node/npm/package.json images/node/npm/package-lock.json \
  /var/tmp/node-tools/

RUN --mount=type=cache,target=/var/cache/npm \
    set -eu; \
    test "$(node --print \
      "require('/var/tmp/node-tools/package.json').dependencies['@redocly/cli']")" \
      = "${REDOCLY_VERSION}"; \
    npm ci \
      --fund=false \
      --ignore-scripts \
      --no-audit \
      --omit=dev \
      --prefix /var/tmp/node-tools; \
    test "$(node --print \
      "require('/var/tmp/node-tools/node_modules/@redocly/cli/package.json').version")" \
      = "${REDOCLY_VERSION}"; \
    install -d /opt/ci-tools/node; \
    mv \
      /var/tmp/node-tools \
      "/opt/ci-tools/node/${NODE_TOOLS_BUNDLE_VERSION}"; \
    ln -s \
      "../node/${NODE_TOOLS_BUNDLE_VERSION}/node_modules/.bin/redocly" \
      /opt/ci-tools/bin/redocly

RUN install -d -o ci -g ci \
      /var/cache/npm \
      /var/cache/pnpm/store

LABEL org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.description="MyFlow generic Node CI job environment" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.source="https://github.com/myflow-xyz/ci-images" \
      org.opencontainers.image.title="MyFlow Node CI" \
      org.myflow.ci.manifest-sha="${MANIFEST_SHA}"

USER ci
WORKDIR /workspace

CMD ["bash"]
