#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 4 ]]; then
	printf 'usage: %s <image> <output-json> <platform-json> <platform-json>\n' "$0" >&2
	exit 64
fi

name=$1
output_file=$2
shift 2

case "$name" in
base | go | node | playwright | postgres | vite) ;;
*)
	printf 'unsupported image: %s\n' "$name" >&2
	exit 64
	;;
esac

run_id=${GITHUB_RUN_ID:?GITHUB_RUN_ID is not set}
run_attempt=${GITHUB_RUN_ATTEMPT:?GITHUB_RUN_ATTEMPT is not set}
if [[ ! $run_id =~ ^[1-9][0-9]*$ || ! $run_attempt =~ ^[1-9][0-9]*$ ]]; then
	printf 'invalid workflow run identity: %s/%s\n' "$run_id" "$run_attempt" >&2
	exit 1
fi

image="ghcr.io/myflow-xyz/ci-${name}"
records=$(jq --slurp . "$@")
if ! jq --exit-status \
	--arg name "$name" \
	--arg image "$image" \
	--arg run_id "$run_id" \
	'
		length == 2 and
		([.[].platform] | sort) == ["linux/amd64", "linux/arm64"] and
		([
			.[] |
			.name == $name and
			.image == $image and
			(.digest | test("^sha256:[0-9a-f]{64}$")) and
			.ref == ($image + "@" + .digest) and
			(
				($image + ":candidate-" + $run_id + "-") as $prefix |
				(.platform | ltrimstr("linux/")) as $architecture |
				(.candidate | startswith($prefix)) and
				(.candidate | ltrimstr($prefix) |
					test("^[1-9][0-9]*-" + $architecture + "$"))
			)
		] | all)
	' <<<"$records" >/dev/null; then
	printf 'platform records violate the publication contract\n' >&2
	exit 1
fi

references=()
while IFS= read -r reference; do
	references+=("$reference")
done < <(jq --raw-output 'sort_by(.platform)[].ref' <<<"$records")

candidate_tag="${image}:candidate-${run_id}-${run_attempt}"
docker buildx imagetools create --tag "$candidate_tag" "${references[@]}"
digest=$(
	docker buildx imagetools inspect "$candidate_tag" --format '{{.Manifest.Digest}}'
)
if [[ ! $digest =~ ^sha256:[0-9a-f]{64}$ ]]; then
	printf 'invalid merged digest for %s: %s\n' "$name" "$digest" >&2
	exit 1
fi

reference="${image}@${digest}"
index=$(docker buildx imagetools inspect "$reference" --raw)
if ! jq --exit-status '
	[
		.manifests[] | select(.platform.os == "linux")
	] as $images |
	($images | map(.platform.architecture) | sort) == ["amd64", "arm64"] and
	([
		$images[].digest as $digest |
		[
			.manifests[] |
			select(
				.platform.os == "unknown" and
				.platform.architecture == "unknown" and
				.annotations["vnd.docker.reference.type"] == "attestation-manifest" and
				.annotations["vnd.docker.reference.digest"] == $digest
			)
		] | length > 0
	] | all)
' <<<"$index" >/dev/null; then
	printf 'merged index is missing target platforms or their attestations: %s\n' \
		"$reference" >&2
	exit 1
fi

jq --null-input \
	--arg name "$name" \
	--arg image "$image" \
	--arg digest "$digest" \
	--arg ref "$reference" \
	--arg candidate "$candidate_tag" \
	'{name: $name, image: $image, digest: $digest, ref: $ref, candidate: $candidate}' \
	>"$output_file"
