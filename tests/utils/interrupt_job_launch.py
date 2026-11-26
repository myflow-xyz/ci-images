"""Test-only cancellation after child creation, before Popen returns its handle."""

import os
import pathlib
import runpy
import signal
import subprocess
import sys

original_popen = subprocess.Popen
pid_path = pathlib.Path(sys.argv[1])


def interrupted_launch(*args, **kwargs):
    kwargs.update(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    child = original_popen(*args, **kwargs)
    pid_path.write_text(str(child.pid))
    os.kill(os.getpid(), signal.SIGTERM)
    raise AssertionError("launcher did not handle cancellation")


subprocess.Popen = interrupted_launch
sys.argv = sys.argv[2:]
runpy.run_path(sys.argv[0], run_name="__main__")
