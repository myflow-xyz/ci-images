#!/usr/bin/env bash

set -euo pipefail

LC_ALL=C
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export LC_ALL PATH

readonly program_name=${0##*/}
runner_root=/opt/actions-runner
owner_spec=github-runner
group_spec=mfci
dry_run=false

usage() {
	printf '%s\n' \
		"Usage: sudo ${program_name} [options]" \
		'' \
		'Configure writable GitHub Actions runner data under:' \
		'  <runner-root>/*/_work' \
		'  <runner-root>/shared/cache' \
		'' \
		'Options:' \
		'  --runner-root PATH Runner root (default: /opt/actions-runner)' \
		'  --owner USER|UID   Resolved file owner (default: github-runner)' \
		'  --group GROUP|GID  Resolved shared group (default: mfci)' \
		'  --dry-run          Resolve and report without changing the host' \
		'  -h, --help         Show this help'
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

((EUID == 0)) ||
	fail 'run as root (for example, with sudo)'

required_commands=(
	awk
	chmod
	chown
	find
	getent
	getfacl
	id
	install
	readlink
	setfacl
	usermod
)

for command_name in "${required_commands[@]}"; do
	command -v "$command_name" >/dev/null 2>&1 ||
		fail "required command is unavailable: ${command_name}"
done

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

declare -a group_records=()
mapfile -t group_records < <(getent group "$group_spec" || true)
((${#group_records[@]} == 1)) ||
	fail "group does not resolve uniquely: ${group_spec}"

IFS=: read -r group_name _ group_gid _ <<<"${group_records[0]}"
[[ $group_gid =~ ^[0-9]+$ ]] ||
	fail "group has invalid numeric identity: ${group_spec}"
((group_gid != 0)) ||
	fail "group must not be root: ${group_name}"

[[ $runner_root == /* ]] ||
	fail "runner root must be an absolute path: ${runner_root}"
[[ $runner_root != / ]] ||
	fail 'runner root must not be /'
[[ -d $runner_root && ! -L $runner_root ]] ||
	fail "runner root must be a real directory: ${runner_root}"

runner_root=$(readlink -f -- "$runner_root")
[[ $runner_root != / ]] ||
	fail 'resolved runner root must not be /'

shared_root="${runner_root}/shared"
cache_root="${shared_root}/cache"

shared_state=existing
if [[ -e $shared_root || -L $shared_root ]]; then
	[[ -d $shared_root && ! -L $shared_root ]] ||
		fail "shared root must be a real directory: ${shared_root}"
else
	shared_state=create
fi

cache_state=existing
if [[ -e $cache_root || -L $cache_root ]]; then
	[[ -d $cache_root && ! -L $cache_root ]] ||
		fail "cache root must be a real directory: ${cache_root}"
else
	cache_state=create
fi

declare -a workdirs=()
shopt -s nullglob
declare -a workdir_candidates=("${runner_root}"/*/_work)
shopt -u nullglob

for workdir in "${workdir_candidates[@]}"; do
	runner_directory=${workdir%/_work}
	[[ ! -L $runner_directory ]] ||
		fail "runner directory must not be a symbolic link: ${runner_directory}"
	[[ ! -L $workdir ]] ||
		fail "work tree must not be a symbolic link: ${workdir}"
	[[ -d $workdir ]] ||
		fail "work tree is not a directory: ${workdir}"
	workdirs+=("$workdir")
done

reject_unsupported_entries() {
	local target=$1
	local unsupported_entry

	unsupported_entry=$(
		find "$target" \
			! \( -type d -o -type f -o -type l \) \
			-print \
			-quit
	)
	[[ -z $unsupported_entry ]] ||
		fail "unsupported file type: ${unsupported_entry}"
}

declare -a existing_targets=("${workdirs[@]}")
if [[ $cache_state == existing ]]; then
	existing_targets+=("$cache_root")
fi

for target in "${existing_targets[@]}"; do
	reject_unsupported_entries "$target"
done

owner_has_group() {
	local current_gid
	local owner_groups
	local -a owner_group_ids=()

	owner_groups=$(id -G "$owner_name") ||
		fail "cannot resolve owner groups: ${owner_name}"
	read -r -a owner_group_ids <<<"$owner_groups"
	for current_gid in "${owner_group_ids[@]}"; do
		[[ $current_gid != "$group_gid" ]] || return 0
	done
	return 1
}

if owner_has_group; then
	membership_plan=present
else
	membership_plan=add
fi

mode=apply
$dry_run && mode=dry-run
target_count=$((${#workdirs[@]} + 1))
printf \
	'%s: plan mode=%s root=%s owner=%s(%s) group=%s(%s) workdirs=%s shared=%s cache=%s membership=%s\n' \
	"$program_name" \
	"$mode" \
	"$runner_root" \
	"$owner_name" \
	"$owner_uid" \
	"$group_name" \
	"$group_gid" \
	"${#workdirs[@]}" \
	"$shared_state" \
	"$cache_state" \
	"$membership_plan"

if $dry_run; then
	printf '%s: dry-run status=ok targets=%s\n' \
		"$program_name" \
		"$target_count"
	exit 0
fi

membership_result=present
if ! owner_has_group; then
	usermod --append --groups "$group_name" "$owner_name"
	membership_result=added
fi

if [[ $shared_state == create ]]; then
	install \
		--directory \
		--owner "$owner_uid" \
		--group "$owner_primary_gid" \
		--mode 0755 \
		-- \
		"$shared_root"
fi

if [[ $cache_state == create ]]; then
	install \
		--directory \
		--owner "$owner_uid" \
		--group "$group_gid" \
		--mode 2770 \
		-- \
		"$cache_root"
fi

declare -a targets=("${workdirs[@]}" "$cache_root")

apply_permissions() {
	local target=$1

	reject_unsupported_entries "$target"
	find "$target" \
		-exec chown --no-dereference "${owner_uid}:${group_gid}" -- {} +
	find "$target" \
		-type d \
		-exec chmod u+rwx,g+rwx,g+s,o-rwx -- {} +
	find "$target" \
		-type d \
		-exec setfacl \
		--set \
		user::rwx,group::rwx,other::---,default:user::rwx,default:group::rwx,default:other::--- \
		-- \
		{} +
	find "$target" \
		-type f \
		-perm /111 \
		-exec chmod u+rwx,g+rwx,o-rwx -- {} +
	find "$target" \
		-type f \
		-perm /111 \
		-exec setfacl \
		--set user::rwx,group::rwx,other::--- \
		-- \
		{} +
	find "$target" \
		-type f \
		! -perm /111 \
		-exec chmod u+rw,g+rw,o-rwx -- {} +
	find "$target" \
		-type f \
		! -perm /111 \
		-exec setfacl \
		--set user::rw,group::rw,other::--- \
		-- \
		{} +
}

acl_records_match() {
	local owner_permissions=$1
	local group_permissions=$2
	local include_defaults=$3

	awk \
		-v owner_permissions="$owner_permissions" \
		-v group_permissions="$group_permissions" \
		-v include_defaults="$include_defaults" '
		BEGIN {
			RS = ""
		}
		{
			owner_count = 0
			group_count = 0
			other_count = 0
			default_owner_count = 0
			default_group_count = 0
			default_other_count = 0
			entry_count = 0

			line_count = split($0, lines, "\n")
			for (line_number = 1; line_number <= line_count; line_number++) {
				if (lines[line_number] == "") {
					continue
				}
				entry_count++
				if (lines[line_number] == "user::" owner_permissions) {
					owner_count++
				} else if (lines[line_number] == "group::" group_permissions) {
					group_count++
				} else if (lines[line_number] == "other::---") {
					other_count++
				} else if (lines[line_number] == "default:user::" owner_permissions) {
					default_owner_count++
				} else if (lines[line_number] == "default:group::" group_permissions) {
					default_group_count++
				} else if (lines[line_number] == "default:other::---") {
					default_other_count++
				} else {
					exit 1
				}
			}

			if (owner_count != 1 || group_count != 1 || other_count != 1) {
				exit 1
			}
			if (include_defaults == "true" &&
			    (entry_count != 6 ||
			     default_owner_count != 1 ||
			     default_group_count != 1 ||
			     default_other_count != 1)) {
				exit 1
			}
			if (include_defaults != "true" && entry_count != 3) {
				exit 1
			}
		}
	'
}

verify_permissions() {
	local target=$1
	local mismatch

	reject_unsupported_entries "$target"

	mismatch=$(
		find "$target" \
			\( ! -uid "$owner_uid" -o ! -gid "$group_gid" \) \
			-print \
			-quit
	)
	[[ -z $mismatch ]] ||
		fail "ownership verification failed: ${mismatch}"

	mismatch=$(
		find "$target" \
			-type d \
			! -perm -2770 \
			-print \
			-quit
	)
	[[ -z $mismatch ]] ||
		fail "directory mode verification failed: ${mismatch}"

	mismatch=$(
		find "$target" \
			-type d \
			-perm /0007 \
			-print \
			-quit
	)
	[[ -z $mismatch ]] ||
		fail "directory other-access verification failed: ${mismatch}"

	mismatch=$(
		find "$target" \
			-type f \
			-perm /111 \
			! -perm -0770 \
			-print \
			-quit
	)
	[[ -z $mismatch ]] ||
		fail "executable mode verification failed: ${mismatch}"

	mismatch=$(
		find "$target" \
			-type f \
			-perm /0007 \
			-print \
			-quit
	)
	[[ -z $mismatch ]] ||
		fail "file other-access verification failed: ${mismatch}"

	mismatch=$(
		find "$target" \
			-type f \
			! -perm /111 \
			! -perm -0660 \
			-print \
			-quit
	)
	[[ -z $mismatch ]] ||
		fail "file mode verification failed: ${mismatch}"

	find "$target" \
		-type d \
		-exec getfacl -cp -- {} + |
		acl_records_match rwx rwx true ||
		fail "directory ACL verification failed below: ${target}"

	find "$target" \
		-type f \
		-perm /111 \
		-exec getfacl -cp -- {} + |
		acl_records_match rwx rwx false ||
		fail "executable ACL verification failed below: ${target}"

	find "$target" \
		-type f \
		! -perm /111 \
		-exec getfacl -cp -- {} + |
		acl_records_match rw- rw- false ||
		fail "file ACL verification failed below: ${target}"
}

owner_has_group ||
	fail "owner is not a member of resolved group: ${owner_name}/${group_name}"

for target in "${targets[@]}"; do
	apply_permissions "$target"
	verify_permissions "$target"
done

if [[ $membership_result == added ]]; then
	printf \
		'%s: verified status=ok targets=%s membership=added restart-required=yes\n' \
		"$program_name" \
		"$target_count"
else
	printf \
		'%s: verified status=ok targets=%s membership=present\n' \
		"$program_name" \
		"$target_count"
fi
