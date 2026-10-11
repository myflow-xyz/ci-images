#!/usr/bin/env bash

set -euo pipefail

: "${EXPECTED_CI_UID:?EXPECTED_CI_UID is not set}"
: "${EXPECTED_CI_GID:?EXPECTED_CI_GID is not set}"

[[ $(id -u) == "$EXPECTED_CI_UID" ]]
[[ $(id -g) == "$EXPECTED_CI_GID" ]]
[[ $HOME == /home/ci && $TMPDIR == /var/tmp && $PWD == /workspace ]]
[[ ! -S /var/run/docker.sock ]]

for package in nftables iproute2 iputils-ping wireguard-tools tcpdump; do
	[[ $(dpkg-query -W -f='${db:Status-Status}' "$package") == installed ]]
done
while IFS='=' read -r package version; do
	[[ $(dpkg-query -W -f='${Version}' "$package") == "$version" ]]
done </usr/local/share/ci/net-debian-packages.lock

for tool in nft ip ss tc ping wg wg-quick tcpdump; do
	command -v "$tool" >/dev/null
	[[ ! -w $(command -v "$tool") ]]
done
nft --version
ip -Version
ss --version
tc -Version
ping -V
wg --version
wg-quick --help >/dev/null
tcpdump --version

if dpkg-query -W -f='${binary:Package} ${db:Status-Status}\n' |
	grep -E '^(wireguard|linux-image-[^ ]+) installed$' >/dev/null; then
	printf 'WireGuard metapackage or kernel image leaked into the runtime\n' >&2
	exit 1
fi

# Installing ping must not bypass the runtime capability boundary.
[[ -z $(getcap /usr/bin/ping) ]]
[[ ! -u /usr/bin/ping && ! -g /usr/bin/ping ]]
python3 - <<'PY'
from pathlib import Path

status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines() if ":" in line)
assert int(status["CapEff"], 16) == 0, "ordinary smoke checks must have no effective capabilities"
PY

printf 'ci-net package, command, and unprivileged runtime checks passed\n'
