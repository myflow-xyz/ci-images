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
	.github/scripts/merge-image.sh
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
	images/base/bash-5.3-patches.sha256
	images/base/debian-packages.amd64.lock
	images/base/debian-packages.arm64.lock
	images/go/Dockerfile
	images/node/Dockerfile
	images/node/markdownlint/package.json
	images/node/markdownlint/package-lock.json
	images/node/npm/package.json
	images/node/npm/package-lock.json
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
      ["Bash", .tools.base.bash.version],
      ["CPython", .tools.base.python.version],
      ["actionlint", .tools.base.actionlint.version],
      ["GitHub CLI", .tools.base.gh.version],
      ["Git LFS", .tools.base.git_lfs.version],
      ["gitleaks", .tools.base.gitleaks.version],
      ["jq", .tools.base.jq.version],
      ["osv-scanner", .tools.base.osv_scanner.version],
      ["ripgrep", .tools.base.ripgrep.version],
      ["ShellCheck", .tools.base.shellcheck.version],
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
      ["pnpm", .tools.node.pnpm.version],
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

debian_package_lock_amd64=$(
	jq -r '.tools.base.debian_packages.lockfiles.amd64.lockfile' "$manifest"
)
debian_package_lock_arm64=$(
	jq -r '.tools.base.debian_packages.lockfiles.arm64.lockfile' "$manifest"
)
while IFS='=' read -r package amd64_version arm64_version; do
	version=$amd64_version
	if [[ $amd64_version != "$arm64_version" ]]; then
		version="${amd64_version} (amd64) / ${arm64_version} (arm64)"
	fi
	row="| \`${package}\` | \`${version}\` |"
	grep --fixed-strings --line-regexp "$row" "$versions_doc" >/dev/null ||
		fail "missing Debian package inventory row: ${package}"
done < <(
	join \
		-t '=' \
		"${repository_root}/${debian_package_lock_amd64}" \
		"${repository_root}/${debian_package_lock_arm64}"
)

jq --exit-status '
  .schema_version == 1 and
  .platforms == ["linux/amd64", "linux/arm64"] and
  .ci_user.name == "ci" and
  .ci_user.uid == 1001 and
  .ci_user.gid == 2001 and
  (.debian_snapshot | test("^[0-9]{8}T[0-9]{6}Z$")) and
  (.upstream_images.debian.reference |
    endswith("debian:trixie-slim")) and
  (.upstream_images.node.reference |
    endswith("node:26.10.0-trixie-slim")) and
  (.upstream_images.pgvector.reference |
    endswith("pgvector:0.8.6-pg18-trixie")) and
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
  (.tools.base.bash as $bash |
    ($bash.release | test("^5\\.[3-9]$")) and
    $bash.version == ($bash.release + "." + ($bash.patchlevel | tostring)) and
    $bash.asset.url ==
      ("https://ftp.gnu.org/gnu/bash/bash-" +
       $bash.release + ".tar.gz") and
    $bash.patches.lockfile == "images/base/bash-5.3-patches.sha256") and
  (.tools.base.gh as $gh |
    $gh.assets.amd64.url ==
      ("https://github.com/cli/cli/releases/download/v" +
       $gh.version + "/gh_" + $gh.version + "_linux_amd64.tar.gz") and
    $gh.assets.arm64.url ==
      ("https://github.com/cli/cli/releases/download/v" +
       $gh.version + "/gh_" + $gh.version + "_linux_arm64.tar.gz")) and
  .tools.base.git_lfs.module == "github.com/git-lfs/git-lfs/v3" and
  (.tools.base.jq as $jq |
    $jq.assets.amd64.url ==
      ("https://github.com/jqlang/jq/releases/download/jq-" +
       $jq.version + "/jq-linux-amd64") and
    $jq.assets.arm64.url ==
      ("https://github.com/jqlang/jq/releases/download/jq-" +
       $jq.version + "/jq-linux-arm64")) and
  (.tools.base.python.version | test("^3\\.14\\.[0-9]+$")) and
  .upstream_images.python.reference ==
    ("docker.io/library/python:" + .tools.base.python.version +
     "-slim-trixie") and
  (.tools.base.osv_scanner as $osv |
    $osv.module ==
      "github.com/google/osv-scanner/v2/cmd/osv-scanner") and
  (.tools.base.ripgrep as $ripgrep |
    $ripgrep.assets.amd64.url ==
      ("https://github.com/BurntSushi/ripgrep/releases/download/" +
       $ripgrep.version + "/ripgrep-" + $ripgrep.version +
       "-x86_64-unknown-linux-musl.tar.gz") and
    $ripgrep.assets.arm64.url ==
      ("https://github.com/BurntSushi/ripgrep/releases/download/" +
       $ripgrep.version + "/ripgrep-" + $ripgrep.version +
       "-aarch64-unknown-linux-musl.tar.gz")) and
  (.tools.base.shellcheck as $shellcheck |
    $shellcheck.assets.amd64.url ==
      ("https://github.com/koalaman/shellcheck/releases/download/v" +
       $shellcheck.version + "/shellcheck-v" + $shellcheck.version +
       ".linux.x86_64.tar.gz") and
    $shellcheck.assets.arm64.url ==
      ("https://github.com/koalaman/shellcheck/releases/download/v" +
       $shellcheck.version + "/shellcheck-v" + $shellcheck.version +
       ".linux.aarch64.tar.gz")) and
  .tools.base.debian_packages.lockfiles.amd64.lockfile ==
    "images/base/debian-packages.amd64.lock" and
  .tools.base.debian_packages.lockfiles.arm64.lockfile ==
    "images/base/debian-packages.arm64.lock" and
  (.tools.base.trivy as $trivy |
    $trivy.module == "github.com/aquasecurity/trivy/cmd/trivy" and
    ($trivy.build_go.version | test("^1\\.26\\.[0-9]+$")) and
    $trivy.build_go.assets.amd64.url ==
      ("https://go.dev/dl/go" + $trivy.build_go.version +
       ".linux-amd64.tar.gz") and
    $trivy.build_go.assets.arm64.url ==
      ("https://go.dev/dl/go" + $trivy.build_go.version +
       ".linux-arm64.tar.gz")) and
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
  (.tools.node.pnpm as $pnpm |
    $pnpm.source == "https://github.com/pnpm/pnpm" and
    ($pnpm.store_version | test("^[0-9]+$")) and
    $pnpm.assets.amd64.url ==
      ("https://github.com/pnpm/pnpm/releases/download/v" +
       $pnpm.version + "/pnpm-linux-x64.tar.gz") and
    $pnpm.assets.arm64.url ==
      ("https://github.com/pnpm/pnpm/releases/download/v" +
       $pnpm.version + "/pnpm-linux-arm64.tar.gz")) and
  ([.tools.base.git_lfs.dependency_overrides[],
    .tools.base.gitleaks.dependency_overrides[],
    .tools.base.trivy.dependency_overrides[],
    .tools.base.yq.dependency_overrides[],
    .tools.go.golangci_lint.dependency_overrides[],
    .tools.go.sqlc.dependency_overrides[],
    .tools.go.goose.dependency_overrides[],
    .tools.vite.typescript_source.dependency_overrides[],
    .tools.vite.oxlint_tsgolint_source.dependency_overrides[]] |
    map(test("^v[0-9]+\\.[0-9]+\\.[0-9]+$")) |
    all) and
  (.tools.node.markdownlint_cli2.dependency_overrides["smol-toml"] |
    test("^[0-9]+\\.[0-9]+\\.[0-9]+$")) and
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

while IFS= read -r debian_package_lock; do
	debian_package_lock_path="${repository_root}/${debian_package_lock}"
	LC_ALL=C sort -c -u "$debian_package_lock_path" ||
		fail "Debian package lock must be sorted and unique: ${debian_package_lock}"
	while IFS= read -r package; do
		[[ $package =~ ^[a-z0-9][a-z0-9+.-]*=[0-9A-Za-z][0-9A-Za-z.+:~_-]*$ ]] ||
			fail "invalid Debian package lock entry: ${package}"
	done <"$debian_package_lock_path"
done < <(
	jq -r '.tools.base.debian_packages.lockfiles[].lockfile' "$manifest"
)

cmp \
	<(cut -d= -f1 "${repository_root}/${debian_package_lock_amd64}") \
	<(cut -d= -f1 "${repository_root}/${debian_package_lock_arm64}") \
	>/dev/null || fail 'Debian package locks must contain the same package names'

bash_patch_lock="${repository_root}/images/base/bash-5.3-patches.sha256"
[[ $(wc -l <"$bash_patch_lock") -eq $(jq -r '.tools.base.bash.patchlevel' "$manifest") ]] ||
	fail 'Bash patch lock must match the pinned patchlevel'
awk -F= '
  $1 != sprintf("bash53-%03d", NR) || $2 !~ /^[0-9a-f]{64}$/ {
    exit 1
  }
' "$bash_patch_lock" || fail 'Bash patch lock has an invalid entry'

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
assert_package_version \
	images/node/markdownlint/package-lock.json \
	smol-toml \
	"$(jq -r '.tools.node.markdownlint_cli2.dependency_overrides["smol-toml"]' "$manifest")"
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
jq --exit-status \
	'.packages | has("node_modules/pnpm") | not' \
	"${repository_root}/images/node/npm/package-lock.json" >/dev/null ||
	fail 'pnpm must remain outside the Node npm tool lockfile'
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

base_dockerfile="${repository_root}/images/base/Dockerfile"
[[ $(grep -c --fixed-strings \
	'/usr/local/share/ci/debian-packages.lock' \
	"$base_dockerfile") == 2 ]] ||
	fail 'base image must install and retain its Debian package lock'
grep \
	--fixed-strings \
	--line-regexp \
	"FROM --platform=\${BUILDPLATFORM} \${BASE_IMAGE} AS base-go-tools-builder" \
	"$base_dockerfile" \
	>/dev/null ||
	fail 'base Go tools must build on the native build platform'
[[ $(grep -c "CGO_ENABLED=0 GOARCH=\"\${TARGETARCH}\" GOOS=linux" \
	"$base_dockerfile") == 3 ]] ||
	fail 'base Go tools must compile all binaries for the target platform'

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
