# shellcheck shell=sh

Describe 'setup-runner-user.sh CLI'
	helper="${SHELLSPEC_PROJECT_ROOT}/setup-runner-user.sh"

	It 'documents the fixed runner identity'
		When run "$helper" --help
		The status should be success
		The output should include 'user:              ci-runner'
		The output should include 'home:              /opt/actions-runner'
		The output should include 'primary group:     ci-runner'
		The output should include 'shared group:      mfci (GID 2001)'
		The output should include 'additional groups: docker, mfci'
		The output should include 'Docker group membership grants control of the Docker daemon'
		The output should include 'home path is configured on the account but created by the directory helper'
		The error should be blank
	End

	It 'rejects unknown options'
		When run "$helper" --user another-runner
		The status should eq 64
		The error should include 'unknown option: --user'
	End

	It 'rejects positional arguments'
		When run "$helper" ci-runner
		The status should eq 64
		The error should include 'unexpected argument: ci-runner'
	End

	It 'requires root for dry-run'
		Skip if 'requires a non-root test process' [ "$(id -u)" -eq 0 ]
		When run "$helper" --dry-run
		The status should eq 1
		The error should include 'run as root'
	End
End
