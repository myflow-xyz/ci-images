# syntax=docker/dockerfile:1.27.0@sha256:bde3983e9c939224420ddaf6b784cc30e09b035a4dea01f581230c50809f372e
# check=skip=InvalidDefaultArgInFrom

ARG BASE_IMAGE
ARG PYTHON_IMAGE
FROM ${BASE_IMAGE} AS base-source-builder

ARG BASH_PATCHLEVEL
ARG BASH_RELEASE
ARG BASH_SHA256
ARG DEBIAN_SNAPSHOT
ARG GIT_SHA256
ARG GIT_VERSION

USER root

COPY images/common/fetch-verified /usr/local/libexec/ci/fetch-verified
COPY images/base/bash-5.3-patches.sha256 /usr/local/share/ci/bash-patches.sha256

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
    && printf '%s\n' \
      'path-include /usr/share/man/man7/bash-builtins.7.gz' \
      > /etc/dpkg/dpkg.cfg.d/zz-ci-bash-builtins \
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
      patch \
      perl \
      xz-utils \
      zlib1g-dev \
    && rm -rf /var/lib/apt/lists/* \
    && chmod 0755 /usr/local/libexec/ci/fetch-verified

RUN set -eu; \
    /usr/local/libexec/ci/fetch-verified \
      "https://ftp.gnu.org/gnu/bash/bash-${BASH_RELEASE}.tar.gz" \
      "${BASH_SHA256}" \
      /var/tmp/bash.tar.gz; \
    install -d /var/tmp/bash /out/usr/local/bin; \
    tar -xzf /var/tmp/bash.tar.gz \
      --strip-components=1 \
      -C /var/tmp/bash; \
    patch_number=0; \
    while IFS='=' read -r patch_name patch_sha256; do \
      patch_number=$((patch_number + 1)); \
      test "${patch_name}" \
        = "$(printf 'bash53-%03d' "${patch_number}")"; \
      /usr/local/libexec/ci/fetch-verified \
        "https://ftp.gnu.org/gnu/bash/bash-${BASH_RELEASE}-patches/${patch_name}" \
        "${patch_sha256}" \
        "/var/tmp/${patch_name}"; \
      patch -d /var/tmp/bash -p0 < "/var/tmp/${patch_name}"; \
      rm -f "/var/tmp/${patch_name}"; \
    done < /usr/local/share/ci/bash-patches.sha256; \
    test "${patch_number}" -eq "${BASH_PATCHLEVEL}"; \
    cd /var/tmp/bash; \
    ./configure --prefix=/usr/local --without-bash-malloc; \
    make -j2 bash; \
    install -m 0755 bash /out/usr/local/bin/bash; \
    test "$(/out/usr/local/bin/bash -c 'printf "%s.%s.%s" "${BASH_VERSINFO[0]}" "${BASH_VERSINFO[1]}" "${BASH_VERSINFO[2]}"')" \
      = "${BASH_RELEASE}.${BASH_PATCHLEVEL}"; \
    rm -rf /var/tmp/bash /var/tmp/bash.tar.gz

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

FROM ${PYTHON_IMAGE} AS base-python-runtime

ARG PYTHON_VERSION

USER root

RUN set -eu; \
    test "$(python3 --version)" = "Python ${PYTHON_VERSION}"; \
    install -d /out/usr; \
    cp -a /usr/local /out/usr/; \
    python_series=${PYTHON_VERSION%.*}; \
    rm -f \
      /out/usr/local/bin/idle \
      /out/usr/local/bin/idle3 \
      "/out/usr/local/bin/idle${python_series}" \
      /out/usr/local/bin/pip \
      /out/usr/local/bin/pip3 \
      "/out/usr/local/bin/pip${python_series}" \
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
      "/usr/local/lib/python${python_series}/LICENSE.txt" \
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
      "${PYTHON_VERSION}"

RUN set -eu; \
    find /out/usr/local -type f -executable -exec ldd '{}' ';' \
      | awk '/=>/ { \
          so = $(NF - 1); \
          if (index(so, "/out/usr/local/") == 1 || \
              index(so, "/usr/local/") == 1) next; \
          gsub("^/(usr/)?", "", so); \
          printf "*%s\n", so \
        }' \
      | sort -u \
      | xargs -r dpkg-query --search \
      | awk 'sub(":$", "", $1) { print $1 }' \
      | sort -u \
      > /out/python-runtime-packages

FROM --platform=${BUILDPLATFORM} ${BASE_IMAGE} AS base-go-tools-builder

ARG ACTIONLINT_VERSION
ARG BUILDARCH
ARG DEBIAN_SNAPSHOT
ARG GH_ASSET_URL_AMD64
ARG GH_ASSET_URL_ARM64
ARG GH_SHA256_AMD64
ARG GH_SHA256_ARM64
ARG GH_VERSION
ARG GIT_LFS_VERSION
ARG GIT_LFS_X_CRYPTO_VERSION
ARG GITLEAKS_VERSION
ARG GITLEAKS_X_CRYPTO_VERSION
ARG GITLEAKS_XZ_VERSION
ARG GO_SHA256_AMD64
ARG GO_SHA256_ARM64
ARG GO_VERSION
ARG JQ_ASSET_URL_AMD64
ARG JQ_ASSET_URL_ARM64
ARG JQ_SHA256_AMD64
ARG JQ_SHA256_ARM64
ARG JQ_VERSION
ARG OSV_SCANNER_VERSION
ARG RIPGREP_ASSET_URL_AMD64
ARG RIPGREP_ASSET_URL_ARM64
ARG RIPGREP_SHA256_AMD64
ARG RIPGREP_SHA256_ARM64
ARG RIPGREP_VERSION
ARG SHELLCHECK_ASSET_URL_AMD64
ARG SHELLCHECK_ASSET_URL_ARM64
ARG SHELLCHECK_SHA256_AMD64
ARG SHELLCHECK_SHA256_ARM64
ARG SHELLCHECK_VERSION
ARG SHFMT_VERSION
ARG TARGETARCH
ARG TRIVY_GO_SHA256_AMD64
ARG TRIVY_GO_SHA256_ARM64
ARG TRIVY_GO_VERSION
ARG TRIVY_GRPC_VERSION
ARG TRIVY_VERSION
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
    case "${BUILDARCH}" in \
      amd64) go_sha256="${GO_SHA256_AMD64}" ;; \
      arm64) go_sha256="${GO_SHA256_ARM64}" ;; \
      *) \
        printf 'unsupported build architecture: %s\n' "${BUILDARCH}" >&2; \
        exit 1 \
        ;; \
    esac; \
    /usr/local/libexec/ci/fetch-verified \
      "https://go.dev/dl/go${GO_VERSION}.linux-${BUILDARCH}.tar.gz" \
      "${go_sha256}" \
      /var/tmp/go.tar.gz; \
    tar -xzf /var/tmp/go.tar.gz -C /usr/local; \
    rm -f /var/tmp/go.tar.gz; \
    test "$(/usr/local/go/bin/go version | awk '{print $3}')" \
      = "go${GO_VERSION}"

RUN set -eu; \
    case "${BUILDARCH}" in \
      amd64) trivy_go_sha256="${TRIVY_GO_SHA256_AMD64}" ;; \
      arm64) trivy_go_sha256="${TRIVY_GO_SHA256_ARM64}" ;; \
      *) \
        printf 'unsupported build architecture: %s\n' "${BUILDARCH}" >&2; \
        exit 1 \
        ;; \
    esac; \
    /usr/local/libexec/ci/fetch-verified \
      "https://go.dev/dl/go${TRIVY_GO_VERSION}.linux-${BUILDARCH}.tar.gz" \
      "${trivy_go_sha256}" \
      /var/tmp/trivy-go.tar.gz; \
    install -d /opt/trivy-go; \
    tar -xzf /var/tmp/trivy-go.tar.gz \
      --strip-components=1 \
      -C /opt/trivy-go; \
    rm -f /var/tmp/trivy-go.tar.gz; \
    test "$(/opt/trivy-go/bin/go version | awk '{print $3}')" \
      = "go${TRIVY_GO_VERSION}"

RUN --mount=type=cache,target=/var/cache/go/mod,sharing=locked \
    --mount=type=cache,target=/var/cache/go/build,sharing=locked \
    --mount=type=cache,target=/var/cache/go/trivy-mod,sharing=locked \
    --mount=type=cache,target=/var/cache/go/trivy-build,sharing=locked \
    set -eu; \
    build_tool() { \
      name=$1; \
      package=$2; \
      version=$3; \
      shift 3; \
      build_directory="/var/tmp/build/${name}"; \
      output_directory="/out/${name}/${version#v}"; \
      install -d "${build_directory}" "${output_directory}"; \
      if [ "${name}" = trivy ]; then \
        source_directory="/var/cache/go/trivy-mod/github.com/aquasecurity/trivy@${version}"; \
        cd "${build_directory}"; \
        GOCACHE=/var/cache/go/trivy-build \
          GOMODCACHE=/var/cache/go/trivy-mod \
          /opt/trivy-go/bin/go mod download \
          "github.com/aquasecurity/trivy@${version}"; \
        cp -R "${source_directory}/." "${build_directory}/"; \
        chmod -R u+w "${build_directory}"; \
        for dependency in "$@"; do \
          GOCACHE=/var/cache/go/trivy-build \
            GOMODCACHE=/var/cache/go/trivy-mod \
            /opt/trivy-go/bin/go get "${dependency}"; \
        done; \
        CGO_ENABLED=0 GOARCH="${TARGETARCH}" GOOS=linux \
          GOEXPERIMENT=jsonv2 \
          GOCACHE=/var/cache/go/trivy-build \
          GOMODCACHE=/var/cache/go/trivy-mod \
          /opt/trivy-go/bin/go build \
          -buildvcs=false \
          -ldflags \
          "-s -w -X=github.com/aquasecurity/trivy/pkg/version/app.ver=${TRIVY_VERSION}" \
          -trimpath \
          -o "${output_directory}/${name}" \
          ./cmd/trivy; \
        return; \
      fi; \
      cd "${build_directory}"; \
      /usr/local/go/bin/go mod init "ci.invalid/${name}"; \
      /usr/local/go/bin/go get "${package}@${version}"; \
      for dependency in "$@"; do \
        /usr/local/go/bin/go get "${dependency}"; \
      done; \
      if [ "${name}" = gitleaks ]; then \
        CGO_ENABLED=0 GOARCH="${TARGETARCH}" GOOS=linux \
          /usr/local/go/bin/go build \
          -buildvcs=false \
          -ldflags \
          "-s -w -X=github.com/zricethezav/gitleaks/v8/version.Version=${GITLEAKS_VERSION}" \
          -trimpath \
          -o "${output_directory}/${name}" \
          "${package}"; \
      else \
        CGO_ENABLED=0 GOARCH="${TARGETARCH}" GOOS=linux \
          /usr/local/go/bin/go build \
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
      git-lfs \
      github.com/git-lfs/git-lfs/v3 \
      "v${GIT_LFS_VERSION}" \
      "golang.org/x/crypto@${GIT_LFS_X_CRYPTO_VERSION}"; \
    build_tool \
      gitleaks \
      github.com/zricethezav/gitleaks/v8 \
      "v${GITLEAKS_VERSION}" \
      "github.com/ulikunitz/xz@${GITLEAKS_XZ_VERSION}" \
      "golang.org/x/crypto@${GITLEAKS_X_CRYPTO_VERSION}"; \
    build_tool \
      osv-scanner \
      github.com/google/osv-scanner/v2/cmd/osv-scanner \
      "v${OSV_SCANNER_VERSION}"; \
    build_tool \
      shfmt \
      mvdan.cc/sh/v3/cmd/shfmt \
      "v${SHFMT_VERSION}"; \
    build_tool \
      trivy \
      github.com/aquasecurity/trivy/cmd/trivy \
      "v${TRIVY_VERSION}" \
      "google.golang.org/grpc@${TRIVY_GRPC_VERSION}"; \
    build_tool \
      yq \
      github.com/mikefarah/yq/v4 \
      "v${YQ_VERSION}" \
      "golang.org/x/text@${YQ_X_TEXT_VERSION}"

RUN set -eu; \
    case "${TARGETARCH}" in \
      amd64) \
        gh_asset_url="${GH_ASSET_URL_AMD64}"; \
        gh_sha256="${GH_SHA256_AMD64}"; \
        jq_asset_url="${JQ_ASSET_URL_AMD64}"; \
        jq_sha256="${JQ_SHA256_AMD64}"; \
        ripgrep_asset_url="${RIPGREP_ASSET_URL_AMD64}"; \
        ripgrep_root="ripgrep-${RIPGREP_VERSION}-x86_64-unknown-linux-musl"; \
        ripgrep_sha256="${RIPGREP_SHA256_AMD64}"; \
        shellcheck_asset_url="${SHELLCHECK_ASSET_URL_AMD64}"; \
        shellcheck_sha256="${SHELLCHECK_SHA256_AMD64}" \
        ;; \
      arm64) \
        gh_asset_url="${GH_ASSET_URL_ARM64}"; \
        gh_sha256="${GH_SHA256_ARM64}"; \
        jq_asset_url="${JQ_ASSET_URL_ARM64}"; \
        jq_sha256="${JQ_SHA256_ARM64}"; \
        ripgrep_asset_url="${RIPGREP_ASSET_URL_ARM64}"; \
        ripgrep_root="ripgrep-${RIPGREP_VERSION}-aarch64-unknown-linux-musl"; \
        ripgrep_sha256="${RIPGREP_SHA256_ARM64}"; \
        shellcheck_asset_url="${SHELLCHECK_ASSET_URL_ARM64}"; \
        shellcheck_sha256="${SHELLCHECK_SHA256_ARM64}" \
        ;; \
      *) \
        printf 'unsupported target architecture: %s\n' "${TARGETARCH}" >&2; \
        exit 1 \
        ;; \
    esac; \
    install -d \
      "/out/gh/${GH_VERSION}" \
      "/out/jq/${JQ_VERSION}" \
      "/out/ripgrep/${RIPGREP_VERSION}" \
      "/out/shellcheck/${SHELLCHECK_VERSION}"; \
    /usr/local/libexec/ci/fetch-verified \
      "${gh_asset_url}" \
      "${gh_sha256}" \
      /var/tmp/gh.tar.gz; \
    tar -xzf /var/tmp/gh.tar.gz \
      --strip-components=2 \
      -C "/out/gh/${GH_VERSION}" \
      "gh_${GH_VERSION}_linux_${TARGETARCH}/bin/gh"; \
    if [ "${BUILDARCH}" = "${TARGETARCH}" ]; then \
      "/out/gh/${GH_VERSION}/gh" --version \
        | grep --fixed-strings "gh version ${GH_VERSION}" >/dev/null; \
    fi; \
    printf 'verified GitHub CLI %s for %s\n' "${GH_VERSION}" "${TARGETARCH}"; \
    /usr/local/libexec/ci/fetch-verified \
      "${jq_asset_url}" \
      "${jq_sha256}" \
      "/out/jq/${JQ_VERSION}/jq"; \
    chmod 0755 "/out/jq/${JQ_VERSION}/jq"; \
    if [ "${BUILDARCH}" = "${TARGETARCH}" ]; then \
      test "$("/out/jq/${JQ_VERSION}/jq" --version)" \
        = "jq-${JQ_VERSION}"; \
    fi; \
    printf 'verified jq %s for %s\n' "${JQ_VERSION}" "${TARGETARCH}"; \
    /usr/local/libexec/ci/fetch-verified \
      "${ripgrep_asset_url}" \
      "${ripgrep_sha256}" \
      /var/tmp/ripgrep.tar.gz; \
    tar -xzf /var/tmp/ripgrep.tar.gz \
      --strip-components=1 \
      -C "/out/ripgrep/${RIPGREP_VERSION}" \
      "${ripgrep_root}/rg"; \
    if [ "${BUILDARCH}" = "${TARGETARCH}" ]; then \
      "/out/ripgrep/${RIPGREP_VERSION}/rg" --version \
        | head -n 1 \
        | grep --fixed-strings "ripgrep ${RIPGREP_VERSION}" >/dev/null; \
    fi; \
    printf 'verified ripgrep %s for %s\n' \
      "${RIPGREP_VERSION}" \
      "${TARGETARCH}"; \
    /usr/local/libexec/ci/fetch-verified \
      "${shellcheck_asset_url}" \
      "${shellcheck_sha256}" \
      /var/tmp/shellcheck.tar.gz; \
    tar -xzf /var/tmp/shellcheck.tar.gz \
      --strip-components=1 \
      -C "/out/shellcheck/${SHELLCHECK_VERSION}" \
      "shellcheck-v${SHELLCHECK_VERSION}/shellcheck"; \
    if [ "${BUILDARCH}" = "${TARGETARCH}" ]; then \
      "/out/shellcheck/${SHELLCHECK_VERSION}/shellcheck" --version \
        | grep --fixed-strings "version: ${SHELLCHECK_VERSION}" >/dev/null; \
    fi; \
    printf 'verified ShellCheck %s for %s\n' \
      "${SHELLCHECK_VERSION}" \
      "${TARGETARCH}"; \
    rm -f \
      /var/tmp/gh.tar.gz \
      /var/tmp/ripgrep.tar.gz \
      /var/tmp/shellcheck.tar.gz

FROM ${BASE_IMAGE}

USER root

ARG ACTIONLINT_VERSION
ARG BASH_PATCHLEVEL
ARG BASH_RELEASE
ARG BUILD_CREATED=unknown
ARG BUILD_REVISION=unknown
ARG CI_GID=2001
ARG CI_UID=1001
ARG DEBIAN_SNAPSHOT
ARG GH_VERSION
ARG GIT_LFS_VERSION
ARG GITLEAKS_VERSION
ARG JQ_VERSION
ARG MANIFEST_SHA=unknown
ARG OSV_SCANNER_VERSION
ARG PYTHON_VERSION
ARG RIPGREP_VERSION
ARG SHELLCHECK_VERSION
ARG SHELLSPEC_SHA256
ARG SHELLSPEC_VERSION
ARG SHFMT_VERSION
ARG TARGETARCH
ARG TRIVY_VERSION
ARG YQ_VERSION

ENV CI=true \
    DEBIAN_FRONTEND=noninteractive \
    HOME=/home/ci \
    PATH=/opt/ci-tools/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    TMPDIR=/var/tmp \
    TZ=UTC

COPY images/common/fetch-verified /usr/local/libexec/ci/fetch-verified
COPY images/base/debian-packages.*.lock /usr/local/share/ci/

RUN --mount=from=base-python-runtime,source=/out/python-runtime-packages,target=/var/tmp/python-runtime-packages,ro \
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
    && printf '%s\n' \
      'path-include /usr/share/man/man7/bash-builtins.7.gz' \
      > /etc/dpkg/dpkg.cfg.d/zz-ci-bash-builtins \
    && apt-get update \
    && apt-get upgrade --yes --no-install-recommends \
    && case "${TARGETARCH}" in \
      amd64|arm64) \
        debian_package_lock="/usr/local/share/ci/debian-packages.${TARGETARCH}.lock" \
        ;; \
      *) \
        printf 'unsupported target architecture: %s\n' "${TARGETARCH}" >&2; \
        exit 1 \
        ;; \
    esac \
    && install -m 0644 \
      "${debian_package_lock}" \
      /usr/local/share/ci/debian-packages.lock \
    && xargs -r \
      apt-get install --yes --no-install-recommends \
      < /usr/local/share/ci/debian-packages.lock \
    && xargs -r \
      apt-get install --yes --no-install-recommends \
      < /var/tmp/python-runtime-packages \
    && sed -ri 's/^# (en_US.UTF-8 UTF-8)$/\1/' /etc/locale.gen \
    && locale-gen \
    && rm -f /usr/local/share/ci/debian-packages.*.lock \
    && rm -rf /var/lib/apt/lists/* \
    && chmod 0755 /usr/local/libexec/ci/fetch-verified

ENV LANG=en_US.utf8 \
    LC_ALL=en_US.utf8

COPY --from=base-go-tools-builder /out/ /opt/ci-tools/
COPY --from=base-source-builder /out/ /
COPY --from=base-python-runtime /out/usr/local/ /usr/local/

RUN set -eu; \
    ldconfig; \
    dpkg-divert \
      --local \
      --add \
      --rename \
      --divert /usr/bin/bash.debian \
      /usr/bin/bash; \
    ln -s /usr/local/bin/bash /usr/bin/bash; \
    test "$(/bin/bash -c 'printf "%s.%s.%s" "${BASH_VERSINFO[0]}" "${BASH_VERSINFO[1]}" "${BASH_VERSINFO[2]}"')" \
      = "${BASH_RELEASE}.${BASH_PATCHLEVEL}"; \
    test "$(python3 --version)" = "Python ${PYTHON_VERSION}"; \
    install -d /opt/ci-tools/bin; \
    ln -s \
      "../actionlint/${ACTIONLINT_VERSION}/actionlint" \
      /opt/ci-tools/bin/actionlint; \
    ln -s \
      "../gh/${GH_VERSION}/gh" \
      /opt/ci-tools/bin/gh; \
    ln -s \
      "../git-lfs/${GIT_LFS_VERSION}/git-lfs" \
      /opt/ci-tools/bin/git-lfs; \
    ln -s \
      "../gitleaks/${GITLEAKS_VERSION}/gitleaks" \
      /opt/ci-tools/bin/gitleaks; \
    ln -s \
      "../jq/${JQ_VERSION}/jq" \
      /opt/ci-tools/bin/jq; \
    ln -s \
      "../osv-scanner/${OSV_SCANNER_VERSION}/osv-scanner" \
      /opt/ci-tools/bin/osv-scanner; \
    ln -s \
      "../ripgrep/${RIPGREP_VERSION}/rg" \
      /opt/ci-tools/bin/rg; \
    ln -s \
      "../shellcheck/${SHELLCHECK_VERSION}/shellcheck" \
      /opt/ci-tools/bin/shellcheck; \
    ln -s \
      "../shfmt/${SHFMT_VERSION}/shfmt" \
      /opt/ci-tools/bin/shfmt; \
    ln -s \
      "../trivy/${TRIVY_VERSION}/trivy" \
      /opt/ci-tools/bin/trivy; \
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
