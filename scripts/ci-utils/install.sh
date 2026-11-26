#!/bin/sh
# Keep this first check readable by /bin/sh and by older Bash releases.
if ! command -v bash >/dev/null 2>&1; then
	printf 'ci-utils requires Bash >= 5.0 (detected: missing)\n' >&2
	exit 2
fi
exec bash -s -- "$@" <<'CI_UTILS_INSTALL'
if [ "${BASH_VERSINFO[0]}" -lt 5 ]; then
	printf 'ci-utils requires Bash >= 5.0 (detected: %s)\n' "$BASH_VERSION" >&2
	exit 2
fi
set -euo pipefail
umask 022

fail() {
	printf 'ci-utils: %s\n' "$*" >&2
	exit 2
}

usage='install.sh X.Y.Z [--prefix ABSOLUTE_PATH] [--from-dir TRUSTED_RELEASE_DIRECTORY]'
[[ ${1:-} != --help ]] || {
	echo "$usage"
	exit 0
}
version=${1:-}
[[ $version =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || fail "$usage"
shift
prefix=
source_dir=
while (($#)); do
	case "$1" in
	--prefix)
		[[ ${2:-} == /* ]] || fail "$usage"
		prefix=$2
		;;
	--from-dir)
		[[ -d ${2:-} ]] || fail "$usage"
		source_dir=$2
		;;
	*) fail "$usage" ;;
	esac
	shift 2
done

command -v python3 >/dev/null || fail 'requires Python >= 3.9 (detected: missing)'
python3 -Ic 'import sys; sys.exit(sys.version_info < (3, 9))' ||
	fail "requires Python >= 3.9 (detected: $(python3 --version 2>&1))"
[[ -x /usr/bin/env ]] || fail 'requires executable /usr/bin/env (detected: missing)'
for tool in uname readlink docker curl sha256sum tar gzip mktemp cp rm; do
	command -v "$tool" >/dev/null || fail "requires executable $tool (detected: missing)"
done
[[ $(uname -s) == Linux ]] || fail "requires Linux (detected: $(uname -s))"
case "$(uname -m)" in
x86_64) arch=amd64 ;;
aarch64 | arm64) arch=arm64 ;;
*) fail "requires Linux amd64 or arm64 (detected: $(uname -m))" ;;
esac
readlink -f / >/dev/null || fail 'requires readlink -f (detected: unsupported)'
user_directory=()
if [[ -z $prefix ]]; then
	if ((EUID == 0)); then
		prefix=/usr/local
	else
		[[ ${HOME:-} == /* ]] || fail 'per-user installation requires an absolute HOME'
		prefix="$HOME/.local"
		data=${XDG_DATA_HOME:-}
		[[ $data == /* ]] || data="$prefix/share"
		user_directory=("$data/ci-utils")
	fi
fi
python3 -Ic 'import fcntl, hashlib, http.client, json, pathlib, socketserver, ssl, subprocess, urllib.request' ||
	fail 'requires the Python standard library with Linux, HTTPS and SHA-256 support (detected: incomplete)'
docker --version >/dev/null || fail 'requires a working Docker CLI (detected: unusable)'
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
docker --config "$work" buildx version >/dev/null 2>&1 ||
	fail 'requires Docker Buildx (detected: missing or unusable with a clean Docker configuration)'
base="ci-utils_${version}_linux_${arch}"
archive="$base.tar.gz"
sums="ci-utils_${version}_SHA256SUMS"
fetch() {
	if [[ -n $source_dir ]]; then
		cp -- "$source_dir/$1" "$work/$1"
	else
		curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
			--output "$work/$1" "https://github.com/myflow-xyz/ci-images/releases/download/v$version/$1"
	fi
}
fetch "$sums"
fetch "$archive"
digest=
while read -r hash name; do
	[[ $name == "$archive" ]] || continue
	[[ -z $digest && $hash =~ ^[a-f0-9]{64}$ ]] || fail "invalid checksum for $archive"
	digest=$hash
done <"$work/$sums"
[[ -n $digest ]] || fail "release checksum missing for $archive"
(
	cd "$work"
	printf '%s  %s\n' "$digest" "$archive" | sha256sum --check --status || fail "checksum mismatch for $archive"
	tar --no-same-owner -xzf "$archive"
	[[ -f $base/lib/activate.py ]] || fail "archive does not contain the expected version $version and architecture $arch"
	python3 -IB "$base/lib/activate.py" "$prefix" "$version" "$arch" "$digest" "${user_directory[@]}"
)
CI_UTILS_INSTALL
