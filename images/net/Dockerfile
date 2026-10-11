# syntax=docker/dockerfile:1.28.0@sha256:bb22d9815c728170f72750f4e5b0d672e06176142e1d602c7e66c050100b7e5b
# check=skip=InvalidDefaultArgInFrom

ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG BUILD_CREATED=unknown
ARG BUILD_REVISION=unknown
ARG MANIFEST_SHA=unknown
ARG TARGETARCH

USER root

COPY images/net/debian-packages.*.lock /var/tmp/ci-net/

RUN set -eu; \
    case "${TARGETARCH}" in amd64|arm64) ;; *) exit 1 ;; esac; \
    install -m 0644 \
      "/var/tmp/ci-net/debian-packages.${TARGETARCH}.lock" \
      /usr/local/share/ci/net-debian-packages.lock; \
    apt-get update; \
    xargs -r apt-get install --yes --no-install-recommends \
      < /usr/local/share/ci/net-debian-packages.lock; \
    ping_capabilities=$(getcap /usr/bin/ping); \
    if [ -n "${ping_capabilities}" ]; then setcap -r /usr/bin/ping; fi; \
    chmod u-s,g-s /usr/bin/ping; \
    rm -rf /var/tmp/ci-net /var/lib/apt/lists/*

LABEL org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.description="Network test tools based on ci-base. Use an independent network namespace; avoid --network host; no --privileged. NET_ADMIN only on the test container. Avoid nft flush ruleset; remove only test-owned rules." \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.source="https://github.com/myflow-xyz/ci-images" \
      org.opencontainers.image.title="MyFlow network CI" \
      org.myflow.ci.manifest-sha="${MANIFEST_SHA}"

USER ci
WORKDIR /workspace

CMD ["bash"]
