"""Qualify installed commands on the empty, network-isolated nested Engine."""

import datetime as dt
import io
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import tarfile
import tempfile
import time
import unittest

from docker_fixture import (
    DOCKER,
    OWNED,
    ROOT,
    SOCKET,
    DelayedDeleteProxy,
    command,
    docker,
    wait_for,
)
from ci_utils.engine import Engine
from release_http_fixture import REPO, VERSION, ReleaseServer


def events(args, **kwargs):
    return [json.loads(line) for line in command(args, **kwargs).splitlines()]


def readme_quickstart():
    readme = Path("/workspace/README.md").read_text()
    section = readme.split("## Upgrade runner images\n", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"```bash\n(.*?)\n```", section, re.DOTALL)


def seed(tag):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as tar:
        tar.addfile(tarfile.TarInfo(tag.rpartition(":")[2]))
    subprocess.run(
        [DOCKER, "--host", SOCKET, "import", "-", tag],
        input=data.getvalue(),
        check=True,
        stdout=subprocess.DEVNULL,
        timeout=30,
    )


class NativeDocker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Engine(SOCKET, run_timeout=300)
        info = cls.engine.preflight()
        assert info["ID"] != os.environ["CI_UTILS_OUTER_DAEMON"]
        assert "ci-utils-test=" + os.environ["CI_UTILS_TEST_FIXTURE"] in info["Labels"]
        assert not cls.engine.get("/images/json?all=true"), (
            "native suite requires an empty test daemon"
        )
        cls.daemon = info["ID"]

    @classmethod
    def tearDownClass(cls):
        assert not docker("image", "ls", "--quiet", "ghcr.io/myflow-xyz/ci-utils")
        assert not docker("ps", "-aq", "--filter", "label=xyz.myflow.cleanup.run")

    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.config = self.root / "cleanup.json"
        self.policy = dict(
            schema_version=1,
            endpoint=SOCKET,
            expected_daemon_id=self.daemon,
            container_min_age="1s",
            cache={"mode": "off"},
            pressure={"reserve_bytes": 1},
        )
        self.save()
        self.gate = self.root / "gate"
        host = self.root / "host.json"
        host.write_text(
            json.dumps(
                dict(
                    schema_version=1,
                    policy_path=str(self.config),
                    gate_directory=str(self.gate),
                    job_gid=0,
                    participants=["runner"],
                    admission_evidence="isolated job lifecycle",
                    docker_cli=DOCKER,
                    storage=dict(
                        docker="/var/lib/docker",
                        containerd="/var/lib/docker/containerd/daemon",
                        other=[],
                    ),
                )
            )
        )
        self.host = ["ci-docker-maintenance", "--config", str(host)]
        events([*self.host, "init"])

    def save(self):
        self.config.write_text(json.dumps(self.policy))

    def test_operator_bootstrap_downloads_the_pinned_release(self):
        guide = Path("/workspace/scripts/docs/ci-utils/install.md").read_text()
        example = guide.split("```bash\n", 1)[1].split("\n```", 1)[0]
        readme_install, _ = readme_quickstart()
        version = json.loads(command(["ci-docker-cleanup", "version"]))["version"]
        with ReleaseServer(version):
            for bootstrap in (readme_install, example):
                output = command(
                    ["bash", "-ec", bootstrap.replace("v=0.0.31;", f"v={version};")],
                    env={**os.environ, "CURL_CA_BUNDLE": "/fixture-tls/ca.crt"},
                )
                self.assertIn(f"Installed ci-utils {version}", output)
        self.assertEqual(
            json.loads(command(["ci-docker-cleanup", "version"]))["version"], version
        )

    def test_refresh_and_digest_mismatch(self):
        old = REPO + ":0.0.1"
        seed(old)
        _, refresh = readme_quickstart()
        args = [*shlex.split(refresh), "--config", str(self.config)]
        arch = self.engine.version["Arch"]
        other = "arm64" if arch == "amd64" else "amd64"
        with ReleaseServer() as registry:
            result = events(
                args, env={**os.environ, "DOCKER_DEFAULT_PLATFORM": f"linux/{other}"}
            )
            pulled = next(e for e in result if e["event"] == "pulled")
            self.assertEqual(
                (pulled["id"], pulled["digest"]), (f"{REPO}:{VERSION}", registry.digest)
            )
            for tag in ("latest", VERSION):
                image = self.engine.inspect("images", f"{REPO}:{tag}")
                self.assertEqual(
                    (image["Os"], image["Architecture"], image["Id"]),
                    ("linux", arch, pulled["image_id"]),
                )
            registry.mismatch()
            result = events([*args, "--prune-old-versions"], expected=5)
            self.assertIn(
                "does not match",
                next(e["message"] for e in result if e["event"] == "error"),
            )
            self.assertIn(old, self.engine.inspect("images", old)["RepoTags"])

    def test_retirement_protects_aliases_and_container_images(self):
        repo = "ghcr.io/myflow-xyz/ci-vite:"
        eligible, protected, in_use = (repo + v for v in ("1.0.1", "1.0.2", "1.0.3"))
        for tag in (eligible, protected, in_use):
            seed(tag)
        docker("tag", protected, "fixture:rollback")
        docker("create", "--pull=never", in_use, "/fixture")
        self.policy["protected"] = {"image_references": ["fixture:rollback"]}
        self.save()
        selection = ["--versions", "1.0.1,1.0.2,1.0.3"]
        direct = ["ci-remove-images", "--config", str(self.config), *selection]
        self.assertEqual(
            [e["id"] for e in events(direct) if e["event"] == "would-remove"],
            [eligible],
        )
        events([*direct, "--apply"], expected=4)
        events([*direct, "--expected-daemon-id", "another-daemon"], expected=3)
        self.assertIn(eligible, self.engine.inspect("images", eligible)["RepoTags"])
        result = events([*self.host, "remove-images", *selection, "--apply"])
        self.assertEqual(
            [e["id"] for e in result if e["event"] == "removed"], [eligible]
        )
        self.assertEqual(docker("image", "ls", "--quiet", eligible), "")
        for tag in (protected, in_use):
            self.assertIn(tag, self.engine.inspect("images", tag)["RepoTags"])

    def test_probe_and_private_resolution(self):
        probe = "/usr/local/libexec/ci-utils/current/lib/ci-buildkit-probe"
        proof = json.loads(
            command([probe, "--host", SOCKET, "--expected-daemon-id", self.daemon])
        )
        self.assertEqual((proof["daemon_id"], proof["driver"]), (self.daemon, "docker"))
        self.assertTrue(proof["worker_id"])
        command(
            [probe, "--host", SOCKET, "--expected-daemon-id", "another-daemon"],
            expected=2,
        )
        self.policy["cache"] = {"mode": "native"}
        self.save()
        decoy = self.root / "ci-buildkit-probe"
        decoy.write_text("#!/bin/sh\nexit 77\n")
        decoy.chmod(0o755)
        result = events(
            ["ci-docker-cleanup", "check", "--config", str(self.config)],
            env={**os.environ, "PATH": f"{self.root}:{os.environ['PATH']}"},
        )
        self.assertTrue(any(e.get("worker_id") == proof["worker_id"] for e in result))

    def test_cleanup_waits_for_participating_job(self):
        tag = "fixture:job"
        seed(tag)
        victim = docker("create", "--label", OWNED, tag, "/fixture")
        time.sleep(1.1)
        plan = events([*self.host, "plan"])
        self.assertTrue(
            any(e.get("id") == victim and e.get("outcome") == "candidate" for e in plan)
        )
        job = [
            *self.host,
            "job",
            "--participant",
            "runner",
            "--",
            "bash",
            "-ec",
            'touch "$1/admitted"; while [[ ! -e $1/finish ]]; do sleep 0.1; done; '
            "/usr/local/libexec/ci-utils/ci-docker-maintenance job-complete",
            "bash",
            str(self.root),
        ]
        with subprocess.Popen(job, stdout=subprocess.PIPE) as worker:
            try:
                wait_for((self.root / "admitted").exists)
                with subprocess.Popen(
                    [*self.host, "apply"], stdout=subprocess.PIPE
                ) as apply:
                    try:
                        wait_for((self.gate / "maintenance.json").exists)
                        self.assertEqual(
                            self.engine.inspect("containers", victim)["Id"], victim
                        )
                    finally:
                        (self.root / "finish").touch()
                    output, _ = apply.communicate(timeout=30)
                    self.assertEqual(apply.returncode, 0, output)
            finally:
                (self.root / "finish").touch()
            output, _ = worker.communicate(timeout=10)
            self.assertEqual(worker.returncode, 0, output)
        self.assertNotIn(
            victim, {c["Id"] for c in self.engine.get("/containers/json?all=true")}
        )
        self.assertIsNone(events([*self.host, "status"])[0]["maintenance"])

    def test_lost_engine_reply_blocks_admission_until_reconciled(self):
        tag = "fixture:interruption"
        seed(tag)
        victims = {
            docker("create", "--label", OWNED, tag, "/fixture") for _ in range(2)
        }
        time.sleep(1.1)
        with DelayedDeleteProxy(self.root / "delay.sock", victims) as proxy:
            self.policy["endpoint"] = "unix://" + str(proxy.path)
            self.save()
            with subprocess.Popen(
                [*self.host, "apply"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
            ) as apply:
                try:
                    self.assertTrue(
                        proxy.deleted.wait(10), "no Engine DELETE reached the daemon"
                    )
                    record = json.loads((self.gate / "maintenance.json").read_text())
                    scope = dict(
                        protocol_version=2,
                        operation="apply",
                        run_id=record["id"],
                        daemon_id=self.daemon,
                        policy_hash=record["policy_hash"],
                        profile=record["profile"],
                        archive_digest=record["archive_digest"],
                    )
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                        client.settimeout(2)
                        client.connect(str(self.gate / "lease.sock"))
                        client.sendall((json.dumps(scope) + "\n").encode())
                        with client.makefile("rb") as stream:
                            reply = json.loads(stream.readline(4096))
                    self.assertEqual(reply, dict(**scope, active=False, pending=False))
                    # Exact scope and release, but another process cannot use the live lease.
                    events(
                        [
                            "ci-docker-cleanup",
                            "apply",
                            "--run-id",
                            record["id"],
                            "--config",
                            str(self.config),
                            "--lease-socket",
                            str(self.gate / "lease.sock"),
                        ],
                        expected=4,
                    )
                    apply.kill()
                finally:
                    proxy.release.set()
                apply.communicate(timeout=15)
            self.assertTrue(proxy.replied.wait(5))
            self.assertEqual(len(proxy.mutations), 1)
            self.assertEqual(
                len(
                    victims
                    & {c["Id"] for c in self.engine.get("/containers/json?all=true")}
                ),
                1,
            )
            events([*self.host, "apply", "--wait", "1s"], expected=4)
            events(
                [
                    *self.host,
                    "job",
                    "--participant",
                    "runner",
                    "--wait",
                    "1s",
                    "--",
                    "false",
                ],
                expected=4,
            )
            evidence = self.root / "evidence.json"
            evidence.write_text(
                json.dumps(
                    dict(
                        schema_version=1,
                        record_id=record["id"],
                        daemon_id=self.daemon,
                        observed_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                        observer="fixture",
                        evidence="the worker exited and the Engine completed exactly one DELETE",
                        participants_drained=True,
                        daemon_operations_complete=True,
                    )
                )
            )
            events(
                [
                    *self.host,
                    "reconcile",
                    "--record-id",
                    record["id"],
                    "--evidence",
                    str(evidence),
                ]
            )
            self.assertIsNone(events([*self.host, "status"])[0]["maintenance"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
