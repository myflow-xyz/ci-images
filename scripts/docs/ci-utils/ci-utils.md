# ci-utils

Show command help and the maintenance catalog. Run `ci-utils` or `ci-utils help`. Use `-h` or `--help` for the same usage page.

```bash
ci-utils
```

The command prints plain text to stdout. It runs offline with the installed Bash and Python runtimes and leaves daemon, cache and gate state untouched. Exit 0 means help was displayed. Exit 2 indicates an invalid argument.

Run `(cd scripts && shellspec tests/ci-utils/ci-utils_spec.sh)` from the repository root.
