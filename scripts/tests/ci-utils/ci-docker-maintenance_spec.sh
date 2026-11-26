# shellcheck shell=bash

Describe 'ci-docker-maintenance'
	It 'refuses a completion receipt outside an admitted job'
		When run env -u CI_DOCKER_JOB_ID "${CI_UTILS_BIN:-$SHELLSPEC_PROJECT_ROOT/ci-utils/bin}/ci-docker-maintenance" job-complete
		The status should eq 2
		The output should include '"event": "host_error"'
	End
End
