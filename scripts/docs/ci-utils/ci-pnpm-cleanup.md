# ci-pnpm-cleanup

Preview or reset a pnpm store, including all store versions. The default is `/opt/actions-runner/shared/cache/pnpm/store`. Use `--store-dir [PATH]` to select an existing absolute directory ending in `pnpm/store`. Omitting the value selects the default. Use `-h` for help.

```bash
ci-pnpm-cleanup --store-dir /var/cache/pnpm/store
# After draining every store consumer
ci-pnpm-cleanup --store-dir /var/cache/pnpm/store --apply
```

Preview inspects the entries. Explicit apply empties the store and preserves its root. Later installs may fetch packages again. The account needs traversal and read access for preview and removal access for apply. A symlinked root or nested mount is rejected. The installed Bash and Python runtimes suffice for both modes.

JSON Lines report a `cache_plan`, a `cache_reset` on successful apply and a final `result`. Exit codes are 0 for success, 2 for invalid input or pre-mutation access failure, 4 for lock contention and 5 for interruption or failure during mutation.

Run `(cd scripts && shellspec tests/ci-utils/ci-pnpm-cleanup_spec.sh)` from the repository root.
