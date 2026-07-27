# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG BUILD_CREATED=unknown
ARG BUILD_REVISION=unknown
ARG MANIFEST_SHA=unknown
ARG OXFMT_VERSION
ARG OXLINT_TSGOLINT_VERSION
ARG OXLINT_VERSION
ARG TYPESCRIPT_VERSION
ARG VITE_TOOLS_BUNDLE_VERSION
ARG VITE_VERSION
ARG VITEST_VERSION

LABEL org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.description="MyFlow Vite CI job environment" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.source="https://github.com/myflow-xyz/ci-images" \
      org.opencontainers.image.title="MyFlow Vite CI" \
      org.myflow.ci.manifest-sha="${MANIFEST_SHA}"

USER root

COPY images/vite/npm/package.json images/vite/npm/package-lock.json \
  /tmp/vite-tools/

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

USER ci
WORKDIR /workspace

CMD ["bash"]
