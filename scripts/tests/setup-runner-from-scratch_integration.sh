#!/usr/bin/env bash

set -euo pipefail

scripts_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
bootstrap_source="${scripts_root}/setup-runner-from-scratch.sh"
permission_helper_source="${scripts_root}/setup-runner-permissions.sh"

fail() {
	printf 'setup-runner-from-scratch integration failed: %s\n' "$*" >&2
	exit 1
}

((EUID == 0)) || fail 'run this test as root'

required_commands=(
	groupdel
	getent
	getfacl
	install
	setpriv
	stat
	useradd
	userdel
)

for command_name in "${required_commands[@]}"; do
	command -v "$command_name" >/dev/null 2>&1 ||
		fail "required command is unavailable: ${command_name}"
done

temporary_directory=$(mktemp -d --tmpdir=/var/tmp mfci-bootstrap.XXXXXX)
owner_name="mfci-bootstrap-$$"
owner_created=false
owner_group_created=false
mfci_created=false

cleanup() {
	local status=$?

	rm -rf -- "$temporary_directory"
	if $owner_created && getent passwd "$owner_name" >/dev/null; then
		userdel "$owner_name" >/dev/null 2>&1 || true
	fi
	if $owner_group_created && getent group "$owner_name" >/dev/null; then
		groupdel "$owner_name" >/dev/null 2>&1 || true
	fi
	if $mfci_created && getent group mfci >/dev/null; then
		groupdel mfci >/dev/null 2>&1 || true
	fi
	exit "$status"
}
trap cleanup EXIT
chmod 0755 "$temporary_directory"

helper_directory="${temporary_directory}/helpers"
mkdir "$helper_directory"
helper="${helper_directory}/setup-runner-from-scratch.sh"
permission_helper="${helper_directory}/setup-runner-permissions.sh"
install --mode 0755 "$bootstrap_source" "$helper"
install \
	--mode 0755 \
	"$permission_helper_source" \
	"$permission_helper"

if mfci_record=$(getent group mfci); then
	IFS=: read -r group_name _ group_gid _ <<<"$mfci_record"
	[[ $group_name == mfci && $group_gid == 2001 ]] ||
		fail "existing mfci group does not use GID 2001: ${mfci_record}"
	expected_group_state=existing
	expected_group_result=present
else
	[[ -z $(getent group 2001 || true) ]] ||
		fail 'GID 2001 is already assigned to another group'
	group_name=mfci
	group_gid=2001
	mfci_created=true
	expected_group_state=create
	expected_group_result=created
fi

if getent passwd "$owner_name" >/dev/null; then
	fail "test owner already exists: ${owner_name}"
fi
if getent group "$owner_name" >/dev/null; then
	fail "test owner group already exists: ${owner_name}"
fi
useradd \
	--system \
	--no-create-home \
	--user-group \
	--shell /usr/sbin/nologin \
	"$owner_name"
owner_created=true
owner_group_created=true
owner_record=$(getent passwd "$owner_name")
[[ -n $owner_record ]] || fail 'test owner is unavailable'
IFS=: read -r _ _ owner_uid owner_gid _ _ _ <<<"$owner_record"

owner_has_group() {
	local current_gid

	for current_gid in $(id -G "$owner_name"); do
		[[ $current_gid != "$group_gid" ]] || return 0
	done
	return 1
}

owner_has_group &&
	fail 'new test owner unexpectedly has the shared group'

failure_output="${temporary_directory}/failure-output"
assert_fails_with() {
	local label=$1
	local expected=$2
	shift 2

	if "$@" >"$failure_output" 2>&1; then
		fail "${label} succeeded"
	fi
	grep -Fq -- "$expected" "$failure_output" ||
		fail "${label} did not report: ${expected}"
}

assert_fails_with \
	'root alias' \
	'resolved runner root must not be /' \
	"$helper" \
	--runner-root /tmp/.. \
	--owner "$owner_name" \
	--repository repo-example \
	--dry-run

assert_fails_with \
	'top-level runner root' \
	'runner root must resolve below /opt, /var, /home, or /Users: /tmp' \
	"$helper" \
	--runner-root /tmp \
	--owner "$owner_name" \
	--repository repo-example \
	--dry-run

assert_fails_with \
	'unapproved runner root' \
	'runner root must resolve below /opt, /var, /home, or /Users: /usr/local' \
	"$helper" \
	--runner-root /usr/local \
	--owner "$owner_name" \
	--repository repo-example \
	--dry-run

assert_fails_with \
	'unmarked existing runner root' \
	'existing runner root is not helper-managed; marker is missing: /var/tmp/.mfci-runner-root' \
	"$helper" \
	--runner-root /var/tmp \
	--owner "$owner_name" \
	--repository repo-example \
	--dry-run

if [[ $expected_group_state == create ]]; then
	[[ -z $(getent group mfci || true) ]] ||
		fail 'unsafe root validation created the default group'
fi
owner_has_group &&
	fail 'unsafe root validation changed owner group membership'

runner_root="${temporary_directory}/runner root"
repository=repo-example

dry_run_output=$(
	"$helper" \
		--runner-root "$runner_root" \
		--owner "$owner_uid" \
		--repository "$repository" \
		--dry-run
)
[[ $dry_run_output == *'mode=dry-run'* ]] ||
	fail 'dry-run mode was not reported'
[[ $dry_run_output == *'root-state=create'* ]] ||
	fail 'dry-run reported the wrong runner-root state'
[[ $dry_run_output == *"group-state=${expected_group_state} configured-membership=add"* ]] ||
	fail 'dry-run reported the wrong identity plan'
[[ $dry_run_output == *'create=8 existing=0'* ]] ||
	fail 'dry-run reported the wrong directory plan'
[[ $dry_run_output == *'dry-run status=ok directories=8'* ]] ||
	fail 'dry-run success was not reported'
[[ ! -e $runner_root ]] ||
	fail 'dry-run created the runner root'
if [[ $expected_group_state == create ]]; then
	[[ -z $(getent group mfci || true) ]] ||
		fail 'dry-run created the default group'
fi
owner_has_group &&
	fail 'dry-run changed owner group membership'

apply_output=$(
	"$helper" \
		--runner-root "$runner_root" \
		--owner "$owner_name" \
		--repository "$repository"
)
[[ $apply_output == *'setup-runner-permissions.sh: verified status=ok'* ]] ||
	fail 'permission-helper success was not reported'
[[ $apply_output == *"setup-runner-from-scratch.sh: verified status=ok directories=8 permission-helper=ok group=${expected_group_result} membership=added restart-required=yes"* ]] ||
	fail 'bootstrap verification was not reported'
runner_marker="${runner_root}/.mfci-runner-root"
[[ -f $runner_marker && ! -L $runner_marker ]] ||
	fail 'bootstrap did not create the runner-root marker'
[[ $(stat --format '%u:%g:%a' "$runner_marker") == 0:0:444 ]] ||
	fail 'runner-root marker identity is wrong'
mfci_record=$(getent group mfci)
IFS=: read -r group_name _ group_gid _ <<<"$mfci_record"
[[ $group_name == mfci && $group_gid == 2001 ]] ||
	fail "default group has the wrong identity: ${mfci_record}"
owner_has_group ||
	fail 'bootstrap did not add the owner to the shared group'

repository_root="${runner_root}/workspace/${repository}"
work_root="${repository_root}/_work"
shared_root="${runner_root}/shared"

declare -a unmanaged_directories=(
	"$runner_root"
	"${runner_root}/workspace"
	"$repository_root"
	"$shared_root"
	"${shared_root}/bin"
	"${shared_root}/downloads"
)

for directory in "${unmanaged_directories[@]}"; do
	[[ -d $directory && ! -L $directory ]] ||
		fail "unmanaged directory is missing: ${directory}"
	[[ $(stat --format '%u:%g:%a' "$directory") == "${owner_uid}:${owner_gid}:755" ]] ||
		fail "unmanaged directory identity is wrong: ${directory}"
done

for directory in "$work_root" "${shared_root}/cache"; do
	[[ -d $directory && ! -L $directory ]] ||
		fail "managed directory is missing: ${directory}"
	[[ $(stat --format '%u:%g:%a' "$directory") == "${owner_uid}:${group_gid}:2770" ]] ||
		fail "managed directory identity is wrong: ${directory}"
done

check_output=$(
	setpriv \
		--reuid "$owner_uid" \
		--regid "$owner_gid" \
		--init-groups \
		"$permission_helper" \
		--runner-root "$runner_root" \
		--owner "$owner_name" \
		--group "$group_name" \
		--check
)
[[ $check_output == *'verified status=ok mode=check targets=2'* ]] ||
	fail 'delegated permission state did not pass check mode'

printf 'bin\n' >"${shared_root}/bin/preserved"
printf 'download\n' >"${shared_root}/downloads/preserved"
chown \
	"${owner_uid}:${owner_gid}" \
	"${shared_root}/bin/preserved" \
	"${shared_root}/downloads/preserved"
chmod 0640 \
	"${shared_root}/bin/preserved" \
	"${shared_root}/downloads/preserved"

repeat_output=$(
	"$helper" \
		--runner-root "$runner_root" \
		--owner "$owner_name" \
		--repository "$repository"
)
[[ $repeat_output == *'create=0 existing=8'* ]] ||
	fail 'repeat run did not recognize the existing structure'
[[ $repeat_output == *'root-state=existing'* ]] ||
	fail 'repeat run did not recognize the managed runner root'
[[ $repeat_output == *'group-state=existing configured-membership=present'* ]] ||
	fail 'repeat run did not recognize the existing identity state'
[[ $repeat_output == *'group=present membership=present'* ]] ||
	fail 'repeat run did not preserve the existing identity state'
[[ $(cat "${shared_root}/bin/preserved") == bin ]] ||
	fail 'repeat run changed shared bin content'
[[ $(cat "${shared_root}/downloads/preserved") == download ]] ||
	fail 'repeat run changed shared download content'
[[ $(stat --format '%u:%g:%a' "${shared_root}/bin/preserved") == "${owner_uid}:${owner_gid}:640" ]] ||
	fail 'repeat run changed shared bin file policy'
[[ $(stat --format '%u:%g:%a' "${shared_root}/downloads/preserved") == "${owner_uid}:${owner_gid}:640" ]] ||
	fail 'repeat run changed shared download file policy'

linked_root="${temporary_directory}/linked-root"
linked_target="${temporary_directory}/linked-target"
mkdir -p "$linked_target"
ln -s "$linked_target" "$linked_root"
assert_fails_with \
	'linked runner root' \
	"runner root must be a real directory: ${linked_root}" \
	"$helper" \
	--runner-root "$linked_root" \
	--owner "$owner_name" \
	--repository "$repository" \
	--dry-run

conflict_root="${temporary_directory}/conflict-root"
mkdir -p "$conflict_root"
chmod 0700 "$conflict_root"
install \
	--owner 0 \
	--group 0 \
	--mode 0444 \
	/dev/null \
	"${conflict_root}/.mfci-runner-root"
printf 'conflict\n' >"${conflict_root}/workspace"
assert_fails_with \
	'non-directory target' \
	"target must be a real directory: ${conflict_root}/workspace" \
	"$helper" \
	--runner-root "$conflict_root" \
	--owner "$owner_name" \
	--repository "$repository"
[[ $(cat "${conflict_root}/workspace") == conflict ]] ||
	fail 'target validation changed the conflicting entry'
[[ $(stat --format %a "$conflict_root") == 700 ]] ||
	fail 'target validation changed the runner root'

printf 'setup-runner-from-scratch integration passed\n'
