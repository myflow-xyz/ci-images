#!/usr/bin/env bash

set -euo pipefail

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
integration="${repository_root}/tests/smoke/docker-integration.sh"
temporary_directory=$(mktemp -d)
trap 'rm -rf "$temporary_directory"' EXIT
fake_bin="${temporary_directory}/bin"
output="${temporary_directory}/output"
export FAKE_COMPOSE_STARTED="${temporary_directory}/started"
mkdir -p "$fake_bin"

fail() {
	printf 'Compose preflight verification failed: %s\n' "$*" >&2
	cat "$output" >&2
	exit 1
}

cat >"${fake_bin}/id" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "$*" in
	-u) printf '%s\n' "${FAKE_UID:-1001}" ;;
	-g) printf '%s\n' "${FAKE_GID:-2001}" ;;
	*) exit 99 ;;
esac
EOF
cat >"${fake_bin}/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "$1" in
	--version) printf 'Docker version client-fixture\n' ;;
	info)
		if [[ ${FAKE_DAEMON_UNAVAILABLE:-false} == true ]]; then
			printf 'daemon fixture unavailable\n' >&2
			exit 1
		fi
		printf '%s\n' "${FAKE_DAEMON_OS:-linux}"
		;;
	version)
		jq --null-input --arg version "${FAKE_DAEMON_VERSION:?}" \
			--arg api "${FAKE_DAEMON_API:-1.48}" '{Version: $version, ApiVersion: $api}'
		;;
	compose)
		shift
		while [[ $1 == --* ]]; do shift 2; done
		case "$1" in
			up)
				# Stop at fixture startup: these cases test preflight, not a fake daemon.
				: >"${FAKE_COMPOSE_STARTED:?}"
				exit 78
				;;
			down) exit 0 ;;
			*) exit 99 ;;
		esac
		;;
	*) exit 99 ;;
esac
EOF
chmod 0755 "${fake_bin}/id" "${fake_bin}/docker"

run_case() {
	rm -f "$FAKE_COMPOSE_STARTED"
	case_status=0
	env PATH="${fake_bin}:${PATH}" DOCKER_HOST=unix:///var/run/docker.sock \
		FAKE_DAEMON_VERSION=29.4.0 "$@" bash "$integration" >"$output" 2>&1 || case_status=$?
}

assert_rejected() {
	local message=$1
	[[ $case_status == 1 && ! -e $FAKE_COMPOSE_STARTED ]] ||
		fail "unsafe preflight reached fixture startup: ${message}"
	grep --fixed-strings "$message" "$output" >/dev/null ||
		fail "missing rejection diagnostic: ${message}"
}

# Current hosted runner and supported Engine families must reach real fixture checks.
for version in 28.0.4 28.5.1 29.0.1 29.4.0 29.8.2 29.10.0; do
	run_case FAKE_DAEMON_VERSION="$version"
	[[ $case_status == 78 && -f $FAKE_COMPOSE_STARTED ]] ||
		fail "supported Linux daemon ${version} rejected before fixture startup (exit ${case_status})"
	grep --fixed-strings "daemon ${version}; API 1.48" "$output" >/dev/null ||
		fail "missing daemon/API diagnostic for ${version}"
done

for version in 27.5.1 30.0.0 invalid; do
	run_case FAKE_DAEMON_VERSION="$version"
	assert_rejected "unsupported Docker Engine ${version}"
	grep --fixed-strings "daemon ${version}; API 1.48" "$output" >/dev/null ||
		fail "unsupported daemon ${version} was not recorded"
done

run_case FAKE_UID=0
assert_rejected 'requires UID 1001/GID 2001; got 0/2001'
run_case FAKE_GID=0
assert_rejected 'requires UID 1001/GID 2001; got 1001/0'
run_case DOCKER_HOST=tcp://unexpected:2375
assert_rejected 'requires explicitly supplied unix:///var/run/docker.sock'
run_case FAKE_DAEMON_OS=windows
assert_rejected 'requires a Linux Docker daemon; got windows'
run_case FAKE_DAEMON_UNAVAILABLE=true
assert_rejected 'cannot query the explicitly supplied Docker daemon'

printf 'Compose preflight verification passed\n'
