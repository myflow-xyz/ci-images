# shellcheck shell=bash

Describe 'ci-pnpm-cleanup'
setup_store() {
	root=$(cd "$(mktemp -d)" && pwd -P)
	mkdir -p "$root/pnpm/store" "$root/other/pnpm"
	touch "$root/pnpm/store/item"
	ln -s "$root/pnpm/store" "$root/other/pnpm/store"
}
BeforeEach setup_store
remove_fixture() { rm -rf "$root"; }
AfterEach remove_fixture
tool="${CI_UTILS_BIN:-$SHELLSPEC_PROJECT_ROOT/ci-utils/bin}/ci-pnpm-cleanup"

It 'preserves store entries in preview'
When run "$tool" --store-dir "$root/pnpm/store"
The status should be success
The output should include '"mode": "plan"'
The path "$root/pnpm/store/item" should be file
End
It 'resets the store and preserves the root'
When run "$tool" --store-dir "$root/pnpm/store" --apply
The status should be success
The output should include '"event": "cache_reset"'
The path "$root/pnpm/store" should be directory
The path "$root/pnpm/store/item" should not be exist
End
It 'refuses a symlink root before changing its target'
When run "$tool" --store-dir "$root/other/pnpm/store" --apply
The status should eq 2
The error should include 'cannot open pnpm-store'
The output should include '"mutation_started": false'
The path "$root/pnpm/store/item" should be file
End
End
