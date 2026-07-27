# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG ACTIONLINT_SHA256_AMD64
ARG ACTIONLINT_SHA256_ARM64
ARG ACTIONLINT_VERSION
ARG BUILD_CREATED=unknown
ARG BUILD_REVISION=unknown
ARG CI_GID=1001
ARG CI_UID=1001
ARG DEBIAN_SNAPSHOT
ARG GITLEAKS_SHA256_AMD64
ARG GITLEAKS_SHA256_ARM64
ARG GITLEAKS_VERSION
ARG MANIFEST_SHA=unknown
ARG MARKDOWNLINT_CLI2_VERSION
ARG SHELLSPEC_SHA256
ARG SHELLSPEC_VERSION
ARG SHFMT_SHA256_AMD64
ARG SHFMT_SHA256_ARM64
ARG SHFMT_VERSION
ARG TARGETARCH
ARG YQ_SHA256_AMD64
ARG YQ_SHA256_ARM64
ARG YQ_VERSION

ENV CI=true \
    DEBIAN_FRONTEND=noninteractive \
    HOME=/home/ci \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    NPM_CONFIG_CACHE=/cache/npm \
    PATH=/opt/ci-tools/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    TZ=UTC \
    XDG_CACHE_HOME=/cache/xdg

COPY images/common/fetch-verified /usr/local/libexec/ci/fetch-verified

RUN test -n "${DEBIAN_SNAPSHOT}" \
    && sed -ri \
      "s|URIs: http://deb.debian.org/debian$|URIs: https://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/|" \
      /etc/apt/sources.list.d/debian.sources \
    && sed -ri \
      "s|URIs: http://deb.debian.org/debian-security$|URIs: https://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}/|" \
      /etc/apt/sources.list.d/debian.sources \
    && printf '%s\n' \
      'Acquire::Check-Valid-Until "false";' \
      'Acquire::Retries "5";' \
      > /etc/apt/apt.conf.d/99-ci-snapshot \
    && apt-get update \
    && apt-get install --yes --no-install-recommends \
      bash \
      ca-certificates \
      coreutils \
      curl \
      diffutils \
      findutils \
      gawk \
      gh \
      git \
      grep \
      gzip \
      jq \
      make \
      openssl \
      procps \
      ripgrep \
      sed \
      shellcheck \
      tar \
      tini \
      unzip \
      wget \
      xz-utils \
      zip \
    && rm -rf /var/lib/apt/lists/* \
    && chmod 0755 /usr/local/libexec/ci/fetch-verified

RUN set -eu; \
    case "${TARGETARCH}" in \
      amd64) \
        actionlint_arch=amd64; \
        actionlint_sha="${ACTIONLINT_SHA256_AMD64}"; \
        gitleaks_arch=x64; \
        gitleaks_sha="${GITLEAKS_SHA256_AMD64}"; \
        shfmt_arch=amd64; \
        shfmt_sha="${SHFMT_SHA256_AMD64}"; \
        yq_arch=amd64; \
        yq_sha="${YQ_SHA256_AMD64}" \
        ;; \
      arm64) \
        actionlint_arch=arm64; \
        actionlint_sha="${ACTIONLINT_SHA256_ARM64}"; \
        gitleaks_arch=arm64; \
        gitleaks_sha="${GITLEAKS_SHA256_ARM64}"; \
        shfmt_arch=arm64; \
        shfmt_sha="${SHFMT_SHA256_ARM64}"; \
        yq_arch=arm64; \
        yq_sha="${YQ_SHA256_ARM64}" \
        ;; \
      *) \
        printf 'unsupported target architecture: %s\n' "${TARGETARCH}" >&2; \
        exit 1 \
        ;; \
    esac; \
    install -d \
      /opt/ci-tools/bin \
      "/opt/ci-tools/actionlint/${ACTIONLINT_VERSION}" \
      "/opt/ci-tools/gitleaks/${GITLEAKS_VERSION}" \
      "/opt/ci-tools/shfmt/${SHFMT_VERSION}" \
      "/opt/ci-tools/yq/${YQ_VERSION}"; \
    /usr/local/libexec/ci/fetch-verified \
      "https://github.com/mikefarah/yq/releases/download/v${YQ_VERSION}/yq_linux_${yq_arch}" \
      "${yq_sha}" \
      "/opt/ci-tools/yq/${YQ_VERSION}/yq"; \
    /usr/local/libexec/ci/fetch-verified \
      "https://github.com/mvdan/sh/releases/download/v${SHFMT_VERSION}/shfmt_v${SHFMT_VERSION}_linux_${shfmt_arch}" \
      "${shfmt_sha}" \
      "/opt/ci-tools/shfmt/${SHFMT_VERSION}/shfmt"; \
    /usr/local/libexec/ci/fetch-verified \
      "https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}/actionlint_${ACTIONLINT_VERSION}_linux_${actionlint_arch}.tar.gz" \
      "${actionlint_sha}" \
      /tmp/actionlint.tar.gz; \
    tar -xzf /tmp/actionlint.tar.gz \
      -C "/opt/ci-tools/actionlint/${ACTIONLINT_VERSION}" \
      actionlint; \
    /usr/local/libexec/ci/fetch-verified \
      "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_${gitleaks_arch}.tar.gz" \
      "${gitleaks_sha}" \
      /tmp/gitleaks.tar.gz; \
    tar -xzf /tmp/gitleaks.tar.gz \
      -C "/opt/ci-tools/gitleaks/${GITLEAKS_VERSION}" \
      gitleaks; \
    chmod 0755 \
      "/opt/ci-tools/actionlint/${ACTIONLINT_VERSION}/actionlint" \
      "/opt/ci-tools/gitleaks/${GITLEAKS_VERSION}/gitleaks" \
      "/opt/ci-tools/shfmt/${SHFMT_VERSION}/shfmt" \
      "/opt/ci-tools/yq/${YQ_VERSION}/yq"; \
    ln -s \
      "../actionlint/${ACTIONLINT_VERSION}/actionlint" \
      /opt/ci-tools/bin/actionlint; \
    ln -s \
      "../gitleaks/${GITLEAKS_VERSION}/gitleaks" \
      /opt/ci-tools/bin/gitleaks; \
    ln -s \
      "../shfmt/${SHFMT_VERSION}/shfmt" \
      /opt/ci-tools/bin/shfmt; \
    ln -s \
      "../yq/${YQ_VERSION}/yq" \
      /opt/ci-tools/bin/yq; \
    rm -f /tmp/actionlint.tar.gz /tmp/gitleaks.tar.gz

RUN set -eu; \
    install -d "/opt/ci-tools/shellspec/${SHELLSPEC_VERSION}"; \
    /usr/local/libexec/ci/fetch-verified \
      "https://github.com/shellspec/shellspec/archive/refs/tags/${SHELLSPEC_VERSION}.tar.gz" \
      "${SHELLSPEC_SHA256}" \
      /tmp/shellspec.tar.gz; \
    tar -xzf /tmp/shellspec.tar.gz \
      --strip-components=1 \
      -C "/opt/ci-tools/shellspec/${SHELLSPEC_VERSION}"; \
    ln -s \
      "../shellspec/${SHELLSPEC_VERSION}/shellspec" \
      /opt/ci-tools/bin/shellspec; \
    rm -f /tmp/shellspec.tar.gz

COPY images/base/npm/package.json images/base/npm/package-lock.json \
  /tmp/markdownlint-tools/

RUN --mount=type=cache,target=/root/.npm \
    set -eu; \
    test "$(node --print \
      "require('/tmp/markdownlint-tools/package.json').dependencies['markdownlint-cli2']")" \
      = "${MARKDOWNLINT_CLI2_VERSION}"; \
    NPM_CONFIG_CACHE=/root/.npm npm ci \
      --fund=false \
      --ignore-scripts \
      --no-audit \
      --omit=dev \
      --prefix /tmp/markdownlint-tools; \
    test "$(node --print \
      "require('/tmp/markdownlint-tools/node_modules/markdownlint-cli2/package.json').version")" \
      = "${MARKDOWNLINT_CLI2_VERSION}"; \
    install -d /opt/ci-tools/markdownlint-cli2; \
    mv \
      /tmp/markdownlint-tools \
      "/opt/ci-tools/markdownlint-cli2/${MARKDOWNLINT_CLI2_VERSION}"; \
    ln -s \
      "../markdownlint-cli2/${MARKDOWNLINT_CLI2_VERSION}/node_modules/.bin/markdownlint-cli2" \
      /opt/ci-tools/bin/markdownlint-cli2

RUN set -eu; \
    groupadd --gid "${CI_GID}" ci; \
    useradd \
      --create-home \
      --gid "${CI_GID}" \
      --shell /bin/bash \
      --uid "${CI_UID}" \
      ci; \
    install -d -o ci -g ci \
      /cache/npm \
      /cache/xdg \
      /home/ci/.config \
      /workspace; \
    chown -R ci:ci /home/ci; \
    git config --system --add safe.directory /workspace

LABEL org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.description="Shared MyFlow CI job environment" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.source="https://github.com/myflow-xyz/ci-images" \
      org.opencontainers.image.title="MyFlow CI base" \
      org.myflow.ci.manifest-sha="${MANIFEST_SHA}"

USER ci
WORKDIR /workspace

CMD ["bash"]
