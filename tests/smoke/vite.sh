#!/usr/bin/env bash

set -euo pipefail

: "${EXPECTED_VITE_BUNDLE_VERSION:?EXPECTED_VITE_BUNDLE_VERSION is not set}"
expected_bundle=$EXPECTED_VITE_BUNDLE_VERSION
expected_go=${EXPECTED_TOOLCHAIN_GO_VERSION:?EXPECTED_TOOLCHAIN_GO_VERSION is not set}
: "${EXPECTED_OXLINT_TSGOLINT_X_TEXT_VERSION:?EXPECTED_OXLINT_TSGOLINT_X_TEXT_VERSION is not set}"
bundle_root="/opt/ci-tools/vite/${expected_bundle}/node_modules"

assert_package_version() {
	local package=$1
	local expected=$2
	local actual
	actual=$(node --print \
		"require('${bundle_root}/${package}/package.json').version")
	[[ $actual == "$expected" ]]
}

assert_package_version \
	typescript \
	"${EXPECTED_TYPESCRIPT_VERSION:?EXPECTED_TYPESCRIPT_VERSION is not set}"
assert_package_version \
	vite \
	"${EXPECTED_VITE_VERSION:?EXPECTED_VITE_VERSION is not set}"
assert_package_version \
	vitest \
	"${EXPECTED_VITEST_VERSION:?EXPECTED_VITEST_VERSION is not set}"
assert_package_version \
	@vitest/coverage-v8 \
	"${EXPECTED_COVERAGE_V8_VERSION:?EXPECTED_COVERAGE_V8_VERSION is not set}"
assert_package_version \
	oxlint \
	"${EXPECTED_OXLINT_VERSION:?EXPECTED_OXLINT_VERSION is not set}"
assert_package_version \
	oxlint-tsgolint \
	"${EXPECTED_OXLINT_TSGOLINT_VERSION:?EXPECTED_OXLINT_TSGOLINT_VERSION is not set}"
assert_package_version \
	oxfmt \
	"${EXPECTED_OXFMT_VERSION:?EXPECTED_OXFMT_VERSION is not set}"

for command in oxfmt oxlint tsc tsgolint tsserver vite vitest; do
	[[ $(command -v "$command") == "/opt/ci-tools/bin/${command}" ]]
done

tsgolint_binary=$(find \
	"${bundle_root}/@oxlint-tsgolint" \
	-mindepth 2 \
	-maxdepth 2 \
	-name tsgolint \
	-type f)
[[ -n $tsgolint_binary ]]
grep \
	--binary-files=text \
	--fixed-strings \
	"go${expected_go}" \
	"$tsgolint_binary" \
	>/dev/null
grep \
	--binary-files=text \
	--fixed-strings \
	$'dep\tgolang.org/x/text\t'"${EXPECTED_OXLINT_TSGOLINT_X_TEXT_VERSION}" \
	"$tsgolint_binary" \
	>/dev/null

smoke_directory=$(mktemp -d /var/tmp/vite-shadow-smoke.XXXXXX)
trap 'rm -rf "$smoke_directory"' EXIT
mkdir -p "${smoke_directory}/node_modules/.bin"

cat >"${smoke_directory}/package.json" <<'EOF'
{
  "name": "vite-shadow-smoke",
  "private": true,
  "scripts": {
    "check": "vite"
  }
}
EOF

cat >"${smoke_directory}/node_modules/.bin/vite" <<'EOF'
#!/usr/bin/env sh
printf 'repository-local-vite\n'
EOF
chmod 0755 "${smoke_directory}/node_modules/.bin/vite"

actual=$(
	cd "$smoke_directory"
	pnpm run --silent check
)
[[ $actual == repository-local-vite ]]
