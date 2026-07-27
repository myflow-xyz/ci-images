# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG BUILD_CREATED=unknown
ARG BUILD_REVISION=unknown
ARG MANIFEST_SHA=unknown
ARG NODE_TOOLS_BUNDLE_VERSION
ARG PNPM_VERSION
ARG REDOCLY_VERSION

LABEL org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.description="MyFlow generic Node CI job environment" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.source="https://github.com/myflow-xyz/ci-images" \
      org.opencontainers.image.title="MyFlow Node CI" \
      org.myflow.ci.manifest-sha="${MANIFEST_SHA}"

USER root

COPY images/node/npm/package.json images/node/npm/package-lock.json \
  /tmp/node-tools/

RUN --mount=type=cache,target=/root/.npm \
    set -eu; \
    test "$(node --print \
      "require('/tmp/node-tools/package.json').dependencies.pnpm")" \
      = "${PNPM_VERSION}"; \
    test "$(node --print \
      "require('/tmp/node-tools/package.json').dependencies['@redocly/cli']")" \
      = "${REDOCLY_VERSION}"; \
    NPM_CONFIG_CACHE=/root/.npm npm ci \
      --fund=false \
      --ignore-scripts \
      --no-audit \
      --omit=dev \
      --prefix /tmp/node-tools; \
    test "$(node --print \
      "require('/tmp/node-tools/node_modules/pnpm/package.json').version")" \
      = "${PNPM_VERSION}"; \
    test "$(node --print \
      "require('/tmp/node-tools/node_modules/@redocly/cli/package.json').version")" \
      = "${REDOCLY_VERSION}"; \
    install -d /opt/ci-tools/node; \
    mv \
      /tmp/node-tools \
      "/opt/ci-tools/node/${NODE_TOOLS_BUNDLE_VERSION}"; \
    ln -s \
      "../node/${NODE_TOOLS_BUNDLE_VERSION}/node_modules/.bin/pnpm" \
      /opt/ci-tools/bin/pnpm; \
    ln -s \
      "../node/${NODE_TOOLS_BUNDLE_VERSION}/node_modules/.bin/pnpx" \
      /opt/ci-tools/bin/pnpx; \
    ln -s \
      "../node/${NODE_TOOLS_BUNDLE_VERSION}/node_modules/.bin/redocly" \
      /opt/ci-tools/bin/redocly; \
    install -d -o ci -g ci \
      /cache/npm \
      /cache/pnpm \
      /home/ci/.config/pnpm; \
    printf 'store-dir=/cache/pnpm\n' \
      > /home/ci/.config/pnpm/rc; \
    chown ci:ci /home/ci/.config/pnpm/rc

ENV NPM_CONFIG_CACHE=/cache/npm \
    PNPM_HOME=/home/ci/.local/share/pnpm

USER ci
WORKDIR /workspace

CMD ["bash"]
