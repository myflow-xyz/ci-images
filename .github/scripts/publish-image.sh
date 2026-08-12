#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 3 ]]; then
	printf 'usage: %s <image> <output-json> <parent-reference>\n' "$0" >&2
	exit 64
fi

name=$1
output_file=$2
parent_reference=$3

case "$name" in
base | go | node | playwright | postgres | vite) ;;
*)
	printf 'unsupported image: %s\n' "$name" >&2
	exit 64
	;;
esac

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
manifest="${repository_root}/manifests/versions.json"

json() {
	jq -r "$1" "$manifest"
}

image_reference() {
	local image=$1
	jq -r \
		--arg image "$image" \
		'.upstream_images[$image] | "\(.reference)@\(.digest)"' \
		"$manifest"
}

sha256_file() {
	if command -v sha256sum >/dev/null 2>&1; then
		sha256sum "$1" | awk '{print $1}'
	else
		shasum -a 256 "$1" | awk '{print $1}'
	fi
}

expected_parent=
case "$name" in
go | node) expected_parent=base ;;
vite) expected_parent=node ;;
playwright) expected_parent=vite ;;
esac

if [[ -n $expected_parent ]]; then
	expected_parent_image=$(json ".images.${expected_parent}.name")
	parent_digest=${parent_reference##*@}
	if [[ ! $parent_digest =~ ^sha256:[0-9a-f]{64}$ ||
		$parent_reference != "${expected_parent_image}@${parent_digest}" ]]; then
		printf 'invalid parent reference for %s: %s\n' \
			"$name" \
			"$parent_reference" \
			>&2
		exit 1
	fi
elif [[ -n $parent_reference ]]; then
	printf 'image %s does not accept a parent reference\n' "$name" >&2
	exit 1
fi

revision=${GITHUB_SHA:?GITHUB_SHA is not set}
run_attempt=${GITHUB_RUN_ATTEMPT:?GITHUB_RUN_ATTEMPT is not set}
run_id=${GITHUB_RUN_ID:?GITHUB_RUN_ID is not set}
sbom_generator=${CI_IMAGES_SBOM_GENERATOR:?CI_IMAGES_SBOM_GENERATOR is not set}

if [[ ! $revision =~ ^[0-9a-f]{40}$ ]]; then
	printf 'invalid source revision: %s\n' "$revision" >&2
	exit 1
fi
if [[ ! $run_id =~ ^[1-9][0-9]*$ ||
	! $run_attempt =~ ^[1-9][0-9]*$ ]]; then
	printf 'invalid workflow run identity: %s/%s\n' \
		"$run_id" "$run_attempt" >&2
	exit 1
fi
if [[ ! $sbom_generator =~ ^docker\.io/docker/buildkit-syft-scanner@sha256:[0-9a-f]{64}$ ]]; then
	printf 'SBOM generator is not pinned to the expected image: %s\n' \
		"$sbom_generator" >&2
	exit 1
fi

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
candidate_image=$(json ".images.${name}.name")
expected_image="ghcr.io/myflow-xyz/ci-${name}"

if [[ $candidate_image != "$expected_image" ]]; then
	printf 'invalid image name for %s: %s\n' "$name" "$candidate_image" >&2
	exit 1
fi

candidate_tag="${candidate_image}:candidate-${run_id}-${run_attempt}"
metadata_file="${temporary_directory}/${name}-metadata.json"
common_build_args=(
	--build-arg "BUILD_CREATED=${build_created}"
	--build-arg "BUILD_REVISION=${revision}"
	--build-arg "MANIFEST_SHA=${manifest_sha}"
)

publish_image() {
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
}

case "$name" in
base)
	debian_image=$(image_reference debian)
	publish_image \
		--build-arg "BASE_IMAGE=${debian_image}" \
		--build-arg "CI_GID=$(json '.ci_user.gid')" \
		--build-arg "CI_UID=$(json '.ci_user.uid')" \
		--build-arg "DEBIAN_SNAPSHOT=$(json '.debian_snapshot')" \
		--build-arg \
		"ACTIONLINT_VERSION=$(json '.tools.base.actionlint.version')" \
		--build-arg \
		"GIT_VERSION=$(json '.tools.base.git.version')" \
		--build-arg \
		"GIT_SHA256=$(json '.tools.base.git.asset.sha256')" \
		--build-arg \
		"GITLEAKS_VERSION=$(json '.tools.base.gitleaks.version')" \
		--build-arg \
		"GITLEAKS_X_CRYPTO_VERSION=$(json '.tools.base.gitleaks.dependency_overrides["golang.org/x/crypto"]')" \
		--build-arg \
		"GITLEAKS_XZ_VERSION=$(json '.tools.base.gitleaks.dependency_overrides["github.com/ulikunitz/xz"]')" \
		--build-arg \
		"PYTHON_VERSION=$(json '.tools.base.python.version')" \
		--build-arg \
		"PYTHON_SHA256=$(json '.tools.base.python.asset.sha256')" \
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
	;;
go)
	publish_image \
		--build-arg "BASE_IMAGE=${parent_reference}" \
		--build-arg "GO_VERSION=$(json '.tools.go.runtime')" \
		--build-arg \
		"GO_SHA256_AMD64=$(json '.tools.go.assets.amd64.sha256')" \
		--build-arg \
		"GO_SHA256_ARM64=$(json '.tools.go.assets.arm64.sha256')" \
		--build-arg "HURL_VERSION=$(json '.tools.go.hurl.version')" \
		--build-arg \
		"HURL_SHA256_AMD64=$(json '.tools.go.hurl.assets.amd64.sha256')" \
		--build-arg \
		"HURL_SHA256_ARM64=$(json '.tools.go.hurl.assets.arm64.sha256')" \
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
	;;
node)
	node_image=$(image_reference node)
	publish_image \
		--build-arg "BASE_IMAGE=${parent_reference}" \
		--build-arg "NODE_IMAGE=${node_image}" \
		--build-arg \
		"MARKDOWNLINT_CLI2_VERSION=$(json '.tools.node.markdownlint_cli2.version')" \
		--build-arg \
		"NODE_TOOLS_BUNDLE_VERSION=$(json '.tools.node.bundle_version')" \
		--build-arg "NODE_VERSION=$(json '.tools.node.runtime')" \
		--build-arg \
		"NPM_VERSION=$(json '.tools.node.npm.version')" \
		--build-arg \
		"NPM_ASSET_URL=$(json '.tools.node.npm.asset.url')" \
		--build-arg \
		"NPM_BRACE_EXPANSION_VERSION=$(json '.tools.node.npm.dependency_replacements["brace-expansion"]')" \
		--build-arg \
		"NPM_SHA256=$(json '.tools.node.npm.asset.sha256')" \
		--build-arg \
		"NPM_TAR_VERSION=$(json '.tools.node.npm.dependency_replacements.tar')" \
		--build-arg "PNPM_VERSION=$(json '.tools.node.pnpm')" \
		--build-arg "REDOCLY_VERSION=$(json '.tools.node.redocly')"
	;;
vite)
	publish_image \
		--build-arg "BASE_IMAGE=${parent_reference}" \
		--build-arg "GO_VERSION=$(json '.tools.go.runtime')" \
		--build-arg \
		"GO_SHA256_AMD64=$(json '.tools.go.assets.amd64.sha256')" \
		--build-arg \
		"GO_SHA256_ARM64=$(json '.tools.go.assets.arm64.sha256')" \
		--build-arg \
		"VITE_TOOLS_BUNDLE_VERSION=$(json '.tools.vite.bundle_version')" \
		--build-arg \
		"TYPESCRIPT_VERSION=$(json '.tools.vite.typescript')" \
		--build-arg \
		"TYPESCRIPT_GO_SOURCE=$(json '.tools.vite.typescript_source.repository')" \
		--build-arg \
		"TYPESCRIPT_GO_COMMIT=$(json '.tools.vite.typescript_source.commit')" \
		--build-arg \
		"TYPESCRIPT_X_TEXT_VERSION=$(json '.tools.vite.typescript_source.dependency_overrides["golang.org/x/text"]')" \
		--build-arg \
		"TYPESCRIPT_LEGACY_COMPAT_PACKAGE_VERSION=$(json '.tools.vite.typescript_legacy.compat_package')" \
		--build-arg \
		"TYPESCRIPT_LEGACY_COMPILER_VERSION=$(json '.tools.vite.typescript_legacy.compiler')" \
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
		--build-arg "OXFMT_VERSION=$(json '.tools.vite.oxfmt')"
	;;
playwright)
	publish_image \
		--build-arg "BASE_IMAGE=${parent_reference}" \
		--build-arg \
		"PLAYWRIGHT_VERSION=$(json '.tools.playwright.version')"
	;;
postgres)
	pgvector_image=$(image_reference pgvector)
	publish_image \
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
	;;
esac

digest=$(jq -r '."containerimage.digest"' "$metadata_file")
if [[ ! $digest =~ ^sha256:[0-9a-f]{64}$ ]]; then
	printf 'invalid published digest for %s: %s\n' "$name" "$digest" >&2
	exit 1
fi

reference="${candidate_image}@${digest}"
assert_published_index "$reference"

jq -n \
	--arg name "$name" \
	--arg image "$candidate_image" \
	--arg digest "$digest" \
	--arg ref "$reference" \
	--arg candidate "$candidate_tag" \
	'{
		name: $name,
		image: $image,
		digest: $digest,
		ref: $ref,
		candidate: $candidate
	}' \
	>"$output_file"
