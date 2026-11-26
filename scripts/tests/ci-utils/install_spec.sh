# shellcheck shell=bash

Describe 'ci-utils installer'
	installer="$SHELLSPEC_PROJECT_ROOT/ci-utils/install.sh"

	It 'identifies a missing Bash before touching the target'
		When run env PATH=/nonexistent /bin/sh "$installer" 1.2.3 --prefix "$SHELLSPEC_TMPBASE/missing-bash"
		The status should be failure
		The error should include 'Bash >= 5.0'
		The error should include 'missing'
		The path "$SHELLSPEC_TMPBASE/missing-bash" should not be exist
	End
	It 'requires a pinned numeric release'
		When run "$installer" latest --prefix "$SHELLSPEC_TMPBASE/unpinned"
		The status should be failure
		The error should include 'X.Y.Z'
		The path "$SHELLSPEC_TMPBASE/unpinned" should not be exist
	End
End
