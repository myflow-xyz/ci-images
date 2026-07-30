# shellcheck shell=sh

Describe 'setup-runner-permissions.sh CLI'
	helper="${SHELLSPEC_PROJECT_ROOT}/setup-runner-permissions.sh"

	It 'documents the runner-root interface'
		When run "$helper" --help
		The status should be success
		The output should include '<runner-root>/workspace/*/_work'
		The output should include '--runner-root PATH'
		The output should include '--check'
		The output should include 'membership is verified but never changed'
		The output should not include 'runner-home'
		The error should be blank
	End

	It 'rejects the retired runner-home option'
		When run "$helper" --runner-home /tmp
		The status should eq 64
		The error should include 'unknown option: --runner-home'
	End

	It 'rejects a missing runner-root value'
		When run "$helper" --runner-root
		The status should eq 64
		The error should include '--runner-root requires a value'
	End

	It 'rejects positional arguments'
		When run "$helper" /opt/actions-runner
		The status should eq 64
		The error should include 'unexpected argument'
	End

	It 'rejects conflicting read-only modes'
		When run "$helper" --check --dry-run
		The status should eq 64
		The error should include 'mutually exclusive'
	End

	It 'accepts the runner-root equals form before privilege validation'
		Skip if 'requires root to select a non-root identity' \
			[ "$(id -u)" -ne 0 ]
		When run command setpriv \
			--reuid 65534 \
			--regid 65534 \
			--clear-groups \
			"$helper" \
			--runner-root=/tmp \
			--dry-run
		The status should eq 1
		The error should include 'run as root'
		The error should not include 'unknown option'
	End
End
