#!/usr/bin/env python3
"""Pin a published utility image and record the source/artifact qualification pair."""

import argparse
import base64
import http.client
import json
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "images/utils"))
from ci_utils.engine import UnixConnection

REPOSITORY = "ghcr.io/myflow-xyz/ci-utils"
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
INDEX_TYPES = {
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
}
IMAGE_TYPES = {
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
}


class QualificationError(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def normalize(value):
    if not value.strip():
        return REPOSITORY + ":latest"
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise QualificationError(
            "image selector must not contain control characters", 2
        )
    value = value.strip()
    if value == "latest" or VERSION.fullmatch(value):
        return REPOSITORY + ":" + value
    digest = value.removeprefix(REPOSITORY + "@")
    if re.fullmatch(r"[0-9a-f]{64}", value):
        digest = "sha256:" + digest
    if DIGEST.fullmatch(digest):
        return REPOSITORY + "@" + digest
    if value.startswith("v") and VERSION.fullmatch(value[1:]):
        raise QualificationError(
            "image selector must use X.Y.Z without the Git-tag v prefix", 2
        )
    raise QualificationError(
        "image selector must be blank/latest, X.Y.Z, sha256:<64 lowercase hex characters>, "
        "64 lowercase hex characters, or "
        + REPOSITORY
        + "@sha256:<64 lowercase hex characters>",
        2,
    )


def command(arguments, operation, environment, timeout=120):
    try:
        result = subprocess.run(
            arguments,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise QualificationError(operation + " unavailable or timed out") from error
    if result.returncode:
        # Registry/client diagnostics can contain credentials or untrusted content.
        raise QualificationError(
            operation
            + f" failed (exit {result.returncode}); check Docker and registry access"
        )
    return result.stdout


def registry_descriptor(endpoint, reference, api_version):
    headers = {}
    token = os.environ.get("GH_TOKEN")
    if token:
        actor = os.environ.get("GH_ACTOR")
        if not actor:
            raise QualificationError("GH_ACTOR is required with GH_TOKEN", 2)
        auth = {"username": actor, "password": token, "serveraddress": "ghcr.io"}
        headers["X-Registry-Auth"] = base64.urlsafe_b64encode(
            json.dumps(auth).encode()
        ).decode()
    connection = UnixConnection(endpoint.removeprefix("unix://"), 30)
    try:
        path = (
            f"/v{api_version}/distribution/"
            + urllib.parse.quote(reference, safe="")
            + "/json"
        )
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            raise QualificationError(
                f"Cannot inspect {reference}: Docker registry API HTTP {response.status}. "
                "Verify package access and publication. If latest is unavailable, select an existing "
                "version/index digest or wait for a release."
            )
        body = response.read(1024 * 1024 + 1)
        if len(body) > 1024 * 1024:
            raise QualificationError("Registry descriptor exceeds the response limit")
        data = json.loads(body)
        descriptor = data.get("Descriptor") if isinstance(data, dict) else None
        if not isinstance(descriptor, dict) or not isinstance(
            descriptor.get("digest"), str
        ):
            raise QualificationError("Registry returned an invalid index descriptor")
        if not DIGEST.fullmatch(descriptor["digest"]):
            raise QualificationError("Registry returned an invalid index digest")
        if descriptor.get("mediaType") not in INDEX_TYPES:
            raise QualificationError(
                "Image must identify an OCI index or Docker manifest list, not an image/config/layer digest"
            )
        if "@" in reference and reference.rsplit("@", 1)[1] != descriptor["digest"]:
            raise QualificationError(
                "Registry index digest does not match the requested digest"
            )
        return descriptor
    except (OSError, http.client.HTTPException) as error:
        raise QualificationError(
            "Docker registry inspection unavailable or timed out"
        ) from error
    except (ValueError, UnicodeError) as error:
        raise QualificationError(
            "Registry returned malformed index metadata"
        ) from error
    finally:
        connection.close()


def resolve(selector):
    reference = normalize(selector)
    endpoint = os.environ.get("DOCKER_HOST", "")
    if (
        not endpoint.startswith("unix:///")
        or endpoint == "unix:///"
        or any(c in endpoint for c in "\x00\n\r?#")
    ):
        raise QualificationError(
            "DOCKER_HOST must identify an explicit local Unix Docker socket", 2
        )
    environment = dict(os.environ)
    environment.pop("DOCKER_CONTEXT", None)
    environment.pop("DOCKER_DEFAULT_PLATFORM", None)
    docker = ["docker", "--host", endpoint]
    server = json.loads(
        command(
            docker + ["version", "--format", "{{json .Server}}"],
            "Docker server inspection",
            environment,
        )
    )
    if (
        not isinstance(server, dict)
        or server.get("Os") != "linux"
        or server.get("Arch") not in ("amd64", "arm64")
    ):
        raise QualificationError(
            "Qualification requires a Linux amd64 or arm64 Docker daemon"
        )
    architecture = server["Arch"]
    platform = "linux/" + architecture
    api_version = server.get("ApiVersion", "")
    if not isinstance(api_version, str) or not re.fullmatch(
        r"[0-9]+\.[0-9]+", api_version
    ):
        raise QualificationError("Docker returned an invalid API version")
    if tuple(map(int, api_version.split("."))) < (1, 30):
        raise QualificationError(
            "Registry inspection requires Docker API 1.30 or newer"
        )
    descriptor = registry_descriptor(endpoint, reference, api_version)
    pinned = REPOSITORY + "@" + descriptor["digest"]
    index = json.loads(
        command(
            docker + ["manifest", "inspect", pinned],
            "Docker index inspection",
            environment,
        )
    )
    if (
        not isinstance(index, dict)
        or index.get("schemaVersion") != 2
        or index.get("mediaType") not in INDEX_TYPES
        or not isinstance(index.get("manifests"), list)
    ):
        raise QualificationError("Registry object is not a valid image index")
    matches = []
    for manifest in index["manifests"]:
        if not isinstance(manifest, dict) or not isinstance(
            manifest.get("platform"), dict
        ):
            raise QualificationError("Index contains malformed platform metadata")
        candidate = manifest["platform"]
        variants = ("", "v8") if architecture == "arm64" else ("", "v1")
        if (
            candidate.get("os") == "linux"
            and candidate.get("architecture") == architecture
            and candidate.get("variant", "") in variants
        ):
            matches.append(manifest)
    if len(matches) != 1:
        raise QualificationError(
            f"Index must contain exactly one compatible {platform} image; found {len(matches)}"
        )
    child = matches[0]
    if (
        child.get("mediaType") not in IMAGE_TYPES
        or not isinstance(child.get("digest"), str)
        or not DIGEST.fullmatch(child["digest"])
    ):
        raise QualificationError("Index contains an invalid platform image descriptor")
    command(
        docker + ["pull", "--platform", platform, pinned],
        "Docker image pull",
        environment,
        timeout=600,
    )
    images = json.loads(
        command(
            docker + ["image", "inspect", pinned],
            "Docker image inspection",
            environment,
        )
    )
    if (
        not isinstance(images, list)
        or len(images) != 1
        or not isinstance(images[0], dict)
    ):
        raise QualificationError("Docker returned invalid pulled-image metadata")
    image = images[0]
    if image.get("Os") != "linux" or image.get("Architecture") != architecture:
        raise QualificationError(f"Pulled image does not match {platform}")
    labels = image.get("Config", {}).get("Labels") or {}
    revision = labels.get("org.opencontainers.image.revision")
    return {
        "requested_selector": selector,
        "normalized_reference": reference,
        "resolved_reference": pinned,
        "index_digest": descriptor["digest"],
        "platform": platform,
        "platform_digest": child["digest"],
        "workflow_ref": os.environ.get("GITHUB_REF")
        or command(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            "Git ref inspection",
            environment,
        ).strip(),
        "checkout_revision": command(
            ["git", "rev-parse", "HEAD"], "Git revision inspection", environment
        ).strip(),
        "image_revision": revision if isinstance(revision, str) else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image", default="latest", help="latest, X.Y.Z, or a sha256 index digest"
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="write qualification input metadata as JSON",
    )
    args = parser.parse_args()
    try:
        report = resolve(args.image)
        serialized = json.dumps(report, indent=2) + "\n"
        args.output.write_text(serialized)
        if os.environ.get("GITHUB_ENV"):
            with open(os.environ["GITHUB_ENV"], "a") as stream:
                stream.write(
                    "CI_UTILS_TEST_IMAGE=" + report["resolved_reference"] + "\n"
                )
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
                stream.write(
                    "### Utility qualification inputs\n\n```json\n"
                    + serialized.replace("`", "\\u0060")
                    + "```\n"
                )
        print(serialized, end="")
    except QualificationError as error:
        print(str(error), file=sys.stderr)
        return error.code
    except (ValueError, TypeError, AttributeError, OSError) as error:
        print(
            "Invalid qualification metadata or unavailable output path ("
            + type(error).__name__
            + ")",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
