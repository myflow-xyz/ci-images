"""Exercise the qualification CLI through a disposable Docker API endpoint."""

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/utils"))
from api_fixture import APIFixture

REPOSITORY = "ghcr.io/myflow-xyz/ci-utils"
INDEX = "sha256:" + "1" * 64
CHILD = "sha256:" + "2" * 64
IMAGE_REVISION = "3" * 40
CLI = ROOT / ".github/scripts/resolve-utils-image.py"
OCI_INDEX = "application/vnd.oci.image.index.v1+json"
OCI_IMAGE = "application/vnd.oci.image.manifest.v1+json"
DOCKER_INDEX = "application/vnd.docker.distribution.manifest.list.v2+json"
DOCKER_IMAGE = "application/vnd.docker.distribution.manifest.v2+json"

FAKE_DOCKER = r"""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['QUALIFY_DOCKER_LOG'], 'a') as log:
    log.write(json.dumps(args) + '\n')
assert args[:2] == ['--host', os.environ['DOCKER_HOST']], args
assert not os.environ.get('DOCKER_CONTEXT')
args = args[2:]
state = json.loads(Path(os.environ['QUALIFY_DOCKER_STATE']).read_text())
if args[0] == 'version':
    print(json.dumps(state['server']))
elif args[:2] == ['manifest', 'inspect']:
    assert args[-1] == state['reference'], args
    print(json.dumps(state['index']))
elif args[0] == 'pull':
    assert args[-1] == state['reference'], args
    if state.get('pull_error'):
        print('fixture-secret must not be logged', file=sys.stderr)
        sys.exit(1)
    print('Pulled fixture')
elif args[:2] == ['image', 'inspect']:
    assert args[-1] == state['reference'], args
    print(json.dumps([state['image']]))
else:
    raise AssertionError('unexpected Docker command: ' + repr(args))
"""


def distribution_path(reference, version="1.48"):
    return (
        f"/v{version}/distribution/" + urllib.parse.quote(reference, safe="") + "/json"
    )


class ImageSelection(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="utils-selection-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        binary = self.directory / "docker"
        binary.write_text(FAKE_DOCKER)
        binary.chmod(0o755)
        self.log = self.directory / "docker.jsonl"
        self.state_file = self.directory / "state.json"
        self.output = self.directory / "result.json"
        self.environment_file = self.directory / "github-env"
        self.summary = self.directory / "summary.md"
        self.state = {
            "reference": REPOSITORY + "@" + INDEX,
            "server": {"Os": "linux", "Arch": "arm64", "ApiVersion": "1.48"},
            "index": {
                "schemaVersion": 2,
                "mediaType": OCI_INDEX,
                "manifests": [
                    {
                        "mediaType": OCI_IMAGE,
                        "digest": CHILD,
                        "platform": {
                            "os": "linux",
                            "architecture": "arm64",
                            "variant": "v8",
                        },
                    },
                    {
                        "mediaType": OCI_IMAGE,
                        "digest": "sha256:" + "4" * 64,
                        "platform": {"os": "unknown", "architecture": "unknown"},
                    },
                ],
            },
            "image": {
                "Os": "linux",
                "Architecture": "arm64",
                "Config": {
                    "Labels": {"org.opencontainers.image.revision": IMAGE_REVISION}
                },
            },
        }

    def invoke(
        self,
        selector=None,
        status=200,
        descriptor=None,
        payload=None,
        ref="refs/heads/main",
        extra_env=None,
        move_tag=False,
        cli=CLI,
    ):
        self.state_file.write_text(json.dumps(self.state))
        self.log.write_text("")
        for file in (self.output, self.environment_file, self.summary):
            file.unlink(missing_ok=True)
        if descriptor is None:
            descriptor = {"mediaType": OCI_INDEX, "digest": INDEX}
        if payload is None:
            payload = {"Descriptor": descriptor}
        request_selector = selector.strip() if selector is not None else "latest"
        if not request_selector:
            request_selector = "latest"
        if request_selector.startswith(REPOSITORY):
            normalized = request_selector
        elif request_selector.startswith("sha256:"):
            normalized = REPOSITORY + "@" + request_selector
        elif len(request_selector) == 64 and all(
            c in "0123456789abcdef" for c in request_selector
        ):
            normalized = REPOSITORY + "@sha256:" + request_selector
        else:
            normalized = REPOSITORY + ":" + request_selector
        route = (
            "GET",
            distribution_path(normalized, self.state["server"]["ApiVersion"]),
        )
        self.tag_moved = False

        def first_resolution():
            api.routes[route] = (
                200,
                {
                    "Descriptor": {
                        "mediaType": OCI_INDEX,
                        "digest": "sha256:" + "9" * 64,
                    }
                },
            )
            self.tag_moved = True
            return status, payload

        with APIFixture(
            {route: first_resolution if move_tag else (status, payload)}
        ) as api:
            environment = {
                **os.environ,
                "PATH": str(self.directory) + os.pathsep + os.environ["PATH"],
                "DOCKER_HOST": api.endpoint,
                "DOCKER_CONTEXT": "unrelated-context",
                "QUALIFY_DOCKER_STATE": str(self.state_file),
                "QUALIFY_DOCKER_LOG": str(self.log),
                "GITHUB_ENV": str(self.environment_file),
                "GITHUB_STEP_SUMMARY": str(self.summary),
                "GITHUB_REF": ref,
                "GH_TOKEN": "",
                "GH_ACTOR": "",
            }
            environment.update(extra_env or {})
            arguments = [sys.executable, "-B", str(cli), "--output", str(self.output)]
            if selector is not None:
                arguments.append("--image=" + selector)
            result = subprocess.run(
                arguments,
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.requests = list(api.requests)
            self.headers = list(api.headers)
        self.commands = [
            json.loads(line)[2:] for line in self.log.read_text().splitlines()
        ]
        return result

    def test_all_documented_inputs_resolve_to_one_immutable_index(self):
        for selector, suffix in [
            (None, ":latest"),
            ("", ":latest"),
            ("  \t ", ":latest"),
            ("latest", ":latest"),
            (" 0.0.17 ", ":0.0.17"),
            (INDEX, "@" + INDEX),
            (INDEX[7:], "@" + INDEX),
            (REPOSITORY + "@" + INDEX, "@" + INDEX),
        ]:
            with self.subTest(selector=selector):
                result = self.invoke(selector)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(self.output.read_text())
                self.assertEqual(report["normalized_reference"], REPOSITORY + suffix)
                self.assertEqual(report["resolved_reference"], REPOSITORY + "@" + INDEX)
                self.assertEqual(report["index_digest"], INDEX)
                self.assertEqual(report["platform"], "linux/arm64")
                self.assertEqual(report["platform_digest"], CHILD)
                self.assertEqual(report["image_revision"], IMAGE_REVISION)
                self.assertEqual(
                    self.requests, [("GET", distribution_path(REPOSITORY + suffix))]
                )
                self.assertEqual(
                    self.environment_file.read_text(),
                    "CI_UTILS_TEST_IMAGE=" + report["resolved_reference"] + "\n",
                )
                pulls = [args for args in self.commands if args[0] == "pull"]
                self.assertEqual(len(pulls), 1)
                self.assertIn("linux/arm64", pulls[0])
                self.assertIn(INDEX, self.summary.read_text())

    def test_invalid_selector_fails_before_docker_or_api_use(self):
        for selector in [
            "v0.0.17",
            "0.0",
            "1.2.3-rc1",
            "01.2.3",
            "Latest",
            "sha256:abc...",
            "f" * 63,
            "f" * 65,
            "F" * 64,
            "sha256:" + "z" * 64,
            "other/image@" + INDEX,
            "ghcr.io/myflow-xyz/ci-node@" + INDEX,
            REPOSITORY + "@" + INDEX[7:],
            "latest\n",
            "0.0.17\tlatest",
            "$(touch unsafe)",
            "--help",
        ]:
            with self.subTest(selector=selector):
                result = self.invoke(selector)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("image selector", result.stderr)
                self.assertEqual(self.commands, [])
                self.assertEqual(self.requests, [])
                self.assertFalse(self.output.exists())
                self.assertFalse(self.environment_file.exists())

    def test_registry_errors_are_explicit_and_do_not_fallback_or_pull(self):
        for status in [401, 403, 404, 500]:
            with self.subTest(status=status):
                result = self.invoke(
                    "latest", status=status, payload={"message": "fixture-secret"}
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(str(status), result.stderr)
                self.assertIn("latest", result.stderr)
                self.assertNotIn("fixture-secret", result.stderr + result.stdout)
                self.assertFalse(any(args[0] == "pull" for args in self.commands))
                self.assertEqual(len(self.requests), 1)
                self.assertFalse(self.environment_file.exists())

    def test_manifest_config_and_layer_digests_are_not_indexes(self):
        for media_type in [
            OCI_IMAGE,
            "application/vnd.oci.image.config.v1+json",
            "application/vnd.oci.image.layer.v1.tar+gzip",
        ]:
            with self.subTest(media_type=media_type):
                result = self.invoke(
                    INDEX, descriptor={"digest": INDEX, "mediaType": media_type}
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("index", result.stderr)
                self.assertFalse(any(args[0] == "pull" for args in self.commands))

    def test_digest_mismatch_and_malformed_registry_metadata_fail_closed(self):
        for payload in [
            {},
            {"Descriptor": None},
            {"Descriptor": {"digest": "invalid", "mediaType": OCI_INDEX}},
            {"Descriptor": {"digest": "sha256:" + "8" * 64, "mediaType": OCI_INDEX}},
        ]:
            with self.subTest(payload=payload):
                result = self.invoke(INDEX, payload=payload)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(args[0] == "pull" for args in self.commands))
                self.assertFalse(self.environment_file.exists())

    def test_missing_ambiguous_and_wrong_pulled_platforms_fail(self):
        self.state["index"]["manifests"][0]["platform"]["architecture"] = "amd64"
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("linux/arm64", result.stderr)
        self.assertFalse(any(args[0] == "pull" for args in self.commands))
        self.state["index"]["manifests"][0]["platform"]["architecture"] = "arm64"
        self.state["index"]["manifests"].append(self.state["index"]["manifests"][0])
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(args[0] == "pull" for args in self.commands))
        self.state["index"]["manifests"].pop()
        self.state["image"]["Architecture"] = "amd64"
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.environment_file.exists())

    def test_docker_manifest_list_and_amd64_are_supported(self):
        self.state["server"]["Arch"] = "amd64"
        self.state["image"]["Architecture"] = "amd64"
        self.state["index"]["mediaType"] = DOCKER_INDEX
        descriptor = self.state["index"]["manifests"][0]
        descriptor["mediaType"] = DOCKER_IMAGE
        descriptor["platform"] = {"os": "linux", "architecture": "amd64"}
        result = self.invoke(
            "0.0.17", descriptor={"digest": INDEX, "mediaType": DOCKER_INDEX}
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.output.read_text())["platform"], "linux/amd64")

    def test_registry_lookup_uses_the_daemons_supported_api_version(self):
        self.state["server"]["ApiVersion"] = "1.54"
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.requests, [("GET", distribution_path(REPOSITORY + ":latest", "1.54"))]
        )

    def test_malformed_index_and_platform_descriptors_do_not_pull(self):
        for index in [
            None,
            {},
            {"mediaType": OCI_INDEX, "manifests": []},
            {"schemaVersion": 2, "mediaType": OCI_INDEX, "manifests": [None]},
            {
                "schemaVersion": 2,
                "mediaType": OCI_INDEX,
                "manifests": [{"platform": None}],
            },
            {
                "schemaVersion": 2,
                "mediaType": OCI_INDEX,
                "manifests": [
                    {
                        "platform": {"os": "linux", "architecture": "arm64"},
                        "mediaType": OCI_IMAGE,
                        "digest": "invalid",
                    }
                ],
            },
        ]:
            with self.subTest(index=index):
                self.state["index"] = index
                result = self.invoke()
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(args[0] == "pull" for args in self.commands))
                self.assertFalse(self.environment_file.exists())

    def test_missing_image_revision_is_reported_without_attributing_checkout_code(self):
        self.state["image"]["Config"]["Labels"] = None
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(json.loads(self.output.read_text())["image_revision"])

    def test_registry_auth_is_forwarded_to_local_engine_without_disclosure(self):
        result = self.invoke(
            extra_env={"GH_TOKEN": "fixture-secret", "GH_ACTOR": "fixture-actor"}
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        auth = json.loads(base64.urlsafe_b64decode(self.headers[0]["X-Registry-Auth"]))
        self.assertEqual(
            auth,
            {
                "username": "fixture-actor",
                "password": "fixture-secret",
                "serveraddress": "ghcr.io",
            },
        )
        self.assertNotIn(
            "fixture-secret",
            result.stdout
            + result.stderr
            + self.output.read_text()
            + self.summary.read_text(),
        )

    def test_pull_failure_does_not_publish_environment_or_report(self):
        self.state["pull_error"] = True
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pull", result.stderr)
        self.assertNotIn("fixture-secret", result.stderr + result.stdout)
        self.assertFalse(self.environment_file.exists())
        self.assertFalse(self.output.exists())

    def test_selected_image_does_not_change_source_ref_or_checkout(self):
        expected_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        for selector, ref in [
            ("0.0.17", "refs/heads/main"),
            ("0.0.18", "refs/heads/main"),
        ]:
            with self.subTest(selector=selector, ref=ref):
                result = self.invoke(selector, ref=ref)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(self.output.read_text())
                self.assertEqual(report["workflow_ref"], ref)
                self.assertEqual(report["checkout_revision"], expected_sha)
                self.assertEqual(report["image_revision"], IMAGE_REVISION)
        self.assertEqual(
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            expected_sha,
        )

    def test_actual_checkout_changes_are_distinct_from_the_fixed_image_revision(self):
        checkout = self.directory / "checkout"
        scripts = checkout / ".github/scripts"
        scripts.mkdir(parents=True)
        shutil.copy2(CLI, scripts / CLI.name)
        shutil.copytree(
            ROOT / "images/utils/ci_utils",
            checkout / "images/utils/ci_utils",
            ignore=shutil.ignore_patterns("__pycache__"),
        )

        def git(*arguments):
            return subprocess.check_output(
                [
                    "git",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "-c",
                    "user.name=Qualification fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    *arguments,
                ],
                cwd=checkout,
                text=True,
                stderr=subprocess.PIPE,
            ).strip()

        git("init", "--initial-branch=main")
        git("add", ".")
        git("commit", "--no-gpg-sign", "-m", "fixture main source")
        revisions = []
        for branch in ("main", "harness-change"):
            if branch != "main":
                git("checkout", "-b", branch)
                (checkout / "fixture-source.txt").write_text("harness-change\n")
                git("add", "fixture-source.txt")
                git("commit", "--no-gpg-sign", "-m", "fixture harness source")
            revision = git("rev-parse", "HEAD")
            result = self.invoke(
                INDEX, ref="refs/heads/" + branch, cli=scripts / CLI.name
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(self.output.read_text())
            self.assertEqual(report["checkout_revision"], revision)
            self.assertEqual(report["workflow_ref"], "refs/heads/" + branch)
            self.assertEqual(report["image_revision"], IMAGE_REVISION)
            self.assertEqual(report["index_digest"], INDEX)
            revisions.append(revision)
        self.assertNotEqual(*revisions)

    def test_both_workflow_stores_use_the_first_digest_after_a_tag_moves(self):
        result = self.invoke("latest", move_tag=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.tag_moved)
        self.assertEqual(len(self.requests), 1)
        extract = """
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
const require=createRequire(import.meta.url);
const {load}=await import(require.resolve('js-yaml',{paths:['./images/node/markdownlint']}));
const workflow=load(readFileSync('.github/workflows/utils-test.yml','utf8'));
console.log(workflow.jobs['utils-runner'].steps.filter(s=>(s.run??'').includes('tests/utils-docker.sh')).map(s=>s.run).join('\\n'));
"""
        commands = subprocess.check_output(
            ["node", "--input-type=module", "-e", extract], cwd=ROOT, text=True
        )
        harness = self.directory / "tests/utils-docker.sh"
        harness.parent.mkdir()
        harness.write_text(
            '#!/usr/bin/env bash\nset -eu\nprintf "%s %s\\n" "${CI_UTILS_TEST_IMAGE_STORE:-containerd}" "$CI_UTILS_TEST_IMAGE" >>"$QUALIFY_STORE_LOG"\n'
        )
        harness.chmod(0o755)
        log = self.directory / "stores.log"
        variables = dict(
            line.split("=", 1)
            for line in self.environment_file.read_text().splitlines()
        )
        environment = {
            **os.environ,
            **variables,
            "CI_UTILS_IMAGE_SELECTOR": "latest",
            "QUALIFY_STORE_LOG": str(log),
        }
        environment.pop("CI_UTILS_TEST_IMAGE_STORE", None)
        subprocess.run(
            ["bash", "-eu", "-c", commands],
            cwd=self.directory,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            log.read_text().splitlines(),
            [
                store + " " + REPOSITORY + "@" + INDEX
                for store in ("containerd", "classic")
            ],
        )


if __name__ == "__main__":
    unittest.main()
