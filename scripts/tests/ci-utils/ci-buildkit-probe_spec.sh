# shellcheck shell=bash

Describe 'packaged ci-buildkit-probe'
probe="${CI_UTILS_PROBE:-/usr/local/libexec/ci-utils/current/lib/ci-buildkit-probe}"
Skip if 'requires an installed Linux archive' test ! -x "$probe"

It 'requires an explicit socket and daemon ID'
When run "$probe"
The status should eq 2
The error should include 'explicit local Unix endpoint, daemon identity'
End

It 'identifies the selected local BuildKit worker'
Skip if 'requires the disposable daemon' test -z "${CI_UTILS_PROBE_ENDPOINT:-}"
When run "$probe" --host "$CI_UTILS_PROBE_ENDPOINT" --expected-daemon-id "$CI_UTILS_DAEMON_ID"
The status should be success
The output should include "$CI_UTILS_DAEMON_ID"
The output should include '"driver":"docker"'
The output should include '"worker_id":'
End

It 'rejects a different daemon identity'
Skip if 'requires the disposable daemon' test -z "${CI_UTILS_PROBE_ENDPOINT:-}"
When run "$probe" --host "$CI_UTILS_PROBE_ENDPOINT" --expected-daemon-id wrong-daemon
The status should eq 2
The error should include 'daemon identity mismatch'
End
End
