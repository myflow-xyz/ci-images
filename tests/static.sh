#!/usr/bin/env bash

set -euo pipefail

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
manifest="${repository_root}/manifests/versions.json"

fail() {
	printf 'static verification failed: %s\n' "$*" >&2
	exit 1
}

sha256_file() {
	if command -v sha256sum >/dev/null 2>&1; then
		sha256sum "$1" | awk '{print $1}'
	else
		shasum -a 256 "$1" | awk '{print $1}'
	fi
}

command -v jq >/dev/null 2>&1 || fail 'jq is required'

required_files=(
	.github/scripts/next-version.sh
	.github/scripts/release-images.sh
	README.md
	docs/index.md
	docs/release.md
	docs/usage.md
	docs/images/base.md
	docs/images/go.md
	docs/images/node.md
	docs/images/vite.md
	docs/images/playwright.md
	docs/images/postgres.md
	images/base/Dockerfile
	images/base/npm-runtime/package.json
	images/base/npm-runtime/package-lock.json
	images/go/Dockerfile
	images/node/Dockerfile
	images/vite/Dockerfile
	images/playwright/Dockerfile
	images/postgres/Dockerfile
	manifests/versions.json
	tests/release.sh
)

for relative_path in "${required_files[@]}"; do
	[[ -f "${repository_root}/${relative_path}" ]] ||
		fail "missing ${relative_path}"
done

jq --exit-status '
  .schema_version == 1 and
  .platforms == ["linux/amd64", "linux/arm64"] and
  .ci_user.name == "ci" and
  (.ci_user.uid | type == "number") and
  (.ci_user.gid | type == "number") and
  (.debian_snapshot | test("^[0-9]{8}T[0-9]{6}Z$")) and
  (.upstream_images.node.reference |
    endswith("node:24.18.0-bookworm-slim")) and
  ([.upstream_images[].digest |
    test("^sha256:[0-9a-f]{64}$")] | all) and
  ([.images[].name] | sort) == ([
    "ghcr.io/myflow-xyz/ci-base",
    "ghcr.io/myflow-xyz/ci-go",
    "ghcr.io/myflow-xyz/ci-node",
    "ghcr.io/myflow-xyz/ci-playwright",
    "ghcr.io/myflow-xyz/ci-postgres",
    "ghcr.io/myflow-xyz/ci-vite"
  ] | sort) and
  .images.base.parent == "upstream_images.node" and
  .images.go.parent == "images.base" and
  .images.node.parent == "images.base" and
  .images.vite.parent == "images.node" and
  .images.playwright.parent == "images.vite" and
  .images.postgres.parent == "upstream_images.pgvector" and
  (.tools.vite.oxlint_tsgolint_source.commit |
    test("^[0-9a-f]{40}$")) and
  (.tools.vite.oxlint_tsgolint_source.typescript_go_commit |
    test("^[0-9a-f]{40}$")) and
  (.tools.postgres.gosu.commit | test("^[0-9a-f]{40}$")) and
  ([.tools.base.gitleaks.dependency_overrides[],
    .tools.go.sqlc.dependency_overrides[],
    .tools.go.goose.dependency_overrides[]] |
    map(test("^v[0-9]+\\.[0-9]+\\.[0-9]+$")) |
    all) and
  ([.. | objects |
    select(has("url") or has("sha256")) |
    (.url | startswith("https://")) and
    (.sha256 | test("^[0-9a-f]{64}$"))] | all)
' "$manifest" >/dev/null || fail 'manifest structure or image graph'

while IFS=$'\t' read -r lockfile expected_sha256; do
	lockfile_path="${repository_root}/${lockfile}"
	[[ -f $lockfile_path ]] || fail "missing lockfile ${lockfile}"
	actual_sha256=$(sha256_file "$lockfile_path")
	[[ $actual_sha256 == "$expected_sha256" ]] ||
		fail "lockfile checksum mismatch: ${lockfile}"
done < <(
	jq -r '
    .. |
    objects |
    select(has("lockfile")) |
    [.lockfile, .lockfile_sha256] |
    @tsv
  ' "$manifest"
)

package_version() {
	local lockfile=$1
	local package=$2
	jq -r \
		--arg path "node_modules/${package}" \
		'.packages[$path].version' \
		"${repository_root}/${lockfile}"
}

assert_package_version() {
	local lockfile=$1
	local package=$2
	local expected=$3
	local actual
	actual=$(package_version "$lockfile" "$package")
	[[ $actual == "$expected" ]] ||
		fail "${package}: lockfile=${actual}, manifest=${expected}"
}

assert_package_version \
	images/base/npm/package-lock.json \
	markdownlint-cli2 \
	"$(jq -r '.tools.base.markdownlint_cli2.version' "$manifest")"
assert_package_version \
	images/base/npm-runtime/package-lock.json \
	npm \
	"$(jq -r '.tools.base.npm.version' "$manifest")"
assert_package_version \
	images/base/npm-runtime/package-lock.json \
	brace-expansion \
	"$(jq -r '.tools.base.npm.dependency_replacements["brace-expansion"]' "$manifest")"
assert_package_version \
	images/node/npm/package-lock.json \
	pnpm \
	"$(jq -r '.tools.node.pnpm' "$manifest")"
assert_package_version \
	images/node/npm/package-lock.json \
	@redocly/cli \
	"$(jq -r '.tools.node.redocly' "$manifest")"
assert_package_version \
	images/vite/npm/package-lock.json \
	typescript \
	"$(jq -r '.tools.vite.typescript' "$manifest")"
assert_package_version \
	images/vite/npm/package-lock.json \
	vite \
	"$(jq -r '.tools.vite.vite' "$manifest")"
assert_package_version \
	images/vite/npm/package-lock.json \
	vitest \
	"$(jq -r '.tools.vite.vitest' "$manifest")"
assert_package_version \
	images/vite/npm/package-lock.json \
	@vitest/coverage-v8 \
	"$(jq -r '.tools.vite.coverage_v8' "$manifest")"
assert_package_version \
	images/vite/npm/package-lock.json \
	oxlint \
	"$(jq -r '.tools.vite.oxlint' "$manifest")"
assert_package_version \
	images/vite/npm/package-lock.json \
	oxlint-tsgolint \
	"$(jq -r '.tools.vite.oxlint_tsgolint' "$manifest")"
assert_package_version \
	images/vite/npm/package-lock.json \
	oxfmt \
	"$(jq -r '.tools.vite.oxfmt' "$manifest")"
assert_package_version \
	images/playwright/npm/package-lock.json \
	@playwright/test \
	"$(jq -r '.tools.playwright.version' "$manifest")"

frontend_reference=$(jq -r '
  .upstream_images.dockerfile_frontend |
  (.reference | sub("^docker.io/"; "")) + "@" + .digest
' "$manifest")

while IFS= read -r dockerfile; do
	first_line=$(head -n 1 "$dockerfile")
	[[ $first_line == "# syntax=${frontend_reference}" ]] ||
		fail "${dockerfile#"$repository_root/"} has an unpinned frontend"
done < <(find "${repository_root}/images" -name Dockerfile -type f | sort)

if git -C "$repository_root" grep -nE \
	'mf-ci-|image-hub' \
	-- README.md docs images manifests; then
	fail 'obsolete repository or package naming remains'
fi

"${repository_root}/tests/release.sh"

printf 'static verification passed\n'
