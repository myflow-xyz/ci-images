# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS base-go-tools

ARG ACTIONLINT_VERSION
ARG DEBIAN_SNAPSHOT
ARG GITLEAKS_VERSION
ARG GITLEAKS_X_CRYPTO_VERSION
ARG GO_SHA256_AMD64
ARG GO_SHA256_ARM64
ARG GO_VERSION
ARG SHFMT_VERSION
ARG TARGETARCH
ARG YQ_VERSION

USER root

COPY images/common/fetch-verified /usr/local/libexec/ci/fetch-verified

RUN test -n "${DEBIAN_SNAPSHOT}" \
    && sed -ri \
      "s|URIs: http://deb.debian.org/debian$|URIs: http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/|" \
      /etc/apt/sources.list.d/debian.sources \
    && sed -ri \
      "s|URIs: http://deb.debian.org/debian-security$|URIs: http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}/|" \
      /etc/apt/sources.list.d/debian.sources \
    && printf '%s\n' \
      'Acquire::Check-Valid-Until "false";' \
      'Acquire::Retries "5";' \
      > /etc/apt/apt.conf.d/99-ci-snapshot \
    && apt-get update \
    && apt-get install --yes --no-install-recommends \
      ca-certificates \
      curl \
    && rm -rf /var/lib/apt/lists/* \
    && chmod 0755 /usr/local/libexec/ci/fetch-verified

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
    build_tool() { \
      name=$1; \
      package=$2; \
      version=$3; \
      shift 3; \
      build_directory="/tmp/build/${name}"; \
      output_directory="/out/${name}/${version#v}"; \
      install -d "${build_directory}" "${output_directory}"; \
      cd "${build_directory}"; \
      /usr/local/go/bin/go mod init "ci.invalid/${name}"; \
      /usr/local/go/bin/go get "${package}@${version}"; \
      for dependency in "$@"; do \
        /usr/local/go/bin/go get "${dependency}"; \
      done; \
      if [ "${name}" = gitleaks ]; then \
        CGO_ENABLED=0 /usr/local/go/bin/go build \
          -buildvcs=false \
          -ldflags \
          "-s -w -X=github.com/zricethezav/gitleaks/v8/version.Version=${GITLEAKS_VERSION}" \
          -trimpath \
          -o "${output_directory}/${name}" \
          "${package}"; \
      else \
        CGO_ENABLED=0 /usr/local/go/bin/go build \
          -buildvcs=false \
          -trimpath \
          -o "${output_directory}/${name}" \
          "${package}"; \
      fi; \
    }; \
    export \
      GOCACHE=/root/.cache/go-build \
      GOMODCACHE=/go/pkg/mod \
      GOPATH=/go \
      GOTOOLCHAIN=local; \
    build_tool \
      actionlint \
      github.com/rhysd/actionlint/cmd/actionlint \
      "v${ACTIONLINT_VERSION}"; \
    build_tool \
      gitleaks \
      github.com/zricethezav/gitleaks/v8 \
      "v${GITLEAKS_VERSION}" \
      "golang.org/x/crypto@${GITLEAKS_X_CRYPTO_VERSION}"; \
    build_tool \
      shfmt \
      mvdan.cc/sh/v3/cmd/shfmt \
      "v${SHFMT_VERSION}"; \
    build_tool \
      yq \
      github.com/mikefarah/yq/v4 \
      "v${YQ_VERSION}"

FROM ${BASE_IMAGE}

USER root

ARG ACTIONLINT_VERSION
ARG BUILD_CREATED=unknown
ARG BUILD_REVISION=unknown
ARG CI_GID=1001
ARG CI_UID=1001
ARG DEBIAN_SNAPSHOT
ARG GITLEAKS_VERSION
ARG MANIFEST_SHA=unknown
ARG MARKDOWNLINT_CLI2_VERSION
ARG NPM_BRACE_EXPANSION_VERSION
ARG NPM_VERSION
ARG SHELLSPEC_SHA256
ARG SHELLSPEC_VERSION
ARG SHFMT_VERSION
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
      "s|URIs: http://deb.debian.org/debian$|URIs: http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/|" \
      /etc/apt/sources.list.d/debian.sources \
    && sed -ri \
      "s|URIs: http://deb.debian.org/debian-security$|URIs: http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}/|" \
      /etc/apt/sources.list.d/debian.sources \
    && printf '%s\n' \
      'Acquire::Check-Valid-Until "false";' \
      'Acquire::Retries "5";' \
      > /etc/apt/apt.conf.d/99-ci-snapshot \
    && apt-get update \
    && apt-get upgrade --yes --no-install-recommends \
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

RUN test -n "${YARN_VERSION}" \
    && rm -rf "/opt/yarn-v${YARN_VERSION}" \
    && rm -f /usr/local/bin/yarn /usr/local/bin/yarnpkg

COPY --from=base-go-tools /out/ /opt/ci-tools/

RUN set -eu; \
    install -d /opt/ci-tools/bin; \
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
      /opt/ci-tools/bin/yq

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

COPY images/base/npm-runtime/package.json \
  images/base/npm-runtime/package-lock.json \
  /tmp/npm-runtime/

RUN --mount=type=cache,target=/root/.npm \
    set -eu; \
    test "$(node --print \
      "require('/tmp/npm-runtime/package.json').dependencies.npm")" \
      = "${NPM_VERSION}"; \
    NPM_CONFIG_CACHE=/root/.npm npm ci \
      --fund=false \
      --ignore-scripts \
      --no-audit \
      --omit=dev \
      --prefix /tmp/npm-runtime; \
    test "$(node --print \
      "require('/tmp/npm-runtime/node_modules/npm/package.json').version")" \
      = "${NPM_VERSION}"; \
    test "$(node --print \
      "require('/tmp/npm-runtime/node_modules/brace-expansion/package.json').version")" \
      = "${NPM_BRACE_EXPANSION_VERSION}"; \
    rm -rf \
      /tmp/npm-runtime/node_modules/npm/node_modules/brace-expansion; \
    mv \
      /tmp/npm-runtime/node_modules/brace-expansion \
      /tmp/npm-runtime/node_modules/npm/node_modules/brace-expansion; \
    rm -rf /usr/local/lib/node_modules/npm; \
    rm -f /usr/local/bin/npm /usr/local/bin/npx; \
    install -d /opt/ci-tools/npm; \
    mv \
      /tmp/npm-runtime/node_modules/npm \
      "/opt/ci-tools/npm/${NPM_VERSION}"; \
    ln -s \
      "../npm/${NPM_VERSION}/bin/npm-cli.js" \
      /opt/ci-tools/bin/npm; \
    ln -s \
      "../npm/${NPM_VERSION}/bin/npx-cli.js" \
      /opt/ci-tools/bin/npx; \
    rm -rf /tmp/npm-runtime; \
    test "$(/opt/ci-tools/bin/npm --version)" = "${NPM_VERSION}"; \
    test "$(node --print \
      "require('/opt/ci-tools/npm/${NPM_VERSION}/node_modules/brace-expansion/package.json').version")" \
      = "${NPM_BRACE_EXPANSION_VERSION}"

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
