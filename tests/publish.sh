#!/usr/bin/env bash

set -euo pipefail

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
collector="${repository_root}/.github/scripts/collect-published-images.sh"
manifest="${repository_root}/manifests/versions.json"
publisher="${repository_root}/.github/scripts/publish-image.sh"
temporary_directory=$(mktemp -d)
trap 'rm -rf "$temporary_directory"' EXIT

fail() {
	printf 'publication verification failed: %s\n' "$*" >&2
	exit 1
}

output_file="${temporary_directory}/published-images.json"
failure_output="${temporary_directory}/failure.log"
names=(base go node vite playwright postgres)
declare -a records

for index in "${!names[@]}"; do
	name=${names[$index]}
	image="ghcr.io/myflow-xyz/ci-${name}"
	digest=$(printf 'sha256:%064d' "$((index + 1))")
	attempt=$((index < 3 ? 1 : 2))
	records+=(
		"$(jq --compact-output --null-input \
			--arg name "$name" \
			--arg image "$image" \
			--arg digest "$digest" \
			--arg candidate "${image}:candidate-123-${attempt}" \
			'{name: $name, image: $image, digest: $digest,
				ref: ($image + "@" + $digest), candidate: $candidate}')"
	)
done

"$collector" "$output_file" "${records[@]}"
jq --exit-status \
	--argjson expected_names "$(printf '%s\n' "${names[@]}" | jq -R . | jq -s .)" \
	'
		length == 6 and
		[.[].name] == $expected_names and
		([
			.[] |
			.ref == (.image + "@" + .digest) and
			(
				(.image + ":candidate-123-") as $candidate_prefix |
				(.candidate | startswith($candidate_prefix))
			)
		] | all)
	' \
	"$output_file" >/dev/null ||
	fail 'valid image records were not preserved'

if "$collector" \
	"$output_file" \
	"${records[0]}" \
	"${records[1]}" \
	"${records[2]}" \
	"${records[3]}" \
	"${records[4]}" \
	"${records[0]}" \
	>"$failure_output" 2>&1; then
	fail 'duplicate image records were accepted'
fi
grep -q 'suite contract' "$failure_output" ||
	fail 'duplicate image diagnostic'

invalid_record=$(
	jq --compact-output \
		'.ref = "ghcr.io/myflow-xyz/ci-base@sha256:invalid"' \
		<<<"${records[0]}"
)
if "$collector" \
	"$output_file" \
	"$invalid_record" \
	"${records[1]}" \
	"${records[2]}" \
	"${records[3]}" \
	"${records[4]}" \
	"${records[5]}" \
	>"$failure_output" 2>&1; then
	fail 'invalid image reference was accepted'
fi
grep -q 'suite contract' "$failure_output" ||
	fail 'invalid image reference diagnostic'

invalid_record=$(
	jq --compact-output \
		'.candidate = "ghcr.io/myflow-xyz/ci-node:candidate-123-1"' \
		<<<"${records[0]}"
)
if "$collector" \
	"$output_file" \
	"$invalid_record" \
	"${records[1]}" \
	"${records[2]}" \
	"${records[3]}" \
	"${records[4]}" \
	"${records[5]}" \
	>"$failure_output" 2>&1; then
	fail 'candidate for another image was accepted'
fi
grep -q 'suite contract' "$failure_output" ||
	fail 'candidate image diagnostic'

if "$publisher" unknown "$output_file" "" \
	>"$failure_output" 2>&1; then
	fail 'unknown image was accepted'
fi
grep -q 'unsupported image' "$failure_output" ||
	fail 'unknown image diagnostic'

base_digest=$(printf 'sha256:%064d' 1)
if "$publisher" \
	go \
	"$output_file" \
	"ghcr.io/myflow-xyz/ci-node@${base_digest}" \
	>"$failure_output" 2>&1; then
	fail 'wrong parent image was accepted'
fi
grep -q 'invalid parent reference' "$failure_output" ||
	fail 'wrong parent diagnostic'

if "$publisher" \
	base \
	"$output_file" \
	"ghcr.io/myflow-xyz/ci-base@${base_digest}" \
	>"$failure_output" 2>&1; then
	fail 'unexpected parent image was accepted'
fi
grep -q 'does not accept a parent reference' "$failure_output" ||
	fail 'unexpected parent diagnostic'

fake_bin="${temporary_directory}/bin"
fake_log="${temporary_directory}/docker.log"
mkdir -p "$fake_bin"

cat >"${fake_bin}/docker" <<'EOF'
#!/usr/bin/env bash

set -euo pipefail

log=${FAKE_DOCKER_LOG:?}
digest=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

if [[ ${1-} == buildx && ${2-} == build ]]; then
	shift 2
	printf 'build %s\n' "$*" >>"$log"
	metadata_file=
	while (($# > 0)); do
		case "$1" in
		--metadata-file)
			metadata_file=${2:?}
			shift 2
			;;
		*)
			shift
			;;
		esac
	done
	[[ -n $metadata_file ]]
	printf '{"containerimage.digest":"%s"}\n' "$digest" >"$metadata_file"
	exit 0
fi

if [[ ${1-} == buildx && ${2-} == imagetools &&
	${3-} == inspect && ${5-} == --raw ]]; then
	printf 'inspect %s\n' "$*" >>"$log"
	jq --null-input \
		'{
			manifests: [
				{platform: {os: "linux", architecture: "amd64"}},
				{platform: {os: "linux", architecture: "arm64"}},
				{
					platform: {os: "unknown", architecture: "unknown"},
					annotations: {
						"vnd.docker.reference.type": "attestation-manifest"
					}
				},
				{
					platform: {os: "unknown", architecture: "unknown"},
					annotations: {
						"vnd.docker.reference.type": "attestation-manifest"
					}
				}
			]
		}'
	exit 0
fi

printf 'unsupported fake docker invocation: %s\n' "$*" >&2
exit 1
EOF
chmod 0755 "${fake_bin}/docker"

export CI_IMAGES_SBOM_GENERATOR
CI_IMAGES_SBOM_GENERATOR=$(
	printf 'docker.io/docker/buildkit-syft-scanner@sha256:%064d' 0
)
export FAKE_DOCKER_LOG="$fake_log"
export GITHUB_RUN_ATTEMPT=1
export GITHUB_RUN_ID=123
GITHUB_SHA=$(git -C "$repository_root" rev-parse HEAD)
export GITHUB_SHA
export PATH="${fake_bin}:${PATH}"

for name in "${names[@]}"; do
	case "$name" in
	go | node)
		parent="ghcr.io/myflow-xyz/ci-base@${base_digest}"
		;;
	vite)
		parent="ghcr.io/myflow-xyz/ci-node@${base_digest}"
		;;
	playwright)
		parent="ghcr.io/myflow-xyz/ci-vite@${base_digest}"
		;;
	*)
		parent=
		;;
	esac

	: >"$fake_log"
	"$publisher" "$name" "$output_file" "$parent"

	jq --exit-status \
		--arg name "$name" \
		'
			.name == $name and
			.image == ("ghcr.io/myflow-xyz/ci-" + $name) and
			.ref == (.image + "@" + .digest) and
			.candidate == (.image + ":candidate-123-1")
		' \
		"$output_file" >/dev/null ||
		fail "invalid ${name} publication record"
	[[ $(grep -c '^build ' "$fake_log") == 1 ]] ||
		fail "unexpected ${name} build count"
	grep -Fq -- "type=gha,scope=${name}" "$fake_log" ||
		fail "missing ${name} cache scope"
	grep -Fq -- \
		"ghcr.io/myflow-xyz/ci-${name}:candidate-123-1" \
		"$fake_log" ||
		fail "missing ${name} candidate tag"
	if [[ -n $parent ]]; then
		grep -Fq -- "BASE_IMAGE=${parent}" "$fake_log" ||
			fail "missing ${name} parent reference"
	fi
	if [[ $name == vite ]]; then
		for build_arg in \
			"TYPESCRIPT_GO_SOURCE=$(jq -r '.tools.vite.typescript_source.repository' "$manifest")" \
			"TYPESCRIPT_GO_COMMIT=$(jq -r '.tools.vite.typescript_source.commit' "$manifest")" \
			"TYPESCRIPT_X_TEXT_VERSION=$(jq -r '.tools.vite.typescript_source.dependency_overrides["golang.org/x/text"]' "$manifest")"; do
			grep -Fq -- "--build-arg ${build_arg}" "$fake_log" ||
				fail "missing vite build argument: ${build_arg%%=*}"
		done
	fi
done

printf 'publication verification passed\n'
