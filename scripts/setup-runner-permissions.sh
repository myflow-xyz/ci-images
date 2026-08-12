#!/usr/bin/env bash

set -euo pipefail

LC_ALL=C
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export LC_ALL PATH

readonly program_name=${0##*/}
runner_root=/opt/actions-runner
owner_spec=ci-runner
group_spec=mfci
dry_run=false
check_only=false

usage() {
	printf '%s\n' \
		"Usage: ${program_name} [options]" \
		'' \
		'Configure writable GitHub Actions runner data under:' \
		'  <runner-root>/workspace/*/_work' \
		'  <runner-root>/shared/cache' \
		'' \
		'Options:' \
		'  --runner-root PATH Runner root (default: /opt/actions-runner)' \
		'  --owner USER|UID   Resolved file owner (default: ci-runner)' \
		'  --group GROUP|GID  Resolved shared group (default: mfci)' \
		'  --check            Verify without changing the host' \
		'  --dry-run          Resolve and report without changing the host' \
		'  -h, --help         Show this help' \
		'' \
		'Host dependency: install the acl package on Debian or RHEL.' \
		'Owner group membership is verified but never changed.' \
		'Apply mode (default) and --dry-run require root.'
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
	--check)
		check_only=true
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

$check_only && $dry_run &&
	usage_error '--check and --dry-run are mutually exclusive'

if ! $check_only; then
	((EUID == 0)) ||
		fail 'run as root (for example, with sudo)'
fi

required_commands=(
	awk
	find
	getent
	getfacl
	id
	readlink
)

if ! $check_only; then
	required_commands+=(
		chmod
		chown
		install
		setfacl
	)
fi

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

group_list_has_gid() {
	local group_list=$1
	local current_gid
	local -a group_ids=()

	read -r -a group_ids <<<"$group_list"
	for current_gid in "${group_ids[@]}"; do
		[[ $current_gid != "$group_gid" ]] || return 0
	done
	return 1
}

owner_has_configured_group() {
	local configured_groups

	configured_groups=$(id -G "$owner_name") ||
		fail "cannot resolve owner groups: ${owner_name}"
	group_list_has_gid "$configured_groups"
}

current_process_has_group() {
	local effective_groups

	effective_groups=$(id -G) ||
		fail 'cannot resolve current process groups'
	group_list_has_gid "$effective_groups"
}

if $check_only; then
	((EUID == owner_uid)) ||
		fail "--check must run as resolved owner: ${owner_name}(${owner_uid})"
	if ! owner_has_configured_group; then
		warn "owner ${owner_name} is not a member of ${group_name}(${group_gid}); add the owner, restart its runner service, and rerun"
		fail "owner is not configured for resolved group: ${owner_name}/${group_name}"
	fi
	current_process_has_group ||
		fail "resolved group is not effective for the current runner process; restart the runner service: ${owner_name}/${group_name}"
fi

[[ $runner_root == /* ]] ||
	fail "runner root must be an absolute path: ${runner_root}"
[[ $runner_root != / ]] ||
	fail 'runner root must not be /'
[[ -d $runner_root && ! -L $runner_root ]] ||
	fail "runner root must be a real directory: ${runner_root}"

runner_root=$(readlink -f -- "$runner_root")
[[ $runner_root != / ]] ||
	fail 'resolved runner root must not be /'

workspace_root="${runner_root}/workspace"
shared_root="${runner_root}/shared"
cache_root="${shared_root}/cache"

[[ -d $workspace_root && ! -L $workspace_root ]] ||
	fail "workspace root must be a real directory: ${workspace_root}"

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
declare -a workdir_candidates=("${workspace_root}"/*/_work)
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

reject_writable_unmanaged_parent() {
	local parent=$1
	local parent_acl

	parent_acl=$(getfacl -cnpe -- "$parent") ||
		fail "cannot read unmanaged parent ACL: ${parent}"
	if awk '
		{
			entry = $1
			split(entry, fields, ":")
			entry_type = fields[1]
			qualifier = fields[2]
			permissions = fields[3]

			for (field_number = 2;
			     field_number <= NF;
			     field_number++) {
				if ($field_number ~ /^#effective:/) {
					permissions = substr($field_number, 12)
				}
			}

			if ((entry_type == "group" ||
			     entry_type == "other" ||
			     (entry_type == "user" && qualifier != "")) &&
			    permissions ~ /w/) {
				writable = 1
			}
		}
		END {
			exit(writable ? 0 : 1)
		}
	' <<<"$parent_acl"; then
		fail "unmanaged parent grants non-owner write access: ${parent}"
	fi
}

reject_writable_unmanaged_parent "$runner_root"
reject_writable_unmanaged_parent "$workspace_root"
if [[ $shared_state == existing ]]; then
	reject_writable_unmanaged_parent "$shared_root"
fi
for workdir in "${workdirs[@]}"; do
	reject_writable_unmanaged_parent "${workdir%/_work}"
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

if owner_has_configured_group; then
	membership_plan=present
else
	membership_plan=missing
fi

mode=apply
if $check_only; then
	mode=check
elif $dry_run; then
	mode=dry-run
fi
target_count=$((${#workdirs[@]} + 1))
printf \
	'%s: plan mode=%s root=%s owner=%s(%s) group=%s(%s) workdirs=%s shared=%s cache=%s configured-membership=%s\n' \
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

if $check_only; then
	[[ $shared_state == existing ]] ||
		fail "shared root is missing: ${shared_root}"
	[[ $cache_state == existing ]] ||
		fail "cache root is missing: ${cache_root}"
fi

declare -a targets=("${workdirs[@]}" "$cache_root")

apply_permissions() {
	local target=$1

	reject_unsupported_entries "$target"
	find "$target" \
		-exec chown --no-dereference "${owner_uid}:${group_gid}" -- {} +
	find "$target" \
		-type d \
		-exec chmod 2770 -- {} +
	find "$target" \
		-type d \
		-exec setfacl \
		--set \
		user::rwx,group::rwx,other::---,default:user::rwx,default:group::rwx,default:other::--- \
		-- \
		{} +
	find "$target" \
		-type f \
		-exec setfacl --remove-all -- {} +
	find "$target" \
		-type f \
		-exec chmod u-s,g-s,o-t,g=u,o= -- {} +
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

file_acl_records_match() {
	awk '
		BEGIN {
			RS = ""
		}
		{
			owner_permissions = ""
			group_permissions = ""
			owner_count = 0
			group_count = 0
			other_count = 0
			entry_count = 0

			line_count = split($0, lines, "\n")
			for (line_number = 1; line_number <= line_count; line_number++) {
				if (lines[line_number] == "") {
					continue
				}
				entry_count++
				if (lines[line_number] ~ /^user::[r-][w-][x-]$/) {
					owner_permissions = substr(lines[line_number], 7)
					owner_count++
				} else if (lines[line_number] ~ /^group::[r-][w-][x-]$/) {
					group_permissions = substr(lines[line_number], 8)
					group_count++
				} else if (lines[line_number] == "other::---") {
					other_count++
				} else {
					exit 1
				}
			}

			if (entry_count != 3 ||
			    owner_count != 1 ||
			    group_count != 1 ||
			    other_count != 1 ||
			    owner_permissions != group_permissions) {
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
			-maxdepth 0 \
			\( ! -uid "$owner_uid" -o ! -gid "$group_gid" \) \
			-print \
			-quit
	)
	[[ -z $mismatch ]] ||
		fail "managed-root ownership verification failed: ${mismatch}"

	mismatch=$(
		find "$target" \
			-mindepth 1 \
			! -gid "$group_gid" \
			-print \
			-quit
	)
	[[ -z $mismatch ]] ||
		fail "descendant group verification failed: ${mismatch}"

	mismatch=$(
		find "$target" \
			-type d \
			! -perm 2770 \
			-print \
			-quit
	)
	[[ -z $mismatch ]] ||
		fail "directory mode verification failed: ${mismatch}"

	mismatch=$(
		find "$target" \
			-type f \
			-perm /7007 \
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
		-exec getfacl -cp -- {} + |
		file_acl_records_match ||
		fail "file ACL verification failed below: ${target}"
}

if $check_only; then
	for target in "${targets[@]}"; do
		verify_permissions "$target"
	done

	printf \
		'%s: verified status=ok mode=check targets=%s configured-membership=present effective-membership=present\n' \
		"$program_name" \
		"$target_count"
	exit 0
fi

if ! owner_has_configured_group; then
	warn "owner ${owner_name} is not a member of ${group_name}(${group_gid}); add the owner, restart its runner service, and rerun"
	fail 'operator-managed group membership is required'
fi

if [[ $shared_state == create ]]; then
	install \
		--directory \
		--owner "$owner_uid" \
		--group "$owner_primary_gid" \
		--mode 0755 \
		-- \
		"$shared_root"
	reject_writable_unmanaged_parent "$shared_root"
fi

if [[ $cache_state == create ]]; then
	reject_writable_unmanaged_parent "$shared_root"
	install \
		--directory \
		--owner "$owner_uid" \
		--group "$group_gid" \
		--mode 2770 \
		-- \
		"$cache_root"
fi

owner_has_configured_group ||
	fail "owner is not a member of resolved group: ${owner_name}/${group_name}"

for target in "${targets[@]}"; do
	apply_permissions "$target"
	verify_permissions "$target"
done

printf \
	'%s: verified status=ok targets=%s membership=present\n' \
	"$program_name" \
	"$target_count"
