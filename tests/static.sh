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
	.github/scripts/collect-published-images.sh
	.github/scripts/next-version.sh
	.github/scripts/publish-image.sh
	.github/scripts/release-images.sh
	.github/workflows/images.yml
	.github/workflows/publish-image.yml
	.github/workflows/release.yml
	README.md
	docs/index.md
	docs/release.md
	docs/usage.md
	docs/versions.md
	docs/images/base.md
	docs/images/go.md
	docs/images/node.md
	docs/images/vite.md
	docs/images/playwright.md
	docs/images/postgres.md
	images/base/Dockerfile
	images/go/Dockerfile
	images/node/Dockerfile
	images/node/markdownlint/package.json
	images/node/markdownlint/package-lock.json
	images/node/npm-runtime/package.json
	images/node/npm-runtime/package-lock.json
	images/vite/Dockerfile
	images/playwright/Dockerfile
	images/postgres/Dockerfile
	manifests/versions.json
	tests/publish.sh
	tests/release.sh
	tests/scan-local-image.sh
	tests/scan-local-image_spec.sh
)

for relative_path in "${required_files[@]}"; do
	[[ -f "${repository_root}/${relative_path}" ]] ||
		fail "missing ${relative_path}"
done

for image_doc in "${repository_root}"/docs/images/*.md; do
	grep --line-regexp '## Runtime environment' "$image_doc" >/dev/null ||
		fail "missing runtime environment contract: ${image_doc#"$repository_root/"}"
done

versions_doc="${repository_root}/docs/versions.md"
while IFS=$'\t' read -r component version; do
	row="| \`${component}\` | \`${version#v}\` |"
	grep --fixed-strings --line-regexp "$row" "$versions_doc" >/dev/null ||
		fail "missing version inventory row: ${component} ${version#v}"
done < <(
	jq -r '
    [
      ["Git", .tools.base.git.version],
      ["CPython", .tools.base.python.version],
      ["actionlint", .tools.base.actionlint.version],
      ["gitleaks", .tools.base.gitleaks.version],
      ["osv-scanner", .tools.base.osv_scanner.version],
      ["shellspec", .tools.base.shellspec.version],
      ["shfmt", .tools.base.shfmt.version],
      ["Trivy", .tools.base.trivy.version],
      ["yq", .tools.base.yq.version],
      ["Go", .tools.go.runtime],
      ["Hurl", .tools.go.hurl.version],
      ["sqlc", .tools.go.sqlc.version],
      ["goose", .tools.go.goose.version],
      ["golangci-lint", .tools.go.golangci_lint.version],
      ["goimports", .tools.go.goimports.version],
      ["govulncheck", .tools.go.govulncheck.version],
      ["Node.js", .tools.node.runtime],
      ["npm", .tools.node.npm.version],
      ["pnpm", .tools.node.pnpm],
      ["markdownlint-cli2", .tools.node.markdownlint_cli2.version],
      ["@redocly/cli", .tools.node.redocly],
      ["@typescript/native", .tools.vite.typescript],
      ["TypeScript compatibility package", .tools.vite.typescript_legacy.compat_package],
      ["TypeScript legacy compiler", .tools.vite.typescript_legacy.compiler],
      ["vite", .tools.vite.vite],
      ["vitest", .tools.vite.vitest],
      ["@vitest/coverage-v8", .tools.vite.coverage_v8],
      ["oxlint", .tools.vite.oxlint],
      ["oxlint-tsgolint", .tools.vite.oxlint_tsgolint],
      ["oxfmt", .tools.vite.oxfmt],
      ["@playwright/test", .tools.playwright.version],
      ["PostgreSQL", .tools.postgres.postgres],
      ["pgvector", .tools.postgres.pgvector],
      ["gosu", .tools.postgres.gosu.version]
    ][] |
    @tsv
  ' "$manifest"
)

jq --exit-status '
  .schema_version == 1 and
  .platforms == ["linux/amd64", "linux/arm64"] and
  .ci_user.name == "ci" and
  .ci_user.uid == 1001 and
  .ci_user.gid == 2001 and
  (.debian_snapshot | test("^[0-9]{8}T[0-9]{6}Z$")) and
  (.upstream_images.debian.reference |
    endswith("debian:bookworm-slim")) and
  (.upstream_images.node.reference |
    endswith("node:24.19.0-bookworm-slim")) and
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
  .images.base.parent == "upstream_images.debian" and
  .images.go.parent == "images.base" and
  .images.node.parent == "images.base" and
  .images.vite.parent == "images.node" and
  .images.playwright.parent == "images.vite" and
  .images.postgres.parent == "upstream_images.pgvector" and
  (.tools.vite.oxlint_tsgolint_source.commit |
    test("^[0-9a-f]{40}$")) and
  (.tools.vite.typescript_source.commit |
    test("^[0-9a-f]{40}$")) and
  (.tools.postgres.gosu.commit | test("^[0-9a-f]{40}$")) and
  (.tools.base.git as $git |
    $git.asset.url ==
      ("https://www.kernel.org/pub/software/scm/git/git-" +
       $git.version + ".tar.xz")) and
  (.tools.base.python as $python |
    ($python.version | test("^3\\.14\\.[0-9]+$")) and
    $python.asset.url ==
      ("https://www.python.org/ftp/python/" +
       $python.version + "/Python-" + $python.version + ".tar.xz")) and
  (.tools.base.osv_scanner as $osv |
    $osv.module ==
      "github.com/google/osv-scanner/v2/cmd/osv-scanner") and
  (.tools.base.trivy as $trivy |
    $trivy.assets.amd64.url ==
      ("https://github.com/aquasecurity/trivy/releases/download/v" +
       $trivy.version + "/trivy_" + $trivy.version +
       "_Linux-64bit.tar.gz") and
    $trivy.assets.arm64.url ==
      ("https://github.com/aquasecurity/trivy/releases/download/v" +
       $trivy.version + "/trivy_" + $trivy.version +
       "_Linux-ARM64.tar.gz")) and
  (.tools.go.hurl as $hurl |
    $hurl.assets.amd64.url ==
      ("https://github.com/Orange-OpenSource/hurl/releases/download/" +
       $hurl.version + "/hurl-" + $hurl.version +
       "-x86_64-unknown-linux-gnu.tar.gz") and
    $hurl.assets.arm64.url ==
      ("https://github.com/Orange-OpenSource/hurl/releases/download/" +
       $hurl.version + "/hurl-" + $hurl.version +
       "-aarch64-unknown-linux-gnu.tar.gz")) and
  (.tools.node.npm as $npm |
    $npm.asset.url ==
      ("https://registry.npmjs.org/npm/-/npm-" +
       $npm.version + ".tgz")) and
  ([.tools.base.gitleaks.dependency_overrides[],
    .tools.base.yq.dependency_overrides[],
    .tools.go.golangci_lint.dependency_overrides[],
    .tools.go.sqlc.dependency_overrides[],
    .tools.go.goose.dependency_overrides[],
    .tools.vite.typescript_source.dependency_overrides[],
    .tools.vite.oxlint_tsgolint_source.dependency_overrides[]] |
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
	images/node/markdownlint/package-lock.json \
	markdownlint-cli2 \
	"$(jq -r '.tools.node.markdownlint_cli2.version' "$manifest")"
jq --exit-status \
	'.packages | has("node_modules/npm") | not' \
	"${repository_root}/images/node/npm-runtime/package-lock.json" >/dev/null ||
	fail 'npm artifact must remain outside the replacement lockfile'
assert_package_version \
	images/node/npm-runtime/package-lock.json \
	brace-expansion \
	"$(jq -r '.tools.node.npm.dependency_replacements["brace-expansion"]' "$manifest")"
assert_package_version \
	images/node/npm-runtime/package-lock.json \
	ip-address \
	"$(jq -r '.tools.node.npm.dependency_replacements["ip-address"]' "$manifest")"
assert_package_version \
	images/node/npm-runtime/package-lock.json \
	tar \
	"$(jq -r '.tools.node.npm.dependency_replacements.tar' "$manifest")"
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
	@typescript/native \
	"$(jq -r '.tools.vite.typescript' "$manifest")"
assert_package_version \
	images/vite/npm/package-lock.json \
	typescript \
	"$(jq -r '.tools.vite.typescript_legacy.compat_package' "$manifest")"
assert_package_version \
	images/vite/npm/package-lock.json \
	@typescript/old \
	"$(jq -r '.tools.vite.typescript_legacy.compiler' "$manifest")"
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

while IFS= read -r cache_mount; do
	[[ $cache_mount == *,sharing=locked* ]] ||
		fail "unlocked Go build cache mount: ${cache_mount}"
done < <(
	git -C "$repository_root" grep -n \
		-e '--mount=type=cache,target=/var/cache/go/' \
		-- 'images/*/Dockerfile'
)

if git -C "$repository_root" grep -nE \
	'mf-ci-|image-hub' \
	-- README.md docs images manifests; then
	fail 'obsolete repository or package naming remains'
fi

"${repository_root}/tests/release.sh"
"${repository_root}/tests/publish.sh"
"${repository_root}/tests/scan-local-image_spec.sh"

printf 'static verification passed\n'
