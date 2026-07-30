#!/usr/bin/env bash

set -euo pipefail

expected_uid=${EXPECTED_CI_UID:?EXPECTED_CI_UID is not set}
expected_gid=${EXPECTED_CI_GID:?EXPECTED_CI_GID is not set}
expected_go=${EXPECTED_TOOLCHAIN_GO_VERSION:?EXPECTED_TOOLCHAIN_GO_VERSION is not set}
: "${EXPECTED_ACTIONLINT_VERSION:?EXPECTED_ACTIONLINT_VERSION is not set}"
: "${EXPECTED_GITLEAKS_X_CRYPTO_VERSION:?EXPECTED_GITLEAKS_X_CRYPTO_VERSION is not set}"
: "${EXPECTED_GITLEAKS_XZ_VERSION:?EXPECTED_GITLEAKS_XZ_VERSION is not set}"
: "${EXPECTED_GITLEAKS_VERSION:?EXPECTED_GITLEAKS_VERSION is not set}"
: "${EXPECTED_SHFMT_VERSION:?EXPECTED_SHFMT_VERSION is not set}"
: "${EXPECTED_YQ_VERSION:?EXPECTED_YQ_VERSION is not set}"
: "${EXPECTED_YQ_X_TEXT_VERSION:?EXPECTED_YQ_X_TEXT_VERSION is not set}"

[[ $(id -u) == "$expected_uid" ]]
[[ $(id -g) == "$expected_gid" ]]
[[ $HOME == /home/ci ]]
[[ $LANG == en_US.utf8 ]]
[[ $LC_ALL == en_US.utf8 ]]
[[ $TMPDIR == /var/tmp ]]
[[ -z ${NODE_VERSION+x} ]]
[[ -z ${NPM_CONFIG_CACHE+x} ]]
[[ -z ${PNPM_CONFIG_STORE_DIR+x} ]]
[[ -z ${XDG_CACHE_HOME+x} ]]
[[ -z ${XDG_CONFIG_HOME+x} ]]
[[ -z ${XDG_DATA_HOME+x} ]]
[[ -z ${XDG_STATE_HOME+x} ]]
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
	python3 \
	rg \
	shellcheck \
	shellspec \
	shfmt \
	yq; do
	command -v "$command" >/dev/null
done

python3 -c '
import json
import socket
import urllib.parse
import urllib.request

assert json.loads("{\"ok\": true}")["ok"]
assert socket.gethostname()
assert urllib.parse.urlsplit("https://ci.example/path").hostname == "ci.example"
'

actionlint --version 2>&1 |
	grep --fixed-strings "$EXPECTED_ACTIONLINT_VERSION" >/dev/null
[[ $(gitleaks version) == "$EXPECTED_GITLEAKS_VERSION" ]]
grep \
	--binary-files=text \
	--fixed-strings \
	$'dep\tgithub.com/ulikunitz/xz\t'"${EXPECTED_GITLEAKS_XZ_VERSION}" \
	"$(command -v gitleaks)" \
	>/dev/null
grep \
	--binary-files=text \
	--fixed-strings \
	$'dep\tgolang.org/x/crypto\t'"${EXPECTED_GITLEAKS_X_CRYPTO_VERSION}" \
	"$(command -v gitleaks)" \
	>/dev/null
shfmt --version |
	grep --fixed-strings "$EXPECTED_SHFMT_VERSION" >/dev/null
yq --version |
	grep --fixed-strings "$EXPECTED_YQ_VERSION" >/dev/null
grep \
	--binary-files=text \
	--fixed-strings \
	$'dep\tgolang.org/x/text\t'"${EXPECTED_YQ_X_TEXT_VERSION}" \
	"$(command -v yq)" \
	>/dev/null

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
	shellspec \
	shfmt \
	yq; do
	[[ $(command -v "$command") == "/opt/ci-tools/bin/${command}" ]]
done

for command in go markdownlint-cli2 node npm npx yarn yarnpkg; do
	if command -v "$command" >/dev/null 2>&1; then
		printf 'runtime command is present in ci-base: %s\n' "$command" >&2
		exit 1
	fi
done

for command in pip pip3; do
	if command -v "$command" >/dev/null 2>&1; then
		printf 'Python package manager is present in ci-base: %s\n' "$command" >&2
		exit 1
	fi
done

for path in \
	/opt/ci-tools/markdownlint-cli2 \
	/opt/ci-tools/npm \
	/var/cache/npm \
	/var/cache/pnpm; do
	[[ ! -e $path ]]
done

if command -v docker >/dev/null 2>&1; then
	printf 'Docker CLI must not be present in a job image\n' >&2
	exit 1
fi

probe=/workspace/.ci-base-write-probe
printf 'writable\n' >"$probe"
rm -f "$probe"

touch "$HOME/.write-probe" /var/tmp/.write-probe
rm -f "$HOME/.write-probe" /var/tmp/.write-probe
