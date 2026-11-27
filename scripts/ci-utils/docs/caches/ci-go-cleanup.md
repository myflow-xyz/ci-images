# ci-go-cleanup

Preview or empty the Go build and module cache directories. With no flags, the command previews both `/opt/actions-runner/shared/cache/go/build` and `/opt/actions-runner/shared/cache/go/mod`. Specify `--build-cache [PATH]`, `--mod-cache [PATH]`, or both to select individual caches. A flag without a path uses its default. Use `-h` for help.

```bash
ci-go-cleanup --build-cache /var/cache/go/build
# After draining every consumer of the selected cache
ci-go-cleanup --build-cache /var/cache/go/build --apply
```

Use existing absolute directories ending in `go/build` or `go/mod`. Preview requires read and traversal access. Apply requires removal access. The command checks every selected root and rejects symlinked paths, overlapping roots, nested mounts and special files. It locks the roots, removes the selected contents and preserves the root directories. Subsequent builds may download modules or recompile. Run as the cache owner or another account with the required access. Go, Docker and network access are unnecessary.

JSON Lines report each `cache_plan`, each completed `cache_reset` and a final `result`. Exit 0 means success, 2 means invalid selection or pre-mutation access failure, 4 means another reset holds a lock, and 5 means interruption or failure during mutation. Inspect the selected cache before resuming jobs after exit 5.

Run `(cd scripts && shellspec ci-utils/tests/caches/ci-go-cleanup_spec.sh)` from the repository root.
