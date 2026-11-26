# ci-utils-list

Print the maintenance catalog for discovery or a runner diagnostic. The default and the optional `help` argument print command names, operations and examples. Use `-h` or `--help` to include usage syntax.

```bash
ci-utils-list
```

The list is plain text on stdout. Only the installed Bash and Python runtimes are required. Listing reads no caches, contacts no daemon and changes no files. Exit 0 means the catalog or help was displayed. Invalid arguments exit 2.

Run `(cd scripts && shellspec ci-utils/tests/catalog/ci-utils-list_spec.sh)` from the repository root.
