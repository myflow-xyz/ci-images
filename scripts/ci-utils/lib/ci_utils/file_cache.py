"""Explicit, offline resets of Go and pnpm cache directories."""

import argparse
import contextlib
import fcntl
import json
import os
import pathlib
import re
import signal
import stat
import sys

from .cleanup import Parser, Report
from .engine import Failure
from .policy import InvalidPolicy

SUFFIXES = {
    "go-build": ("go", "build"),
    "go-mod": ("go", "mod"),
    "pnpm-store": ("pnpm", "store"),
}
DEFAULT_PATHS = {
    kind: "/opt/actions-runner/shared/cache/" + "/".join(suffix)
    for kind, suffix in SUFFIXES.items()
}
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def cache_path(value, kind):
    path = pathlib.Path(value)
    if (
        not path.is_absolute()
        or value != os.path.normpath(value)
        or value.startswith("//")
        or path.parts[-2:] != SUFFIXES[kind]
    ):
        raise InvalidPolicy(
            f"{kind} requires an absolute path ending in {'/'.join(SUFFIXES[kind])} "
            "without dot components or a trailing slash"
        )
    return path


def open_directory(path):
    """Resolve every component through directory descriptors without symlinks."""
    fd = os.open("/", DIRECTORY_FLAGS)
    try:
        for part in path.parts[1:]:
            child = os.open(part, DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def identity(info):
    return info.st_dev, info.st_ino


def check_root(path, info):
    current = open_directory(path)
    try:
        if identity(os.fstat(current)) != identity(info):
            raise InvalidPolicy(f"cache root changed: {path}")
    finally:
        os.close(current)


def reject_nested_mounts(path):
    # st_dev alone does not detect a bind mount of the same filesystem.
    if sys.platform == "linux":
        for line in pathlib.Path("/proc/self/mountinfo").read_text().splitlines():
            fields = line.split()
            if len(fields) < 7 or "-" not in fields:
                raise InvalidPolicy("cannot read the mount inventory")
            mount = re.sub(
                r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), fields[4]
            )
            if mount.startswith(str(path) + "/"):
                raise InvalidPolicy(f"nested mount inside cache: {mount}")


def walk_cache(fd, path, device, *, remove=False):
    """Count or remove entries relative to open directories; keep the root."""
    counts = {"files": 0, "directories": 0, "symlinks": 0, "logical_bytes": 0}
    for name in os.listdir(fd):
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        child_path = path / name
        if info.st_dev != device:
            raise InvalidPolicy(f"filesystem boundary inside cache: {child_path}")
        if stat.S_ISDIR(info.st_mode):
            if os.path.ismount(child_path):
                raise InvalidPolicy(f"nested mount inside cache: {child_path}")
            child = os.open(name, DIRECTORY_FLAGS, dir_fd=fd)
            with contextlib.ExitStack() as stack:
                stack.callback(os.close, child)
                if identity(os.fstat(child)) != identity(info):
                    raise InvalidPolicy(f"cache directory changed: {child_path}")
                mode = stat.S_IMODE(info.st_mode)
                changed_mode = False
                try:
                    # Go's unpacked module directories are normally read-only.
                    # Do not change the cache root or another owner's permissions.
                    if (
                        remove
                        and info.st_uid == os.geteuid()
                        and not mode & stat.S_IWUSR
                    ):
                        os.fchmod(child, mode | stat.S_IWUSR)
                        changed_mode = True
                    nested = walk_cache(child, child_path, device, remove=remove)
                    if remove:
                        current = os.stat(name, dir_fd=fd, follow_symlinks=False)
                        if identity(current) != identity(info):
                            raise InvalidPolicy(
                                f"cache directory changed: {child_path}"
                            )
                        os.rmdir(name, dir_fd=fd)
                except BaseException:
                    if changed_mode:
                        os.fchmod(child, mode)
                    raise
            for key, value in nested.items():
                counts[key] += value
            counts["directories"] += 1
        elif stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
            if remove:
                os.unlink(name, dir_fd=fd)
            if stat.S_ISREG(info.st_mode):
                counts["files"] += 1
                counts["logical_bytes"] += info.st_size
            else:
                counts["symlinks"] += 1
        else:
            raise InvalidPolicy(f"unsupported special file inside cache: {child_path}")
    return counts


def arguments(tool, argv):
    examples = (
        "Examples:\n"
        "  ci-go-cleanup                         # Preview both mfci Go caches\n"
        "  ci-go-cleanup --build-cache           # Preview only the default build cache\n"
        "  ci-go-cleanup --mod-cache             # Preview only the default module cache\n"
        "  ci-go-cleanup --build-cache /var/cache/go/build\n"
        "  ci-go-cleanup --build-cache /var/cache/go/build --mod-cache /var/cache/go/mod\n"
        "  ci-go-cleanup --apply                 # Reset both defaults after consumers stop"
        if tool == "go"
        else "Examples:\n"
        "  ci-pnpm-cleanup                       # Preview the mfci pnpm store\n"
        "  ci-pnpm-cleanup --store-dir            # Preview the same default store\n"
        "  ci-pnpm-cleanup --store-dir /var/cache/pnpm/store\n"
        "  ci-pnpm-cleanup --apply               # Reset the default after consumers stop"
    )
    parser = Parser(
        prog=f"ci-{tool}-cleanup",
        description=(
            "Reset selected caches completely, preserving their root directories. "
            "Default: preview only. Stop all cache consumers before --apply."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=examples,
    )
    if tool == "go":
        parser.add_argument(
            "--build-cache",
            nargs="?",
            const=DEFAULT_PATHS["go-build"],
            metavar="PATH",
            help=f"select the build cache; omitted PATH:\n{DEFAULT_PATHS['go-build']}",
        )
        parser.add_argument(
            "--mod-cache",
            nargs="?",
            const=DEFAULT_PATHS["go-mod"],
            metavar="PATH",
            help=f"select the module cache; omitted PATH:\n{DEFAULT_PATHS['go-mod']}",
        )
    else:
        parser.add_argument(
            "--store-dir",
            nargs="?",
            default=DEFAULT_PATHS["pnpm-store"],
            const=DEFAULT_PATHS["pnpm-store"],
            metavar="PATH",
            help=f"store path; default:\n{DEFAULT_PATHS['pnpm-store']}",
        )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="reset caches after all consumers have stopped",
    )
    args = parser.parse_args(argv)
    selected = (
        [("go-build", args.build_cache), ("go-mod", args.mod_cache)]
        if tool == "go"
        else [("pnpm-store", args.store_dir)]
    )
    selected = [(kind, value) for kind, value in selected if value is not None]
    if not selected:
        selected = [(kind, DEFAULT_PATHS[kind]) for kind in ("go-build", "go-mod")]
    selected = [(kind, cache_path(value, kind)) for kind, value in selected]
    for _, path in selected:
        if any(path != other and path.is_relative_to(other) for _, other in selected):
            parser.error("selected caches must not overlap")
    return args, selected


def interrupted(signum, frame):
    raise Failure(5, "cache reset interrupted; inspect the caches before resuming jobs")


def main(tool, argv=None):
    report = Report()
    code = 0
    mutation_started = False
    old_signals = {}
    try:
        args, selected = arguments(tool, argv)
        report.context = {"mode": "apply" if args.apply else "plan", "tool": tool}
        for signum in (signal.SIGINT, signal.SIGTERM):
            old_signals[signum] = signal.signal(signum, interrupted)
        with contextlib.ExitStack() as stack:
            caches = []
            identities = set()
            # Validate, lock, and inspect every selection before the first mutation.
            for kind, path in selected:
                try:
                    fd = open_directory(path)
                except OSError as error:
                    raise InvalidPolicy(
                        f"cannot open {kind} cache at {path}: {error}"
                    ) from error
                stack.callback(os.close, fd)
                info = os.fstat(fd)
                if identity(info) in identities:
                    raise InvalidPolicy("selected caches refer to the same directory")
                identities.add(identity(info))
                try:
                    fcntl.flock(
                        fd,
                        (fcntl.LOCK_EX if args.apply else fcntl.LOCK_SH)
                        | fcntl.LOCK_NB,
                    )
                except BlockingIOError as error:
                    raise Failure(
                        4, f"another cleanup holds the cache lock: {path}"
                    ) from error
                reject_nested_mounts(path)
                counts = walk_cache(fd, path, info.st_dev)
                caches.append((kind, path, fd, info))
                report.emit(
                    "cache_plan",
                    kind=kind,
                    path=str(path),
                    action="reset",
                    requires_idle_consumers=True,
                    **counts,
                    physical_reclaimed_bytes=None,
                )
            if args.apply:
                for kind, path, fd, info in caches:
                    check_root(path, info)
                    reject_nested_mounts(path)
                    mutation_started = True
                    counts = walk_cache(fd, path, info.st_dev, remove=True)
                    if os.listdir(fd):
                        raise Failure(5, f"cache changed during reset: {path}")
                    check_root(path, info)
                    report.emit(
                        "cache_reset",
                        kind=kind,
                        path=str(path),
                        **counts,
                        physical_reclaimed_bytes=None,
                    )
    except (InvalidPolicy, OSError, RecursionError, Failure) as error:
        code = (
            error.code if isinstance(error, Failure) else 5 if mutation_started else 2
        )
        report.emit("error", message=str(error), exit_code=code)
        print(json.dumps(str(error)), file=sys.stderr)
    finally:
        for signum, handler in old_signals.items():
            signal.signal(signum, handler)
    report.finish(code, mutation_started)
    return code
