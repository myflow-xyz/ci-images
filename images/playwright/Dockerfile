# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG BUILD_CREATED=unknown
ARG BUILD_REVISION=unknown
ARG MANIFEST_SHA=unknown
ARG PLAYWRIGHT_VERSION

LABEL org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.description="MyFlow Playwright CI job environment" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.source="https://github.com/myflow-xyz/ci-images" \
      org.opencontainers.image.title="MyFlow Playwright CI" \
      org.myflow.ci.manifest-sha="${MANIFEST_SHA}" \
      org.myflow.ci.playwright-version="${PLAYWRIGHT_VERSION}"

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PLAYWRIGHT_VERSION=${PLAYWRIGHT_VERSION}

USER root

COPY \
  images/playwright/npm/package.json \
  images/playwright/npm/package-lock.json \
  /tmp/playwright-tools/

COPY images/playwright/check-version \
  /usr/local/libexec/ci/check-playwright-version

RUN --mount=type=cache,target=/root/.npm \
    set -eu; \
    test "$(node --print \
      "require('/tmp/playwright-tools/package.json').dependencies['@playwright/test']")" \
      = "${PLAYWRIGHT_VERSION}"; \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
      NPM_CONFIG_CACHE=/root/.npm npm ci \
        --fund=false \
        --ignore-scripts \
        --no-audit \
        --omit=dev \
        --prefix /tmp/playwright-tools; \
    test "$(node --print \
      "require('/tmp/playwright-tools/node_modules/@playwright/test/package.json').version")" \
      = "${PLAYWRIGHT_VERSION}"; \
    install -d /opt/ci-tools/playwright; \
    mv \
      /tmp/playwright-tools \
      "/opt/ci-tools/playwright/${PLAYWRIGHT_VERSION}"; \
    chmod 0755 /usr/local/libexec/ci/check-playwright-version; \
    ln -s \
      /usr/local/libexec/ci/check-playwright-version \
      /opt/ci-tools/bin/check-playwright-version; \
    "/opt/ci-tools/playwright/${PLAYWRIGHT_VERSION}/node_modules/.bin/playwright" \
      install --with-deps chromium; \
    chmod -R a+rX "${PLAYWRIGHT_BROWSERS_PATH}"

USER ci
WORKDIR /workspace

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["bash"]
