# syntax=docker/dockerfile:1.29.0@sha256:572cebbc2b15e6f84c077742952674889cb63cd5e9b80abdffcbe587b6f19183
# check=skip=InvalidDefaultArgInFrom

ARG BASE_IMAGE
ARG GO_IMAGE
FROM --platform=$BUILDPLATFORM ${GO_IMAGE} AS utils-tools-builder

USER root

ARG TARGETARCH
ARG GO_VERSION

ENV GOCACHE=/var/cache/go/build \
    GOMODCACHE=/var/cache/go/mod \
    GOPATH=/var/lib/go \
    GOTOOLCHAIN=local

COPY images/utils/buildkit-probe/ /var/tmp/buildkit-probe/

RUN --mount=type=cache,target=/var/cache/go/mod,sharing=locked \
    --mount=type=cache,target=/var/cache/go/build,sharing=locked \
    set -eu; \
    test "$(/usr/local/go/bin/go version | awk '{print $3}')" = "go${GO_VERSION}"; \
    install -d /out/ci-utils; \
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

COPY --from=utils-tools-builder /out/ /opt/ci-tools/
COPY images/utils/ci_utils/ /opt/ci-tools/ci-utils/ci_utils/
COPY images/utils/bin/ /opt/ci-tools/ci-utils/bin/

RUN set -eu; \
    install -d /etc/ci-utils /run/ci-utils; \
    ln -s ../ci-utils/bin/ci-utils /opt/ci-tools/bin/ci-utils; \
    ln -s ../ci-utils/bin/ci-utils-list /opt/ci-tools/bin/ci-utils-list; \
    ln -s ../ci-utils/bin/ci-docker-cleanup /opt/ci-tools/bin/ci-docker-cleanup; \
    ln -s ../ci-utils/bin/ci-remove-images /opt/ci-tools/bin/ci-remove-images; \
    ln -s ../ci-utils/bin/ci-upgrade-images /opt/ci-tools/bin/ci-upgrade-images; \
    ln -s ../ci-utils/bin/ci-go-cleanup /opt/ci-tools/bin/ci-go-cleanup; \
    ln -s ../ci-utils/bin/ci-pnpm-cleanup /opt/ci-tools/bin/ci-pnpm-cleanup; \
    ln -s ../ci-utils/ci-buildkit-probe /opt/ci-tools/bin/ci-buildkit-probe; \
    python3 -c 'import json,sys; from pathlib import Path; Path("/opt/ci-tools/ci-utils/build.json").write_text(json.dumps({"revision":sys.argv[1],"version":"sha-"+sys.argv[1]})+"\n")' "${BUILD_REVISION}"; \
    chmod -R go-w /opt/ci-tools/ci-utils

LABEL org.opencontainers.image.created="${BUILD_CREATED}" \
      org.opencontainers.image.description="Shared CI maintenance tools with guarded Docker cleanup" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.source="https://github.com/myflow-xyz/ci-images" \
      org.opencontainers.image.title="MyFlow CI utilities" \
      org.myflow.ci.manifest-sha="${MANIFEST_SHA}" \
      org.myflow.ci.utils-host-protocol="1" \
      org.myflow.ci.utils-image-maintenance="1"

USER ci
WORKDIR /workspace

CMD ["ci-utils"]
