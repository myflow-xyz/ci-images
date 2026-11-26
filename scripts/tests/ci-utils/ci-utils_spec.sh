# shellcheck shell=bash

Describe 'ci-utils'
It 'shows offline command help with an unusable daemon'
When run env DOCKER_HOST=invalid "${CI_UTILS_BIN:-$SHELLSPEC_PROJECT_ROOT/ci-utils/bin}/ci-utils"
The status should be success
The output should include 'usage: ci-utils'
The output should include 'ci-docker-maintenance'
End
End
