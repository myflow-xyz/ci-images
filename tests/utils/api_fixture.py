"""Disposable Unix HTTP fixture; never connects to a Docker daemon."""

import http.server
import json
import pathlib
import socketserver
import tempfile
import threading
import time


class UnixHTTP(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


class APIFixture:
    def __init__(self, routes):
        self.routes = routes
        self.requests = []
        self.root = tempfile.TemporaryDirectory(prefix="ci-utils-api-", dir="/tmp")
        self.path = pathlib.Path(self.root.name) / "docker.sock"
        fixture = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.respond("GET")

            def do_DELETE(self):
                self.respond("DELETE")

            def respond(self, method):
                fixture.requests.append((method, self.path))
                response = fixture.routes.get((method, self.path), (404, {}))
                if callable(response):
                    response = response()
                status, payload, *delays = response
                data = (
                    payload
                    if isinstance(payload, bytes)
                    else json.dumps(payload).encode()
                )
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    if delays:
                        for byte in data:
                            time.sleep(delays[0])
                            self.wfile.write(bytes([byte]))
                            self.wfile.flush()
                    else:
                        self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass

        self.server = UnixHTTP(str(self.path), Handler)
        self.thread = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True
        )

    @property
    def endpoint(self):
        return "unix://" + str(self.path)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.root.cleanup()


def daemon_routes():
    return {
        ("GET", "/version"): (
            200,
            {"Version": "29.4.0", "ApiVersion": "1.54", "MinAPIVersion": "1.44"},
        ),
        ("GET", "/v1.48/info"): (
            200,
            {"ID": "fixture-daemon", "OSType": "linux", "SecurityOptions": []},
        ),
    }
