# syntax=docker/dockerfile:1.28.0@sha256:bb22d9815c728170f72750f4e5b0d672e06176142e1d602c7e66c050100b7e5b
# check=skip=InvalidDefaultArgInFrom

ARG BASE_IMAGE
ARG BUILDER_IMAGE
FROM ${BUILDER_IMAGE} AS hurl-build-base

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
      build-essential ca-certificates cmake curl git libclang-dev libidn2-dev libkrb5-dev libldap2-dev libnghttp2-dev libpsl-dev librtmp-dev libssh2-1-dev libxml2-dev libzstd-dev pkg-config python3 xz-utils zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

FROM hurl-build-base AS hurl-builder

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

ARG BROTLI_ASSET_URL
ARG BROTLI_SHA256
ARG CURL_ASSET_URL
ARG CURL_SHA256
ARG HURL_VERSION
ARG NGHTTP3_ASSET_URL
ARG NGHTTP3_SHA256
ARG NGTCP2_ASSET_URL
ARG NGTCP2_SHA256
ARG OPENSSL_ASSET_URL
ARG OPENSSL_SHA256

RUN set -eu; \
    unpack_source() { \
      install -d "/var/tmp/native/$1"; \
      /usr/local/libexec/ci/fetch-verified "$2" "$3" "/var/tmp/$1.tar"; \
      tar -xf "/var/tmp/$1.tar" --strip-components=1 -C "/var/tmp/native/$1"; \
    }; \
    unpack_source brotli "${BROTLI_ASSET_URL}" "${BROTLI_SHA256}"; \
    unpack_source openssl "${OPENSSL_ASSET_URL}" "${OPENSSL_SHA256}"; \
    unpack_source nghttp3 "${NGHTTP3_ASSET_URL}" "${NGHTTP3_SHA256}"; \
    unpack_source ngtcp2 "${NGTCP2_ASSET_URL}" "${NGTCP2_SHA256}"; \
    unpack_source curl "${CURL_ASSET_URL}" "${CURL_SHA256}"; \
    prefix="/opt/ci-tools/hurl/${HURL_VERSION}"; \
    export PKG_CONFIG_PATH="${prefix}/lib/pkgconfig" \
      CPPFLAGS="-I${prefix}/include" LDFLAGS="-L${prefix}/lib -Wl,-rpath,${prefix}/lib"; \
    cmake -S /var/tmp/native/brotli -B /var/tmp/brotli-build \
      -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="${prefix}" \
      -DCMAKE_INSTALL_LIBDIR=lib -DCMAKE_INSTALL_RPATH="${prefix}/lib" -DBUILD_SHARED_LIBS=ON; \
    cmake --build /var/tmp/brotli-build --parallel 2; \
    cmake --install /var/tmp/brotli-build; \
    cd /var/tmp/native/openssl; \
    ./Configure --prefix="${prefix}" --libdir=lib --openssldir=/etc/ssl shared no-tests; \
    make -j2; \
    make install_sw; \
    cd /var/tmp/native/nghttp3; \
    ./configure --prefix="${prefix}" --enable-lib-only --disable-static; \
    make -j2; \
    make install; \
    cd /var/tmp/native/ngtcp2; \
    ./configure --prefix="${prefix}" --enable-lib-only --disable-static \
      --with-openssl --without-gnutls --without-boringssl --without-picotls; \
    make -j2; \
    make install; \
    cd /var/tmp/native/curl; \
    ./configure --prefix="${prefix}" --disable-static \
      --with-openssl="${prefix}" --with-nghttp2 --with-nghttp3="${prefix}" \
      --with-ngtcp2="${prefix}" --with-brotli="${prefix}" --with-libssh2 \
      --with-libidn2 --with-gssapi --with-zstd --with-libpsl \
      --with-ca-bundle=/etc/ssl/certs/ca-certificates.crt --with-ca-path=/etc/ssl/certs; \
    make -j2; \
    make install; \
    "${prefix}/bin/curl" --version; \
    "${prefix}/bin/curl" --version | grep --fixed-strings HTTP3 >/dev/null

ARG HURL_SOURCE_URL
ARG HURL_SOURCE_SHA256

COPY images/go/hurl/Cargo.lock /var/tmp/hurl-inputs/Cargo.lock

RUN --mount=type=cache,target=/var/cache/cargo,sharing=locked \
    --mount=type=cache,target=/var/cache/hurl-target,sharing=locked \
    set -eu; \
    /usr/local/libexec/ci/fetch-verified "${HURL_SOURCE_URL}" "${HURL_SOURCE_SHA256}" /var/tmp/hurl.tar.gz; \
    install -d /var/tmp/hurl-source; \
    tar -xzf /var/tmp/hurl.tar.gz --strip-components=1 -C /var/tmp/hurl-source; \
    cd /var/tmp/hurl-source; \
    cp /var/tmp/hurl-inputs/Cargo.lock Cargo.lock; \
    prefix="/opt/ci-tools/hurl/${HURL_VERSION}"; \
    export CARGO_HOME=/var/cache/cargo CARGO_TARGET_DIR=/var/cache/hurl-target \
      PKG_CONFIG_PATH="${prefix}/lib/pkgconfig" OPENSSL_DIR="${prefix}" \
      RUSTFLAGS="-C link-arg=-Wl,-rpath,${prefix}/lib"; \
    cargo build --release --locked -j2 --package hurl --package hurlfmt; \
    install -d /out/hurl/lib /out/hurl/licenses; \
    install -m 0755 /var/cache/hurl-target/release/hurl /var/cache/hurl-target/release/hurlfmt /out/hurl/; \
    cp -a "${prefix}/lib/." /out/hurl/lib/; \
    find /out/hurl/lib -type f \( -name '*.a' -o -name '*.la' \) -delete; \
    rm -rf /out/hurl/lib/pkgconfig /out/hurl/lib/cmake; \
    install -m 0644 LICENSE /out/hurl/licenses/hurl; \
    install -m 0644 /var/tmp/native/brotli/LICENSE /out/hurl/licenses/brotli; \
    install -m 0644 /var/tmp/native/openssl/LICENSE.txt /out/hurl/licenses/openssl; \
    for name in curl nghttp3 ngtcp2; do \
      install -m 0644 "/var/tmp/native/${name}/COPYING" "/out/hurl/licenses/${name}"; \
    done

FROM ${BASE_IMAGE}

ARG BUILD_CREATED=unknown
ARG BUILD_REVISION=unknown
ARG GOLANGCI_LINT_VERSION
ARG GOLANGCI_LINT_X_TEXT_VERSION
ARG GOIMPORTS_VERSION
ARG GOIMPORTS_X_NET_VERSION
ARG GOOSE_VERSION
ARG GOOSE_COMPRESS_VERSION
ARG GOOSE_X_CRYPTO_VERSION
ARG GOOSE_GRPC_VERSION
ARG GOOSE_MODERNC_LIBC_VERSION
ARG GOOSE_MODERNC_SQLITE_VERSION
ARG GOOSE_X_NET_VERSION
ARG GOOSE_BROTLI_VERSION
ARG GOVULNCHECK_VERSION
ARG GO_SHA256_AMD64
ARG GO_SHA256_ARM64
ARG GO_VERSION
ARG HURL_VERSION
ARG LINUX_LIBC_DEV_ASSET_URL
ARG LINUX_LIBC_DEV_SHA256
ARG LINUX_LIBC_DEV_VERSION
ARG MANIFEST_SHA=unknown
ARG SQLC_VERSION
ARG SQLC_CEL_GO_VERSION
ARG SQLC_GRPC_VERSION
ARG SQLC_X_NET_VERSION
ARG TARGETARCH

USER root

RUN libc_version=$(dpkg-query -W -f='${Version}' libc6) \
    && /usr/local/libexec/ci/fetch-verified \
      "${LINUX_LIBC_DEV_ASSET_URL}" "${LINUX_LIBC_DEV_SHA256}" /var/tmp/linux-libc-dev.deb \
    && apt-get update \
    && apt-get install --yes --no-install-recommends \
      gcc \
      g++ \
      "libc6-dev=${libc_version}" \
      "libc-dev-bin=${libc_version}" \
      libxml2 \
      pkg-config \
      /var/tmp/linux-libc-dev.deb \
    && test "$(dpkg-query -W -f='${Version}' linux-libc-dev)" = "${LINUX_LIBC_DEV_VERSION}" \
    && rm -rf /var/lib/apt/lists/* /var/tmp/linux-libc-dev.deb

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

COPY --from=hurl-builder /out/hurl/ /opt/ci-tools/hurl/${HURL_VERSION}/

RUN set -eu; \
    ln -s \
      "../hurl/${HURL_VERSION}/hurl" \
      /opt/ci-tools/bin/hurl; \
    ln -s \
      "../hurl/${HURL_VERSION}/hurlfmt" \
      /opt/ci-tools/bin/hurlfmt; \
    hurl --version | grep --fixed-strings "hurl ${HURL_VERSION}" >/dev/null; \
    hurlfmt --version | grep --fixed-strings "hurlfmt ${HURL_VERSION}" >/dev/null

RUN --mount=type=cache,target=/var/cache/go/mod,sharing=locked \
    --mount=type=cache,target=/var/cache/go/build,sharing=locked \
    set -eu; \
    build_tool() { \
      name=$1; \
      package=$2; \
      version=$3; \
      shift 3; \
      build_directory="/var/tmp/build/${name}"; \
      output_directory="/opt/ci-tools/${name}/${version#v}"; \
      install -d "${build_directory}" "${output_directory}"; \
      cd "${build_directory}"; \
      /usr/local/go/bin/go mod init "ci.invalid/${name}"; \
      /usr/local/go/bin/go get "${package}@${version}"; \
      for dependency in "$@"; do \
        /usr/local/go/bin/go get "${dependency}"; \
      done; \
      CGO_ENABLED=0 /usr/local/go/bin/go build \
          -buildvcs=false \
          -mod=mod \
          -trimpath \
          -o "${output_directory}/${name}" \
          "${package}"; \
    }; \
    export \
      GOCACHE=/var/cache/go/build \
      GOMODCACHE=/var/cache/go/mod \
      GOPATH=/var/lib/go \
      GOTOOLCHAIN=local; \
    build_tool \
      sqlc \
      github.com/sqlc-dev/sqlc/cmd/sqlc \
      "${SQLC_VERSION}" \
      "github.com/google/cel-go@${SQLC_CEL_GO_VERSION}" \
      "golang.org/x/net@${SQLC_X_NET_VERSION}" \
      "google.golang.org/grpc@${SQLC_GRPC_VERSION}"; \
    build_tool \
      goose \
      github.com/pressly/goose/v3/cmd/goose \
      "${GOOSE_VERSION}" \
      "golang.org/x/crypto@${GOOSE_X_CRYPTO_VERSION}" \
      "github.com/andybalholm/brotli@${GOOSE_BROTLI_VERSION}" \
      "golang.org/x/net@${GOOSE_X_NET_VERSION}" \
      "google.golang.org/grpc@${GOOSE_GRPC_VERSION}" \
      "modernc.org/libc@${GOOSE_MODERNC_LIBC_VERSION}" \
      "modernc.org/sqlite@${GOOSE_MODERNC_SQLITE_VERSION}" \
      "github.com/klauspost/compress@${GOOSE_COMPRESS_VERSION}"; \
    build_tool \
      golangci-lint \
      github.com/golangci/golangci-lint/v2/cmd/golangci-lint \
      "${GOLANGCI_LINT_VERSION}" \
      "golang.org/x/text@${GOLANGCI_LINT_X_TEXT_VERSION}"; \
    build_tool \
      goimports \
      golang.org/x/tools/cmd/goimports \
      "${GOIMPORTS_VERSION}" \
      "golang.org/x/net@${GOIMPORTS_X_NET_VERSION}"; \
    build_tool \
      govulncheck \
      golang.org/x/vuln/cmd/govulncheck \
      "${GOVULNCHECK_VERSION}"

ENV GOBIN=/opt/ci-tools/bin \
    GOCACHE=/var/cache/go/build \
    GOMODCACHE=/var/cache/go/mod \
    GOPATH=/var/lib/go \
    GOROOT=/usr/local/go \
    GOTMPDIR=/var/tmp/go \
    GOTOOLCHAIN=local \
    PATH=/usr/local/go/bin:/opt/ci-tools/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN set -eu; \
    ln -s \
      "../sqlc/${SQLC_VERSION#v}/sqlc" \
      /opt/ci-tools/bin/sqlc; \
    ln -s \
      "../goose/${GOOSE_VERSION#v}/goose" \
      /opt/ci-tools/bin/goose; \
    ln -s \
      "../golangci-lint/${GOLANGCI_LINT_VERSION#v}/golangci-lint" \
      /opt/ci-tools/bin/golangci-lint; \
    ln -s \
      "../goimports/${GOIMPORTS_VERSION#v}/goimports" \
      /opt/ci-tools/bin/goimports; \
    ln -s \
      "../govulncheck/${GOVULNCHECK_VERSION#v}/govulncheck" \
      /opt/ci-tools/bin/govulncheck; \
    install -d -o ci -g ci \
      /var/cache/go/build \
      /var/cache/go/mod \
      /var/lib/go \
      /var/tmp/go

LABEL org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.description="MyFlow Go CI job environment" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.source="https://github.com/myflow-xyz/ci-images" \
      org.opencontainers.image.title="MyFlow Go CI" \
      org.myflow.ci.go-version="${GO_VERSION}" \
      org.myflow.ci.manifest-sha="${MANIFEST_SHA}"

USER ci
WORKDIR /workspace

CMD ["bash"]
