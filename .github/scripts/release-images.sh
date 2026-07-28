#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 2 ]]; then
	printf 'usage: %s <version> <output-json>\n' "$0" >&2
	exit 64
fi

version=$1
output_file=$2
revision=${GITHUB_SHA:?GITHUB_SHA is not set}
repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
manifest="${repository_root}/manifests/versions.json"

if [[ ! $version =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
	printf 'stable release version is not supported: %s\n' "$version" >&2
	exit 64
fi
if [[ ! $revision =~ ^[0-9a-f]{40}$ ]]; then
	printf 'invalid source revision: %s\n' "$revision" >&2
	exit 1
fi
if [[ ! -d $(dirname "$output_file") ]]; then
	printf 'output directory does not exist: %s\n' "$(dirname "$output_file")" >&2
	exit 1
fi

jq --exit-status '
	(.images | keys | sort) == [
		"base",
		"go",
		"node",
		"playwright",
		"postgres",
		"vite"
	] and
	([.images[].name] | sort) == [
		"ghcr.io/myflow-xyz/ci-base",
		"ghcr.io/myflow-xyz/ci-go",
		"ghcr.io/myflow-xyz/ci-node",
		"ghcr.io/myflow-xyz/ci-playwright",
		"ghcr.io/myflow-xyz/ci-postgres",
		"ghcr.io/myflow-xyz/ci-vite"
	]
' "$manifest" >/dev/null

temporary_directory=$(mktemp -d)
trap 'rm -rf "$temporary_directory"' EXIT

inspect_digest() {
	local reference=$1

	docker buildx imagetools inspect \
		"$reference" \
		--format '{{.Manifest.Digest}}'
}

inspect_optional_digest() {
	local reference=$1
	local error_file=$2
	local digest

	if digest=$(inspect_digest "$reference" 2>"$error_file"); then
		printf '%s\n' "$digest"
		return 0
	fi
	if grep -Eiq \
		'manifest unknown|name unknown|404[[:space:]]+not found|ghcr\.io/myflow-xyz/ci-[a-z]+:v[0-9]+\.[0-9]+\.[0-9]+: not found' \
		"$error_file"; then
		return 1
	fi

	printf 'unable to determine whether release tag exists: %s\n' \
		"$reference" >&2
	command cat "$error_file" >&2
	return 2
}

assert_digest() {
	local digest=$1
	local reference=$2

	if [[ ! $digest =~ ^sha256:[0-9a-f]{64}$ ]]; then
		printf 'registry returned an invalid digest for %s: %s\n' \
			"$reference" "$digest" >&2
		exit 1
	fi
}

while IFS=$'\t' read -r name image; do
	revision_ref="${image}:sha-${revision}"
	latest_ref="${image}:latest"
	release_ref="${image}:${version}"

	if ! revision_digest=$(inspect_digest "$revision_ref"); then
		printf 'immutable revision tag is unavailable: %s\n' \
			"$revision_ref" >&2
		exit 1
	fi
	assert_digest "$revision_digest" "$revision_ref"

	if ! latest_digest=$(inspect_digest "$latest_ref"); then
		printf 'latest tag is unavailable: %s\n' "$latest_ref" >&2
		exit 1
	fi
	assert_digest "$latest_digest" "$latest_ref"

	if [[ $latest_digest != "$revision_digest" ]]; then
		printf \
			'latest does not identify the selected revision: %s (%s != %s)\n' \
			"$image" \
			"$latest_digest" \
			"$revision_digest" \
			>&2
		exit 1
	fi

	version_digest=
	if version_digest=$(
		inspect_optional_digest \
			"$release_ref" \
			"${temporary_directory}/${name}-inspect.err"
	); then
		version_status=0
	else
		version_status=$?
	fi

	case "$version_status" in
	0)
		assert_digest "$version_digest" "$release_ref"
		if [[ $version_digest != "$revision_digest" ]]; then
			printf \
				'stable tag already identifies another digest: %s\n' \
				"$release_ref" \
				>&2
			exit 1
		fi
		needs_promotion=false
		;;
	1)
		needs_promotion=true
		;;
	*)
		exit "$version_status"
		;;
	esac

	jq -n \
		--arg name "$name" \
		--arg image "$image" \
		--arg version "$version" \
		--arg digest "$revision_digest" \
		--arg revision_ref "$revision_ref" \
		--arg release_ref "$release_ref" \
		--argjson needs_promotion "$needs_promotion" \
		'{
			name: $name,
			image: $image,
			version: $version,
			digest: $digest,
			revision_ref: $revision_ref,
			release_ref: $release_ref,
			needs_promotion: $needs_promotion
		}' \
		>"${temporary_directory}/${name}.json"
done < <(
	jq -r '
		.images |
		to_entries |
		sort_by(.key) |
		.[] |
		[.key, .value.name] |
		@tsv
	' "$manifest"
)

for record in "${temporary_directory}"/*.json; do
	image=$(jq -r '.image' "$record")
	digest=$(jq -r '.digest' "$record")
	release_ref=$(jq -r '.release_ref' "$record")
	needs_promotion=$(jq -r '.needs_promotion' "$record")

	if [[ $needs_promotion == true ]]; then
		docker buildx imagetools create \
			--tag "$release_ref" \
			"${image}@${digest}"
	fi

	promoted_digest=$(inspect_digest "$release_ref")
	assert_digest "$promoted_digest" "$release_ref"
	if [[ $promoted_digest != "$digest" ]]; then
		printf 'release tag has unexpected digest: %s\n' \
			"$release_ref" >&2
		exit 1
	fi
done

jq -s 'map(del(.needs_promotion))' \
	"${temporary_directory}"/*.json \
	>"$output_file"
