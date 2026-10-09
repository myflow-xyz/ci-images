"""Local Docker CLI fixture; container lifecycle is a subprocess, not a real daemon."""

import contextlib
import json
import socketserver
import subprocess
import sys
import tempfile
import threading

from test_apply_cli import DIGEST, ROOT


class HostDocker:
    def __init__(self, root, endpoint):
        self.path = root / "fake-docker"
        self.socket = root / "cli.sock"
        self.endpoint = endpoint
        self.calls = []
        self.mode = "success"
        self.process = None
        self.files = contextlib.ExitStack()
        self.container_id = "f" * 64
        fixture = self

        class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
            daemon_threads = True

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                request = json.loads(self.rfile.readline(65537))
                try:
                    result = fixture.call(request)
                except (
                    AssertionError,
                    OSError,
                    ValueError,
                    subprocess.SubprocessError,
                ) as error:
                    result = {"status": 1, "stderr": str(error), "stdout": ""}
                self.wfile.write((json.dumps(result) + "\n").encode())

        self.server = Server(str(self.socket), Handler)
        self.thread = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True
        )
        self.path.write_text(f"""#!{sys.executable}
import json, socket, sys
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
    client.connect({str(self.socket)!r})
    client.sendall((json.dumps(sys.argv[1:]) + "\\n").encode())
    response = json.loads(client.makefile("rb").readline())
sys.stdout.write(response["stdout"])
sys.stderr.write(response.get("stderr", ""))
sys.exit(response["status"])
""")
        self.path.chmod(0o755)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
            self.process.wait(timeout=5)
        self.files.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def call(self, args):
        if args[:1] != ["--config"] or args[2:4] != ["--host", self.endpoint]:
            return {
                "status": 1,
                "stdout": "",
                "stderr": "explicit daemon/config missing",
            }
        args = args[4:]
        self.calls.append(args)
        command = args[0]
        output = ""
        if args[:2] == ["image", "inspect"]:
            output = json.dumps(
                [
                    {
                        "Id": DIGEST,
                        "RepoDigests": [],
                        "Config": {
                            "User": "ci",
                            "Volumes": None,
                            "Entrypoint": None,
                            "Labels": {
                                "org.myflow.ci.utils-host-protocol": "0"
                                if self.mode == "wrong-image"
                                else "1"
                            },
                        },
                    }
                ]
            )
        elif command == "create":
            if self.mode == "create-error":
                return {"status": 125, "stdout": ""}
            self.create = args
            image_position = args.index(DIGEST)
            self.application_args = args[image_position + 1 :]
            mounts = {}
            self.environment = {
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "TMPDIR": "/tmp",
            }
            for position, value in enumerate(args[:image_position]):
                if value == "--mount":
                    fields = dict(
                        field.split("=", 1)
                        for field in args[position + 1].split(",")
                        if "=" in field
                    )
                    mounts[fields["dst"]] = fields["src"]
                elif value == "--env":
                    key, value = args[position + 1].split("=", 1)
                    if key not in ("TMPDIR", "HOME"):
                        self.environment[key] = value
            self.application_args = [
                mounts.get(value, value) for value in self.application_args
            ]
            self.application_args += ["--config", mounts["/etc/ci-utils/cleanup.json"]]
            output = self.container_id + "\n"
        elif command == "start":
            self.output = self.files.enter_context(tempfile.TemporaryFile())  # noqa: SIM115 - fixture ExitStack owns the file
            self.errors = self.files.enter_context(tempfile.TemporaryFile())  # noqa: SIM115 - fixture ExitStack owns the file
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    "-B",
                    str(ROOT / "images/utils/bin/ci-docker-cleanup"),
                    *self.application_args,
                ],
                stdout=self.output,
                stderr=self.errors,
                env=self.environment,
            )
            if self.mode == "start-error":
                return {"status": 125, "stdout": ""}
            output = self.container_id + "\n"
        elif args[:2] == ["container", "inspect"]:
            code = self.process.poll()
            output = json.dumps(
                [
                    {
                        "Id": self.container_id,
                        "State": {
                            "Running": code is None,
                            "Pid": self.process.pid if code is None else 0,
                            "Status": "running" if code is None else "exited",
                            "ExitCode": code,
                            "OOMKilled": False,
                        },
                    }
                ]
            )
        elif command == "wait":
            output = str(self.process.wait(timeout=15)) + "\n"
        elif command == "logs":
            self.output.seek(0)
            output = self.output.read().decode()
            if self.mode == "lost-report":
                output = ""
            elif self.mode == "wrong-report-daemon":
                events = [json.loads(line) for line in output.splitlines()]
                events[-1]["daemon_id"] = "another-daemon"
                output = "".join(json.dumps(event) + "\n" for event in events)
        elif command == "rm":
            if self.process.poll() is None:
                raise AssertionError("running container must not be removed")
            output = self.container_id + "\n"
        else:
            raise AssertionError("unexpected Docker command: " + repr(args))
        return {"status": 0, "stdout": output}
