# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

ARG BASE_IMAGE
ARG NODE_IMAGE
FROM ${NODE_IMAGE} AS node-runtime

FROM ${BASE_IMAGE}

ARG BUILD_CREATED=unknown
ARG BUILD_REVISION=unknown
ARG MANIFEST_SHA=unknown
ARG MARKDOWNLINT_CLI2_VERSION
ARG NODE_TOOLS_BUNDLE_VERSION
ARG NODE_VERSION
ARG NPM_BRACE_EXPANSION_VERSION
ARG NPM_VERSION
ARG PNPM_VERSION
ARG REDOCLY_VERSION

USER root

ENV NODE_VERSION=${NODE_VERSION} \
    NPM_CONFIG_CACHE=/var/cache/npm \
    PNPM_CONFIG_STORE_DIR=/var/cache/pnpm/store

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
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

COPY images/node/npm-runtime/package.json \
  images/node/npm-runtime/package-lock.json \
  /var/tmp/npm-runtime/

RUN --mount=from=node-runtime,source=/usr/local/lib/node_modules/npm,target=/usr/local/lib/node_modules/npm,ro \
    --mount=type=cache,target=/var/cache/npm \
    set -eu; \
    test "$(node --print \
      "require('/var/tmp/npm-runtime/package.json').dependencies.npm")" \
      = "${NPM_VERSION}"; \
    node /usr/local/lib/node_modules/npm/bin/npm-cli.js ci \
      --fund=false \
      --ignore-scripts \
      --no-audit \
      --omit=dev \
      --prefix /var/tmp/npm-runtime; \
    test "$(node --print \
      "require('/var/tmp/npm-runtime/node_modules/npm/package.json').version")" \
      = "${NPM_VERSION}"; \
    test "$(node --print \
      "require('/var/tmp/npm-runtime/node_modules/brace-expansion/package.json').version")" \
      = "${NPM_BRACE_EXPANSION_VERSION}"; \
    rm -rf \
      /var/tmp/npm-runtime/node_modules/npm/node_modules/brace-expansion; \
    mv \
      /var/tmp/npm-runtime/node_modules/brace-expansion \
      /var/tmp/npm-runtime/node_modules/npm/node_modules/brace-expansion; \
    install -d /opt/ci-tools/npm; \
    mv \
      /var/tmp/npm-runtime/node_modules/npm \
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
      = "${NPM_BRACE_EXPANSION_VERSION}"

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
      "require('/var/tmp/node-tools/package.json').dependencies.pnpm")" \
      = "${PNPM_VERSION}"; \
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
      "require('/var/tmp/node-tools/node_modules/pnpm/package.json').version")" \
      = "${PNPM_VERSION}"; \
    test "$(node --print \
      "require('/var/tmp/node-tools/node_modules/@redocly/cli/package.json').version")" \
      = "${REDOCLY_VERSION}"; \
    install -d /opt/ci-tools/node; \
    mv \
      /var/tmp/node-tools \
      "/opt/ci-tools/node/${NODE_TOOLS_BUNDLE_VERSION}"; \
    ln -s \
      "../node/${NODE_TOOLS_BUNDLE_VERSION}/node_modules/.bin/pnpm" \
      /opt/ci-tools/bin/pnpm; \
    ln -s \
      "../node/${NODE_TOOLS_BUNDLE_VERSION}/node_modules/.bin/pnpx" \
      /opt/ci-tools/bin/pnpx; \
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
