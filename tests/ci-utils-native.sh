#!/usr/bin/env bash

# Run on a disposable Linux CI host with Go and Docker.
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo"
work=$(mktemp -d)
minimum="ci-utils-runtime:${work##*/}"
cleanup() {
	docker image rm "$minimum" >/dev/null 2>&1 || true
	rm -rf -- "$work"
}
trap cleanup EXIT
(
	cd scripts/ci-utils/buildkit-probe
	go test -race -mod=readonly ./...
	for arch in amd64 arm64; do
		CGO_ENABLED=0 GOOS=linux GOARCH=$arch go build -mod=readonly -buildvcs=false -trimpath \
			-ldflags '-s -w' -o "$work/probe-$arch" .
	done
)
revision=$(git rev-parse HEAD)
for version in 0.0.31 0.0.32; do
	python3 .github/scripts/package-ci-utils.py "$version" "$revision" "$work" "$work/assets"
done
docker buildx build --load -t "$minimum" - <tests/utils/native-runtime.Dockerfile
current=${CI_UTILS_NATIVE_CONTROLLER:-ci-base:test}
for runtime in "$minimum" "$current"; do
	docker run --rm --network none --user 1001:2001 \
		-v "$repo:/workspace:ro" -v "$work/assets:/assets:ro" "$runtime" \
		python3 -B /workspace/scripts/tests/ci-utils/user_install_integration.py /assets 0.0.31 0.0.32
	docker run --rm --network none --user 0 \
		-v "$repo:/workspace:ro" -v "$work/assets:/assets:ro" "$runtime" \
		python3 -B /workspace/scripts/tests/ci-utils/install_integration.py /assets 0.0.31 0.0.32
	docker run --rm --network none --user 0 \
		-v "$repo:/workspace:ro" -v "$work/assets:/assets:ro" "$runtime" bash -ec '
			/workspace/scripts/ci-utils/install.sh 0.0.31 --from-dir /assets
			python3 -B /workspace/tests/utils/native_api_e2e.py
		'
	CI_UTILS_NATIVE_CONTROLLER="$runtime" tests/utils-docker.sh --native "$work/assets" 0.0.31
done
