"""Dispatch native Bash entry points using only this release and the standard library."""

import pathlib
import sys

library = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(library), str(library / "ci_utils")]
command = sys.argv.pop(1)
sys.argv[0] = command

if command in ("ci-utils", "ci-utils-list"):
    from ci_utils.catalog import main

    raise SystemExit(main(command))
if command in ("ci-go-cleanup", "ci-pnpm-cleanup"):
    from ci_utils.file_cache import main

    raise SystemExit(main("go" if command == "ci-go-cleanup" else "pnpm"))
if command == "ci-docker-maintenance":
    from ci_docker_maintenance import main

    raise SystemExit(main())
if command == "ci-docker-cleanup":
    from ci_utils.cleanup import main

    raise SystemExit(main(probe=library / "ci-buildkit-probe"))
if command == "ci-remove-images":
    from ci_utils.remove_images import main
elif command == "ci-upgrade-images":
    from ci_utils.upgrade_images import main
else:
    sys.exit(f"unknown ci-utils command: {command}")

raise SystemExit(main())
