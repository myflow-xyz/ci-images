# syntax=docker/dockerfile:1.28.0@sha256:bb22d9815c728170f72750f4e5b0d672e06176142e1d602c7e66c050100b7e5b
# check=skip=InvalidDefaultArgInFrom

ARG BASE_IMAGE
ARG GO_IMAGE
FROM --platform=$BUILDPLATFORM ${GO_IMAGE} AS utils-tools-builder

USER root

ARG TARGETARCH
ARG BUILDX_VERSION
ARG BUILDX_MODULE_SUM
ARG BUILDX_COMMIT
ARG BUILDX_GO_ARCHIVE_VERSION
ARG GO_VERSION

ENV GOCACHE=/var/cache/go/build \
    GOMODCACHE=/var/cache/go/mod \
    GOPATH=/var/lib/go \
    GOTOOLCHAIN=local

RUN --mount=type=cache,target=/var/cache/go/mod,sharing=locked \
    --mount=type=cache,target=/var/cache/go/build,sharing=locked \
    set -eu; \
    test "$(/usr/local/go/bin/go version | awk '{print $3}')" = "go${GO_VERSION}"; \
    install -d /out/ci-utils "/out/buildx/${BUILDX_VERSION}"; \
    /usr/local/go/bin/go mod download -json "github.com/docker/buildx@v${BUILDX_VERSION}" > /var/tmp/buildx-source.json; \
    test "$(jq -r .Sum /var/tmp/buildx-source.json)" = "${BUILDX_MODULE_SUM}"; \
    test "$(jq -r .Origin.Hash /var/tmp/buildx-source.json)" = "${BUILDX_COMMIT}"; \
    cp -R "/var/cache/go/mod/github.com/docker/buildx@v${BUILDX_VERSION}" /var/tmp/buildx; \
    chmod -R u+w /var/tmp/buildx; \
    cd /var/tmp/buildx; \
    /usr/local/go/bin/go get "github.com/moby/go-archive@${BUILDX_GO_ARCHIVE_VERSION}"; \
    CGO_ENABLED=0 GOOS=linux GOARCH="${TARGETARCH}" \
      /usr/local/go/bin/go build -buildvcs=false -trimpath -mod=mod \
      -ldflags "-s -w -X github.com/docker/buildx/version.Version=v${BUILDX_VERSION} -X github.com/docker/buildx/version.Revision=${BUILDX_COMMIT}" \
      -o "/out/buildx/${BUILDX_VERSION}/docker-buildx" ./cmd/buildx; \
    /usr/local/go/bin/go version -m "/out/buildx/${BUILDX_VERSION}/docker-buildx" > /out/ci-utils/buildx.buildinfo

COPY images/utils/buildkit-probe/ /var/tmp/buildkit-probe/

RUN --mount=type=cache,target=/var/cache/go/mod,sharing=locked \
    --mount=type=cache,target=/var/cache/go/build,sharing=locked \
    set -eu; \
    cd /var/tmp/buildkit-probe; \
    /usr/local/go/bin/go test -race -mod=readonly ./...; \
    CGO_ENABLED=0 GOOS=linux GOARCH="${TARGETARCH}" \
      /usr/local/go/bin/go build -buildvcs=false -trimpath -mod=readonly \
      -ldflags '-s -w' -o /out/ci-utils/ci-buildkit-probe .; \
    /usr/local/go/bin/go version -m /out/ci-utils/ci-buildkit-probe > /out/ci-utils/buildkit-probe.buildinfo

FROM ${BASE_IMAGE}

USER root

ARG BUILD_CREATED=unknown
ARG BUILD_REVISION=unknown
ARG MANIFEST_SHA=unknown
ARG BUILDX_VERSION

COPY --from=utils-tools-builder /out/ /opt/ci-tools/
COPY images/utils/ci_utils/ /opt/ci-tools/ci-utils/ci_utils/
COPY images/utils/bin/ /opt/ci-tools/ci-utils/bin/

RUN set -eu; \
    install -d /etc/ci-utils /run/ci-utils; \
    ln -s ../ci-utils/bin/ci-utils /opt/ci-tools/bin/ci-utils; \
    ln -s ../ci-utils/bin/ci-docker-cleanup /opt/ci-tools/bin/ci-docker-cleanup; \
    ln -s ../ci-utils/ci-buildkit-probe /opt/ci-tools/bin/ci-buildkit-probe; \
    ln -s "/opt/ci-tools/buildx/${BUILDX_VERSION}/docker-buildx" /usr/local/lib/docker/cli-plugins/docker-buildx; \
    python3 -c 'import json,sys; from pathlib import Path; Path("/opt/ci-tools/ci-utils/build.json").write_text(json.dumps({"revision":sys.argv[1],"version":"sha-"+sys.argv[1]})+"\n")' "${BUILD_REVISION}"; \
    chmod -R go-w /opt/ci-tools/ci-utils

LABEL org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.description="Shared CI maintenance tools with guarded Docker cleanup" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.source="https://github.com/myflow-xyz/ci-images" \
      org.opencontainers.image.title="MyFlow CI utilities" \
      org.myflow.ci.manifest-sha="${MANIFEST_SHA}" \
      org.myflow.ci.utils-host-protocol="1"

USER ci
WORKDIR /workspace

CMD ["ci-utils"]
