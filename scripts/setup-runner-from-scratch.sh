#!/usr/bin/env bash

set -euo pipefail

LC_ALL=C
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export LC_ALL PATH

readonly program_name=${0##*/}
readonly default_group_name=mfci
readonly default_group_gid=2001
readonly runner_root_marker=.mfci-runner-root
runner_root=
owner_spec=
repository=
group_spec=$default_group_name
dry_run=false

usage() {
	printf '%s\n' \
		"Usage: ${program_name} --runner-root PATH --owner USER|UID --repository NAME [options]" \
		'' \
		'Create this self-hosted runner directory structure:' \
		'  <runner-root>/workspace/<repository>/_work' \
		'  <runner-root>/shared/{bin,cache,downloads}' \
		'' \
		'Required:' \
		'  --runner-root PATH New or helper-managed runner root below:' \
		'                     /opt, /var, /home, or /Users' \
		'  --owner USER|UID   Existing non-root runner owner' \
		'  --repository NAME  Repository-specific runner directory name' \
		'' \
		'Options:' \
		'  --group GROUP|GID  Shared group (default: mfci)' \
		'                     Missing mfci is created with GID 2001' \
		'  --dry-run          Resolve and report without changing the host' \
		'  -h, --help         Show this help' \
		'' \
		'Host dependency: install the acl package on Debian or RHEL.' \
		'Owner group membership is verified but never changed.' \
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

warn() {
	printf '%s: warning: %s\n' "$program_name" "$*" >&2
}

require_value() {
	local option=$1
	local value=${2-}

	[[ -n $value ]] || usage_error "${option} requires a value"
}

while (($# > 0)); do
	case "$1" in
	--runner-root)
		require_value "$1" "${2-}"
		runner_root=$2
		shift 2
		;;
	--runner-root=*)
		runner_root=${1#*=}
		require_value --runner-root "$runner_root"
		shift
		;;
	--owner)
		require_value "$1" "${2-}"
		owner_spec=$2
		shift 2
		;;
	--owner=*)
		owner_spec=${1#*=}
		require_value --owner "$owner_spec"
		shift
		;;
	--repository)
		require_value "$1" "${2-}"
		repository=$2
		shift 2
		;;
	--repository=*)
		repository=${1#*=}
		require_value --repository "$repository"
		shift
		;;
	--group)
		require_value "$1" "${2-}"
		group_spec=$2
		shift 2
		;;
	--group=*)
		group_spec=${1#*=}
		require_value --group "$group_spec"
		shift
		;;
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

[[ -n $runner_root ]] || usage_error '--runner-root is required'
[[ -n $owner_spec ]] || usage_error '--owner is required'
[[ -n $repository ]] || usage_error '--repository is required'
[[ $repository =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] ||
	usage_error "invalid repository name: ${repository}"

((EUID == 0)) ||
	fail 'run as root (for example, with sudo)'

required_commands=(
	awk
	chmod
	chown
	find
	getent
	getfacl
	groupadd
	id
	install
	mkdir
	readlink
	rmdir
	setfacl
	stat
)

for command_name in "${required_commands[@]}"; do
	if ! command -v "$command_name" >/dev/null 2>&1; then
		case "$command_name" in
		getfacl | setfacl)
			fail "required POSIX ACL command is unavailable: ${command_name}; install the acl package"
			;;
		esac
		fail "required command is unavailable: ${command_name}"
	fi
done

script_path=$(readlink -f -- "${BASH_SOURCE[0]}") ||
	fail 'cannot resolve helper path'
script_directory=${script_path%/*}
permission_helper="${script_directory}/setup-runner-permissions.sh"
[[ -f $permission_helper && -x $permission_helper ]] ||
	fail "permission helper is unavailable: ${permission_helper}"

declare -a owner_records=()
mapfile -t owner_records < <(getent passwd "$owner_spec" || true)
((${#owner_records[@]} == 1)) ||
	fail "owner does not resolve uniquely: ${owner_spec}"

IFS=: read -r \
	owner_name \
	_ \
	owner_uid \
	owner_primary_gid \
	_ \
	_ \
	_ \
	<<<"${owner_records[0]}"

[[ $owner_uid =~ ^[0-9]+$ && $owner_primary_gid =~ ^[0-9]+$ ]] ||
	fail "owner has invalid numeric identity: ${owner_spec}"
((owner_uid != 0)) ||
	fail "owner must not be root: ${owner_name}"

group_state=existing
declare -a group_records=()
mapfile -t group_records < <(getent group "$group_spec" || true)
if [[ $group_spec == "$default_group_name" && ${#group_records[@]} == 0 ]]; then
	declare -a gid_records=()
	mapfile -t gid_records < <(getent group "$default_group_gid" || true)
	if ((${#gid_records[@]} != 0)); then
		warn "GID ${default_group_gid} is already assigned; no group changes were made"
		fail "cannot create ${default_group_name}: GID ${default_group_gid} is already in use"
	fi
	group_state=create
	group_name=$default_group_name
	group_gid=$default_group_gid
else
	((${#group_records[@]} == 1)) ||
		fail "group does not resolve uniquely: ${group_spec}"
	IFS=: read -r group_name _ group_gid _ <<<"${group_records[0]}"
fi

[[ $group_gid =~ ^[0-9]+$ ]] ||
	fail "group has invalid numeric identity: ${group_spec}"
((group_gid != 0)) ||
	fail "group must not be root: ${group_name}"
if [[ $group_name == "$default_group_name" && $group_gid != "$default_group_gid" ]]; then
	warn "${default_group_name} has an unexpected GID; no group changes were made"
	fail "${default_group_name} must use GID ${default_group_gid}, found ${group_gid}"
fi

owner_groups=$(id -G "$owner_name") ||
	fail "cannot resolve owner groups: ${owner_name}"
membership_plan=missing
for current_gid in $owner_groups; do
	if [[ $current_gid == "$group_gid" ]]; then
		membership_plan=present
		break
	fi
done

while [[ $runner_root != / && $runner_root == */ ]]; do
	runner_root=${runner_root%/}
done
[[ $runner_root == /* ]] ||
	fail "runner root must be an absolute path: ${runner_root}"
[[ $runner_root != / ]] ||
	fail 'runner root must not be /'

runner_root_state=create
if [[ -e $runner_root || -L $runner_root ]]; then
	[[ -d $runner_root && ! -L $runner_root ]] ||
		fail "runner root must be a real directory: ${runner_root}"
	runner_root=$(readlink -f -- "$runner_root")
	runner_root_state=existing
else
	runner_parent=${runner_root%/*}
	runner_name=${runner_root##*/}
	[[ -n $runner_parent ]] || runner_parent=/
	[[ $runner_name != . && $runner_name != .. ]] ||
		fail "runner root has an invalid final component: ${runner_root}"
	[[ -d $runner_parent && ! -L $runner_parent ]] ||
		fail "runner root parent must be a real directory: ${runner_parent}"
	runner_parent=$(readlink -f -- "$runner_parent")
	if [[ $runner_parent == / ]]; then
		runner_root="/${runner_name}"
	else
		runner_root="${runner_parent}/${runner_name}"
	fi
fi

[[ $runner_root != / ]] ||
	fail 'resolved runner root must not be /'
if [[ $runner_root != /opt/* &&
	$runner_root != /var/* &&
	$runner_root != /home/* &&
	$runner_root != /Users/* ]]; then
	fail "runner root must resolve below /opt, /var, /home, or /Users: ${runner_root}"
fi

runner_marker="${runner_root}/${runner_root_marker}"
if [[ $runner_root_state == existing ]]; then
	[[ -f $runner_marker && ! -L $runner_marker ]] ||
		fail "existing runner root is not helper-managed; marker is missing: ${runner_marker}"
	marker_identity=$(stat --format '%u:%g:%a' -- "$runner_marker") ||
		fail "cannot verify runner root marker: ${runner_marker}"
	[[ $marker_identity == 0:0:444 ]] ||
		fail "runner root marker has unexpected identity: ${runner_marker} expected=0:0:444 actual=${marker_identity}"
fi

workspace_root="${runner_root}/workspace"
repository_root="${workspace_root}/${repository}"
work_root="${repository_root}/_work"
shared_root="${runner_root}/shared"
shared_bin="${shared_root}/bin"
shared_cache="${shared_root}/cache"
shared_downloads="${shared_root}/downloads"

declare -a directories=(
	"$runner_root"
	"$workspace_root"
	"$repository_root"
	"$work_root"
	"$shared_root"
	"$shared_bin"
	"$shared_cache"
	"$shared_downloads"
)

create_count=0
existing_count=0
for directory in "${directories[@]}"; do
	if [[ -e $directory || -L $directory ]]; then
		[[ -d $directory && ! -L $directory ]] ||
			fail "target must be a real directory: ${directory}"
		((existing_count += 1))
	else
		((create_count += 1))
	fi
done

mode=apply
$dry_run && mode=dry-run
printf \
	'%s: plan mode=%s root=%s root-state=%s owner=%s(%s) group=%s(%s) group-state=%s configured-membership=%s repository=%s create=%s existing=%s\n' \
	"$program_name" \
	"$mode" \
	"$runner_root" \
	"$runner_root_state" \
	"$owner_name" \
	"$owner_uid" \
	"$group_name" \
	"$group_gid" \
	"$group_state" \
	"$membership_plan" \
	"$repository" \
	"$create_count" \
	"$existing_count"

if $dry_run; then
	printf '%s: dry-run status=ok directories=%s\n' \
		"$program_name" \
		"${#directories[@]}"
	exit 0
fi

group_result=present
if [[ $group_state == create ]]; then
	groupadd --gid "$default_group_gid" "$default_group_name" ||
		fail "cannot create group: ${default_group_name}(${default_group_gid})"
	group_result=created

	declare -a created_group_records=()
	mapfile -t created_group_records < <(getent group "$default_group_name" || true)
	((${#created_group_records[@]} == 1)) ||
		fail "created group does not resolve uniquely: ${default_group_name}"
	IFS=: read -r created_group_name _ created_group_gid _ \
		<<<"${created_group_records[0]}"
	[[ $created_group_name == "$default_group_name" &&
		$created_group_gid == "$default_group_gid" ]] ||
		fail "created group has unexpected identity: ${created_group_records[0]}"
fi

if [[ $membership_plan == missing ]]; then
	if [[ $group_result == created ]]; then
		warn "created ${group_name}(${group_gid}), but owner ${owner_name} was not enrolled; add the owner, restart its runner service, and rerun"
	else
		warn "owner ${owner_name} is not a member of ${group_name}(${group_gid}); add the owner, restart its runner service, and rerun"
	fi
	fail 'operator-managed group membership is required'
fi

owner_groups=$(id -G "$owner_name") ||
	fail "cannot verify owner groups: ${owner_name}"
membership_verified=false
for current_gid in $owner_groups; do
	if [[ $current_gid == "$group_gid" ]]; then
		membership_verified=true
		break
	fi
done
$membership_verified ||
	fail "owner is not configured for group: ${owner_name}/${group_name}"

if [[ $runner_root_state == create ]]; then
	mkdir --mode 0755 -- "$runner_root" ||
		fail "cannot create runner root: ${runner_root}"
	if ! install \
		--owner 0 \
		--group 0 \
		--mode 0444 \
		-- \
		/dev/null \
		"$runner_marker"; then
		rmdir -- "$runner_root" >/dev/null 2>&1 || true
		fail "cannot create runner root marker: ${runner_marker}"
	fi
fi

install \
	--directory \
	--owner "$owner_uid" \
	--group "$owner_primary_gid" \
	--mode 0755 \
	-- \
	"$runner_root" \
	"$workspace_root" \
	"$repository_root" \
	"$shared_root" \
	"$shared_bin" \
	"$shared_downloads"

install \
	--directory \
	--owner "$owner_uid" \
	--group "$group_gid" \
	--mode 2770 \
	-- \
	"$work_root" \
	"$shared_cache"

"$permission_helper" \
	--runner-root "$runner_root" \
	--owner "$owner_uid" \
	--group "$group_gid"

verify_directory() {
	local directory=$1
	local expected=$2
	local actual

	actual=$(stat --format '%u:%g:%a' -- "$directory") ||
		fail "cannot verify directory: ${directory}"
	[[ $actual == "$expected" ]] ||
		fail "directory verification failed: ${directory} expected=${expected} actual=${actual}"
}

for directory in \
	"$runner_root" \
	"$workspace_root" \
	"$repository_root" \
	"$shared_root" \
	"$shared_bin" \
	"$shared_downloads"; do
	verify_directory \
		"$directory" \
		"${owner_uid}:${owner_primary_gid}:755"
done

for directory in "$work_root" "$shared_cache"; do
	verify_directory \
		"$directory" \
		"${owner_uid}:${group_gid}:2770"
done

printf \
	'%s: verified status=ok directories=%s permission-helper=ok group=%s membership=present\n' \
	"$program_name" \
	"${#directories[@]}" \
	"$group_result"
