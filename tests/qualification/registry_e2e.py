"""Opt-in qualification CLI checks against a real Docker daemon and registry."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / ".github/scripts/resolve-utils-image.py"


def invoke(selector, directory, name, expected_error=None):
    output = directory / (name + ".json")
    environment_file = directory / (name + "-github-env")
    summary = directory / (name + ".md")
    environment = dict(
        os.environ,
        GITHUB_ENV=str(environment_file),
        GITHUB_STEP_SUMMARY=str(summary),
    )
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(CLI),
            "--image=" + selector,
            "--output",
            str(output),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    if expected_error:
        assert result.returncode == 1, (name, result.returncode, result.stderr)
        assert expected_error in result.stderr, (name, result.stderr)
        assert not result.stdout, (name, result.stdout)
        assert not any(path.exists() for path in (output, environment_file, summary)), (
            name
        )
        print(name + ": PASS (rejected before qualification handoff)")
        return None
    assert result.returncode == 0, (name, result.returncode, result.stderr)
    report = json.loads(output.read_text())
    assert json.loads(result.stdout) == report, name
    assert environment_file.read_text() == (
        "CI_UTILS_TEST_IMAGE=" + report["resolved_reference"] + "\n"
    ), name
    assert report["resolved_reference"] in summary.read_text(), name
    assert report["resolved_reference"].endswith("@" + report["index_digest"]), name
    assert report["platform_digest"] != report["index_digest"], name
    assert report["platform"] in ("linux/amd64", "linux/arm64"), name
    assert (
        report["checkout_revision"]
        == subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    ), name
    print(name + ": PASS")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image", required=True, help="published version or index digest"
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="resolved image report"
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="utils-registry-e2e-") as temporary:
        directory = Path(temporary)
        report = invoke(args.image, directory, "published-index")
        fields = (
            "resolved_reference",
            "index_digest",
            "platform",
            "platform_digest",
            "workflow_ref",
            "checkout_revision",
            "image_revision",
        )
        for name, selector in (
            ("prefixed-digest", report["index_digest"]),
            ("bare-digest", report["index_digest"].removeprefix("sha256:")),
            ("full-reference", report["resolved_reference"]),
        ):
            repeated = invoke(selector, directory, name)
            assert {field: repeated[field] for field in fields} == {
                field: report[field] for field in fields
            }, name
        invoke(
            report["platform_digest"],
            directory,
            "platform-child",
            expected_error="must identify an OCI index or Docker manifest list",
        )
        missing = "sha256:" + hashlib.sha256(uuid.uuid4().bytes).hexdigest()
        invoke(
            missing,
            directory,
            "missing-index",
            expected_error="Docker registry API HTTP 404",
        )
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        print("6 live registry/CLI checks passed; no fixture daemon was created")


if __name__ == "__main__":
    main()
