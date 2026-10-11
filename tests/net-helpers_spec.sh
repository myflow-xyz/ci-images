#!/usr/bin/env bash

set -euo pipefail

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
temporary_directory=$(mktemp -d)
trap 'rm -rf "$temporary_directory"' EXIT
mkdir -p "${temporary_directory}/bin"
export NET_HELPER_LOG="${temporary_directory}/docker.log"
export PATH="${temporary_directory}/bin:${PATH}"

fail() {
	printf 'net helper verification failed: %s\n' "$*" >&2
	exit 1
}

cat >"${temporary_directory}/bin/docker" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"${NET_HELPER_LOG:?}"
EOF
chmod 0755 "${temporary_directory}/bin/docker"

"${repository_root}/tests/build-local-image.sh" net
[[ $(wc -l <"$NET_HELPER_LOG" | tr -d ' ') == 2 ]] || fail 'net must build its base and itself'
grep -F -- '--tag ci-base:test ' "$NET_HELPER_LOG" >/dev/null || fail 'base build missing'
grep -F -- '--tag ci-net:test ' "$NET_HELPER_LOG" |
	grep -F -- '--build-arg BASE_IMAGE=ci-base:test ' >/dev/null || fail 'net build parent missing'

: >"$NET_HELPER_LOG"
"${repository_root}/tests/smoke-local.sh" net
[[ $(wc -l <"$NET_HELPER_LOG" | tr -d ' ') == 2 ]] || fail 'net and inherited Docker smoke checks required'
grep -F 'ci-net:test bash /tests/smoke/net.sh' "$NET_HELPER_LOG" |
	grep -F -- '--cap-drop=ALL ' |
	grep -F -- '--network=none ' |
	grep -F -- '--security-opt=no-new-privileges ' >/dev/null || fail 'net smoke isolation missing'
grep -F 'ci-net:test bash /tests/smoke/docker.sh' "$NET_HELPER_LOG" >/dev/null || fail 'inherited client contract missing'
if grep -E -- '--cap-add|--privileged|--network[= ]host' "$NET_HELPER_LOG"; then
	fail 'ordinary smoke checks acquired network privileges'
fi

printf 'net build and unprivileged smoke helper verification passed\n'
