- PMem scoping: in the shared `mfinfra` pmem project, every repository-related knowledge block must use `module` anchor `ci`, and every repository-related work item must include tag `ci`.

## PMEM Anchors

Use `pmem kb anchors list` to discover stored IDs, optionally filtered by `--anchor-type module`. Follow pagination and reuse an ID for the same scope. `mfinfra` is shared by the foundation infrastructure repositories; this index lists only the anchors that apply to this repository.

| Anchor | Task area |
| --- | --- |
| `project:mfinfra` | Foundation infrastructure ownership, knowledge publication, verification policy, and agent runbooks |
| `module:ci` | CI images and their release tags, quality gates, pipeline and self-hosted runner practices, and test-first development |
| `module:release` | Release flow, candidates, and final releases |
