#!/usr/bin/env bash

set -euo pipefail

target=${1:-all}

case "$target" in
all | base | go | node | vite | playwright | postgres) ;;
*)
	printf \
		'usage: %s [all|base|go|node|vite|playwright|postgres]\n' \
		"$0" \
		>&2
	exit 64
	;;
esac

if ! command -v trivy >/dev/null 2>&1; then
	printf 'local image scan requires trivy in PATH\n' >&2
	exit 127
fi

scan_image() {
	local name=$1
	local image="ci-${name}:test"

	printf 'Scanning %s\n' "$image"
	trivy image \
		--image-src docker \
		--scanners vuln \
		--pkg-types os,library \
		--severity HIGH,CRITICAL \
		--ignore-unfixed \
		--exit-code 1 \
		--format table \
		--timeout 20m \
		"$image"
}

names=(base go node vite playwright postgres)
scan_status=0

for name in "${names[@]}"; do
	if [[ $target != all && $target != "$name" ]]; then
		continue
	fi
	if ! scan_image "$name"; then
		scan_status=1
	fi
done

exit "$scan_status"
