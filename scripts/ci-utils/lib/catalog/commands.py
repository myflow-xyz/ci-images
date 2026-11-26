"""Offline catalog of the commands installed for this runner."""

import argparse
import sys

MACOS_CATALOG = """Supported maintenance commands:
  ci-utils               Show command help or the installed release (--version).
  ci-utils-list          List the macOS client commands.
  ci-upgrade-images      Refresh cached suite images on the selected Linux Docker daemon.
    [--prune-old-versions] (default: keep old versions)

Examples:
  ci-utils --version
  ci-upgrade-images --help
"""

CATALOG = """Supported maintenance commands:
  ci-utils               Show this catalog and command help.
  ci-utils-list          List supported ci-utils commands.
  ci-docker-cleanup      Inspect or clean owned Docker resources.
    check|plan|apply|version (default: plan; apply requires the host adapter)
  ci-remove-images       Preview or remove old local CI image versions.
    [--versions X.Y.Z[,X.Y.Z]] [--apply] (default: dry-run, keep latest)
  ci-upgrade-images      Refresh cached MyFlow CI images and report exact versions.
    [--prune-old-versions] (default: keep old versions)
  ci-go-cleanup          Preview or reset Go build and module caches.
    [--build-cache [PATH]] [--mod-cache [PATH]] [--apply]
    Default: preview both mfci Go caches; cache flags select individual caches.
  ci-pnpm-cleanup        Preview or reset a pnpm store.
    [--store-dir [PATH]] [--apply] (default: preview the mfci pnpm store)
  ci-docker-maintenance  Coordinate jobs, guarded apply and recovery.
Docker tools:
  docker buildx         Docker Buildx CLI.
  ci-buildkit-probe     Internal capability checker used by Docker cleanup.

Examples:
  ci-utils-list
  ci-go-cleanup -h
  ci-pnpm-cleanup -h
  ci-docker-cleanup -h
  ci-remove-images -h
  ci-upgrade-images -h

Go and pnpm apply performs a full reset; stop all cache consumers first.
"""


def main(prog="ci-utils", argv=None):
    catalog = MACOS_CATALOG if sys.platform == "darwin" else CATALOG
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Reusable CI operations tools. Invoke each command directly.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=catalog,
    )
    if prog == "ci-utils":
        from lib.maintenance.cleanup import build_metadata

        build = build_metadata()
        parser.add_argument("--version", action="version",
                            version=f"%(prog)s {build['version']} (revision {build['revision']})")
    parser.add_argument("operation", nargs="?", choices=("help",), default="help")
    parser.parse_args(argv)
    if prog == "ci-utils-list":
        print(catalog, end="")
    else:
        parser.print_help()
    return 0
