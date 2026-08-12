# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS base-git-builder

ARG DEBIAN_SNAPSHOT
ARG GIT_SHA256
ARG GIT_VERSION

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
      build-essential \
      ca-certificates \
      curl \
      gettext \
      libcurl4-openssl-dev \
      libexpat1-dev \
      libpcre2-dev \
      libssl-dev \
      perl \
      xz-utils \
      zlib1g-dev \
    && rm -rf /var/lib/apt/lists/* \
    && chmod 0755 /usr/local/libexec/ci/fetch-verified

RUN set -eu; \
    /usr/local/libexec/ci/fetch-verified \
      "https://www.kernel.org/pub/software/scm/git/git-${GIT_VERSION}.tar.xz" \
      "${GIT_SHA256}" \
      /var/tmp/git.tar.xz; \
    install -d /var/tmp/git /out; \
    tar -xJf /var/tmp/git.tar.xz \
      --strip-components=1 \
      -C /var/tmp/git; \
    make \
      -C /var/tmp/git \
      -j2 \
      NO_RUST=YesPlease \
      NO_TCLTK=YesPlease \
      prefix=/usr/local \
      sysconfdir=/etc \
      all; \
    make \
      -C /var/tmp/git \
      NO_RUST=YesPlease \
      NO_TCLTK=YesPlease \
      prefix=/usr/local \
      sysconfdir=/etc \
      strip; \
    make \
      -C /var/tmp/git \
      DESTDIR=/out \
      NO_RUST=YesPlease \
      NO_TCLTK=YesPlease \
      prefix=/usr/local \
      sysconfdir=/etc \
      install; \
    test "$(/out/usr/local/bin/git version)" = "git version ${GIT_VERSION}"; \
    rm -rf /var/tmp/git /var/tmp/git.tar.xz

FROM ${BASE_IMAGE} AS base-python-builder

ARG DEBIAN_SNAPSHOT
ARG PYTHON_SHA256
ARG PYTHON_VERSION

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
      build-essential \
      ca-certificates \
      curl \
      dpkg-dev \
      libbluetooth-dev \
      libbz2-dev \
      libc6-dev \
      libdb-dev \
      libffi-dev \
      libgdbm-dev \
      liblzma-dev \
      libncursesw5-dev \
      libreadline-dev \
      libsqlite3-dev \
      libssl-dev \
      libzstd-dev \
      uuid-dev \
      xz-utils \
      zlib1g-dev \
    && rm -rf /var/lib/apt/lists/* \
    && chmod 0755 /usr/local/libexec/ci/fetch-verified

RUN set -eu; \
    /usr/local/libexec/ci/fetch-verified \
      "https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tar.xz" \
      "${PYTHON_SHA256}" \
      /var/tmp/python.tar.xz; \
    install -d /var/tmp/python /out; \
    tar -xJf /var/tmp/python.tar.xz \
      --strip-components=1 \
      -C /var/tmp/python; \
    cd /var/tmp/python; \
    gnu_arch=$(dpkg-architecture --query DEB_BUILD_GNU_TYPE); \
    ./configure \
      --build="${gnu_arch}" \
      --enable-loadable-sqlite-extensions \
      --enable-option-checking=fatal \
      --without-ensurepip; \
    extra_cflags=$(dpkg-buildflags --get CFLAGS); \
    ldflags=$(dpkg-buildflags --get LDFLAGS); \
    make \
      -j2 \
      "EXTRA_CFLAGS=${extra_cflags}" \
      "LDFLAGS=${ldflags} -Wl,--strip-all"; \
    make \
      DESTDIR=/out \
      "EXTRA_CFLAGS=${extra_cflags}" \
      "LDFLAGS=${ldflags} -Wl,--strip-all" \
      install; \
    python_series=${PYTHON_VERSION%.*}; \
    rm -f \
      /out/usr/local/bin/idle \
      /out/usr/local/bin/idle3 \
      "/out/usr/local/bin/idle${python_series}" \
      /out/usr/local/bin/python \
      /out/usr/local/bin/python-config \
      /out/usr/local/bin/python3-config \
      "/out/usr/local/bin/python${python_series}-config" \
      /out/usr/local/lib/libpython*.a; \
    rm -rf \
      "/out/usr/local/include/python${python_series}" \
      "/out/usr/local/lib/python${python_series}/ensurepip" \
      "/out/usr/local/lib/python${python_series}/idlelib" \
      "/out/usr/local/lib/python${python_series}/site-packages" \
      "/out/usr/local/lib/python${python_series}/venv"; \
    rm -rf "/out/usr/local/lib/python${python_series}"/config-*; \
    rm -f /out/usr/local/lib/pkgconfig/python*.pc; \
    install -d \
      "/out/usr/local/lib/python${python_series}/site-packages" \
      "/out/usr/local/share/licenses/python-${PYTHON_VERSION}"; \
    install -m 0644 \
      LICENSE \
      "/out/usr/local/share/licenses/python-${PYTHON_VERSION}/LICENSE"; \
    find /out/usr/local -depth \
      \( \
        \( -type d -a \( -name test -o -name tests \) \) \
        -o \( -type f -a \( -name '*.pyc' -o -name '*.pyo' \) \) \
      \) \
      -exec rm -rf '{}' +; \
    PYTHONDONTWRITEBYTECODE=1 \
      PYTHONHOME=/out/usr/local \
      /out/usr/local/bin/python3 \
      -c 'import bz2, compression.zstd, ctypes, dbm.gnu, lzma, readline, sqlite3, ssl, sys, uuid, zlib; assert sys.version.split()[0] == sys.argv[1]' \
      "${PYTHON_VERSION}"; \
    rm -rf /var/tmp/python /var/tmp/python.tar.xz

RUN set -eu; \
    find /out/usr/local -type f -executable -exec ldd '{}' ';' \
      | awk '/=>/ { \
          so = $(NF - 1); \
          if (index(so, "/out/usr/local/") == 1) next; \
          gsub("^/(usr/)?", "", so); \
          printf "*%s\n", so \
        }' \
      | sort -u \
      | xargs -r dpkg-query --search \
      | awk 'sub(":$", "", $1) { print $1 }' \
      | sort -u \
      > /out/python-runtime-packages

FROM ${BASE_IMAGE} AS base-go-tools-builder

ARG ACTIONLINT_VERSION
ARG DEBIAN_SNAPSHOT
ARG GITLEAKS_VERSION
ARG GITLEAKS_X_CRYPTO_VERSION
ARG GITLEAKS_XZ_VERSION
ARG GO_SHA256_AMD64
ARG GO_SHA256_ARM64
ARG GO_VERSION
ARG SHFMT_VERSION
ARG TARGETARCH
ARG YQ_VERSION
ARG YQ_X_TEXT_VERSION

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
      /var/tmp/go.tar.gz; \
    tar -xzf /var/tmp/go.tar.gz -C /usr/local; \
    rm -f /var/tmp/go.tar.gz; \
    test "$(/usr/local/go/bin/go version | awk '{print $3}')" \
      = "go${GO_VERSION}"

RUN --mount=type=cache,target=/var/cache/go/mod \
    --mount=type=cache,target=/var/cache/go/build \
    set -eu; \
    build_tool() { \
      name=$1; \
      package=$2; \
      version=$3; \
      shift 3; \
      build_directory="/var/tmp/build/${name}"; \
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
      GOCACHE=/var/cache/go/build \
      GOMODCACHE=/var/cache/go/mod \
      GOPATH=/var/lib/go \
      GOTOOLCHAIN=local; \
    build_tool \
      actionlint \
      github.com/rhysd/actionlint/cmd/actionlint \
      "v${ACTIONLINT_VERSION}"; \
    build_tool \
      gitleaks \
      github.com/zricethezav/gitleaks/v8 \
      "v${GITLEAKS_VERSION}" \
      "github.com/ulikunitz/xz@${GITLEAKS_XZ_VERSION}" \
      "golang.org/x/crypto@${GITLEAKS_X_CRYPTO_VERSION}"; \
    build_tool \
      shfmt \
      mvdan.cc/sh/v3/cmd/shfmt \
      "v${SHFMT_VERSION}"; \
    build_tool \
      yq \
      github.com/mikefarah/yq/v4 \
      "v${YQ_VERSION}" \
      "golang.org/x/text@${YQ_X_TEXT_VERSION}"

FROM ${BASE_IMAGE}

USER root

ARG ACTIONLINT_VERSION
ARG BUILD_CREATED=unknown
ARG BUILD_REVISION=unknown
ARG CI_GID=2001
ARG CI_UID=1001
ARG DEBIAN_SNAPSHOT
ARG GITLEAKS_VERSION
ARG MANIFEST_SHA=unknown
ARG PYTHON_VERSION
ARG SHELLSPEC_SHA256
ARG SHELLSPEC_VERSION
ARG SHFMT_VERSION
ARG YQ_VERSION

ENV CI=true \
    DEBIAN_FRONTEND=noninteractive \
    HOME=/home/ci \
    PATH=/opt/ci-tools/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    TMPDIR=/var/tmp \
    TZ=UTC

COPY images/common/fetch-verified /usr/local/libexec/ci/fetch-verified

RUN --mount=from=base-python-builder,source=/out/python-runtime-packages,target=/var/tmp/python-runtime-packages,ro \
    test -n "${DEBIAN_SNAPSHOT}" \
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
      locales \
      make \
      netbase \
      openssl \
      procps \
      ripgrep \
      sed \
      shellcheck \
      tar \
      tini \
      tzdata \
      unzip \
      wget \
      xz-utils \
      zip \
    && xargs -r \
      apt-get install --yes --no-install-recommends \
      < /var/tmp/python-runtime-packages \
    && sed -ri 's/^# (en_US.UTF-8 UTF-8)$/\1/' /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/* \
    && chmod 0755 /usr/local/libexec/ci/fetch-verified

ENV LANG=en_US.utf8 \
    LC_ALL=en_US.utf8

COPY --from=base-go-tools-builder /out/ /opt/ci-tools/
COPY --from=base-git-builder /out/ /
COPY --from=base-python-builder /out/usr/local/ /usr/local/

RUN set -eu; \
    test "$(python3 --version)" = "Python ${PYTHON_VERSION}"; \
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
      /var/tmp/shellspec.tar.gz; \
    tar -xzf /var/tmp/shellspec.tar.gz \
      --strip-components=1 \
      -C "/opt/ci-tools/shellspec/${SHELLSPEC_VERSION}"; \
    ln -s \
      "../shellspec/${SHELLSPEC_VERSION}/shellspec" \
      /opt/ci-tools/bin/shellspec; \
    rm -f /var/tmp/shellspec.tar.gz

RUN set -eu; \
    groupadd --gid "${CI_GID}" ci; \
    useradd \
      --create-home \
      --gid "${CI_GID}" \
      --shell /bin/bash \
      --uid "${CI_UID}" \
      ci; \
    install -d -m 1777 /var/tmp; \
    install -d -o ci -g ci \
      /workspace; \
    chown -R ci:ci /home/ci; \
    git config --system --add safe.directory /workspace; \
    git config --system --add safe.directory '/__w/*'

LABEL org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.description="Shared MyFlow CI job environment" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.source="https://github.com/myflow-xyz/ci-images" \
      org.opencontainers.image.title="MyFlow CI base" \
      org.myflow.ci.manifest-sha="${MANIFEST_SHA}" \
      org.myflow.ci.python-version="${PYTHON_VERSION}"

USER ci
WORKDIR /workspace

CMD ["bash"]
