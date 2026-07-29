# shellcheck shell=sh

spec_helper_precheck() {
	: minimum_version "0.28.1"

	command -v bash >/dev/null 2>&1 ||
		abort 'bash is required'
	command -v shellcheck >/dev/null 2>&1 ||
		abort 'shellcheck is required'
	command -v shfmt >/dev/null 2>&1 ||
		abort 'shfmt is required'

	bash -n \
		setup-runner-permissions.sh \
		tests/setup-runner-permissions_integration.sh \
		tests/setup-runner-permissions_spec.sh \
		tests/spec_helper.sh ||
		abort 'bash syntax check failed'

	shellcheck --severity=style \
		setup-runner-permissions.sh \
		tests/setup-runner-permissions_integration.sh \
		tests/setup-runner-permissions_spec.sh \
		tests/spec_helper.sh ||
		abort 'ShellCheck failed'

	shfmt -d \
		setup-runner-permissions.sh \
		tests/setup-runner-permissions_integration.sh \
		tests/spec_helper.sh ||
		abort 'shfmt failed'
}
