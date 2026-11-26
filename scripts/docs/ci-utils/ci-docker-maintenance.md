# ci-docker-maintenance

Coordinate complete runner jobs and guarded Docker maintenance on a local Linux daemon. Set `--config PATH` before the subcommand to override `/etc/ci-utils/host.json`. The settings name a separate root-owned cleanup policy, the daemon participants, their shared group, the Docker CLI, storage roots and the persistent gate. Review and provision these paths as administrator. [Host and service templates](../../examples/ci-utils/)

```bash
ci-docker-maintenance status
sudo ci-docker-maintenance plan --profile daily
# After reviewing the plan
sudo ci-docker-maintenance apply --profile daily --wait 15m
```

| Operation | Options, defaults and effects |
| --- | --- |
| `init`, `status` | Initialize a new gate once as root. Status reads job and maintenance records. Preserve existing gates across upgrades. |
| `job --participant NAME -- COMMAND ...` | Hold shared admission through all Docker work and teardown. `--wait` defaults to `15m` and `--timeout` to `12h`. Jobs require membership in the reviewed group and a configured capacity reserve. |
| `job-complete` | The admitted job calls this after its children and daemon operations finish. It writes a completion receipt. Existing hooks can use `/usr/local/libexec/ci-utils/ci-docker-maintenance`. |
| `check`, `plan`, `apply` | Run an administrator-owned worker from the verified release. `--profile` defaults to `daily` and also accepts `weekly`. Apply waits up to `--wait` (default `15m`) for exclusive admission. |
| `remove-images` | Preview retirement. Optional `--versions X.Y.Z[,X.Y.Z]` selects tags. `--apply` requires exclusive admission. `--wait` defaults to `15m`. |
| `reconcile --record-id ID --evidence FILE` | As root, verify current evidence for one unresolved job or maintenance run. Persist the audit before reopening admission. |

Host JSON Lines identify the admitted job or maintenance run, daemon and policy. Known maintenance completion emits the worker's result and `host_result`. A signal, lost reply or missing job receipt can leave admission blocked. Disable dispatch, inspect `status`, verify participant drainage and daemon completion, then reconcile with a root-owned evidence file. [Evidence fields and recovery procedure](../../../docs/maintenance.md#reconcile-uncertain-completion)

Exit 0 means success. Job preserves the child exit code after confirmed finalization. Codes 2, 3, 4, 5 and 6 indicate invalid settings or input, daemon access or identity failure, unavailable admission, application failure and uncertain completion respectively. Use `-h` on the adapter or any subcommand.

Run `(cd scripts && shellspec tests/ci-utils/ci-docker-maintenance_spec.sh)` from the repository root.
