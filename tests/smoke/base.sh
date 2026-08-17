#!/usr/bin/env bash

set -euo pipefail

expected_uid=${EXPECTED_CI_UID:?EXPECTED_CI_UID is not set}
expected_gid=${EXPECTED_CI_GID:?EXPECTED_CI_GID is not set}
expected_go=${EXPECTED_TOOLCHAIN_GO_VERSION:?EXPECTED_TOOLCHAIN_GO_VERSION is not set}
expected_python=${EXPECTED_PYTHON_VERSION:?EXPECTED_PYTHON_VERSION is not set}
: "${EXPECTED_ACTIONLINT_VERSION:?EXPECTED_ACTIONLINT_VERSION is not set}"
: "${EXPECTED_GIT_VERSION:?EXPECTED_GIT_VERSION is not set}"
: "${EXPECTED_GITLEAKS_X_CRYPTO_VERSION:?EXPECTED_GITLEAKS_X_CRYPTO_VERSION is not set}"
: "${EXPECTED_GITLEAKS_XZ_VERSION:?EXPECTED_GITLEAKS_XZ_VERSION is not set}"
: "${EXPECTED_GITLEAKS_VERSION:?EXPECTED_GITLEAKS_VERSION is not set}"
: "${EXPECTED_OSV_SCANNER_VERSION:?EXPECTED_OSV_SCANNER_VERSION is not set}"
: "${EXPECTED_SHFMT_VERSION:?EXPECTED_SHFMT_VERSION is not set}"
: "${EXPECTED_TRIVY_VERSION:?EXPECTED_TRIVY_VERSION is not set}"
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
	git-lfs \
	gitleaks \
	jq \
	make \
	osv-scanner \
	python3 \
	rg \
	shellcheck \
	shellspec \
	shfmt \
	trivy \
	yq; do
	command -v "$command" >/dev/null
done

for package in \
	ca-certificates \
	coreutils \
	curl \
	git \
	git-lfs \
	grep \
	jq \
	openssl \
	sed \
	tar \
	unzip; do
	[[ $(dpkg-query --show --showformat='${db:Status-Status}' "$package") == installed ]]
done

git lfs version >/dev/null

[[ $(command -v python3) == /usr/local/bin/python3 ]]
[[ $(python3 --version) == "Python ${expected_python}" ]]

python3 - "$expected_python" <<'PY'
import bz2
import compression.zstd
import ctypes
import dbm.gnu
import json
import lzma
import mimetypes
import readline
import socket
import sqlite3
import ssl
import sys
import urllib.parse
import urllib.request
import uuid
import zlib

assert json.loads("{\"ok\": true}")["ok"]
assert mimetypes.guess_type("artifact.geojson") == ("application/geo+json", None)
assert mimetypes.guess_type("artifact.ics") == ("text/calendar", None)
assert mimetypes.guess_type("artifact.zst") == ("application/zstd", None)
assert socket.gethostname()
assert sys.version.split()[0] == sys.argv[1]
assert urllib.parse.urlsplit("https://ci.example/path").hostname == "ci.example"
PY

actionlint --version 2>&1 |
	grep --fixed-strings "$EXPECTED_ACTIONLINT_VERSION" >/dev/null
[[ $(git version) == "git version ${EXPECTED_GIT_VERSION}" ]]
[[ $(gitleaks version) == "$EXPECTED_GITLEAKS_VERSION" ]]
osv-scanner --version |
	grep \
		--line-regexp \
		--fixed-strings \
		"osv-scanner version: ${EXPECTED_OSV_SCANNER_VERSION}" \
		>/dev/null
trivy --version |
	grep \
		--line-regexp \
		--fixed-strings \
		"Version: ${EXPECTED_TRIVY_VERSION}" \
		>/dev/null
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

for command in actionlint gitleaks osv-scanner shfmt trivy yq; do
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
	osv-scanner \
	shellspec \
	shfmt \
	trivy \
	yq; do
	[[ $(command -v "$command") == "/opt/ci-tools/bin/${command}" ]]
done

for command in go hurl hurlfmt markdownlint-cli2 node npm npx yarn yarnpkg; do
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

for module in ensurepip venv; do
	if python3 -c "import ${module}" >/dev/null 2>&1; then
		printf 'Excluded Python module is present in ci-base: %s\n' "$module" >&2
		exit 1
	fi
done

python_series=${expected_python%.*}
[[ ! -e /usr/local/bin/python3-config ]]
[[ ! -e /usr/local/bin/python${python_series}-config ]]
[[ ! -e /usr/local/include/python${python_series} ]]

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
