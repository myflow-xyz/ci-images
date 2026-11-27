# shellcheck shell=bash

Describe 'ci-docker-cleanup'
It 'reports the build identity offline'
When run "${CI_UTILS_BIN:-$SHELLSPEC_PROJECT_ROOT/ci-utils/bin}/ci-docker-cleanup" version
The status should be success
The output should include '"event": "version"'
The output should include '"revision":'
The output should include '"version":'
End
End
