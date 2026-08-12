#!/usr/bin/env bash

set -euo pipefail

scripts_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
helper="${scripts_root}/setup-runner-user.sh"

fail() {
	printf 'setup-runner-user integration failed: %s\n' "$*" >&2
	exit 1
}

((EUID == 0)) || fail 'run this test as root'

required_commands=(
	getent
	gpasswd
	groupadd
	groupdel
	id
	userdel
)

for command_name in "${required_commands[@]}"; do
	command -v "$command_name" >/dev/null 2>&1 ||
		fail "required command is unavailable: ${command_name}"
done

runner_user=ci-runner
runner_home=/opt/actions-runner
shared_group=mfci
shared_gid=2001
docker_group=docker
duplicate_group=mfci-duplicate-test
runner_created=false
runner_group_created=false
shared_group_created=false
docker_group_created=false
duplicate_group_created=false

cleanup() {
	local status=$?

	if $runner_created && getent passwd "$runner_user" >/dev/null; then
		userdel "$runner_user" >/dev/null 2>&1 || true
	fi
	if $runner_group_created && getent group "$runner_user" >/dev/null; then
		groupdel "$runner_user" >/dev/null 2>&1 || true
	fi
	if $duplicate_group_created && getent group "$duplicate_group" >/dev/null; then
		groupdel "$duplicate_group" >/dev/null 2>&1 || true
	fi
	if $shared_group_created && getent group "$shared_group" >/dev/null; then
		groupdel "$shared_group" >/dev/null 2>&1 || true
	fi
	if $docker_group_created && getent group "$docker_group" >/dev/null; then
		groupdel "$docker_group" >/dev/null 2>&1 || true
	fi
	exit "$status"
}
trap cleanup EXIT

[[ -z $(getent passwd "$runner_user" || true) ]] ||
	fail "test user already exists: ${runner_user}"
[[ -z $(getent group "$runner_user" || true) ]] ||
	fail "test private group already exists: ${runner_user}"
[[ -z $(getent group "$duplicate_group" || true) ]] ||
	fail "test duplicate group already exists: ${duplicate_group}"
[[ -z $(getent group "$docker_group" || true) ]] ||
	fail "test Docker group already exists: ${docker_group}"
[[ -z $(getent group "$shared_group" || true) ]] ||
	fail "test shared group already exists: ${shared_group}"
[[ -z $(getent group "$shared_gid" || true) ]] ||
	fail "test shared GID is already assigned: ${shared_gid}"

if missing_docker_output=$("$helper" --dry-run 2>&1); then
	fail 'identity helper accepted a missing docker group'
fi
[[ $missing_docker_output == *'required group must be local and resolve uniquely: docker'* ]] ||
	fail 'identity helper did not report the missing docker group'

groupadd --gid "$shared_gid" "$docker_group"
docker_group_created=true
if shared_docker_gid_output=$("$helper" 2>&1); then
	fail 'identity helper accepted docker as the shared GID assignment'
fi
[[ $shared_docker_gid_output == *"required group must not use shared GID ${shared_gid}: docker"* ]] ||
	fail 'identity helper did not report docker using the shared GID'
[[ -z $(getent passwd "$runner_user" || true) ]] ||
	fail 'identity helper created the runner user before rejecting docker GID reuse'
groupdel "$docker_group"
docker_group_created=false

groupadd "$docker_group"
docker_group_created=true
docker_record=$(getent group "$docker_group")
IFS=: read -r _ _ docker_gid _ <<<"$docker_record"

groupadd --gid "$shared_gid" "$duplicate_group"
duplicate_group_created=true
if occupied_gid_output=$("$helper" 2>&1); then
	fail 'identity helper accepted an occupied shared GID'
fi
[[ $occupied_gid_output == *"cannot create ${shared_group}: GID ${shared_gid} is already in use"* ]] ||
	fail 'identity helper did not report the occupied shared GID'
[[ -z $(getent passwd "$runner_user" || true) ]] ||
	fail 'identity helper created the runner user before rejecting an occupied GID'
groupdel "$duplicate_group"
duplicate_group_created=false

groupadd --gid "$shared_gid" "$shared_group"
shared_group_created=true
groupadd --non-unique --gid "$shared_gid" "$duplicate_group"
duplicate_group_created=true
if duplicate_gid_output=$("$helper" 2>&1); then
	fail 'identity helper accepted a duplicate shared GID assignment'
fi
[[ $duplicate_gid_output == *"shared GID does not resolve uniquely in /etc/group: ${shared_gid}"* ]] ||
	fail 'identity helper did not report the duplicate shared GID assignment'
[[ -z $(getent passwd "$runner_user" || true) ]] ||
	fail 'identity helper created the runner user before rejecting duplicate GID reuse'
[[ -z $(getent group "$runner_user" || true) ]] ||
	fail 'identity helper created the private group before rejecting duplicate GID reuse'
groupdel "$duplicate_group"
duplicate_group_created=false
groupdel "$shared_group"
shared_group_created=false

home_preexisting=false
if [[ -e $runner_home || -L $runner_home ]]; then
	home_preexisting=true
fi

dry_run_output=$("$helper" --dry-run)
[[ $dry_run_output == *'mode=dry-run user=ci-runner user-state=create home=/opt/actions-runner'* ]] ||
	fail 'dry-run reported the wrong user plan'
[[ $dry_run_output == *'shared-group=mfci(2001) shared-group-state=create'* ]] ||
	fail 'dry-run reported the wrong shared-group plan'
[[ $dry_run_output == *"docker-group=docker(${docker_gid}) docker-membership=missing shared-membership=missing"* ]] ||
	fail 'dry-run reported the wrong membership plan'
[[ $dry_run_output == *'dry-run status=ok'* ]] ||
	fail 'dry-run success was not reported'
[[ -z $(getent passwd "$runner_user" || true) ]] ||
	fail 'dry-run created the runner user'
[[ -z $(getent group "$runner_user" || true) ]] ||
	fail 'dry-run created the private group'
[[ -z $(getent group "$shared_group" || true) ]] ||
	fail 'dry-run created the shared group'

runner_created=true
runner_group_created=true
shared_group_created=true
apply_output=$("$helper")
[[ $apply_output == *'verified status=ok user=created shared-group=created memberships=present home=/opt/actions-runner home-directory=unmanaged'* ]] ||
	fail 'apply verification was not reported'

runner_record=$(getent passwd "$runner_user")
IFS=: read -r \
	resolved_user \
	_ \
	runner_uid \
	runner_primary_gid \
	_ \
	resolved_home \
	resolved_shell \
	<<<"$runner_record"
[[ $resolved_user == "$runner_user" &&
	$runner_uid =~ ^[0-9]+$ &&
	$runner_uid != 0 &&
	$resolved_home == "$runner_home" &&
	$resolved_shell == /bin/bash ]] ||
	fail "runner identity is wrong: ${runner_record}"

private_group_record=$(getent group "$runner_primary_gid")
IFS=: read -r private_group _ private_gid _ <<<"$private_group_record"
[[ $private_group == "$runner_user" && $private_gid == "$runner_primary_gid" ]] ||
	fail "private group is wrong: ${private_group_record}"

shared_record=$(getent group "$shared_group")
IFS=: read -r _ _ resolved_shared_gid _ <<<"$shared_record"
[[ $resolved_shared_gid == "$shared_gid" ]] ||
	fail "shared group is wrong: ${shared_record}"

configured_groups=" $(id -G "$runner_user") "
[[ $configured_groups == *" ${docker_gid} "* ]] ||
	fail 'runner is not a member of docker'
[[ $configured_groups == *" ${shared_gid} "* ]] ||
	fail 'runner is not a member of mfci'

if ! $home_preexisting; then
	[[ ! -e $runner_home && ! -L $runner_home ]] ||
		fail 'identity helper created the runner home directory'
fi

gpasswd --delete "$runner_user" "$docker_group" >/dev/null
configured_groups=" $(id -G "$runner_user") "
[[ $configured_groups != *" ${docker_gid} "* ]] ||
	fail 'test setup did not remove docker membership'

repair_output=$("$helper")
[[ $repair_output == *'docker-membership=missing shared-membership=present'* ]] ||
	fail 'repair run did not report the missing membership'
[[ $repair_output == *'verified status=ok user=present shared-group=present memberships=updated'* ]] ||
	fail 'membership repair was not reported'
configured_groups=" $(id -G "$runner_user") "
[[ $configured_groups == *" ${docker_gid} "* ]] ||
	fail 'runner docker membership was not repaired'

repeat_output=$("$helper")
[[ $repeat_output == *'user-state=existing'* ]] ||
	fail 'repeat run did not recognize the existing user'
[[ $repeat_output == *'shared-group-state=existing'* ]] ||
	fail 'repeat run did not recognize the existing shared group'
[[ $repeat_output == *'docker-membership=present shared-membership=present'* ]] ||
	fail 'repeat run did not recognize configured memberships'
[[ $repeat_output == *'verified status=ok user=present shared-group=present memberships=present'* ]] ||
	fail 'repeat verification was not reported'

printf 'setup-runner-user integration passed\n'
