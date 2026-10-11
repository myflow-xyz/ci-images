#!/usr/bin/env python3
"""Exercise ci-net through disposable containers and the real Docker Engine API."""

import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import unittest
import uuid


def docker(*args, input=None, check=True, timeout=30):
    result = subprocess.run(
        ["docker", *args], input=input, text=True, capture_output=True, timeout=timeout
    )
    if check and result.returncode:
        raise AssertionError(f"docker {args[0]} failed ({result.returncode}): {result.stderr}")
    return result


class EngineConnection(http.client.HTTPConnection):
    def __init__(self, endpoint):
        super().__init__("localhost", timeout=10)
        self.endpoint = endpoint

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.endpoint)


class NetworkE2E(unittest.TestCase):
    @classmethod
    def api(cls, path, expected_status=200):
        connection = EngineConnection(cls.endpoint)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            body = response.read()
            if response.status != expected_status:
                raise AssertionError(f"Engine GET {path}: {response.status}, expected {expected_status}")
            return json.loads(body)
        finally:
            connection.close()

    @classmethod
    def remove(cls, kind, identifier):
        if kind == "containers":
            docker("rm", "--force", identifier)
            cls.api(f"/containers/{identifier}/json", 404)
        else:
            docker("network", "rm", identifier)
            cls.api(f"/networks/{identifier}", 404)

    @classmethod
    def setUpClass(cls):
        endpoint = os.environ.get("DOCKER_HOST")
        if os.environ.get("DOCKER_CONTEXT") or not endpoint:
            endpoint = docker("context", "inspect", "--format", "{{.Endpoints.docker.Host}}").stdout.strip()
        if not endpoint.startswith("unix:///"):
            raise AssertionError("ci-net E2E requires a local Unix Docker endpoint")
        cls.endpoint = endpoint.removeprefix("unix://")
        if cls.api("/info")["OSType"] != "linux":
            raise AssertionError("ci-net E2E requires Linux containers")
        cls.image = os.environ.get("CI_NET_TEST_IMAGE", "ci-net:test")
        prefix = f"ci-net-test-{uuid.uuid4().hex[:12]}"
        cls.network = docker("network", "create", "--internal", prefix).stdout.strip()
        cls.addClassCleanup(cls.remove, "networks", cls.network)
        cls.containers = {}
        for role in ("ordinary", "denied", "left", "right"):
            args = [
                "run", "--detach", "--pull=never", "--name", f"{prefix}-{role}",
                "--network", cls.network, "--read-only", "--cap-drop=ALL",
                "--security-opt=no-new-privileges", "--pids-limit=64",
                "--tmpfs", "/var/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777",
            ]
            if role != "ordinary":
                args += ["--user=0:0"]
            if role in ("left", "right"):
                args += ["--cap-add=NET_ADMIN", "--cap-add=NET_RAW"]
            identifier = docker(*args, cls.image, "sleep", "300").stdout.strip()
            cls.containers[role] = identifier
            cls.addClassCleanup(cls.remove, "containers", identifier)

    def execute(self, role, script, **kwargs):
        return docker("exec", "--interactive", self.containers[role], "bash", "-eu", input=script, **kwargs)

    def test_engine_api_isolation_and_capabilities(self):
        network = self.api(f"/networks/{self.network}")
        self.assertTrue(network["Internal"])
        self.assertEqual(set(network["Containers"]), set(self.containers.values()))
        namespaces = set()
        sandboxes = set()
        for role, identifier in self.containers.items():
            with self.subTest(role=role):
                info = self.api(f"/containers/{identifier}/json")
                host = info["HostConfig"]
                self.assertFalse(host["Privileged"])
                self.assertTrue(host["ReadonlyRootfs"])
                self.assertEqual(host["NetworkMode"], self.network)
                self.assertEqual(host["CapDrop"], ["ALL"])
                capabilities = {cap.removeprefix("CAP_") for cap in host["CapAdd"] or []}
                self.assertEqual(capabilities, {"NET_ADMIN", "NET_RAW"} if role in ("left", "right") else set())
                self.assertIn("no-new-privileges", host["SecurityOpt"])
                self.assertFalse(host.get("Binds"))
                self.assertFalse(host.get("Devices"))
                self.assertFalse(host.get("PidMode"))
                self.assertTrue(all(mount["Type"] == "tmpfs" for mount in info["Mounts"]))
                sandboxes.add(info["NetworkSettings"]["SandboxID"])
                namespaces.add(self.execute(role, "readlink /proc/self/ns/net").stdout.strip())
                status = self.execute(role, "cat /proc/self/status").stdout
                fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
                expected = (1 << 12) | (1 << 13) if role in ("left", "right") else 0
                self.assertEqual(int(fields["CapEff"], 16), expected)
                self.assertEqual(int(fields["CapBnd"], 16), expected)
                self.assertEqual(int(fields["NoNewPrivs"]), 1)
        self.assertEqual(len(namespaces), len(self.containers))
        self.assertEqual(len(sandboxes), len(self.containers))
        self.assertNotIn("", sandboxes)
        ordinary = self.api(f"/containers/{self.containers['ordinary']}/json")
        image = self.api(f"/images/{ordinary['Image']}/json")
        self.assertEqual(image["Config"]["User"], "ci")
        self.assertEqual(self.execute("ordinary", "id -u").stdout.strip(), "1001")
        description = image["Config"]["Labels"]["org.opencontainers.image.description"]
        for constraint in ("independent network namespace", "--network host", "--privileged", "NET_ADMIN", "nft flush ruleset"):
            self.assertIn(constraint, description)

    def test_missing_net_admin_rejects_mutation(self):
        for role in ("ordinary", "denied"):
            with self.subTest(role=role):
                result = self.execute(role, "ip link add denied0 type dummy", check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Operation not permitted", result.stderr)
                links = json.loads(self.execute(role, "ip -j link show").stdout)
                self.assertNotIn("denied0", [link["ifname"] for link in links])

    def test_owned_rules_cleanup_preserves_unrelated_state(self):
        fixture = Path(__file__).with_name("smoke").joinpath("net-rules.sh").read_text()
        self.execute("left", "nft add table inet sentinel\nnft add chain inet sentinel retained")
        before = self.execute("left", "nft -j list table inet sentinel").stdout
        tables_before = self.execute("left", "nft -j list tables").stdout
        try:
            for fail in (False, True):
                with self.subTest(injected_failure=fail):
                    script = f"export CI_NET_INJECT_FAILURE={int(fail)}\n" + fixture
                    result = self.execute("left", script, check=False)
                    self.assertEqual(result.returncode, 23 if fail else 0, result.stdout + result.stderr)
                    if fail:
                        self.assertIn("injected failure after network setup", result.stderr)
                    self.assertEqual(self.execute("left", "nft -j list table inet sentinel").stdout, before)
                    self.assertEqual(self.execute("left", "nft -j list tables").stdout, tables_before)
                    links = json.loads(self.execute("left", "ip -j link show").stdout)
                    self.assertNotIn("ci_net_dummy", [link["ifname"] for link in links])
                    self.assertEqual(json.loads(self.execute("left", "ip -j route show 198.51.100.0/24").stdout), [])
        finally:
            self.execute("left", "nft delete table inet sentinel")

    def test_wireguard_peer_traffic_and_packet_capture(self):
        public_keys = {}
        addresses = {}
        for role, suffix in (("left", 1), ("right", 2)):
            public_keys[role] = self.execute(role, "umask 077\nwg genkey > /var/tmp/wg.key\nwg pubkey < /var/tmp/wg.key").stdout.strip()
            result = self.execute(role, "ip link add ciwg0 type wireguard", check=False)
            self.assertEqual(result.returncode, 0, "Runner prerequisite: WireGuard kernel support is required. " + result.stderr)
            self.addCleanup(self.execute, role, "ip link delete ciwg0\nrm -f /var/tmp/wg.key /var/tmp/wg.pcap /var/tmp/capture.log")
            self.execute(role, f"ip address add 192.0.2.{suffix}/30 dev ciwg0\nwg set ciwg0 private-key /var/tmp/wg.key listen-port 51820\nip link set ciwg0 up")
            info = self.api(f"/containers/{self.containers[role]}/json")
            addresses[role] = next(iter(info["NetworkSettings"]["Networks"].values()))["IPAddress"]
        for role, peer, suffix in (("left", "right", 2), ("right", "left", 1)):
            self.execute(role, f"wg set ciwg0 peer {public_keys[peer]} endpoint {addresses[peer]}:51820 allowed-ips 192.0.2.{suffix}/32")
        capture = subprocess.Popen(
            ["docker", "exec", self.containers["left"], "tcpdump", "-p", "-Z", "root", "-U", "-ni", "ciwg0", "-c", "2", "-w", "/var/tmp/wg.pcap", "icmp"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + 10
            while True:
                ready = self.execute("left", "test -s /var/tmp/wg.pcap", check=False)
                if ready.returncode == 0:
                    break
                self.assertIsNone(capture.poll(), "tcpdump exited before capture started")
                self.assertLess(time.monotonic(), deadline, "tcpdump did not become ready")
                time.sleep(0.1)
            self.execute("left", "ping -c 2 -W 2 -w 10 192.0.2.2", timeout=15)
            self.execute("right", "ping -c 2 -W 2 -w 10 192.0.2.1", timeout=15)
            _, error = capture.communicate(timeout=15)
            self.assertEqual(capture.returncode, 0, error)
            packets = self.execute("left", "tcpdump -Z root -nn -r /var/tmp/wg.pcap").stdout
            self.assertIn("192.0.2.1 > 192.0.2.2: ICMP echo request", packets)
            self.assertIn("192.0.2.2 > 192.0.2.1: ICMP echo reply", packets)
            for role in ("left", "right"):
                handshake = self.execute(role, "wg show ciwg0 latest-handshakes").stdout.split()
                self.assertEqual(len(handshake), 2)
                self.assertGreater(int(handshake[1]), 0)
                transfer = self.execute(role, "wg show ciwg0 transfer").stdout.split()
                self.assertGreater(int(transfer[1]), 0)
                self.assertGreater(int(transfer[2]), 0)
        finally:
            if capture.poll() is None:
                capture.kill()
                capture.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
