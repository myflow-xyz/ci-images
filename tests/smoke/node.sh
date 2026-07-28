#!/usr/bin/env bash

set -euo pipefail

expected_node=${EXPECTED_NODE_VERSION:?EXPECTED_NODE_VERSION is not set}
expected_pnpm=${EXPECTED_PNPM_VERSION:?EXPECTED_PNPM_VERSION is not set}
: "${EXPECTED_NODE_BUNDLE_VERSION:?EXPECTED_NODE_BUNDLE_VERSION is not set}"
: "${EXPECTED_REDOCLY_VERSION:?EXPECTED_REDOCLY_VERSION is not set}"
expected_bundle=$EXPECTED_NODE_BUNDLE_VERSION
expected_redocly=$EXPECTED_REDOCLY_VERSION
bundle_root="/opt/ci-tools/node/${expected_bundle}/node_modules"

[[ $(node --version) == "v${expected_node}" ]]
[[ $(pnpm --version) == "$expected_pnpm" ]]
[[ $(node --print \
	"require('${bundle_root}/@redocly/cli/package.json').version") == "$expected_redocly" ]]
[[ $NPM_CONFIG_CACHE == /var/cache/npm ]]
[[ -z ${PNPM_HOME+x} ]]

for command in pnpm pnpx redocly; do
	[[ $(command -v "$command") == "/opt/ci-tools/bin/${command}" ]]
done

if command -v vite >/dev/null 2>&1; then
	printf 'ci-node must not expose the Vite toolchain\n' >&2
	exit 1
fi

touch /var/cache/npm/.write-probe /var/cache/pnpm/.write-probe
rm -f /var/cache/npm/.write-probe /var/cache/pnpm/.write-probe

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
