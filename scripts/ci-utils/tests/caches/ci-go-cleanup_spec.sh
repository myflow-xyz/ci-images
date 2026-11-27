# shellcheck shell=bash

Describe 'ci-go-cleanup'
setup_cache() {
	root=$(cd "$(mktemp -d)" && pwd -P)
	mkdir -p "$root/go/build" "$root/go/mod"
	touch "$root/go/build/cache" "$root/go/mod/cache"
}
BeforeEach setup_cache
remove_fixture() { rm -rf "$root"; }
AfterEach remove_fixture
tool="${CI_UTILS_BIN:-$SHELLSPEC_PROJECT_ROOT/ci-utils/bin}/ci-go-cleanup"

It 'previews both selected caches without writing'
When run "$tool" --build-cache "$root/go/build" --mod-cache "$root/go/mod"
The status should be success
The output should include '"mode": "plan"'
The path "$root/go/build/cache" should be file
The path "$root/go/mod/cache" should be file
End
It 'resets only the selected build cache'
When run "$tool" --build-cache "$root/go/build" --apply
The status should be success
The output should include '"event": "cache_reset"'
The path "$root/go/build" should be directory
The path "$root/go/build/cache" should not be exist
The path "$root/go/mod/cache" should be file
End
It 'checks all roots before resetting the first'
When run "$tool" --build-cache "$root/go/build" --mod-cache "$root/missing/go/mod" --apply
The status should eq 2
The error should include 'cannot open go-mod'
The output should include '"mutation_started": false'
The path "$root/go/build/cache" should be file
End
End
