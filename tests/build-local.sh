#!/usr/bin/env bash

set -euo pipefail

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
manifest="${repository_root}/manifests/versions.json"
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

build_created=$(git -C "$repository_root" show -s --format=%cI HEAD)
build_revision=$(git -C "$repository_root" rev-parse HEAD)
manifest_sha=$(sha256_file "$manifest")
debian_image=$(image_reference debian)
node_image=$(image_reference node)
pgvector_image=$(image_reference pgvector)

common_labels=(
	--build-arg "BUILD_CREATED=${build_created}"
	--build-arg "BUILD_REVISION=${build_revision}"
	--build-arg "MANIFEST_SHA=${manifest_sha}"
)

build_image() {
	local dockerfile=$1
	shift

	if [[ ${CI_IMAGES_BUILTIN_FRONTEND:-0} == 1 ]]; then
		tail -n +2 "$dockerfile" |
			docker buildx build --file - "$@"
	else
		docker buildx build --file "$dockerfile" "$@"
	fi
}

build_base() {
	build_image "${repository_root}/images/base/Dockerfile" \
		--load \
		--tag ci-base:test \
		"${common_labels[@]}" \
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
		"YQ_X_TEXT_VERSION=$(json '.tools.base.yq.dependency_overrides["golang.org/x/text"]')" \
		"$repository_root"
}

build_go() {
	build_image "${repository_root}/images/go/Dockerfile" \
		--load \
		--tag ci-go:test \
		"${common_labels[@]}" \
		--build-arg BASE_IMAGE=ci-base:test \
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
		"GOVULNCHECK_VERSION=$(json '.tools.go.govulncheck.version')" \
		"$repository_root"
}

build_node() {
	build_image "${repository_root}/images/node/Dockerfile" \
		--load \
		--tag ci-node:test \
		"${common_labels[@]}" \
		--build-arg BASE_IMAGE=ci-base:test \
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
		"NPM_IP_ADDRESS_VERSION=$(json '.tools.node.npm.dependency_replacements["ip-address"]')" \
		--build-arg \
		"NPM_SHA256=$(json '.tools.node.npm.asset.sha256')" \
		--build-arg \
		"NPM_TAR_VERSION=$(json '.tools.node.npm.dependency_replacements.tar')" \
		--build-arg "PNPM_VERSION=$(json '.tools.node.pnpm')" \
		--build-arg "REDOCLY_VERSION=$(json '.tools.node.redocly')" \
		"$repository_root"
}

build_vite() {
	build_image "${repository_root}/images/vite/Dockerfile" \
		--load \
		--tag ci-vite:test \
		"${common_labels[@]}" \
		--build-arg BASE_IMAGE=ci-node:test \
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
		--build-arg "OXFMT_VERSION=$(json '.tools.vite.oxfmt')" \
		"$repository_root"
}

build_playwright() {
	build_image "${repository_root}/images/playwright/Dockerfile" \
		--load \
		--tag ci-playwright:test \
		"${common_labels[@]}" \
		--build-arg BASE_IMAGE=ci-vite:test \
		--build-arg \
		"PLAYWRIGHT_VERSION=$(json '.tools.playwright.version')" \
		"$repository_root"
}

build_postgres() {
	build_image "${repository_root}/images/postgres/Dockerfile" \
		--load \
		--tag ci-postgres:test \
		"${common_labels[@]}" \
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
		"POSTGRES_VERSION=$(json '.tools.postgres.postgres')" \
		"$repository_root"
}

if [[ $target == all || $target == base || $target == go ||
	$target == node || $target == vite || $target == playwright ]]; then
	build_base
fi

if [[ $target == all || $target == go ]]; then
	build_go
fi

if [[ $target == all || $target == node ||
	$target == vite || $target == playwright ]]; then
	build_node
fi

if [[ $target == all || $target == vite || $target == playwright ]]; then
	build_vite
fi

if [[ $target == all || $target == playwright ]]; then
	build_playwright
fi

if [[ $target == all || $target == postgres ]]; then
	build_postgres
fi
