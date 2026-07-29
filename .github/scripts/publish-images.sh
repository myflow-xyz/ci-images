#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 1 ]]; then
	printf 'usage: %s <output-json>\n' "$0" >&2
	exit 64
fi

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
manifest="${repository_root}/manifests/versions.json"
output_file=$1
revision=${GITHUB_SHA:?GITHUB_SHA is not set}
run_attempt=${GITHUB_RUN_ATTEMPT:?GITHUB_RUN_ATTEMPT is not set}
run_id=${GITHUB_RUN_ID:?GITHUB_RUN_ID is not set}
sbom_generator=${CI_IMAGES_SBOM_GENERATOR:?CI_IMAGES_SBOM_GENERATOR is not set}

if [[ ! $revision =~ ^[0-9a-f]{40}$ ]]; then
	printf 'invalid source revision: %s\n' "$revision" >&2
	exit 1
fi
if [[ ! $run_id =~ ^[0-9]+$ || ! $run_attempt =~ ^[0-9]+$ ]]; then
	printf 'invalid workflow run identity: %s/%s\n' \
		"$run_id" "$run_attempt" >&2
	exit 1
fi
if [[ ! $sbom_generator =~ ^docker\.io/docker/buildkit-syft-scanner@sha256:[0-9a-f]{64}$ ]]; then
	printf 'SBOM generator is not pinned to the expected image: %s\n' \
		"$sbom_generator" >&2
	exit 1
fi

json() {
	jq -r "$1" "$manifest"
}

image_reference() {
	local name=$1
	jq -r \
		--arg name "$name" \
		'.upstream_images[$name] | "\(.reference)@\(.digest)"' \
		"$manifest"
}

sha256_file() {
	if command -v sha256sum >/dev/null 2>&1; then
		sha256sum "$1" | awk '{print $1}'
	else
		shasum -a 256 "$1" | awk '{print $1}'
	fi
}

assert_published_index() {
	local reference=$1
	local raw_index
	local actual_platforms
	local attestation_count

	raw_index=$(docker buildx imagetools inspect "$reference" --raw)
	actual_platforms=$(
		jq -r '
			[
				.manifests[] |
				select(.platform.os == "linux") |
				"\(.platform.os)/\(.platform.architecture)"
			] |
			unique |
			sort |
			join(",")
		' <<<"$raw_index"
	)
	if [[ $actual_platforms != linux/amd64,linux/arm64 ]]; then
		printf \
			'published index has unexpected platforms: %s (%s)\n' \
			"$reference" \
			"$actual_platforms" \
			>&2
		exit 1
	fi

	attestation_count=$(
		jq '
			[
				.manifests[] |
				select(
					.platform.os == "unknown" and
					.platform.architecture == "unknown" and
					.annotations["vnd.docker.reference.type"] ==
						"attestation-manifest"
				)
			] |
			length
		' <<<"$raw_index"
	)
	if ((attestation_count < 2)); then
		printf 'published index has no per-platform attestations: %s\n' \
			"$reference" >&2
		exit 1
	fi
}

temporary_directory=$(mktemp -d)
trap 'rm -rf "$temporary_directory"' EXIT

build_created=$(git -C "$repository_root" show -s --format=%cI "$revision")
manifest_sha=$(sha256_file "$manifest")
platforms=$(json '.platforms | join(",")')
debian_image=$(image_reference debian)
node_image=$(image_reference node)
pgvector_image=$(image_reference pgvector)
declare -a records
base_reference=
node_reference=
vite_reference=

common_build_args=(
	--build-arg "BUILD_CREATED=${build_created}"
	--build-arg "BUILD_REVISION=${revision}"
	--build-arg "MANIFEST_SHA=${manifest_sha}"
)

publish_image() {
	local name=$1
	shift
	local image
	local expected_image
	local candidate_tag
	local metadata_file
	local digest
	local reference
	local record

	image=$(json ".images.${name}.name")
	expected_image="ghcr.io/myflow-xyz/ci-${name}"
	if [[ $image != "$expected_image" ]]; then
		printf 'invalid image name for %s: %s\n' "$name" "$image" >&2
		exit 1
	fi

	candidate_tag="${image}:candidate-${run_id}-${run_attempt}"
	metadata_file="${temporary_directory}/${name}-metadata.json"

	docker buildx build \
		--pull \
		--platform "$platforms" \
		--file "${repository_root}/images/${name}/Dockerfile" \
		--tag "$candidate_tag" \
		--push \
		--metadata-file "$metadata_file" \
		--cache-from "type=gha,scope=${name}" \
		--cache-to "type=gha,mode=max,scope=${name}" \
		--provenance mode=max,version=v1 \
		--attest "type=sbom,generator=${sbom_generator}" \
		"${common_build_args[@]}" \
		"$@" \
		"$repository_root"

	digest=$(jq -r '."containerimage.digest"' "$metadata_file")
	if [[ ! $digest =~ ^sha256:[0-9a-f]{64}$ ]]; then
		printf 'invalid published digest for %s: %s\n' "$name" "$digest" >&2
		exit 1
	fi

	reference="${image}@${digest}"
	assert_published_index "$reference"
	case "$name" in
	base) base_reference=$reference ;;
	node) node_reference=$reference ;;
	vite) vite_reference=$reference ;;
	esac

	record="${temporary_directory}/${name}-reference.json"
	jq -n \
		--arg name "$name" \
		--arg image "$image" \
		--arg digest "$digest" \
		--arg ref "$reference" \
		'{name: $name, image: $image, digest: $digest, ref: $ref}' \
		>"$record"
	records+=("$record")
}

publish_image base \
	--build-arg "BASE_IMAGE=${debian_image}" \
	--build-arg "CI_GID=$(json '.ci_user.gid')" \
	--build-arg "CI_UID=$(json '.ci_user.uid')" \
	--build-arg "DEBIAN_SNAPSHOT=$(json '.debian_snapshot')" \
	--build-arg \
	"ACTIONLINT_VERSION=$(json '.tools.base.actionlint.version')" \
	--build-arg \
	"GITLEAKS_VERSION=$(json '.tools.base.gitleaks.version')" \
	--build-arg \
	"GITLEAKS_X_CRYPTO_VERSION=$(json '.tools.base.gitleaks.dependency_overrides["golang.org/x/crypto"]')" \
	--build-arg \
	"GITLEAKS_XZ_VERSION=$(json '.tools.base.gitleaks.dependency_overrides["github.com/ulikunitz/xz"]')" \
	--build-arg \
	"GO_VERSION=$(json '.tools.go.runtime')" \
	--build-arg \
	"GO_SHA256_AMD64=$(json '.tools.go.assets.amd64.sha256')" \
	--build-arg \
	"GO_SHA256_ARM64=$(json '.tools.go.assets.arm64.sha256')" \
	--build-arg \
	"SHELLSPEC_VERSION=$(json '.tools.base.shellspec.version')" \
	--build-arg \
	"SHELLSPEC_SHA256=$(json '.tools.base.shellspec.asset.sha256')" \
	--build-arg "SHFMT_VERSION=$(json '.tools.base.shfmt.version')" \
	--build-arg "YQ_VERSION=$(json '.tools.base.yq.version')" \
	--build-arg \
	"YQ_X_TEXT_VERSION=$(json '.tools.base.yq.dependency_overrides["golang.org/x/text"]')"

publish_image go \
	--build-arg "BASE_IMAGE=${base_reference}" \
	--build-arg "GO_VERSION=$(json '.tools.go.runtime')" \
	--build-arg \
	"GO_SHA256_AMD64=$(json '.tools.go.assets.amd64.sha256')" \
	--build-arg \
	"GO_SHA256_ARM64=$(json '.tools.go.assets.arm64.sha256')" \
	--build-arg "SQLC_VERSION=$(json '.tools.go.sqlc.version')" \
	--build-arg \
	"SQLC_X_NET_VERSION=$(json '.tools.go.sqlc.dependency_overrides["golang.org/x/net"]')" \
	--build-arg \
	"SQLC_GRPC_VERSION=$(json '.tools.go.sqlc.dependency_overrides["google.golang.org/grpc"]')" \
	--build-arg "GOOSE_VERSION=$(json '.tools.go.goose.version')" \
	--build-arg \
	"GOOSE_X_CRYPTO_VERSION=$(json '.tools.go.goose.dependency_overrides["golang.org/x/crypto"]')" \
	--build-arg \
	"GOOSE_X_NET_VERSION=$(json '.tools.go.goose.dependency_overrides["golang.org/x/net"]')" \
	--build-arg \
	"GOOSE_GRPC_VERSION=$(json '.tools.go.goose.dependency_overrides["google.golang.org/grpc"]')" \
	--build-arg \
	"GOLANGCI_LINT_VERSION=$(json '.tools.go.golangci_lint.version')" \
	--build-arg \
	"GOLANGCI_LINT_X_TEXT_VERSION=$(json '.tools.go.golangci_lint.dependency_overrides["golang.org/x/text"]')" \
	--build-arg \
	"GOIMPORTS_VERSION=$(json '.tools.go.goimports.version')" \
	--build-arg \
	"GOVULNCHECK_VERSION=$(json '.tools.go.govulncheck.version')"

publish_image node \
	--build-arg "BASE_IMAGE=${base_reference}" \
	--build-arg "NODE_IMAGE=${node_image}" \
	--build-arg \
	"MARKDOWNLINT_CLI2_VERSION=$(json '.tools.node.markdownlint_cli2.version')" \
	--build-arg \
	"NODE_TOOLS_BUNDLE_VERSION=$(json '.tools.node.bundle_version')" \
	--build-arg "NODE_VERSION=$(json '.tools.node.runtime')" \
	--build-arg \
	"NPM_VERSION=$(json '.tools.node.npm.version')" \
	--build-arg \
	"NPM_BRACE_EXPANSION_VERSION=$(json '.tools.node.npm.dependency_replacements["brace-expansion"]')" \
	--build-arg \
	"NPM_TAR_VERSION=$(json '.tools.node.npm.dependency_replacements.tar')" \
	--build-arg "PNPM_VERSION=$(json '.tools.node.pnpm')" \
	--build-arg "REDOCLY_VERSION=$(json '.tools.node.redocly')"

publish_image vite \
	--build-arg "BASE_IMAGE=${node_reference}" \
	--build-arg "GO_VERSION=$(json '.tools.go.runtime')" \
	--build-arg \
	"GO_SHA256_AMD64=$(json '.tools.go.assets.amd64.sha256')" \
	--build-arg \
	"GO_SHA256_ARM64=$(json '.tools.go.assets.arm64.sha256')" \
	--build-arg \
	"VITE_TOOLS_BUNDLE_VERSION=$(json '.tools.vite.bundle_version')" \
	--build-arg \
	"TYPESCRIPT_VERSION=$(json '.tools.vite.typescript')" \
	--build-arg "VITE_VERSION=$(json '.tools.vite.vite')" \
	--build-arg "VITEST_VERSION=$(json '.tools.vite.vitest')" \
	--build-arg "OXLINT_VERSION=$(json '.tools.vite.oxlint')" \
	--build-arg \
	"OXLINT_TSGOLINT_VERSION=$(json '.tools.vite.oxlint_tsgolint')" \
	--build-arg \
	"OXLINT_TSGOLINT_SOURCE=$(json '.tools.vite.oxlint_tsgolint_source.repository')" \
	--build-arg \
	"OXLINT_TSGOLINT_COMMIT=$(json '.tools.vite.oxlint_tsgolint_source.commit')" \
	--build-arg \
	"OXLINT_TSGOLINT_X_TEXT_VERSION=$(json '.tools.vite.oxlint_tsgolint_source.dependency_overrides["golang.org/x/text"]')" \
	--build-arg \
	"TYPESCRIPT_GO_COMMIT=$(json '.tools.vite.oxlint_tsgolint_source.typescript_go_commit')" \
	--build-arg "OXFMT_VERSION=$(json '.tools.vite.oxfmt')"

publish_image playwright \
	--build-arg "BASE_IMAGE=${vite_reference}" \
	--build-arg \
	"PLAYWRIGHT_VERSION=$(json '.tools.playwright.version')"

publish_image postgres \
	--build-arg "PGVECTOR_IMAGE=${pgvector_image}" \
	--build-arg "DEBIAN_SNAPSHOT=$(json '.debian_snapshot')" \
	--build-arg "GO_VERSION=$(json '.tools.go.runtime')" \
	--build-arg \
	"GO_SHA256_AMD64=$(json '.tools.go.assets.amd64.sha256')" \
	--build-arg \
	"GO_SHA256_ARM64=$(json '.tools.go.assets.arm64.sha256')" \
	--build-arg \
	"GOSU_VERSION=$(json '.tools.postgres.gosu.version')" \
	--build-arg \
	"GOSU_COMMIT=$(json '.tools.postgres.gosu.commit')" \
	--build-arg \
	"PGVECTOR_VERSION=$(json '.tools.postgres.pgvector')" \
	--build-arg \
	"POSTGRES_VERSION=$(json '.tools.postgres.postgres')"

jq -s '.' "${records[@]}" >"$output_file"
