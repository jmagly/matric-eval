#!/usr/bin/env python3
"""Run the isolated incident-client fixtures; missing dependencies/skips fail."""

from __future__ import annotations

import importlib.metadata
import os
import sys
from pathlib import Path

import coverage
import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "litellm": "1.81.11",
    "openai": "2.20.0",
    "httpx": "0.28.1",
    "pydantic": "2.12.4",
    "coverage": "7.15.3",
}


class NoSkippedTests:
    skipped = False

    def pytest_runtest_logreport(self, report):
        if report.skipped:
            self.skipped = True

    def pytest_collectreport(self, report):
        if report.skipped:
            self.skipped = True


def main() -> int:
    actual = {name: importlib.metadata.version(name) for name in EXPECTED}
    if actual != EXPECTED:
        raise RuntimeError("incident client dependency versions do not match the isolated profile")
    print({"python": sys.version.split()[0], "dependencies": actual}, flush=True)
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    sys.path.insert(0, str(ROOT / "src"))
    plugin = NoSkippedTests()
    os.chdir(ROOT)
    measurement = coverage.Coverage(
        config_file=str(ROOT / "pyproject.toml"), data_file=str(ROOT / ".coverage.client")
    )
    measurement.start()
    try:
        result = pytest.main(
            [
                "-c",
                str(ROOT / "tests/profiles/client-conformance/pyproject.toml"),
                "--confcutdir",
                str(ROOT / "tests/unit"),
                str(ROOT / "tests/unit/test_client_conformance.py"),
                "-q",
                "--junitxml=client-conformance-junit.xml",
            ],
            plugins=[plugin],
        )
    finally:
        measurement.stop()
        measurement.save()
    return 1 if plugin.skipped else int(result)


if __name__ == "__main__":
    raise SystemExit(main())
