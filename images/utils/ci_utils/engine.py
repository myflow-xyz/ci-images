"""Bounded local Docker Engine API access."""

import http.client
import json
import re
import socket
import threading
import time
import urllib.parse

from .policy import IMAGE_ID, OBJECT_ID, InvalidPolicy, reference_name


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path, timeout):
        super().__init__("localhost", timeout=timeout)
        self.path = path
        self.transport = None

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.transport = self.sock
        self.sock.settimeout(self.timeout)
        try:
            self.sock.connect(self.path)
        except BaseException:
            self.sock.close()
            raise


class Failure(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class APIError(Failure):
    def __init__(self, status):
        super().__init__(5, f"Docker API returned HTTP {status}")
        self.status = status


class Engine:
    def __init__(self, endpoint, operation_timeout=120, run_timeout=900):
        if (
            not isinstance(endpoint, str)
            or not endpoint.startswith("unix:///")
            or endpoint == "unix:///"
            or any(c in endpoint for c in "\x00\n\r?#")
        ):
            raise Failure(2, "an explicit absolute local Unix socket is required")
        self.endpoint = endpoint
        self.socket_path = endpoint[len("unix://") :]
        self.operation_timeout = operation_timeout
        self.deadline = time.monotonic() + run_timeout
        self.api = "/v1.48"
        self.mutation_started = False
        self.verified = False
        self.version = None

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise Failure(
                6,
                "run deadline exceeded; reconcile completion before reopening admission",
            )
        return min(remaining, self.operation_timeout)

    def _request(self, method, path):
        connection = UnixConnection(self.socket_path, self.remaining())
        expired = threading.Event()

        def expire():
            expired.set()
            if connection.transport is not None:
                try:
                    connection.transport.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        # A socket inactivity timeout alone permits an indefinitely slow response.
        timer = threading.Timer(connection.timeout, expire)
        timer.daemon = True
        timer.start()
        try:
            connection.request(method, path, headers={"Host": "localhost"})
            response = connection.getresponse()
            # Never print daemon error bodies: they may contain untrusted or secret data.
            if not 200 <= response.status < 300:
                raise APIError(response.status)
            data = response.read(32 * 1024 * 1024 + 1)
            if expired.is_set():
                raise Failure(
                    6 if self.mutation_started else 3,
                    "Docker operation deadline exceeded",
                )
            if len(data) > 32 * 1024 * 1024:
                raise Failure(
                    6 if self.mutation_started else 5,
                    "Docker API response exceeds inventory limit",
                )
            try:
                return json.loads(data) if data else None
            except (ValueError, UnicodeError) as error:
                raise Failure(
                    6 if self.mutation_started else 5,
                    "Docker API returned malformed JSON",
                ) from error
        except (OSError, http.client.HTTPException) as error:
            code = 6 if self.mutation_started else 3
            raise Failure(
                code,
                "Docker connection failed or timed out; verify socket access and daemon state",
            ) from error
        finally:
            timer.cancel()
            timer.join()
            connection.close()

    def preflight(self, expected=None):
        self.version = self._request("GET", "/version")
        if not isinstance(self.version, dict):
            raise Failure(2, "invalid Docker version response")

        def api_number(key):
            value = self.version.get(key)
            if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+", value):
                raise Failure(2, "unrecognized Docker API version")
            return tuple(int(x) for x in value.split("."))

        if api_number("ApiVersion") < (1, 48) or api_number("MinAPIVersion") > (1, 48):
            raise Failure(2, "Docker API 1.48 is required by this release")
        version = self.version.get("Version", "")
        if not isinstance(version, str) or version.split(".")[0] not in ("28", "29"):
            raise Failure(2, "this release targets Linux Docker Engine 28.x and 29.x")
        info = self.get("/info")
        if (
            not isinstance(info, dict)
            or not isinstance(info.get("ID"), str)
            or not re.fullmatch(r"[\w:.-]{1,256}", info["ID"], flags=re.ASCII)
        ):
            raise Failure(3, "cannot establish daemon identity")
        if expected is not None and info["ID"] != expected:
            raise Failure(3, "selected Docker daemon identity does not match policy")
        if info.get("OSType") != "linux":
            raise Failure(2, "this release requires a Linux Docker daemon")
        security = info.get("SecurityOptions")
        if not isinstance(security, list) or any(
            not isinstance(option, str) for option in security
        ):
            raise Failure(2, "cannot establish Docker security mode")
        if any("rootless" in option or "userns" in option for option in security):
            raise Failure(
                2, "rootless and user-namespace deployments need separate qualification"
            )
        self.verified = True
        return info

    def get(self, path):
        return self._request("GET", self.api + path)

    def inspect(self, kind, identifier):
        if kind not in ("containers", "networks", "images"):
            raise Failure(2, "unsupported resource class")
        suffix = "" if kind == "networks" else "/json"
        return self.get(f"/{kind}/{urllib.parse.quote(identifier, safe='')}{suffix}")

    def remove(self, kind, identifier, guard):
        if kind not in ("containers", "networks", "images"):
            raise Failure(2, "host cleanup does not support that resource class")
        if not isinstance(identifier, str):
            raise Failure(2, "invalid deletion identity")
        if kind != "images" and not OBJECT_ID.fullmatch(identifier):
            raise Failure(2, "container/network deletion requires a full ID")
        if kind == "images" and not IMAGE_ID.fullmatch(identifier):
            try:
                reference_name(identifier)
            except InvalidPolicy as error:
                raise Failure(2, "invalid image deletion reference") from error
        if not self.verified:
            raise Failure(3, "daemon preflight is required before cleanup")
        guard()
        self.remaining()
        query = {
            "containers": "?force=false&v=false",
            "images": "?force=false&noprune=true",
            "networks": "",
        }[kind]
        self.mutation_started = True
        return self._request(
            "DELETE",
            f"{self.api}/{kind}/{urllib.parse.quote(identifier, safe='')}{query}",
        )
