# shellcheck shell=bash

Describe 'ci-remove-images'
	It 'identifies the missing selected policy before accessing Docker'
		When run "${CI_UTILS_BIN:-$SHELLSPEC_PROJECT_ROOT/ci-utils/bin}/ci-remove-images" --config "$SHELLSPEC_TMPBASE/absent.json"
		The status should eq 2
		The error should include "$SHELLSPEC_TMPBASE/absent.json"
		The output should include '"mutation_started": false'
	End
End
