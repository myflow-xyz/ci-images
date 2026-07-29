#!/usr/bin/env bash

set -euo pipefail

expected_node=${EXPECTED_NODE_VERSION:?EXPECTED_NODE_VERSION is not set}
expected_pnpm=${EXPECTED_PNPM_VERSION:?EXPECTED_PNPM_VERSION is not set}
: "${EXPECTED_MARKDOWNLINT_VERSION:?EXPECTED_MARKDOWNLINT_VERSION is not set}"
: "${EXPECTED_NODE_BUNDLE_VERSION:?EXPECTED_NODE_BUNDLE_VERSION is not set}"
: "${EXPECTED_NPM_BRACE_EXPANSION_VERSION:?EXPECTED_NPM_BRACE_EXPANSION_VERSION is not set}"
: "${EXPECTED_NPM_TAR_VERSION:?EXPECTED_NPM_TAR_VERSION is not set}"
: "${EXPECTED_NPM_VERSION:?EXPECTED_NPM_VERSION is not set}"
: "${EXPECTED_REDOCLY_VERSION:?EXPECTED_REDOCLY_VERSION is not set}"
expected_bundle=$EXPECTED_NODE_BUNDLE_VERSION
expected_markdownlint=$EXPECTED_MARKDOWNLINT_VERSION
expected_redocly=$EXPECTED_REDOCLY_VERSION
bundle_root="/opt/ci-tools/node/${expected_bundle}/node_modules"
npm_root="/opt/ci-tools/npm/${EXPECTED_NPM_VERSION}/node_modules"
expected_store="/var/cache/pnpm/store/v${expected_pnpm%%.*}"

[[ $(node --version) == "v${expected_node}" ]]
[[ $NODE_VERSION == "$expected_node" ]]
[[ $(npm --version) == "$EXPECTED_NPM_VERSION" ]]
[[ $(node --print \
	"require('${npm_root}/brace-expansion/package.json').version") == "$EXPECTED_NPM_BRACE_EXPANSION_VERSION" ]]
[[ $(node --print \
	"require('${npm_root}/tar/package.json').version") == "$EXPECTED_NPM_TAR_VERSION" ]]
[[ $(pnpm --version) == "$expected_pnpm" ]]
markdownlint-cli2 --version 2>&1 |
	grep --fixed-strings "markdownlint-cli2 v${expected_markdownlint}" >/dev/null
[[ $(node --print \
	"require('${bundle_root}/@redocly/cli/package.json').version") == "$expected_redocly" ]]
[[ $NPM_CONFIG_CACHE == /var/cache/npm ]]
[[ $PNPM_CONFIG_STORE_DIR == /var/cache/pnpm/store ]]
[[ -z ${PNPM_HOME+x} ]]
[[ -z ${PNPM_STORE_DIR+x} ]]
[[ ! -e $HOME/.config/pnpm ]]
[[ $(pnpm store path) == "$expected_store" ]]

[[ $(command -v node) == /usr/local/bin/node ]]
for command in markdownlint-cli2 npm npx pnpm pnpx redocly; do
	[[ $(command -v "$command") == "/opt/ci-tools/bin/${command}" ]]
done

for command in yarn yarnpkg; do
	if command -v "$command" >/dev/null 2>&1; then
		printf 'unsupported command is present: %s\n' "$command" >&2
		exit 1
	fi
done

if command -v vite >/dev/null 2>&1; then
	printf 'ci-node must not expose the Vite toolchain\n' >&2
	exit 1
fi

touch /var/cache/npm/.write-probe /var/cache/pnpm/store/.write-probe
rm -f /var/cache/npm/.write-probe /var/cache/pnpm/store/.write-probe

smoke_directory=$(mktemp -d /var/tmp/node-shadow-smoke.XXXXXX)
trap 'rm -rf "$smoke_directory"' EXIT
mkdir -p "${smoke_directory}/node_modules/.bin"

cat >"${smoke_directory}/package.json" <<'EOF'
{
  "name": "node-shadow-smoke",
  "private": true,
  "scripts": {
    "check": "redocly"
  }
}
EOF

cat >"${smoke_directory}/node_modules/.bin/redocly" <<'EOF'
#!/usr/bin/env sh
printf 'repository-local-redocly\n'
EOF
chmod 0755 "${smoke_directory}/node_modules/.bin/redocly"

actual=$(
	cd "$smoke_directory"
	pnpm run --silent check
)
[[ $actual == repository-local-redocly ]]
