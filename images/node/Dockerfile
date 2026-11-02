# syntax=docker/dockerfile:1.28.0@sha256:bb22d9815c728170f72750f4e5b0d672e06176142e1d602c7e66c050100b7e5b
# check=skip=InvalidDefaultArgInFrom

ARG BASE_IMAGE
ARG BUILDER_IMAGE
FROM ${BUILDER_IMAGE} AS node-build-base

ARG DEBIAN_SNAPSHOT

COPY images/common/fetch-verified /usr/local/libexec/ci/fetch-verified

RUN test -n "${DEBIAN_SNAPSHOT}" \
    && sed -ri \
      "s|URIs: http://deb.debian.org/debian$|URIs: http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/|" \
      /etc/apt/sources.list.d/debian.sources \
    && sed -ri \
      "s|URIs: http://deb.debian.org/debian-security$|URIs: http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}/|" \
      /etc/apt/sources.list.d/debian.sources \
    && printf '%s\n' 'Acquire::Check-Valid-Until "false";' 'Acquire::Retries "5";' \
      > /etc/apt/apt.conf.d/99-ci-snapshot \
    && apt-get update \
    && apt-get install --yes --no-install-recommends \
      build-essential ca-certificates cmake curl git libssl-dev pkg-config python3 xz-utils zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

FROM node-build-base AS node-rust-builder

ARG RUST_ASSET_URL_AMD64
ARG RUST_ASSET_URL_ARM64
ARG RUST_SHA256_AMD64
ARG RUST_SHA256_ARM64
ARG RUST_VERSION
ARG TARGETARCH

RUN set -eu; \
    case "${TARGETARCH}" in \
      amd64) rust_target=x86_64-unknown-linux-gnu; rust_url="${RUST_ASSET_URL_AMD64}"; rust_sha256="${RUST_SHA256_AMD64}" ;; \
      arm64) rust_target=aarch64-unknown-linux-gnu; rust_url="${RUST_ASSET_URL_ARM64}"; rust_sha256="${RUST_SHA256_ARM64}" ;; \
      *) exit 1 ;; \
    esac; \
    /usr/local/libexec/ci/fetch-verified "${rust_url}" "${rust_sha256}" /var/tmp/rust.tar.xz; \
    install -d /var/tmp/rust; \
    tar -xJf /var/tmp/rust.tar.xz --strip-components=1 -C /var/tmp/rust; \
    /var/tmp/rust/install.sh --prefix=/opt/rust \
      --components="rustc,cargo,rust-std-${rust_target}" --disable-ldconfig; \
    test "$(/opt/rust/bin/rustc --version | awk '{print $2}')" = "${RUST_VERSION}"; \
    rm -rf /var/tmp/rust /var/tmp/rust.tar.xz

ENV PATH=/opt/rust/bin:${PATH}

FROM node-rust-builder AS pnpm-builder

ARG PNPM_SOURCE_URL
ARG PNPM_SOURCE_SHA256
ARG PNPM_VERSION

COPY images/node/pnpm/Cargo.lock images/node/pnpm/dependencies.patch /var/tmp/pnpm-inputs/

RUN --mount=type=cache,target=/var/cache/cargo,sharing=locked \
    --mount=type=cache,target=/var/cache/pnpm-target,sharing=locked \
    set -eu; \
    /usr/local/libexec/ci/fetch-verified "${PNPM_SOURCE_URL}" "${PNPM_SOURCE_SHA256}" /var/tmp/pnpm.tar.gz; \
    install -d /var/tmp/pnpm-source; \
    tar -xzf /var/tmp/pnpm.tar.gz --strip-components=1 -C /var/tmp/pnpm-source; \
    cd /var/tmp/pnpm-source; \
    patch --batch --fuzz=0 -p1 < /var/tmp/pnpm-inputs/dependencies.patch; \
    cp /var/tmp/pnpm-inputs/Cargo.lock Cargo.lock; \
    export CARGO_HOME=/var/cache/cargo CARGO_TARGET_DIR=/var/cache/pnpm-target; \
    cargo build --release --locked -j2 --package pnpm-cli --bin pnpm; \
    cargo test --release --locked -j2 --package pnpm-tarball --package pnpm-crypto-shasums-file --package pnpr-osv --lib; \
    cargo test --release --locked -j2 --package pnpr --lib resolver::pypi; \
    test "$(cd /; /var/cache/pnpm-target/release/pnpm --version)" = "${PNPM_VERSION}"; \
    install -d /out; \
    install -m 0755 /var/cache/pnpm-target/release/pnpm /out/pnpm; \
    install -m 0644 LICENSE /out/LICENSE

FROM node-build-base AS node-bootstrap

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

FROM node-rust-builder AS node-runtime

ARG BROTLI_ASSET_URL
ARG BROTLI_SHA256
ARG BROTLI_VERSION
ARG NODE_SOURCE_URL
ARG NODE_SOURCE_SHA256
ARG NODE_UNDICI_VERSION
ARG NODE_VERSION

COPY --from=node-bootstrap /usr/local/bin/node /opt/node-bootstrap/bin/node
COPY --from=node-bootstrap /usr/local/lib/node_modules/npm/ /opt/node-bootstrap/lib/node_modules/npm/
COPY images/node/runtime/package.json images/node/runtime/package-lock.json /var/tmp/node-runtime/

ENV PATH=/opt/node-bootstrap/bin:${PATH}

RUN --mount=type=cache,target=/var/cache/npm \
    set -eu; \
    /usr/local/libexec/ci/fetch-verified "${NODE_SOURCE_URL}" "${NODE_SOURCE_SHA256}" /var/tmp/node.tar.xz; \
    /usr/local/libexec/ci/fetch-verified "${BROTLI_ASSET_URL}" "${BROTLI_SHA256}" /var/tmp/brotli.tar.gz; \
    install -d /var/tmp/node-source /var/tmp/brotli; \
    tar -xJf /var/tmp/node.tar.xz --strip-components=1 -C /var/tmp/node-source; \
    tar -xzf /var/tmp/brotli.tar.gz --strip-components=1 -C /var/tmp/brotli; \
    rm -rf /var/tmp/node-source/deps/brotli/c; \
    cp -R /var/tmp/brotli/c /var/tmp/node-source/deps/brotli/c; \
    cp /var/tmp/brotli/LICENSE /var/tmp/node-source/deps/brotli/LICENSE; \
    node /opt/node-bootstrap/lib/node_modules/npm/bin/npm-cli.js ci \
      --cache /var/cache/npm --fund=false --ignore-scripts --no-audit --prefix /var/tmp/node-runtime; \
    cd /var/tmp/node-runtime; \
    test "$(node -p "require('./node_modules/undici/package.json').version")" = "${NODE_UNDICI_VERSION}"; \
    node_modules/.bin/esbuild node_modules/undici/index-fetch.js \
      --bundle --platform=node --define:esbuildDetection=1 --keep-names --legal-comments=none \
      --outfile=/var/tmp/node-source/deps/undici/undici.js; \
    rm -rf /var/tmp/node-source/deps/undici/src; \
    cp -R node_modules/undici /var/tmp/node-source/deps/undici/src; \
    cp node_modules/undici/LICENSE /var/tmp/node-source/deps/undici/LICENSE; \
    sed -i "s/^#define UNDICI_VERSION .*/#define UNDICI_VERSION \"${NODE_UNDICI_VERSION}\"/" \
      /var/tmp/node-source/src/undici_version.h; \
    cd /var/tmp/node-source; \
    ./configure --prefix=/usr/local --without-npm --with-intl=full-icu --v8-enable-temporal-support; \
    make -j2; \
    test "$(out/Release/node --version)" = "v${NODE_VERSION}"; \
    test "$(out/Release/node -p 'typeof Temporal')" = object; \
    test "$(out/Release/node -p 'process.versions.brotli')" = "${BROTLI_VERSION}"; \
    test "$(out/Release/node -p 'process.versions.undici')" = "${NODE_UNDICI_VERSION}"; \
    python3 tools/test.py --mode=release -j2 \
      parallel/test-zlib-brotli parallel/test-zlib-brotli-from-string \
      parallel/test-zlib-brotli-from-brotli parallel/test-zlib-brotli-dictionary \
      parallel/test-zlib-brotli-flush parallel/test-fetch parallel/test-fetch-mock; \
    make install DESTDIR=/out; \
    install -d /out/usr/local/share/doc/node; \
    install -m 0644 LICENSE /out/usr/local/LICENSE; \
    install -m 0644 LICENSE CHANGELOG.md README.md /out/usr/local/share/doc/node/

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
ARG PNPM_SUPPORT_ASSET_URL
ARG PNPM_SUPPORT_SHA256
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

COPY --from=node-runtime /out/usr/local/ /usr/local/

RUN set -eu; \
    ln -s node /usr/local/bin/nodejs; \
    test "$(node --version)" = "v${NODE_VERSION}"

COPY --from=pnpm-builder /out/ /opt/ci-tools/pnpm/${PNPM_VERSION}/

RUN set -eu; \
    pnpm_directory="/opt/ci-tools/pnpm/${PNPM_VERSION}"; \
    /usr/local/libexec/ci/fetch-verified \
      "${PNPM_SUPPORT_ASSET_URL}" "${PNPM_SUPPORT_SHA256}" /var/tmp/pnpm-support.tgz; \
    install -d /var/tmp/pnpm-support; \
    tar -xzf /var/tmp/pnpm-support.tgz --strip-components=1 -C /var/tmp/pnpm-support; \
    test "$(node -p "require('/var/tmp/pnpm-support/package.json').version")" = "${PNPM_VERSION}"; \
    mv /var/tmp/pnpm-support/dist "${pnpm_directory}/dist"; \
    install -m 0644 /var/tmp/pnpm-support/THIRD-PARTY-NOTICES.md "${pnpm_directory}/"; \
    test -x "${pnpm_directory}/dist/node-gyp-bin/node-gyp"; \
    "${pnpm_directory}/dist/node-gyp-bin/node-gyp" --version; \
    rm -rf /var/tmp/pnpm-support /var/tmp/pnpm-support.tgz; \
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

RUN --mount=from=node-bootstrap,source=/usr/local/lib/node_modules/npm,target=/usr/local/lib/node_modules/npm,ro \
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
      /var/tmp/npm-package/node_modules/glob \
      /var/tmp/npm-package/node_modules/lru-cache \
      /var/tmp/npm-package/node_modules/minimatch \
      /var/tmp/npm-package/node_modules/path-scurry \
      /var/tmp/npm-package/node_modules/@isaacs/nonrecursive-glob-match \
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
    install -d /var/tmp/npm-package/node_modules/@isaacs; \
    mv /var/tmp/npm-runtime/node_modules/glob \
      /var/tmp/npm-package/node_modules/glob; \
    mv /var/tmp/npm-runtime/node_modules/lru-cache \
      /var/tmp/npm-package/node_modules/lru-cache; \
    mv /var/tmp/npm-runtime/node_modules/minimatch \
      /var/tmp/npm-package/node_modules/minimatch; \
    mv /var/tmp/npm-runtime/node_modules/path-scurry \
      /var/tmp/npm-package/node_modules/path-scurry; \
    mv /var/tmp/npm-runtime/node_modules/@isaacs/nonrecursive-glob-match \
      /var/tmp/npm-package/node_modules/@isaacs/nonrecursive-glob-match; \
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
  images/node/markdownlint/patch-braces.cjs \
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
    node /var/tmp/markdownlint-tools/patch-braces.cjs \
      /var/tmp/markdownlint-tools/node_modules/braces; \
    rm /var/tmp/markdownlint-tools/patch-braces.cjs; \
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
