"""Real Docker/BuildKit tests; run only through tests/utils-docker.sh."""

import datetime as dt
import http.server
import json
import os
import pathlib
import signal
import socketserver
import subprocess
import sys
import threading
import time
import unittest
import uuid

sys.path.insert(0, "/workspace/images/utils")
from ci_utils.engine import Engine, UnixConnection

ROOT = pathlib.Path("/run/ci-utils-test")
SOCKET = "unix:///run/ci-utils-test/docker.sock"
IMAGE = os.environ["CI_UTILS_TEST_IMAGE"]
DOCKER = str(pathlib.Path("/opt/ci-tools/bin/docker").resolve())
HOST = [sys.executable, "-B", "/workspace/scripts/ci-docker-maintenance"]
OWNED = "xyz.myflow.ci.ephemeral=true"
PROTECTED = "xyz.myflow.cleanup.protect=true"


def command(args, expected=0, timeout=60):
    result = subprocess.run(
        args, capture_output=True, text=True, timeout=timeout, check=False
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


class DockerE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        info = json.loads(docker("info", "--format", "{{json .}}"))
        if (
            info["ID"] == os.environ["CI_UTILS_OUTER_DAEMON"]
            or "ci-utils-test=" + os.environ["CI_UTILS_TEST_FIXTURE"]
            not in info["Labels"]
            or info["DockerRootDir"] != "/var/lib/docker"
        ):
            raise AssertionError(
                "cleanup requires the fresh, explicitly identified disposable daemon"
            )
        cls.daemon = info["ID"]
        cls.containerd_store = any(
            row == ["driver-type", "io.containerd.snapshotter.v1"]
            for row in info["DriverStatus"]
        )
        print(
            json.dumps(
                {
                    "fixture_engine": info["ServerVersion"],
                    "architecture": info["Architecture"],
                    "storage_driver": info["Driver"],
                }
            )
        )

    def setUp(self):
        self.root = ROOT / uuid.uuid4().hex
        self.root.mkdir(mode=0o755)
        self.policy = {
            "schema_version": 1,
            "endpoint": SOCKET,
            "expected_daemon_id": self.daemon,
            "container_min_age": "1s",
            "network_min_age": "1s",
            "dangling_image_min_age": "1s",
            "tagged_image_min_age": "1s",
            "tagged_image_trigger": "scheduled",
            "cache": {"mode": "off"},
            "protected": {"image_ids": [IMAGE]},
            "pressure": {"reserve_bytes": 1},
        }
        self.settings = {
            "schema_version": 1,
            "policy_path": str(self.root / "policy.json"),
            "image": IMAGE,
            "gate_directory": str(self.root / "gate"),
            "job_gid": 0,
            "participants": ["fixture"],
            "admission_evidence": "disposable-daemon full lifecycle test only",
            "docker_cli": DOCKER,
            "storage": {
                "docker": "/var/lib/docker",
                "containerd": "/var/lib/docker/containerd/daemon",
                "other": [],
            },
        }
        self.save()
        self.host("init")

    def save(self):
        for name, value in (("policy", self.policy), ("host", self.settings)):
            (self.root / f"{name}.json").write_text(json.dumps(value))

    def host_args(self, *args):
        return [*HOST, "--config", str(self.root / "host.json"), *args]

    def host(self, *args, expected=0):
        return [
            json.loads(line)
            for line in command(
                self.host_args(*args), expected=expected, timeout=90
            ).splitlines()
        ]

    def create(self, *args):
        return docker("create", "--pull=never", "--network=none", *args, IMAGE, "true")

    def exists(self, kind, identifier):
        result = subprocess.run(
            [DOCKER, "--host", SOCKET, kind, "inspect", identifier],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0

    def test_hardened_check_and_denied_socket(self):
        events = self.host("check")
        self.assertTrue(events[-1]["completion_known"])
        docker(
            "run",
            "--rm",
            "--pull=never",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user=1001:2001",
            "--tmpfs",
            "/var/tmp",
            "--mount",
            f"type=bind,src={SOCKET[7:]},dst={SOCKET[7:]},readonly",
            "--mount",
            f"type=bind,src={self.root}/policy.json,dst=/etc/ci-utils/cleanup.json,readonly",
            IMAGE,
            "ci-docker-cleanup",
            "check",
            expected=3,
        )
        self.policy["expected_daemon_id"] = "wrong-daemon"
        self.save()
        self.host("check", expected=3)

    def test_owned_objects_protections_volumes_and_repeat(self):
        volume = docker("volume", "create", "retained-" + self.root.name)
        owned = self.create(
            "--label",
            OWNED,
            "--mount",
            f"type=volume,src={volume},dst=/data",
            "--volume",
            "/anonymous",
        )
        anonymous = next(
            m["Name"]
            for m in json.loads(docker("container", "inspect", owned))[0]["Mounts"]
            if m["Destination"] == "/anonymous"
        )
        for name in (volume, anonymous):
            docker(
                "run",
                "--rm",
                "--pull=never",
                "--network=none",
                "--user=0",
                "--mount",
                f"type=volume,src={name},dst=/data",
                IMAGE,
                "sh",
                "-c",
                "printf retained > /data/sentinel",
            )
        protected = self.create("--label", OWNED, "--label", PROTECTED)
        unowned = self.create()
        running = docker(
            "run",
            "--detach",
            "--pull=never",
            "--network=none",
            "--label",
            OWNED,
            IMAGE,
            "sleep",
            "300",
        )
        unused = docker(
            "network", "create", "--label", OWNED, "unused-" + self.root.name
        )
        reserved = docker(
            "network", "create", "--label", OWNED, "reserved-" + self.root.name
        )
        reservation = docker(
            "create", "--pull=never", "--network", reserved, IMAGE, "true"
        )
        time.sleep(2)
        plan = self.host("plan")
        docker("pause", running)
        self.assertTrue(
            any(e.get("id") == owned and e.get("outcome") == "candidate" for e in plan)
        )
        self.assertTrue(self.exists("container", owned))
        applied = self.host("apply")
        removed = {e["id"] for e in applied if e["event"] == "removed"}
        self.assertTrue({owned, unused} <= removed)
        self.assertFalse(self.exists("container", owned))
        self.assertFalse(self.exists("network", unused))
        for identifier in (protected, unowned, running, reservation):
            self.assertTrue(self.exists("container", identifier))
        self.assertTrue(self.exists("network", reserved))
        self.assertTrue(self.exists("volume", volume))
        for name in (volume, anonymous):
            self.assertEqual(
                docker(
                    "run",
                    "--rm",
                    "--pull=never",
                    "--network=none",
                    "--mount",
                    f"type=volume,src={name},dst=/data,readonly",
                    IMAGE,
                    "cat",
                    "/data/sentinel",
                ),
                "retained",
            )
        docker("unpause", running)
        again = self.host("apply")
        self.assertFalse(any(e["event"] == "removed" for e in again))
        docker("stop", "--time", "1", running)

    def build(self, tag):
        context = self.root / tag
        context.mkdir(exist_ok=True)
        (context / "Dockerfile").write_text("FROM scratch\nCOPY payload /payload\n")
        (context / "payload").write_bytes(os.urandom(1024 * 1024))
        reference = "ci-utils-test/" + self.root.name + ":" + tag
        docker(
            "buildx",
            "build",
            "--builder",
            "default",
            "--network=none",
            "--load",
            "--tag",
            reference,
            str(context),
        )
        return reference, docker("image", "inspect", reference, "--format", "{{.Id}}")

    def test_weekly_scoped_images_and_protected_alias(self):
        reference, eligible = self.build("eligible")
        keep_ref, keep = self.build("keep")
        alias = "ci-utils-test/rollback:" + self.root.name
        docker("tag", keep_ref, alias)
        time.sleep(2)
        self.host("apply", "--profile", "weekly")
        self.assertTrue(
            self.exists("image", eligible), "empty image scope deleted an image"
        )
        reservation = docker(
            "create", "--pull=never", "--network=none", reference, "/payload"
        )
        docker("rm", reservation)
        self.policy["image_scope"] = {"ids": [eligible, keep]}
        self.policy["protected"]["image_references"] = [alias]
        self.save()
        self.host("apply", "--profile", "daily")
        self.assertTrue(self.exists("image", reference))
        self.host("apply", "--profile", "weekly")
        self.assertFalse(self.exists("image", eligible))
        self.assertTrue(self.exists("image", keep))
        self.assertTrue(self.exists("image", IMAGE))

    def test_dangling_images_preserve_existing_container_references(self):
        if self.containerd_store:
            self.skipTest(
                "Docker's containerd store drops the old image metadata during tag replacement; the dangling-image fixture is qualified on classic overlay2"
            )
        reference, used = self.build("dangling-used")
        reservation = docker(
            "create", "--pull=never", "--network=none", reference, "/payload"
        )
        self.build("dangling-used")
        _, unused = self.build("dangling-unused")
        self.build("dangling-unused")
        self.assertTrue(
            self.exists("image", used),
            f"retagging lost the fixture image before cleanup; container Image={docker('inspect', reservation, '--format', '{{.Image}}')}; original={used}",
        )
        self.assertTrue(
            self.exists("image", unused),
            "fixture has no unused dangling image before cleanup",
        )
        self.policy["image_scope"] = {"ids": [used, unused]}
        self.save()
        time.sleep(2)
        self.host("apply")
        self.assertTrue(self.exists("image", used))
        self.assertFalse(self.exists("image", unused))
        docker("rm", reservation)
        self.host("apply")
        self.assertFalse(self.exists("image", used))

    def test_cache_modes_age_then_budget_on_default_builder(self):
        reference, _ = self.build("cache")
        docker("image", "rm", reference)
        for mode in ("native", "off"):
            self.policy["cache"] = {"mode": mode}
            self.save()
            events = self.host("apply")
            self.assertFalse(any(e["event"] == "cache_stage" for e in events))
        self.policy["cache"] = {
            "mode": "scheduled",
            "max_unused_age": "1s",
            "max_used_space": "1b",
        }
        self.save()
        time.sleep(2)
        events = self.host("apply")
        stages = [e["stage"] for e in events if e["event"] == "cache_stage"]
        self.assertEqual(stages[0], "age")
        self.assertTrue(
            any(
                e["event"] == "cache_budget" and isinstance(e["remaining_bytes"], int)
                for e in events
            )
        )
        backend = next(e for e in events if e["event"] == "cache")
        self.assertEqual((backend["builder"], backend["driver"]), ("default", "docker"))

    def test_cache_budget_reclaims_recent_records_without_an_age_match(self):
        reference, _ = self.build("recent")
        docker("image", "rm", reference)
        before = Engine(SOCKET).get("/system/df?type=build-cache")["BuildCache"]
        self.assertGreater(sum(record["Size"] for record in before), 1024 * 1024)
        self.policy["cache"] = {
            "mode": "scheduled",
            "max_unused_age": "1h",
            "max_used_space": "1b",
        }
        self.save()
        events = self.host("apply")
        age = next(e for e in events if e["event"] == "cache_stage")
        self.assertEqual(age["submitted_candidates"], 0)
        after = Engine(SOCKET).get("/system/df?type=build-cache")["BuildCache"]
        self.assertLess(
            sum(record["Size"] for record in after),
            sum(record["Size"] for record in before),
        )
        self.assertTrue(
            next(e for e in events if e["event"] == "cache_budget")[
                "budget_may_remove_recent_records"
            ]
        )

    def start_job(self, code, *args):
        return subprocess.Popen(
            self.host_args(
                "job",
                "--participant",
                "fixture",
                "--wait",
                "1s",
                "--timeout",
                "30s",
                "--",
                sys.executable,
                "-B",
                "-c",
                code,
                *args,
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def finish(self, process, expected=0):
        stdout, stderr = process.communicate(timeout=45)
        self.assertEqual(process.returncode, expected, stdout + stderr)
        return [json.loads(line) for line in stdout.splitlines()]

    def test_compose_jobs_drain_before_maintenance_and_isolate_projects(self):
        compose = self.root / "compose.json"
        external = docker("volume", "create", "external-" + self.root.name)
        compose.write_text(
            json.dumps(
                {
                    "services": {
                        "worker": {
                            "image": IMAGE,
                            "command": ["sleep", "300"],
                            "stop_grace_period": "1s",
                            "volumes": ["data:/data", "external:/external"],
                        }
                    },
                    "volumes": {
                        "data": {},
                        "external": {"external": True, "name": external},
                    },
                }
            )
        )
        code = """
import json, os, pathlib, subprocess, sys, time
root, compose, marker = map(pathlib.Path, sys.argv[1:])
project = 'ci-' + os.environ['CI_DOCKER_JOB_ID']
command = ['docker', '--host', os.environ['CI_DOCKER_ENDPOINT'], 'compose', '-p', project, '-f', str(compose)]
subprocess.run([*command, 'up', '-d', '--pull', 'never'], check=True, stdout=sys.stderr)
marker.write_text(project)
while not (root / (marker.name + '-release')).exists(): time.sleep(.05)
subprocess.run([*command, 'down', '--volumes'], check=True, stdout=sys.stderr)
subprocess.run([sys.executable, '-B', '/workspace/scripts/ci-docker-maintenance', 'job-complete'], check=True)
"""
        markers = [self.root / str(i) for i in range(2)]
        jobs = [
            self.start_job(code, str(self.root), str(compose), str(marker))
            for marker in markers
        ]
        maintenance = None
        try:
            wait_for(lambda: all(marker.exists() for marker in markers))
            self.assertNotEqual(markers[0].read_text(), markers[1].read_text())
            maintenance = subprocess.Popen(
                self.host_args("apply", "--wait", "20s"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            wait_for(lambda: (self.root / "gate/maintenance.json").exists())
            refused = self.start_job("raise SystemExit('must not start')")
            self.finish(refused, 4)
            (self.root / "0-release").touch()
            self.finish(jobs[0])
            project = markers[1].read_text()
            self.assertTrue(
                docker(
                    "ps",
                    "--filter",
                    "label=com.docker.compose.project=" + project,
                    "--quiet",
                )
            )
            self.assertIsNone(maintenance.poll())
            (self.root / "1-release").touch()
            self.finish(jobs[1])
            self.finish(maintenance)
            self.assertTrue(self.exists("volume", external))
        finally:
            for marker in markers:
                (self.root / (marker.name + "-release")).touch()
            for process in [*jobs, maintenance]:
                if process is not None:
                    if process.poll() is None:
                        process.terminate()
                    process.communicate(timeout=10)

    def test_crashed_job_requires_explicit_reconciliation(self):
        marker = self.root / "child"
        code = """
import os, pathlib, signal, subprocess, sys
subprocess.run(['docker', '--host', os.environ['CI_DOCKER_ENDPOINT'], 'info'], check=True, stdout=subprocess.DEVNULL)
pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))
os.kill(os.getppid(), signal.SIGKILL)
"""
        crashed = self.start_job(code, str(marker))
        self.finish(crashed, -signal.SIGKILL)
        wait_for(lambda: not pathlib.Path("/proc/" + marker.read_text()).exists())
        self.finish(self.start_job("raise SystemExit('must not start')"), 4)
        self.host("apply", "--wait", "1s", expected=4)
        records = list((self.root / "gate/jobs").glob("*.json"))
        self.assertEqual(len(records), 1)
        identifier = json.loads(records[0].read_text())["id"]
        evidence = self.root / "reconcile.json"
        evidence.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "record_id": identifier,
                    "daemon_id": self.daemon,
                    "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "observer": "isolated-test-controller",
                    "evidence": "Read-only Docker info completed; child exited; no other fixture participant or daemon operation remains active.",
                    "participants_drained": True,
                    "daemon_operations_complete": True,
                }
            )
        )
        self.host("reconcile", "--record-id", identifier, "--evidence", str(evidence))
        self.host("apply")
        self.assertEqual(list((self.root / "gate/jobs").glob("*.json")), [])

    def test_capacity_refusal_precedes_job_start(self):
        self.policy["pressure"]["reserve_bytes"] = 2**63 - 1
        self.save()
        marker = self.root / "must-not-start"
        process = self.start_job(
            "import pathlib,sys; pathlib.Path(sys.argv[1]).touch()", str(marker)
        )
        self.finish(process, 4)
        self.assertFalse(marker.exists())
        self.assertEqual(list((self.root / "gate/jobs").glob("*.json")), [])

    def test_interrupted_deletion_stops_later_mutations(self):
        for fault in ("crash", "cancel", "timeout", "disconnect"):
            with self.subTest(fault=fault):
                self.interrupt_deletion(fault)

    def interrupt_deletion(self, fault):
        self.policy["protected"]["container_ids"] = [
            c["Id"] for c in Engine(SOCKET).get("/containers/json?all=true")
        ]
        candidates = {self.create("--label", OWNED) for _ in range(3)}
        time.sleep(2)
        with DelayedDeleteProxy(self.root / f"{fault}.sock", candidates) as proxy:
            self.policy["endpoint"] = "unix://" + str(proxy.path)
            self.policy["timeouts"] = {"operation": "2s", "run": "30s"}
            self.save()
            wrapper = subprocess.Popen(
                self.host_args("apply"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                self.assertTrue(
                    proxy.deleted.wait(15), "no real deletion reached the daemon"
                )
                if fault == "crash":
                    wrapper.kill()
                elif fault == "cancel":
                    wrapper.terminate()
                elif fault == "disconnect":
                    proxy.disconnect = True
                    proxy.release.set()
                self.finish(wrapper, -signal.SIGKILL if fault == "crash" else 6)
            finally:
                proxy.release.set()
                if wrapper.poll() is None:
                    wrapper.terminate()
                    wrapper.communicate(timeout=10)
            self.assertTrue(
                proxy.replied.wait(5), "proxy deletion handler remains active"
            )
            record = json.loads((self.root / "gate/maintenance.json").read_text())
            child = record["container_id"]
            wait_for(
                lambda: (
                    docker("inspect", child, "--format", "{{.State.Running}}")
                    == "false"
                )
            )
            self.assertEqual(
                docker("inspect", child, "--format", "{{.State.ExitCode}}"), "6"
            )
            self.assertEqual(len(proxy.mutations), 1)
            self.assertEqual(sum(self.exists("container", c) for c in candidates), 2)
            self.host("apply", "--wait", "1s", expected=4)
            self.finish(self.start_job("raise SystemExit('must not start')"), 4)
            evidence = self.root / "recovery.json"
            evidence.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "record_id": record["id"],
                        "daemon_id": self.daemon,
                        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                        "observer": "isolated-test-controller",
                        "evidence": "Proxy received the daemon deletion result; maintenance process exited 6 with PID 0; exactly one deletion completed and no daemon requests remain in flight.",
                        "participants_drained": True,
                        "daemon_operations_complete": True,
                    }
                )
            )
            self.host(
                "reconcile", "--record-id", record["id"], "--evidence", str(evidence)
            )
            self.host("apply")
            self.assertFalse(any(self.exists("container", c) for c in candidates))


if __name__ == "__main__":
    unittest.main(verbosity=2)
