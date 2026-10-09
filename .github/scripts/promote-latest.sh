#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 1 ]]; then
	printf 'usage: %s <released-images-json>\n' "$0" >&2
	exit 64
fi

released_images=$1
revision=${GITHUB_SHA:?GITHUB_SHA is not set}
repository=${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is not set}

if [[ ! $revision =~ ^[0-9a-f]{40}$ ]]; then
	printf 'invalid source revision: %s\n' "$revision" >&2
	exit 1
fi

if ! jq --exit-status --arg revision "$revision" '
	type == "array" and
	length == 7 and
	([.[].name] | sort) == [
		"base", "go", "node", "playwright", "postgres", "utils", "vite"
	] and
	([.[].git_tag] | unique | length) == 1 and
	([
		.[] |
		.image == ("ghcr.io/myflow-xyz/ci-" + .name) and
		(.git_tag | test("^v(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$")) and
		.image_tag == (.git_tag | ltrimstr("v")) and
		(.digest | test("^sha256:[0-9a-f]{64}$")) and
		.revision_ref == (.image + ":sha-" + $revision) and
		.release_ref == (.image + ":" + .image_tag)
	] | all)
' "$released_images" >/dev/null; then
	printf 'released image records violate the latest promotion contract\n' >&2
	exit 1
fi

git_tag=$(jq -r '.[0].git_tag' "$released_images")
latest_release=$(gh api "repos/${repository}/releases/latest")
if ! jq --exit-status --arg git_tag "$git_tag" '
	.tag_name == $git_tag and .draft == false and .prerelease == false
' <<<"$latest_release" >/dev/null; then
	printf 'latest promotion requires the current published stable release: %s\n' \
		"$git_tag" >&2
	exit 1
fi

# Validate the complete suite before moving any discovery tags.
while IFS=$'\t' read -r release_ref digest; do
	release_digest=$(
		docker buildx imagetools inspect \
			"$release_ref" \
			--format '{{.Manifest.Digest}}'
	)
	if [[ $release_digest != "$digest" ]]; then
		printf 'release tag has unexpected digest: %s\n' "$release_ref" >&2
		exit 1
	fi
done < <(jq -r '.[] | [.release_ref, .digest] | @tsv' "$released_images")

while IFS=$'\t' read -r image digest; do
	latest_ref="${image}:latest"
	docker buildx imagetools create \
		--tag "$latest_ref" \
		"${image}@${digest}"

	latest_digest=$(
		docker buildx imagetools inspect \
			"$latest_ref" \
			--format '{{.Manifest.Digest}}'
	)
	if [[ $latest_digest != "$digest" ]]; then
		printf 'latest tag has unexpected digest: %s\n' "$latest_ref" >&2
		exit 1
	fi
done < <(jq -r '.[] | [.image, .digest] | @tsv' "$released_images")
