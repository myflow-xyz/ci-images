"""Verify a live host maintenance lease before any cleanup mutation."""

import json
import os
import socket
import stat
import struct
import time

from .engine import Failure


class LeaseGuard:
    def __init__(
        self, engine, socket_path, run_id, daemon_id, policy_hash, profile, image_digest
    ):
        self.engine = engine
        self.path = socket_path
        self.expected = {
            "protocol_version": 1,
            "run_id": run_id,
            "daemon_id": daemon_id,
            "policy_hash": policy_hash,
            "profile": profile,
            "image_digest": image_digest,
        }

    def check(self):
        code = 6 if self.engine.mutation_started else 4
        if (
            not isinstance(self.path, str)
            or not self.path.startswith("/")
            or any(
                not isinstance(value, str) or not value
                for key, value in self.expected.items()
                if key != "protocol_version"
            )
        ):
            raise Failure(code, "trusted host lease identity is required")
        deadline = time.monotonic() + min(30, self.engine.remaining())
        while True:
            response = self._query(code)
            if (
                response == {**self.expected, "active": True, "pending": False}
                and type(response.get("protocol_version")) is int
            ):
                return
            if (
                response != {**self.expected, "active": False, "pending": True}
                or time.monotonic() >= deadline
            ):
                raise Failure(
                    code, "host lease is not active for this cleanup process and scope"
                )
            time.sleep(min(0.025, max(0, deadline - time.monotonic())))

    def _query(self, code):
        try:
            metadata = os.lstat(self.path)
            if (
                not stat.S_ISSOCK(metadata.st_mode)
                or metadata.st_uid != 0
                or metadata.st_mode & 0o007
                or not hasattr(socket, "SO_PEERCRED")
            ):
                raise ValueError("a host-owned Linux lease socket is required")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(min(2, self.engine.remaining()))
                client.connect(self.path)
                _, server_uid, _ = struct.unpack(
                    "3i",
                    client.getsockopt(
                        socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
                    ),
                )
                if server_uid != 0:
                    raise ValueError(
                        "lease server is not owned by the host administrator"
                    )
                client.sendall((json.dumps(self.expected) + "\n").encode())
                with client.makefile("rb") as stream:
                    data = stream.readline(4097)
                if len(data) > 4096 or not data.endswith(b"\n"):
                    raise ValueError("lease response limit")
                response = json.loads(data)
                if not isinstance(response, dict):
                    raise TypeError("invalid lease response")
                if (
                    type(response.get("protocol_version")) is not int
                    or type(response.get("active")) is not bool
                    or type(response.get("pending")) is not bool
                ):
                    raise ValueError("invalid lease response flags")
                return response
        except (OSError, ValueError, TypeError) as error:
            raise Failure(
                code,
                "host maintenance lease unavailable or mismatched; keep admission blocked if cleanup started",
            ) from error
