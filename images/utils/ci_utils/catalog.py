"""Offline catalog shared by the utility image's discovery commands."""

import argparse

CATALOG = """Supported maintenance commands:
  ci-utils               Show this catalog and command help.
  ci-utils-list          List supported ci-utils commands.
  ci-docker-cleanup      Inspect or clean owned Docker resources.
    check|plan|apply|version (default: plan; apply requires the host adapter)
  ci-remove-images       Preview or remove selected local CI image versions.
    --versions X.Y.Z[,X.Y.Z] [--apply] (default: dry-run)
  ci-go-cleanup          Preview or reset Go build and module caches.
    [--build-cache [PATH]] [--mod-cache [PATH]] [--apply]
    Default: preview both mfci Go caches; cache flags select individual caches.
  ci-pnpm-cleanup        Preview or reset a pnpm store.
    [--store-dir [PATH]] [--apply] (default: preview the mfci pnpm store)

Included Docker tools:
  docker buildx         Docker Buildx CLI.
  ci-buildkit-probe     Internal capability checker used by Docker cleanup.

Examples:
  ci-utils-list
  ci-go-cleanup -h
  ci-pnpm-cleanup -h
  ci-docker-cleanup -h
  ci-remove-images -h

Go and pnpm apply performs a full reset; stop all cache consumers first.
The image also includes the tools inherited from ci-base.
"""


def main(prog="ci-utils", argv=None):
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Reusable CI operations tools. Invoke each command directly.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=CATALOG,
    )
    parser.add_argument("operation", nargs="?", choices=("help",), default="help")
    parser.parse_args(argv)
    if prog == "ci-utils-list":
        print(CATALOG, end="")
    else:
        parser.print_help()
    return 0
