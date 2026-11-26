"""Process helpers and a delayed Engine response for the isolated daemon suites."""

import http.server
import pathlib
import shutil
import socketserver
import subprocess
import sys
import threading
import time

sys.path.insert(0, "/workspace/scripts/ci-utils/lib")
from ci_utils.engine import UnixConnection

ROOT = pathlib.Path("/run/ci-utils-test")
SOCKET = "unix:///run/ci-utils-test/docker.sock"
DOCKER = str(pathlib.Path(shutil.which("docker")).resolve())
OWNED = "xyz.myflow.ci.ephemeral=true"
PROTECTED = "xyz.myflow.cleanup.protect=true"


def command(args, expected=0, timeout=60, **identity):
    result = subprocess.run(
        args, capture_output=True, text=True, timeout=timeout, check=False, **identity
    )
    if result.returncode != expected:
        raise AssertionError(
            f"{args!r}: exit {result.returncode}, expected {expected}\n{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def docker(*args, **kwargs):
    return command([DOCKER, "--host", SOCKET, *args], **kwargs).strip()


def wait_for(predicate):
    deadline = time.monotonic() + 15
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("fixture did not reach the expected state within 15s")
        time.sleep(0.05)


class DelayedDeleteProxy:
    """Hold one real deletion reply so the test can kill its host coordinator."""

    def __init__(self, path, containers):
        self.path = path
        self.containers = containers
        self.deleted = threading.Event()
        self.release = threading.Event()
        self.replied = threading.Event()
        self.disconnect = False
        self.mutations = []
        fixture = self

        class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
            daemon_threads = True

        class Handler(http.server.BaseHTTPRequestHandler):
            def respond(self):
                connection = UnixConnection(SOCKET[7:], 30)
                delayed = False
                try:
                    body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                    connection.request(
                        self.command,
                        self.path,
                        body,
                        {
                            "Content-Type": self.headers.get(
                                "Content-Type", "application/json"
                            )
                        },
                    )
                    response = connection.getresponse()
                    data = response.read()
                    if self.command == "DELETE":
                        fixture.mutations.append(self.path)
                        identifier = self.path.split("?")[0].rsplit("/", 1)[-1]
                        if (
                            identifier in fixture.containers
                            and not fixture.deleted.is_set()
                        ):
                            delayed = True
                            fixture.deleted.set()
                            if not fixture.release.wait(15):
                                raise TimeoutError(
                                    "test did not release the completed deletion reply"
                                )
                            if fixture.disconnect:
                                return
                    self.send_response(response.status)
                    for key, value in response.getheaders():
                        if key.lower() not in (
                            "content-length",
                            "transfer-encoding",
                            "connection",
                        ):
                            self.send_header(key, value)
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    # The client may be the process deliberately killed by the test.
                    pass
                finally:
                    connection.close()
                    if delayed:
                        fixture.replied.set()

            do_GET = respond
            do_HEAD = respond
            do_POST = respond
            do_DELETE = respond

            def log_message(self, *args):
                pass

        self.server = Server(str(path), Handler)
        path.chmod(0o660)
        self.thread = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True
        )

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
