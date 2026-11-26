# shellcheck shell=bash

Describe 'ci-utils-list'
It 'lists the native maintenance commands without a configured daemon'
When run env DOCKER_HOST=invalid "${CI_UTILS_BIN:-$SHELLSPEC_PROJECT_ROOT/ci-utils/bin}/ci-utils-list"
The status should be success
The output should include 'Supported maintenance commands'
The output should include 'ci-docker-maintenance'
End
End
