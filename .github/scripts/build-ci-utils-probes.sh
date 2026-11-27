#!/usr/bin/env bash

set -euo pipefail
output=$(cd "${1:?probe output directory is required}" && pwd)
cd "$(dirname "${BASH_SOURCE[0]}")/../../scripts/ci-utils/lib/maintenance/buildkit-probe"

go test -race -mod=readonly ./...
for arch in amd64 arm64; do
	CGO_ENABLED=0 GOOS=linux GOARCH=$arch go build -mod=readonly -buildvcs=false -trimpath \
		-ldflags '-s -w' -o "$output/probe-$arch" .
done
