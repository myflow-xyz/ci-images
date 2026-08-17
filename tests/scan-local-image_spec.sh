#!/usr/bin/env bash

set -euo pipefail

repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
scan_local_image="${repository_root}/tests/scan-local-image.sh"

fail() {
	printf 'local scan verification failed: %s\n' "$*" >&2
	exit 1
}

temporary_directory=$(mktemp -d)
trap 'rm -rf "$temporary_directory"' EXIT

fake_bin="${temporary_directory}/bin"
fake_log="${temporary_directory}/trivy-log"
mkdir -p "$fake_bin"
: >"$fake_log"

cat >"${fake_bin}/trivy" <<'EOF'
#!/usr/bin/env bash

set -euo pipefail

printf '%s\n' "$*" >>"${FAKE_TRIVY_LOG:?}"

if [[ ${!#} == "${FAKE_TRIVY_FAIL_IMAGE:-}" ]]; then
	exit 1
fi
EOF
chmod 0755 "${fake_bin}/trivy"

export FAKE_TRIVY_LOG="$fake_log"
export PATH="${fake_bin}:${PATH}"

expected_policy='image --image-src docker --scanners vuln --pkg-types os,library --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 --format table --timeout 20m'

"$scan_local_image" base >/dev/null
[[ $(wc -l <"$fake_log" | tr -d ' ') == 1 ]] ||
	fail 'base target scan count'
grep --fixed-strings --line-regexp \
	"${expected_policy} ci-base:test" \
	"$fake_log" \
	>/dev/null || fail 'base target scan policy'

: >"$fake_log"
"$scan_local_image" all >/dev/null
[[ $(wc -l <"$fake_log" | tr -d ' ') == 6 ]] ||
	fail 'all target scan count'
for name in base go node vite playwright postgres; do
	grep --fixed-strings --line-regexp \
		"${expected_policy} ci-${name}:test" \
		"$fake_log" \
		>/dev/null || fail "all target missing ci-${name}:test"
done

: >"$fake_log"
if FAKE_TRIVY_FAIL_IMAGE=ci-node:test "$scan_local_image" all >/dev/null; then
	fail 'scanner finding did not fail the helper'
fi
grep --fixed-strings 'ci-postgres:test' "$fake_log" >/dev/null ||
	fail 'scan stopped after the first failing image'

: >"$fake_log"
if "$scan_local_image" unsupported >/dev/null 2>&1; then
	fail 'unsupported target was accepted'
else
	unsupported_status=$?
fi
[[ $unsupported_status == 64 ]] || fail 'unsupported target status'
[[ ! -s $fake_log ]] || fail 'unsupported target invoked trivy'

printf 'local scan verification passed\n'
