#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 1 ]]; then
	printf 'usage: %s <published-images-json>\n' "$0" >&2
	exit 64
fi

published_images=$1
revision=${GITHUB_SHA:?GITHUB_SHA is not set}
event_name=${GITHUB_EVENT_NAME:?GITHUB_EVENT_NAME is not set}
ref_name=${GITHUB_REF_NAME:?GITHUB_REF_NAME is not set}
ref_type=${GITHUB_REF_TYPE:?GITHUB_REF_TYPE is not set}
run_id=${GITHUB_RUN_ID:?GITHUB_RUN_ID is not set}
run_attempt=${GITHUB_RUN_ATTEMPT:?GITHUB_RUN_ATTEMPT is not set}

jq --exit-status '
	type == "array" and
	length == 6 and
	([.[].name] | sort) == [
		"base",
		"go",
		"node",
		"playwright",
		"postgres",
		"vite"
	] and
	([
		.[] |
		(.image | test("^ghcr.io/myflow-xyz/ci-[a-z]+$")) and
		(.digest | test("^sha256:[0-9a-f]{64}$")) and
		(.ref == (.image + "@" + .digest))
	] | all)
' "$published_images" >/dev/null

if [[ ! $revision =~ ^[0-9a-f]{40}$ ||
	! $run_id =~ ^[0-9]+$ ||
	! $run_attempt =~ ^[0-9]+$ ]]; then
	printf 'invalid workflow identity\n' >&2
	exit 1
fi

declare -a aliases

if [[ $event_name == workflow_dispatch ]]; then
	aliases=("run-${run_id}")
elif [[ $ref_type == branch && $ref_name == develop ]]; then
	aliases=(edge)
elif [[ $ref_type == branch && $ref_name == main ]]; then
	aliases=(latest)
else
	printf 'no promotion policy for %s ref %s\n' "$ref_type" "$ref_name" >&2
	exit 1
fi

while IFS=$'\t' read -r image digest reference; do
	candidate_tag="${image}:candidate-${run_id}-${run_attempt}"
	candidate_digest=$(
		docker buildx imagetools inspect \
			"$candidate_tag" \
			--format '{{.Manifest.Digest}}'
	)
	if [[ $candidate_digest != "$digest" ]]; then
		printf \
			'candidate tag changed before promotion: %s (%s != %s)\n' \
			"$candidate_tag" \
			"$candidate_digest" \
			"$digest" \
			>&2
		exit 1
	fi

	immutable_tag="${image}:sha-${revision}"
	if immutable_digest=$(
		docker buildx imagetools inspect \
			"$immutable_tag" \
			--format '{{.Manifest.Digest}}' \
			2>/dev/null
	); then
		if [[ $immutable_digest != "$digest" ]]; then
			printf \
				'immutable tag already identifies another digest: %s\n' \
				"$immutable_tag" \
				>&2
			exit 1
		fi
	fi

	create_arguments=(--tag "$immutable_tag")
	for alias in "${aliases[@]}"; do
		create_arguments+=(--tag "${image}:${alias}")
	done
	docker buildx imagetools create \
		"${create_arguments[@]}" \
		"$reference"

	promoted_digest=$(
		docker buildx imagetools inspect \
			"$immutable_tag" \
			--format '{{.Manifest.Digest}}'
	)
	if [[ $promoted_digest != "$digest" ]]; then
		printf 'immutable tag has unexpected digest: %s\n' \
			"$immutable_tag" >&2
		exit 1
	fi

	for alias in "${aliases[@]}"; do
		promoted_digest=$(
			docker buildx imagetools inspect \
				"${image}:${alias}" \
				--format '{{.Manifest.Digest}}'
		)
		if [[ $promoted_digest != "$digest" ]]; then
			printf \
				'promoted tag has unexpected digest: %s:%s\n' \
				"$image" \
				"$alias" \
				>&2
			exit 1
		fi
	done
done < <(
	jq -r '.[] | [.image, .digest, .ref] | @tsv' "$published_images"
)
