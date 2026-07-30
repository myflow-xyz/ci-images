#!/usr/bin/env bash

set -euo pipefail

scripts_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
helper="${scripts_root}/setup-runner-permissions.sh"

fail() {
	printf 'setup-runner-permissions integration failed: %s\n' "$*" >&2
	exit 1
}

((EUID == 0)) || fail 'run this test as root'

required_commands=(
	getent
	getfacl
	git
	setfacl
	setpriv
	stat
)

for command_name in "${required_commands[@]}"; do
	command -v "$command_name" >/dev/null 2>&1 ||
		fail "required command is unavailable: ${command_name}"
done

if [[ -n ${SUDO_UID:-} && $SUDO_UID != 0 ]]; then
	owner_record=$(getent passwd "$SUDO_UID")
elif owner_record=$(getent passwd ci); then
	:
else
	owner_record=$(getent passwd nobody)
fi
[[ -n $owner_record ]] || fail 'test owner is unavailable'

IFS=: read -r owner_name _ owner_uid owner_gid _ _ _ <<<"$owner_record"
group_record=$(getent group "$owner_gid")
[[ -n $group_record ]] || fail "test group is unavailable: ${owner_gid}"
IFS=: read -r group_name _ group_gid _ <<<"$group_record"

stale_gid=
while IFS=: read -r _ _ candidate_gid _; do
	[[ $candidate_gid =~ ^[0-9]+$ ]] || continue
	((candidate_gid != 0)) || continue
	[[ $candidate_gid != "$group_gid" ]] || continue
	stale_gid=$candidate_gid
	break
done < <(getent group)
[[ -n $stale_gid ]] || fail 'an alternate test group is unavailable'

probe_uid=65534
if [[ $probe_uid == "$owner_uid" ]]; then
	probe_uid=65533
fi
acl_probe_uid=65532
if [[ $acl_probe_uid == "$owner_uid" ]]; then
	acl_probe_uid=65531
fi

temporary_directory=$(mktemp -d)
trap 'rm -rf "$temporary_directory"' EXIT
chmod 0755 "$temporary_directory"

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

runner_root="${temporary_directory}/runner root"
mkdir -p \
	"${runner_root}/shared/cache/go/nested" \
	"${runner_root}/repository-a/_work/project/nested" \
	"${runner_root}/repository-b/_work/_temp" \
	"${runner_root}/repository-c"

printf 'cache\n' >"${runner_root}/shared/cache/go/nested/data"
printf 'workspace\n' > \
	"${runner_root}/repository-a/_work/project/nested/data"
printf 'read-only\n' > \
	"${runner_root}/repository-a/_work/project/nested/read-only"
printf '#!/usr/bin/env bash\n' > \
	"${runner_root}/repository-a/_work/project/tool"
printf 'runner-owned\n' > \
	"${runner_root}/repository-b/_work/_temp/runner-owned"
printf 'protected\n' >"${runner_root}/repository-a/config"
printf 'outside\n' >"${runner_root}/repository-c/outside"
ln -s \
	"${runner_root}/repository-c/outside" \
	"${runner_root}/repository-a/_work/outside-link"

chmod 0700 \
	"${runner_root}/shared/cache" \
	"${runner_root}/shared/cache/go" \
	"${runner_root}/shared/cache/go/nested" \
	"${runner_root}/repository-a/_work" \
	"${runner_root}/repository-a/_work/project" \
	"${runner_root}/repository-a/_work/project/nested" \
	"${runner_root}/repository-b/_work"
chmod 1777 "${runner_root}/repository-b/_work/_temp"
chmod 0600 \
	"${runner_root}/shared/cache/go/nested/data" \
	"${runner_root}/repository-a/_work/project/nested/data"
chmod 0400 \
	"${runner_root}/repository-a/_work/project/nested/read-only"
chmod 0700 "${runner_root}/repository-a/_work/project/tool"
chmod 0755 \
	"${runner_root}" \
	"${runner_root}/shared" \
	"${runner_root}/repository-a" \
	"${runner_root}/repository-b" \
	"${runner_root}/repository-c"
chmod 0640 \
	"${runner_root}/repository-a/config" \
	"${runner_root}/repository-c/outside"
setfacl \
	--modify \
	default:user::rwx,default:group::---,default:mask::---,default:other::rwx \
	"${runner_root}/repository-a/_work"
setfacl \
	--modify \
	"user:${acl_probe_uid}:rwx,default:user:${acl_probe_uid}:rwx" \
	"${runner_root}/repository-a/_work"
setfacl \
	--modify \
	"user:${acl_probe_uid}:rw" \
	"${runner_root}/repository-a/_work/project/nested/data"

work_file="${runner_root}/repository-a/_work/project/nested/data"
before_dry_run=$(stat --format '%u:%g:%a' "$work_file")
dry_run_output=$(
	"$helper" \
		--runner-root "$runner_root" \
		--owner "$owner_uid" \
		--group "$group_gid" \
		--dry-run
)
after_dry_run=$(stat --format '%u:%g:%a' "$work_file")

[[ $before_dry_run == "$after_dry_run" ]] ||
	fail 'dry-run changed a target'
[[ $dry_run_output == *'mode=dry-run'* ]] ||
	fail 'dry-run mode was not reported'
[[ $dry_run_output == *"root=${runner_root}"* ]] ||
	fail 'resolved runner root was not reported'
[[ $dry_run_output == *'workdirs=2'* ]] ||
	fail 'dry-run discovered the wrong work-tree count'
[[ $dry_run_output == *'targets=3'* ]] ||
	fail 'dry-run reported the wrong target count'

outside_before=$(
	stat \
		--format '%u:%g:%a' \
		"${runner_root}/repository-c/outside"
)
parent_before=$(
	stat \
		--format '%u:%g:%a' \
		"${runner_root}/repository-a"
)

apply_output=$(
	"$helper" \
		--runner-root "$runner_root" \
		--owner "$owner_name" \
		--group "$group_name"
)

[[ $apply_output == *'verified status=ok targets=3'* ]] ||
	fail 'successful verification was not reported'
[[ $apply_output == *'membership=present'* ]] ||
	fail 'existing group membership was not reported'

check_output=$(
	setpriv \
		--reuid "$owner_uid" \
		--regid "$owner_gid" \
		--init-groups \
		"$helper" \
		--runner-root "$runner_root" \
		--owner "$owner_name" \
		--group "$group_name" \
		--check
)
[[ $check_output == *'mode=check'* ]] ||
	fail 'verification-only mode was not reported'
[[ $check_output == *'verified status=ok mode=check targets=3'* ]] ||
	fail 'verification-only success was not reported'
[[ $check_output == *'configured-membership=present effective-membership=present'* ]] ||
	fail 'configured and effective memberships were not reported separately'

assert_fails_with \
	'stale effective group membership' \
	'resolved group is not effective for the current runner process; restart the runner service' \
	setpriv \
	--reuid "$owner_uid" \
	--regid "$stale_gid" \
	--clear-groups \
	"$helper" \
	--runner-root "$runner_root" \
	--owner "$owner_name" \
	--group "$group_name" \
	--check

assert_fails_with \
	'wrong verification caller' \
	"--check must run as resolved owner: ${owner_name}(${owner_uid})" \
	setpriv \
	--reuid "$probe_uid" \
	--regid "$group_gid" \
	--clear-groups \
	"$helper" \
	--runner-root "$runner_root" \
	--owner "$owner_name" \
	--group "$group_name" \
	--check

chmod 0600 "$work_file"
check_failure_before=$(stat --format '%u:%g:%a' "$work_file")
assert_fails_with \
	'verification-only mode mismatch' \
	"file ACL verification failed below: ${runner_root}/repository-a/_work" \
	setpriv \
	--reuid "$owner_uid" \
	--regid "$owner_gid" \
	--init-groups \
	"$helper" \
	--runner-root "$runner_root" \
	--owner "$owner_name" \
	--group "$group_name" \
	--check
check_failure_after=$(stat --format '%u:%g:%a' "$work_file")
[[ $check_failure_after == "$check_failure_before" ]] ||
	fail 'verification-only mode changed a target'
chmod 0660 "$work_file"

[[ $(stat --format %A "$work_file") == -rw-rw---- ]] ||
	fail 'an existing regular file did not receive owner and group write access'
tool_mode=$(
	stat --format %A "${runner_root}/repository-a/_work/project/tool"
)
[[ $tool_mode == -rwxrwx--- ]] ||
	fail 'an existing executable did not retain executable access'
read_only_file="${runner_root}/repository-a/_work/project/nested/read-only"
[[ $(stat --format %A "$read_only_file") == -r--r----- ]] ||
	fail 'an existing read-only file did not retain read-only access'

declare -a targets=(
	"${runner_root}/repository-a/_work"
	"${runner_root}/repository-b/_work"
	"${runner_root}/shared/cache"
)
expected_directory_acl=$(
	printf '%s\n' \
		'user::rwx' \
		'group::rwx' \
		'other::---' \
		'default:user::rwx' \
		'default:group::rwx' \
		'default:other::---'
)
expected_read_only_acl=$(
	printf '%s\n' \
		'user::r--' \
		'group::r--' \
		'other::---'
)

assert_mirrored_file_permissions() {
	local regular_file=$1
	local mode
	local owner_permissions
	local group_permissions
	local file_acl
	local expected_file_acl

	mode=$(stat --format %a "$regular_file")
	[[ $mode =~ ^[0-7]{3}$ ]] ||
		fail "file has special permission bits: ${regular_file}"
	[[ ${mode:0:1} == "${mode:1:1}" && ${mode:2:1} == 0 ]] ||
		fail "file owner and group permissions differ: ${regular_file}"

	file_acl=$(getfacl -cp "$regular_file")
	owner_permissions=$(
		printf '%s\n' "$file_acl" |
			awk -F: '$1 == "user" && $2 == "" { print $3 }'
	)
	group_permissions=$(
		printf '%s\n' "$file_acl" |
			awk -F: '$1 == "group" && $2 == "" { print $3 }'
	)
	[[ -n $owner_permissions && $owner_permissions == "$group_permissions" ]] ||
		fail "file ACL owner and group permissions differ: ${regular_file}"
	expected_file_acl=$(
		printf '%s\n' \
			"user::${owner_permissions}" \
			"group::${group_permissions}" \
			'other::---'
	)
	[[ $file_acl == "$expected_file_acl" ]] ||
		fail "file ACL has unexpected entries: ${regular_file}"
}

for target in "${targets[@]}"; do
	[[ $(stat --format '%u:%g' "$target") == "${owner_uid}:${group_gid}" ]] ||
		fail "managed-root ownership was not normalized: ${target}"

	if find "$target" \
		-mindepth 1 \
		! -gid "$group_gid" \
		-print \
		-quit |
		grep -q .; then
		fail "descendant group ownership was not normalized below ${target}"
	fi

	if find "$target" -type d ! -perm 2770 -print -quit |
		grep -q .; then
		fail "directory permissions were not normalized below ${target}"
	fi

	while IFS= read -r directory; do
		[[ $(getfacl -cp "$directory") == "$expected_directory_acl" ]] ||
			fail "directory ACL was not replaced exactly: ${directory}"
	done < <(find "$target" -type d)

	while IFS= read -r regular_file; do
		assert_mirrored_file_permissions "$regular_file"
	done < <(find "$target" -type f)
done

[[ $(getfacl -cp "$read_only_file") == "$expected_read_only_acl" ]] ||
	fail 'the read-only file ACL was not normalized exactly'

outside_after=$(
	stat --format '%u:%g:%a' "${runner_root}/repository-c/outside"
)
[[ $outside_after == "$outside_before" ]] ||
	fail 'a symlink target outside the writable trees changed'
parent_after=$(
	stat --format '%u:%g:%a' "${runner_root}/repository-a"
)
[[ $parent_after == "$parent_before" ]] ||
	fail 'a runner installation directory changed'

linked_runner_target="${temporary_directory}/linked-runner-target"
linked_runner="${runner_root}/linked-runner"
mkdir -p "${linked_runner_target}/_work"
ln -s "$linked_runner_target" "$linked_runner"
assert_fails_with \
	'linked runner directory' \
	'runner directory must not be a symbolic link' \
	"$helper" \
	--runner-root "$runner_root" \
	--owner "$owner_name" \
	--group "$group_name" \
	--dry-run
rm -- "$linked_runner"

assert_fails_with \
	'root owner' \
	'owner must not be root' \
	"$helper" \
	--runner-root "$runner_root" \
	--owner root \
	--group "$group_name" \
	--dry-run

assert_fails_with \
	'root group' \
	'group must not be root' \
	"$helper" \
	--runner-root "$runner_root" \
	--owner "$owner_name" \
	--group 0 \
	--dry-run

special_root="${temporary_directory}/special-root"
mkdir -p \
	"${special_root}/shared/cache" \
	"${special_root}/repository/_work"
special_file="${special_root}/repository/_work/data"
printf 'unchanged\n' >"$special_file"
chmod 0604 "$special_file"
mkfifo "${special_root}/repository/_work/job.fifo"
special_before=$(stat --format '%u:%g:%a' "$special_file")
assert_fails_with \
	'unsupported file type' \
	"unsupported file type: ${special_root}/repository/_work/job.fifo" \
	"$helper" \
	--runner-root "$special_root" \
	--owner "$owner_name" \
	--group "$group_name"
special_after=$(stat --format '%u:%g:%a' "$special_file")
[[ $special_after == "$special_before" ]] ||
	fail 'unsupported entry detection did not precede mutation'

group_probe="${runner_root}/repository-a/_work/group-probe"
# shellcheck disable=SC2016
setpriv \
	--reuid "$probe_uid" \
	--regid "$group_gid" \
	--clear-groups \
	bash -c \
	'printf "group-write\n" >>"$1"; mkdir "$2"; touch "$2/file"' \
	_ \
	"$work_file" \
	"$group_probe"

[[ $(stat --format %g "$group_probe") == "$group_gid" ]] ||
	fail 'a new directory did not inherit the shared group'
[[ $(stat --format %A "$group_probe") == drwxrws--- ]] ||
	fail 'a new directory did not inherit writable group access'
[[ $(stat --format %g "${group_probe}/file") == "$group_gid" ]] ||
	fail 'a new file did not inherit the shared group'
[[ $(stat --format %A "${group_probe}/file") == -rw-rw---- ]] ||
	fail 'a new file did not inherit writable group access'
[[ $(stat --format %u "$group_probe") == "$probe_uid" ]] ||
	fail 'the cross-UID probe was not owned by its creator'

git_home="${temporary_directory}/git-home"
git_repository="${runner_root}/repository-a/_work/git-probe"
install \
	--directory \
	--owner "$probe_uid" \
	--group "$group_gid" \
	--mode 0700 \
	"$git_home"
# shellcheck disable=SC2016
setpriv \
	--reuid "$probe_uid" \
	--regid "$group_gid" \
	--clear-groups \
	env HOME="$git_home" \
	bash -c '
		set -euo pipefail
		repository=$1
		git init --quiet --initial-branch=main "$repository"
		git -C "$repository" config user.email ci@example.invalid
		git -C "$repository" config user.name CI
		printf "tracked\n" >"${repository}/tracked"
		git -C "$repository" add tracked
		git -C "$repository" commit --quiet --message initial
	' \
	_ \
	"$git_repository"

git_object=$(
	find "${git_repository}/.git/objects" \
		-mindepth 2 \
		-maxdepth 2 \
		-type f \
		-print \
		-quit
)
[[ -n $git_object ]] ||
	fail 'Git did not create a loose object'
[[ $(stat --format %a "$git_object") == 440 ]] ||
	fail 'a Git loose object did not inherit read-only group access'
[[ $(getfacl -cp "$git_object") == "$expected_read_only_acl" ]] ||
	fail 'a Git loose object did not inherit the read-only ACL'

post_container_check_output=$(
	setpriv \
		--reuid "$owner_uid" \
		--regid "$owner_gid" \
		--init-groups \
		"$helper" \
		--runner-root "$runner_root" \
		--owner "$owner_name" \
		--group "$group_name" \
		--check
)
[[ $post_container_check_output == *'verified status=ok mode=check targets=3'* ]] ||
	fail 'verification rejected a valid cross-UID descendant'

chmod +t "$group_probe"
assert_fails_with \
	'sticky directory check' \
	"directory mode verification failed: ${group_probe}" \
	setpriv \
	--reuid "$owner_uid" \
	--regid "$owner_gid" \
	--init-groups \
	"$helper" \
	--runner-root "$runner_root" \
	--owner "$owner_name" \
	--group "$group_name" \
	--check
chmod 2770 "$group_probe"

runner_owned_file="${runner_root}/repository-b/_work/_temp/runner-owned"
[[ $(stat --format %u "$runner_owned_file") == "$owner_uid" ]] ||
	fail 'the deletion probe was not owned by the runner'
setpriv \
	--reuid "$probe_uid" \
	--regid "$group_gid" \
	--clear-groups \
	rm -- "$runner_owned_file"
[[ ! -e $runner_owned_file ]] ||
	fail 'a shared-group identity could not remove a runner-owned entry'

empty_root="${temporary_directory}/empty-root"
mkdir -p "$empty_root"
chmod 0755 "$empty_root"

empty_dry_run_output=$(
	"$helper" \
		--runner-root "$empty_root" \
		--owner "$owner_name" \
		--group "$group_name" \
		--dry-run
)
[[ $empty_dry_run_output == *'shared=create'* ]] ||
	fail 'missing shared parent creation was not planned'
[[ $empty_dry_run_output == *'cache=create'* ]] ||
	fail 'missing cache creation was not planned'
[[ ! -e ${empty_root}/shared ]] ||
	fail 'dry-run created the shared parent'
assert_fails_with \
	'missing shared parent check' \
	"shared root is missing: ${empty_root}/shared" \
	setpriv \
	--reuid "$owner_uid" \
	--regid "$owner_gid" \
	--init-groups \
	"$helper" \
	--runner-root "$empty_root" \
	--owner "$owner_name" \
	--group "$group_name" \
	--check
[[ ! -e ${empty_root}/shared ]] ||
	fail 'verification-only mode created the shared parent'

create_output=$(
	"$helper" \
		--runner-root "$empty_root" \
		--owner "$owner_name" \
		--group "$group_name"
)
[[ $create_output == *'shared=create'* ]] ||
	fail 'missing shared parent creation was not reported'
[[ $create_output == *'cache=create'* ]] ||
	fail 'missing cache creation was not reported'
[[ $create_output == *'verified status=ok targets=1'* ]] ||
	fail 'created cache verification was not reported'
shared_identity=$(
	stat --format '%u:%g:%a' "${empty_root}/shared"
)
[[ $shared_identity == "${owner_uid}:${owner_gid}:755" ]] ||
	fail 'missing shared parent was not safely provisioned'
cache_identity=$(
	stat --format '%u:%g:%a' "${empty_root}/shared/cache"
)
[[ $cache_identity == "${owner_uid}:${group_gid}:2770" ]] ||
	fail 'missing cache root was not provisioned'

assert_fails_with \
	'non-root execution' \
	'run as root' \
	setpriv \
	--reuid "$probe_uid" \
	--regid "$group_gid" \
	--clear-groups \
	bash "$helper" \
	--runner-root "$runner_root" \
	--owner "$owner_name" \
	--group "$group_name" \
	--dry-run

printf 'setup-runner-permissions integration passed\n'
