# shellcheck shell=sh

Describe 'setup-runner-from-scratch.sh CLI'
	helper="${SHELLSPEC_PROJECT_ROOT}/setup-runner-from-scratch.sh"

	It 'documents the required structure and inputs'
		When run "$helper" --help
		The status should be success
		The output should include '<runner-root>/workspace/<repository>/_work'
		The output should include '<runner-root>/shared/{bin,cache,downloads}'
		The output should include '--owner USER|UID'
		The output should include '--repository NAME'
		The output should include '/opt, /var, /home, or /Users'
		The output should include 'Missing mfci is created with GID 2001'
		The output should include 'install the acl package on Debian or RHEL'
		The output should include 'membership is verified but never changed'
		The error should be blank
	End

	It 'requires an explicit runner root'
		When run "$helper"
		The status should eq 64
		The error should include '--runner-root is required'
	End

	It 'requires an explicit owner'
		When run "$helper" --runner-root /opt/actions-runner
		The status should eq 64
		The error should include '--owner is required'
	End

	It 'requires an explicit repository'
		When run "$helper" \
			--runner-root /opt/actions-runner \
			--owner github-runner
		The status should eq 64
		The error should include '--repository is required'
	End

	It 'rejects repository path traversal'
		When run "$helper" \
			--runner-root /opt/actions-runner \
			--owner github-runner \
			--repository ../other
		The status should eq 64
		The error should include 'invalid repository name'
	End

	It 'rejects unknown options'
		When run "$helper" --runner-home /opt/actions-runner
		The status should eq 64
		The error should include 'unknown option: --runner-home'
	End

	It 'requires root after validating equals-form inputs'
		Skip if 'requires a non-root test process' [ "$(id -u)" -eq 0 ]
		When run "$helper" \
			--runner-root=/opt/actions-runner \
			--owner=github-runner \
			--repository=repo-example \
			--group=mfci \
			--dry-run
		The status should eq 1
		The error should include 'run as root'
		The error should not include 'unknown option'
	End
End
