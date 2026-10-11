#!/usr/bin/env bash

set -euo pipefail

: "${EXPECTED_BUILDX_VERSION:?EXPECTED_BUILDX_VERSION is not set}"
: "${EXPECTED_CI_UID:?EXPECTED_CI_UID is not set}"
: "${EXPECTED_CI_GID:?EXPECTED_CI_GID is not set}"

[[ $(id -u) == "$EXPECTED_CI_UID" ]]
[[ $(id -g) == "$EXPECTED_CI_GID" ]]
[[ $HOME == /home/ci && $TMPDIR == /var/tmp ]]
[[ ! -S /var/run/docker.sock ]]
if command -v go >/dev/null 2>&1; then
	printf 'Go build toolchain leaked into the utility runtime\n' >&2
	exit 1
fi
for tool in ci-utils ci-docker-cleanup ci-buildkit-probe; do
	[[ $(command -v "$tool") == "/opt/ci-tools/bin/${tool}" ]]
	[[ ! -w $(command -v "$tool") ]]
done

ci-utils | grep --fixed-strings ci-docker-cleanup >/dev/null
ci-docker-cleanup --help | grep --fixed-strings 'check,plan,apply,version' >/dev/null
ci-docker-cleanup version | python3 -c '
import json, sys
value = json.load(sys.stdin)
assert value["event"] == "version"
assert value["policy_schema"] == 1 and value["host_protocol"] == 1
assert value["revision"] not in ("unknown", "unbuilt", "")
'
docker buildx version | grep --fixed-strings "v${EXPECTED_BUILDX_VERSION}" >/dev/null
probe_error=$(mktemp)
trap 'rm -f "$probe_error"' EXIT
if ci-buildkit-probe >"$probe_error" 2>&1; then
	printf 'capability probe accepted a missing endpoint\n' >&2
	exit 1
else
	[[ $? == 2 ]]
fi
grep --fixed-strings 'explicit local Unix endpoint' "$probe_error" >/dev/null
[[ ! -w /opt/ci-tools/ci-utils/ci_utils/policy.py ]]
[[ ! -d $HOME/.docker ]]
printf 'ci-utils direct commands and offline non-root discovery passed\n'
