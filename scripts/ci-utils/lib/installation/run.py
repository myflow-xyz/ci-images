"""Dispatch native Bash entry points using only this release and the standard library."""

import pathlib
import sys

library = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(library.parent))
command = sys.argv.pop(1)
sys.argv[0] = command

if command in ("ci-utils", "ci-utils-list"):
    from lib.catalog.commands import main

    raise SystemExit(main(command))
if command in ("ci-go-cleanup", "ci-pnpm-cleanup"):
    from lib.caches.file_cache import main

    raise SystemExit(main("go" if command == "ci-go-cleanup" else "pnpm"))
if command == "ci-docker-maintenance":
    from lib.maintenance.ci_docker_maintenance import main

    raise SystemExit(main())
if command == "ci-docker-cleanup":
    from lib.maintenance.cleanup import main
elif command == "ci-remove-images":
    from lib.images.remove_images import main
elif command == "ci-upgrade-images":
    from lib.images.upgrade_images import main
else:
    sys.exit(f"unknown ci-utils command: {command}")

raise SystemExit(main())
