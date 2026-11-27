#!/usr/bin/env bash

# Run on a disposable Linux CI host with Go and Docker.
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
cd "$repo"
work=$(mktemp -d)
minimum="ci-utils-runtime:${work##*/}-minimum"
current="ci-utils-runtime:${work##*/}-current"
cleanup() {
	docker image rm "$minimum" "$current" >/dev/null 2>&1 || true
	rm -rf -- "$work"
}
trap cleanup EXIT
.github/scripts/build-ci-utils-probes.sh "$work"
revision=$(git rev-parse HEAD)
for version in 0.0.31 0.0.32; do
	python3 .github/scripts/package-ci-utils.py "$version" "$revision" "$work" "$work/assets"
done
for target in minimum current; do
	docker buildx build --load --target "$target" -t "ci-utils-runtime:${work##*/}-$target" \
		- <scripts/ci-utils/tests/installation/native-runtime.Dockerfile
done
docker run --rm --network none --user 0 -w /workspace/scripts/ci-utils \
	-v "$repo:/workspace:ro" "$current" python3 -B -m unittest discover -s tests -t .
for runtime in "$minimum" "$current"; do
	docker run --rm --network none --user 1001:2001 \
		-w /workspace/scripts/ci-utils -v "$repo:/workspace:ro" -v "$work/assets:/assets:ro" "$runtime" \
		python3 -B -m tests.installation.user_install_integration /assets 0.0.31 0.0.32
	docker run --rm --network none --user 0 \
		-w /workspace/scripts/ci-utils -v "$repo:/workspace:ro" -v "$work/assets:/assets:ro" "$runtime" \
		python3 -B -m tests.installation.install_integration /assets 0.0.31 0.0.32
	docker run --rm --network none --user 0 \
		-w /workspace/scripts/ci-utils -v "$repo:/workspace:ro" -v "$work/assets:/assets:ro" "$runtime" bash -ec '
			/workspace/scripts/ci-utils/install.sh 0.0.31 --from-dir /assets
			python3 -B -m tests.maintenance.native_api_e2e
		'
done
CI_UTILS_NATIVE_CONTROLLER="$minimum" CI_UTILS_TEST_IMAGE_STORE=classic scripts/ci-utils/tests/maintenance/qualify-docker.sh "$work/assets" 0.0.31
CI_UTILS_NATIVE_CONTROLLER="$current" CI_UTILS_TEST_IMAGE_STORE=containerd scripts/ci-utils/tests/maintenance/qualify-docker.sh "$work/assets" 0.0.31
