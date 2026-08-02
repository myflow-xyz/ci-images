#!/usr/bin/env bash

set -euo pipefail

LC_ALL=C
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export LC_ALL PATH

readonly program_name=${0##*/}
readonly runner_user=ci-runner
readonly runner_home=/opt/actions-runner
readonly runner_shell=/bin/bash
readonly shared_group=mfci
readonly shared_group_gid=2001
readonly docker_group=docker
dry_run=false

usage() {
	printf '%s\n' \
		"Usage: ${program_name} [options]" \
		'' \
		'Create or verify this self-hosted runner identity:' \
		'  user:              ci-runner' \
		'  home:              /opt/actions-runner' \
		'  primary group:     ci-runner' \
		'  shared group:      mfci (GID 2001)' \
		'  additional groups: docker, mfci' \
		'' \
		'Options:' \
		'  --dry-run          Resolve and report without changing the host' \
		'  -h, --help         Show this help' \
		'' \
		'The docker group must already exist.' \
		'Docker group membership grants control of the Docker daemon.' \
		'The home path is configured on the account but created by the directory helper.' \
		'Run as root, for example with sudo.'
}

usage_error() {
	printf '%s: %s\n' "$program_name" "$*" >&2
	printf 'Try %s --help for usage.\n' "$program_name" >&2
	exit 64
}

fail() {
	printf '%s: %s\n' "$program_name" "$*" >&2
	exit 1
}

while (($# > 0)); do
	case "$1" in
	--dry-run)
		dry_run=true
		shift
		;;
	-h | --help)
		usage
		exit 0
		;;
	--)
		shift
		(($# == 0)) || usage_error 'positional arguments are not supported'
		;;
	-*)
		usage_error "unknown option: $1"
		;;
	*)
		usage_error "unexpected argument: $1"
		;;
	esac
done

((EUID == 0)) ||
	fail 'run as root (for example, with sudo)'

required_commands=(
	getent
	groupadd
	id
	useradd
	usermod
)

for command_name in "${required_commands[@]}"; do
	command -v "$command_name" >/dev/null 2>&1 ||
		fail "required command is unavailable: ${command_name}"
done

declare -a docker_group_records=()
mapfile -t docker_group_records < <(getent group "$docker_group" || true)
((${#docker_group_records[@]} == 1)) ||
	fail "required group does not resolve uniquely: ${docker_group}"
IFS=: read -r resolved_docker_group _ docker_group_gid _ \
	<<<"${docker_group_records[0]}"
[[ $resolved_docker_group == "$docker_group" && $docker_group_gid =~ ^[0-9]+$ ]] ||
	fail "required group has an invalid identity: ${docker_group}"
((docker_group_gid != 0)) ||
	fail "required group must not be root: ${docker_group}"

shared_group_state=existing
declare -a shared_group_records=()
mapfile -t shared_group_records < <(getent group "$shared_group" || true)
if ((${#shared_group_records[@]} == 0)); then
	declare -a shared_gid_records=()
	mapfile -t shared_gid_records < <(getent group "$shared_group_gid" || true)
	((${#shared_gid_records[@]} == 0)) ||
		fail "cannot create ${shared_group}: GID ${shared_group_gid} is already in use"
	shared_group_state=create
else
	((${#shared_group_records[@]} == 1)) ||
		fail "shared group does not resolve uniquely: ${shared_group}"
	IFS=: read -r resolved_shared_group _ resolved_shared_gid _ \
		<<<"${shared_group_records[0]}"
	[[ $resolved_shared_group == "$shared_group" &&
		$resolved_shared_gid == "$shared_group_gid" ]] ||
		fail "${shared_group} must use GID ${shared_group_gid}, found ${resolved_shared_gid}"
fi

user_state=existing
declare -a user_records=()
mapfile -t user_records < <(getent passwd "$runner_user" || true)
if ((${#user_records[@]} == 0)); then
	declare -a private_group_records=()
	mapfile -t private_group_records < <(getent group "$runner_user" || true)
	((${#private_group_records[@]} == 0)) ||
		fail "cannot create ${runner_user}: group already exists without the user"
	user_state=create
	docker_membership=missing
	shared_membership=missing
else
	((${#user_records[@]} == 1)) ||
		fail "user does not resolve uniquely: ${runner_user}"
	IFS=: read -r \
		resolved_user \
		_ \
		runner_uid \
		runner_primary_gid \
		_ \
		resolved_home \
		resolved_shell \
		<<<"${user_records[0]}"
	[[ $resolved_user == "$runner_user" &&
		$runner_uid =~ ^[0-9]+$ &&
		$runner_primary_gid =~ ^[0-9]+$ ]] ||
		fail "user has an invalid identity: ${runner_user}"
	((runner_uid != 0)) ||
		fail "user must not be root: ${runner_user}"
	[[ $resolved_home == "$runner_home" ]] ||
		fail "user has an unexpected home: ${runner_user} expected=${runner_home} actual=${resolved_home}"
	[[ $resolved_shell == "$runner_shell" ]] ||
		fail "user has an unexpected shell: ${runner_user} expected=${runner_shell} actual=${resolved_shell}"

	declare -a primary_group_records=()
	mapfile -t primary_group_records < <(getent group "$runner_primary_gid" || true)
	((${#primary_group_records[@]} == 1)) ||
		fail "primary group does not resolve uniquely: ${runner_user}/${runner_primary_gid}"
	IFS=: read -r primary_group_name _ primary_group_gid _ \
		<<<"${primary_group_records[0]}"
	[[ $primary_group_name == "$runner_user" &&
		$primary_group_gid == "$runner_primary_gid" ]] ||
		fail "user must use private primary group: ${runner_user}"

	configured_groups=$(id -G "$runner_user") ||
		fail "cannot resolve configured groups: ${runner_user}"
	docker_membership=missing
	shared_membership=missing
	for configured_gid in $configured_groups; do
		[[ $configured_gid != "$docker_group_gid" ]] || docker_membership=present
		[[ $configured_gid != "$shared_group_gid" ]] || shared_membership=present
	done
fi

mode=apply
$dry_run && mode=dry-run
printf \
	'%s: plan mode=%s user=%s user-state=%s home=%s primary-group=%s shared-group=%s(%s) shared-group-state=%s docker-group=%s(%s) docker-membership=%s shared-membership=%s\n' \
	"$program_name" \
	"$mode" \
	"$runner_user" \
	"$user_state" \
	"$runner_home" \
	"$runner_user" \
	"$shared_group" \
	"$shared_group_gid" \
	"$shared_group_state" \
	"$docker_group" \
	"$docker_group_gid" \
	"$docker_membership" \
	"$shared_membership"

if $dry_run; then
	printf '%s: dry-run status=ok\n' "$program_name"
	exit 0
fi

shared_group_result=present
if [[ $shared_group_state == create ]]; then
	groupadd --gid "$shared_group_gid" "$shared_group" ||
		fail "cannot create group: ${shared_group}(${shared_group_gid})"
	shared_group_result=created
fi

user_result=present
membership_result=present
if [[ $user_state == create ]]; then
	useradd \
		--home-dir "$runner_home" \
		--no-create-home \
		--shell "$runner_shell" \
		--user-group \
		--groups "${docker_group},${shared_group}" \
		"$runner_user" ||
		fail "cannot create user: ${runner_user}"
	user_result=created
elif [[ $docker_membership == missing || $shared_membership == missing ]]; then
	usermod \
		--append \
		--groups "${docker_group},${shared_group}" \
		"$runner_user" ||
		fail "cannot configure supplementary groups: ${runner_user}"
	membership_result=updated
fi

verified_user_record=$(getent passwd "$runner_user") ||
	fail "created user is unavailable: ${runner_user}"
IFS=: read -r \
	verified_user \
	_ \
	verified_uid \
	verified_primary_gid \
	_ \
	verified_home \
	verified_shell \
	<<<"$verified_user_record"
[[ $verified_user == "$runner_user" &&
	$verified_uid =~ ^[0-9]+$ &&
	$verified_uid != 0 &&
	$verified_primary_gid =~ ^[0-9]+$ &&
	$verified_home == "$runner_home" &&
	$verified_shell == "$runner_shell" ]] ||
	fail "user verification failed: ${runner_user}"

verified_primary_group_record=$(getent group "$verified_primary_gid") ||
	fail "private primary group is unavailable: ${runner_user}/${verified_primary_gid}"
IFS=: read -r verified_primary_group _ verified_group_gid _ \
	<<<"$verified_primary_group_record"
[[ $verified_primary_group == "$runner_user" &&
	$verified_group_gid == "$verified_primary_gid" ]] ||
	fail "private primary group verification failed: ${runner_user}"

verified_shared_group_record=$(getent group "$shared_group") ||
	fail "shared group is unavailable: ${shared_group}"
IFS=: read -r verified_shared_group _ verified_shared_gid _ \
	<<<"$verified_shared_group_record"
[[ $verified_shared_group == "$shared_group" &&
	$verified_shared_gid == "$shared_group_gid" ]] ||
	fail "shared group verification failed: ${shared_group}(${shared_group_gid})"

verified_groups=$(id -G "$runner_user") ||
	fail "cannot verify configured groups: ${runner_user}"
docker_membership_verified=false
shared_membership_verified=false
for verified_gid in $verified_groups; do
	[[ $verified_gid != "$docker_group_gid" ]] || docker_membership_verified=true
	[[ $verified_gid != "$shared_group_gid" ]] || shared_membership_verified=true
done
$docker_membership_verified ||
	fail "docker group membership verification failed: ${runner_user}/${docker_group}"
$shared_membership_verified ||
	fail "shared group membership verification failed: ${runner_user}/${shared_group}"

printf \
	'%s: verified status=ok user=%s shared-group=%s memberships=%s home=%s home-directory=unmanaged\n' \
	"$program_name" \
	"$user_result" \
	"$shared_group_result" \
	"$membership_result" \
	"$runner_home"
