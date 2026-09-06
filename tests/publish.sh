#!/usr/bin/env bash

set -euo pipefail

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
collector="${repository_root}/.github/scripts/collect-published-images.sh"
manifest="${repository_root}/manifests/versions.json"
publisher="${repository_root}/.github/scripts/publish-image.sh"
merger="${repository_root}/.github/scripts/merge-image.sh"
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
if [[ ${CI_IMAGES_PLATFORM:-} == linux/arm64 ]]; then
	digest=sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd
fi

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
		--arg platforms "${FAKE_INDEX_PLATFORMS:-$CI_IMAGES_PLATFORM}" \
		--arg fault "${FAKE_INDEX_FAULT:-}" \
		'
			$platforms | split(",") | map(ltrimstr("linux/")) |
			map(. as $arch |
				("sha256:" + (if . == "amd64" then "b" else "c" end) * 64) as $digest |
				[
					{platform: {os: "linux", architecture: $arch}, digest: $digest},
					{
						platform: {os: "unknown", architecture: "unknown"},
						annotations: {
							"vnd.docker.reference.type": "attestation-manifest",
							"vnd.docker.reference.digest": $digest
						}
					}
				]
			) | add |
			if $fault == "missing-attestation" then
				map(select(.platform.os != "unknown"))
			elif $fault == "wrong-attestation" then
				map(if .platform.os == "unknown" then
					.annotations["vnd.docker.reference.digest"] = "sha256:wrong"
				else . end)
			else . end |
			{manifests: .}
		'
	exit 0
fi

if [[ ${1-} == buildx && ${2-} == imagetools && ${3-} == create ]]; then
	printf 'create %s\n' "$*" >>"$log"
	exit 0
fi

if [[ ${1-} == buildx && ${2-} == imagetools &&
	${3-} == inspect && ${5-} == --format ]]; then
	printf '%s\n' "$digest"
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

for target in "${names[@]/%/-amd64}" "${names[@]/%/-arm64}"; do
	name=${target%-*}
	architecture=${target##*-}
	platform="linux/${architecture}"
	export CI_IMAGES_PLATFORM="$platform"
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
		--arg platform "$platform" \
		--arg architecture "$architecture" \
		'
		.name == $name and
		.image == ("ghcr.io/myflow-xyz/ci-" + $name) and
		.ref == (.image + "@" + .digest) and
		.candidate == (.image + ":candidate-123-1-" + $architecture) and
		.platform == $platform
	' \
		"$output_file" >/dev/null ||
		fail "invalid ${name} publication record"
	[[ $(grep -c '^build ' "$fake_log") == 1 ]] ||
		fail "unexpected ${name} build count"
	grep -Fq -- "type=gha,scope=${name}-${architecture}" "$fake_log" ||
		fail "missing ${name} cache scope"
	grep -Fq -- "--platform ${platform} " "$fake_log" ||
		fail "incorrect ${name} build platform"
	grep -Fq -- \
		"ghcr.io/myflow-xyz/ci-${name}:candidate-123-1-${architecture}" \
		"$fake_log" ||
		fail "missing ${name} candidate tag"
	if [[ -n $parent ]]; then
		grep -Fq -- "BASE_IMAGE=${parent}" "$fake_log" ||
			fail "missing ${name} parent reference"
	fi
	if [[ $name == base ]]; then
		cp "$output_file" "${temporary_directory}/base-${architecture}.json"
		for build_arg in \
			"OSV_SCANNER_VERSION=$(jq -r '.tools.base.osv_scanner.version' "$manifest")" \
			"OSV_SCANNER_GRPC_VERSION=$(jq -r '.tools.base.osv_scanner.dependency_overrides["google.golang.org/grpc"]' "$manifest")" \
			"OSV_SCANNER_X_MOD_VERSION=$(jq -r '.tools.base.osv_scanner.dependency_overrides["golang.org/x/mod"]' "$manifest")" \
			"PYTHON_VERSION=$(jq -r '.tools.base.python.version' "$manifest")" \
			"PYTHON_IMAGE=$(jq -r '.upstream_images.python | .reference + "@" + .digest' "$manifest")" \
			"TRIVY_VERSION=$(jq -r '.tools.base.trivy.version' "$manifest")" \
			"TRIVY_GO_VERSION=$(jq -r '.tools.base.trivy.build_go.version' "$manifest")" \
			"TRIVY_GO_SHA256_AMD64=$(jq -r '.tools.base.trivy.build_go.assets.amd64.sha256' "$manifest")" \
			"TRIVY_GO_SHA256_ARM64=$(jq -r '.tools.base.trivy.build_go.assets.arm64.sha256' "$manifest")" \
			"TRIVY_GRPC_VERSION=$(jq -r '.tools.base.trivy.dependency_overrides["google.golang.org/grpc"]' "$manifest")"; do
			grep -Fq -- "--build-arg ${build_arg}" "$fake_log" ||
				fail "missing base build argument: ${build_arg%%=*}"
		done
	fi
	if [[ $name == go ]]; then
		for build_arg in \
			"GOOSE_MODERNC_LIBC_VERSION=$(jq -r '.tools.go.goose.dependency_overrides["modernc.org/libc"]' "$manifest")" \
			"GOIMPORTS_X_MOD_VERSION=$(jq -r '.tools.go.goimports.dependency_overrides["golang.org/x/mod"]' "$manifest")" \
			"GOVULNCHECK_X_MOD_VERSION=$(jq -r '.tools.go.govulncheck.dependency_overrides["golang.org/x/mod"]' "$manifest")"; do
			grep -Fq -- "--build-arg ${build_arg}" "$fake_log" ||
				fail "missing go build argument: ${build_arg%%=*}"
		done
	fi
	if [[ $name == node ]]; then
		for build_arg in \
			"PNPM_ASSET_URL_AMD64=$(jq -r '.tools.node.pnpm.assets.amd64.url' "$manifest")" \
			"PNPM_ASSET_URL_ARM64=$(jq -r '.tools.node.pnpm.assets.arm64.url' "$manifest")" \
			"PNPM_SHA256_AMD64=$(jq -r '.tools.node.pnpm.assets.amd64.sha256' "$manifest")" \
			"PNPM_SHA256_ARM64=$(jq -r '.tools.node.pnpm.assets.arm64.sha256' "$manifest")" \
			"PNPM_VERSION=$(jq -r '.tools.node.pnpm.version' "$manifest")"; do
			grep -Fq -- "--build-arg ${build_arg}" "$fake_log" ||
				fail "missing node build argument: ${build_arg%%=*}"
		done
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

if CI_IMAGES_PLATFORM=linux/ppc64le "$publisher" base "$output_file" "" \
	>"$failure_output" 2>&1; then
	fail 'unsupported publication platform was accepted'
fi
grep -q 'unsupported publication platform' "$failure_output" ||
	fail 'unsupported platform diagnostic'

amd64_record="${temporary_directory}/base-amd64.json"
arm64_record="${temporary_directory}/base-arm64.json"
export FAKE_INDEX_PLATFORMS=linux/amd64,linux/arm64

# Successful platform jobs from an earlier attempt remain valid on retry.
jq '.candidate = "ghcr.io/myflow-xyz/ci-base:candidate-123-2-arm64"' \
	"$arm64_record" >"${temporary_directory}/retry.json"
mv "${temporary_directory}/retry.json" "$arm64_record"

: >"$fake_log"
"$merger" base "$output_file" "$arm64_record" "$amd64_record"
jq --exit-status '
	.name == "base" and
	.ref == (.image + "@" + .digest) and
	.candidate == (.image + ":candidate-123-1") and
	(has("platform") | not)
' "$output_file" >/dev/null || fail 'invalid merged publication record'
grep -Fq -- "$(jq -r .ref "$amd64_record")" "$fake_log" ||
	fail 'merge did not use immutable platform references'
grep -Fq -- "$(jq -r .ref "$arm64_record")" "$fake_log" ||
	fail 'merge omitted the ARM64 platform reference'

for fault in duplicate wrong-image wrong-run wrong-digest wrong-architecture; do
	case "$fault" in
	duplicate) filter='.platform = "linux/amd64"' ;;
	wrong-image) filter='.image = "ghcr.io/myflow-xyz/ci-node"' ;;
	wrong-run) filter='.candidate = "ghcr.io/myflow-xyz/ci-base:candidate-999-1-arm64"' ;;
	wrong-digest) filter='.digest = "sha256:invalid"' ;;
	wrong-architecture) filter='.candidate = "ghcr.io/myflow-xyz/ci-base:candidate-123-1-amd64"' ;;
	esac
	jq "$filter" "$arm64_record" >"${temporary_directory}/invalid.json"
	: >"$fake_log"
	if "$merger" base "$output_file" "$amd64_record" "${temporary_directory}/invalid.json" \
		>"$failure_output" 2>&1; then
		fail "invalid platform record was accepted: ${fault}"
	fi
	grep -q 'platform records violate' "$failure_output" ||
		fail "invalid platform record diagnostic: ${fault}"
	[[ ! -s $fake_log ]] || fail 'invalid platform records reached the registry'
done

for fault in missing-attestation wrong-attestation missing-platform; do
	export FAKE_INDEX_FAULT="$fault"
	if [[ $fault == missing-platform ]]; then
		export FAKE_INDEX_PLATFORMS=linux/amd64
	fi
	if "$merger" base "$output_file" "$amd64_record" "$arm64_record" \
		>"$failure_output" 2>&1; then
		fail "invalid merged index was accepted: ${fault}"
	fi
	grep -q 'missing target platforms or their attestations' "$failure_output" ||
		fail "invalid merged index diagnostic: ${fault}"
done

printf 'publication verification passed\n'
