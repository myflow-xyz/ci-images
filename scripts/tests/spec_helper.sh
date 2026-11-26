# shellcheck shell=sh

spec_helper_precheck() {
	: minimum_version "0.28.1"

	command -v bash >/dev/null 2>&1 ||
		abort 'bash is required'
	command -v shellcheck >/dev/null 2>&1 ||
		abort 'shellcheck is required'
	command -v shfmt >/dev/null 2>&1 ||
		abort 'shfmt is required'

	set -- ci-utils/install.sh ci-utils/bin/* ci-utils/tests/*/*.sh
	for source in "$@"; do
		bash -n "$source" || abort "Bash syntax failed in $source"
	done
	shellcheck --severity=style "$@" || abort 'ci-utils ShellCheck failed'
	shfmt -ln bash -d "$@" || abort 'ci-utils shfmt failed'
	# The POSIX bootstrap feeds the complete installer to the selected Bash.
	body=$(sed -n "/^exec bash -s -- /,/^CI_UTILS_INSTALL$/p" ci-utils/install.sh | sed '1d;$d')
	printf '%s\n' "$body" | bash -n || abort 'installer Bash syntax failed'
	printf '%s\n' "$body" | shellcheck -s bash - || abort 'installer ShellCheck failed'
	printf '%s\n' "$body" | shfmt -ln bash -d || abort 'installer shfmt failed'

	bash -n \
		setup-runner-from-scratch.sh \
		setup-runner-permissions.sh \
		setup-runner-user.sh \
		tests/setup-runner-from-scratch_integration.sh \
		tests/setup-runner-from-scratch_spec.sh \
		tests/setup-runner-permissions_integration.sh \
		tests/setup-runner-permissions_spec.sh \
		tests/setup-runner-user_integration.sh \
		tests/setup-runner-user_spec.sh \
		tests/spec_helper.sh ||
		abort 'bash syntax check failed'

	shellcheck --severity=style \
		setup-runner-from-scratch.sh \
		setup-runner-permissions.sh \
		setup-runner-user.sh \
		tests/setup-runner-from-scratch_integration.sh \
		tests/setup-runner-from-scratch_spec.sh \
		tests/setup-runner-permissions_integration.sh \
		tests/setup-runner-permissions_spec.sh \
		tests/setup-runner-user_integration.sh \
		tests/setup-runner-user_spec.sh \
		tests/spec_helper.sh ||
		abort 'ShellCheck failed'

	shfmt -d \
		setup-runner-from-scratch.sh \
		setup-runner-permissions.sh \
		setup-runner-user.sh \
		tests/setup-runner-from-scratch_integration.sh \
		tests/setup-runner-permissions_integration.sh \
		tests/setup-runner-user_integration.sh \
		tests/spec_helper.sh ||
		abort 'shfmt failed'
}
