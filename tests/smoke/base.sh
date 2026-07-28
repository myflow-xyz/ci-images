#!/usr/bin/env bash

set -euo pipefail

expected_uid=${EXPECTED_CI_UID:?EXPECTED_CI_UID is not set}
expected_node=${EXPECTED_NODE_VERSION:?EXPECTED_NODE_VERSION is not set}
expected_go=${EXPECTED_TOOLCHAIN_GO_VERSION:?EXPECTED_TOOLCHAIN_GO_VERSION is not set}
: "${EXPECTED_MARKDOWNLINT_VERSION:?EXPECTED_MARKDOWNLINT_VERSION is not set}"
expected_markdownlint=$EXPECTED_MARKDOWNLINT_VERSION
: "${EXPECTED_ACTIONLINT_VERSION:?EXPECTED_ACTIONLINT_VERSION is not set}"
: "${EXPECTED_GITLEAKS_VERSION:?EXPECTED_GITLEAKS_VERSION is not set}"
: "${EXPECTED_NPM_VERSION:?EXPECTED_NPM_VERSION is not set}"
: "${EXPECTED_SHFMT_VERSION:?EXPECTED_SHFMT_VERSION is not set}"
: "${EXPECTED_YQ_VERSION:?EXPECTED_YQ_VERSION is not set}"

[[ $(id -u) == "$expected_uid" ]]
[[ $HOME == /home/ci ]]
[[ $LANG == en_US.utf8 ]]
[[ $LC_ALL == en_US.utf8 ]]
[[ $(node --version) == "v${expected_node}" ]]
[[ $(npm --version) == "$EXPECTED_NPM_VERSION" ]]
[[ $NPM_CONFIG_CACHE == /var/cache/npm ]]
[[ $TMPDIR == /var/tmp ]]
[[ $(locale charmap) == UTF-8 ]]
locale -a | grep --line-regexp en_US.utf8 >/dev/null

for command in \
	actionlint \
	bash \
	gh \
	git \
	gitleaks \
	jq \
	make \
	markdownlint-cli2 \
	rg \
	shellcheck \
	shellspec \
	shfmt \
	yq; do
	command -v "$command" >/dev/null
done

markdownlint-cli2 --version 2>&1 |
	grep --fixed-strings "markdownlint-cli2 v${expected_markdownlint}" >/dev/null

actionlint --version 2>&1 |
	grep --fixed-strings "$EXPECTED_ACTIONLINT_VERSION" >/dev/null
[[ $(gitleaks version) == "$EXPECTED_GITLEAKS_VERSION" ]]
shfmt --version |
	grep --fixed-strings "$EXPECTED_SHFMT_VERSION" >/dev/null
yq --version |
	grep --fixed-strings "$EXPECTED_YQ_VERSION" >/dev/null

for command in actionlint gitleaks shfmt yq; do
	grep \
		--binary-files=text \
		--fixed-strings \
		"go${expected_go}" \
		"$(command -v "$command")" \
		>/dev/null
done

for command in \
	actionlint \
	gitleaks \
	markdownlint-cli2 \
	npm \
	npx \
	shellspec \
	shfmt \
	yq; do
	[[ $(command -v "$command") == "/opt/ci-tools/bin/${command}" ]]
done

for command in yarn yarnpkg; do
	if command -v "$command" >/dev/null 2>&1; then
		printf 'unsupported command is present: %s\n' "$command" >&2
		exit 1
	fi
done
[[ ! -e "/opt/yarn-v${YARN_VERSION}" ]]

if command -v docker >/dev/null 2>&1; then
	printf 'Docker CLI must not be present in a job image\n' >&2
	exit 1
fi

probe=/workspace/.ci-base-write-probe
printf 'writable\n' >"$probe"
rm -f "$probe"

touch \
	"$HOME/.write-probe" \
	/var/cache/npm/.write-probe \
	/var/tmp/.write-probe
rm -f \
	"$HOME/.write-probe" \
	/var/cache/npm/.write-probe \
	/var/tmp/.write-probe
