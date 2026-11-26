# shellcheck shell=bash

Describe 'ci-upgrade-images'
	It 'requires a reachable selected daemon before refreshing'
		When run "${CI_UTILS_BIN:-$SHELLSPEC_PROJECT_ROOT/ci-utils/bin}/ci-upgrade-images" --endpoint unix:///missing-fixture/docker.sock
		The status should eq 3
		The output should include '"mutation_started": false'
		The error should be present
	End
End
