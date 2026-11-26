"""Resolve the shared package for image commands run from a checkout."""

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parents[3] / "scripts/ci-utils/lib/ci_utils")]
