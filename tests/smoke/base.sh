#!/usr/bin/env bash

set -euo pipefail

expected_uid=${EXPECTED_CI_UID:?EXPECTED_CI_UID is not set}
expected_node=${EXPECTED_NODE_VERSION:?EXPECTED_NODE_VERSION is not set}
: "${EXPECTED_MARKDOWNLINT_VERSION:?EXPECTED_MARKDOWNLINT_VERSION is not set}"
expected_markdownlint=$EXPECTED_MARKDOWNLINT_VERSION

[[ $(id -u) == "$expected_uid" ]]
[[ $HOME == /home/ci ]]
[[ $(node --version) == "v${expected_node}" ]]

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

if command -v docker >/dev/null 2>&1; then
	printf 'Docker CLI must not be present in a job image\n' >&2
	exit 1
fi

probe=/workspace/.ci-base-write-probe
printf 'writable\n' >"$probe"
rm -f "$probe"

touch "$HOME/.write-probe" /cache/npm/.write-probe
rm -f "$HOME/.write-probe" /cache/npm/.write-probe
