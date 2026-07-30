#!/usr/bin/env bash

set -euo pipefail

expected_uid=${EXPECTED_CI_UID:?EXPECTED_CI_UID is not set}
expected_gid=${EXPECTED_CI_GID:?EXPECTED_CI_GID is not set}
foreign_uid=2002
workspace=/__w/example/example
untrusted_repository=/var/tmp/untrusted-repository

[[ $foreign_uid != "$expected_uid" ]]

git config --system --get-all safe.directory |
	grep --fixed-strings --line-regexp '/__w/*' >/dev/null
if git config --system --get-all safe.directory |
	grep --fixed-strings --line-regexp '*' >/dev/null; then
	printf 'Git ownership checks must not be disabled globally\n' >&2
	exit 1
fi

initialize_repository() {
	local repository=$1

	install \
		--directory \
		--mode 2770 \
		--owner "$foreign_uid" \
		--group "$expected_gid" \
		"$repository"

	# shellcheck disable=SC2016
	chroot \
		--userspec="${foreign_uid}:${expected_gid}" \
		/ \
		/usr/bin/env \
		HOME=/var/tmp \
		/bin/bash \
		-c '
		set -euo pipefail
		repository=$1
		git -C "$repository" init --quiet
		git -C "$repository" config user.email ci@example.invalid
		git -C "$repository" config user.name CI
		printf "tracked\n" >"${repository}/tracked"
		git -C "$repository" add tracked
		git -C "$repository" commit --quiet --message initial
	' \
		_ \
		"$repository"
}

initialize_repository "$workspace"
[[ $(stat --format %u "$workspace") == "$foreign_uid" ]]

status=$(
	chroot \
		--userspec="${expected_uid}:${expected_gid}" \
		/ \
		/usr/bin/env \
		HOME=/home/ci \
		git \
		-C "$workspace" \
		status \
		--short
)
[[ -z $status ]]

initialize_repository "$untrusted_repository"
if chroot \
	--userspec="${expected_uid}:${expected_gid}" \
	/ \
	/usr/bin/env \
	HOME=/home/ci \
	git \
	-C "$untrusted_repository" \
	status \
	--short \
	>/var/tmp/untrusted-git.out 2>&1; then
	printf 'Git accepted a foreign-owned repository outside trusted roots\n' >&2
	exit 1
fi
grep --fixed-strings 'detected dubious ownership' /var/tmp/untrusted-git.out \
	>/dev/null
