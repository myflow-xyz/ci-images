#!/usr/bin/env bash

set -euo pipefail

: "${EXPECTED_BUILDX_VERSION:?EXPECTED_BUILDX_VERSION is not set}"
: "${EXPECTED_BUILDX_X_NET_VERSION:?EXPECTED_BUILDX_X_NET_VERSION is not set}"
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
for tool in ci-utils ci-utils-list ci-docker-cleanup ci-remove-images ci-buildkit-probe ci-go-cleanup ci-pnpm-cleanup; do
	[[ $(command -v "$tool") == "/opt/ci-tools/bin/${tool}" ]]
	[[ ! -w $(command -v "$tool") ]]
done

ci-utils | grep --fixed-strings ci-docker-cleanup >/dev/null
ci-utils | grep --fixed-strings ci-remove-images >/dev/null
ci-utils | grep --fixed-strings ci-go-cleanup >/dev/null
ci-utils | grep --fixed-strings ci-pnpm-cleanup >/dev/null
ci-utils-list | grep --fixed-strings ci-go-cleanup >/dev/null
ci-utils-list | grep --fixed-strings ci-pnpm-cleanup >/dev/null
for tool in ci-utils-list ci-go-cleanup ci-pnpm-cleanup; do
	"$tool" -h | grep --fixed-strings 'Examples:' >/dev/null
done
ci-go-cleanup --help | grep --fixed-strings 'preview only' >/dev/null
ci-pnpm-cleanup --help | grep --fixed-strings 'preview only' >/dev/null
ci-remove-images --help | grep --fixed-strings 'dry-run' >/dev/null
ci-docker-cleanup --help | grep --fixed-strings 'check,plan,apply,version' >/dev/null
ci-docker-cleanup version | python3 -c '
import json, sys
value = json.load(sys.stdin)
assert value["event"] == "version"
assert value["policy_schema"] == 1 and value["host_protocol"] == 1
assert value["revision"] not in ("unknown", "unbuilt", "")
'
docker buildx version | grep --fixed-strings "v${EXPECTED_BUILDX_VERSION}" >/dev/null
grep --binary-files=text --fixed-strings \
	$'dep\tgolang.org/x/net\t'"${EXPECTED_BUILDX_X_NET_VERSION}"$'\t' \
	"/opt/ci-tools/buildx/${EXPECTED_BUILDX_VERSION}/docker-buildx" >/dev/null
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
python3 -B - <<'PY'
import json
import pathlib
import subprocess
import tempfile

with tempfile.TemporaryDirectory(prefix="ci-cache-smoke-") as directory:
    root = pathlib.Path(directory)
    caches = [root / name for name in ("go/build", "go/mod", "pnpm/store")]
    identities = []
    for cache in caches:
        cache.mkdir(parents=True, mode=0o2770)
        nested = cache / "nested"
        nested.mkdir()
        (nested / "data").write_text("disposable fixture")
        nested.chmod(0o555)
        info = cache.stat()
        identities.append((info.st_ino, info.st_mode, info.st_uid, info.st_gid))
    for command in (
        ["ci-go-cleanup", "--build-cache", str(caches[0]), "--mod-cache", str(caches[1])],
        ["ci-pnpm-cleanup", "--store-dir", str(caches[2])],
    ):
        preview = subprocess.run(command, capture_output=True, text=True, check=True, timeout=10)
        result = json.loads(preview.stdout.splitlines()[-1])
        assert result["mode"] == "plan" and not result["mutation_started"]
        selected = caches[:2] if command[0] == "ci-go-cleanup" else caches[2:]
        assert all((cache / "nested/data").is_file() for cache in selected)
        applied = subprocess.run(command + ["--apply"], capture_output=True, text=True, check=True, timeout=10)
        assert json.loads(applied.stdout.splitlines()[-1])["status"] == "success"
    for cache, identity in zip(caches, identities):
        info = cache.stat()
        assert (info.st_ino, info.st_mode, info.st_uid, info.st_gid) == identity
        assert not list(cache.iterdir())
PY
printf 'ci-utils direct commands and offline non-root discovery passed\n'
