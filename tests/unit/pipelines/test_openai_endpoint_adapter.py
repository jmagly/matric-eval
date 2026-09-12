"""Unit coverage for the reference OpenAI-compatible endpoint adapter.

The adapter ships as a standalone script rather than a package module, because
the pipeline executes it with a scrubbed environment in which this project is
not importable. It is loaded by path here for the same reason.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

ADAPTER_PATH = Path("pipelines/openai-endpoint-adapter.py")


def _load() -> ModuleType:
    specification = importlib.util.spec_from_file_location("openai_endpoint_adapter", ADAPTER_PATH)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def adapter() -> ModuleType:
    return _load()


def test_adapter_uses_only_the_standard_library(adapter: ModuleType) -> None:
    # The scrubbed child environment has no project virtualenv, so a third-party
    # import would fail at run time rather than here.
    source = ADAPTER_PATH.read_text(encoding="utf-8")
    for forbidden in ("import requests", "import httpx", "import aiohttp"):
        assert forbidden not in source


def test_read_fixture_includes_documents_and_skips_hidden_and_binary(
    adapter: ModuleType, tmp_path: Path
) -> None:
    (tmp_path / "README.md").write_text("Project name: demo fixture.\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("kept\n", encoding="utf-8")
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01")
    hidden = tmp_path / ".secrets"
    hidden.mkdir()
    (hidden / "token.txt").write_text("do-not-read\n", encoding="utf-8")

    fixture = adapter.read_fixture(tmp_path)

    assert "Project name: demo fixture." in fixture
    assert "kept" in fixture
    assert "blob.bin" not in fixture
    assert "do-not-read" not in fixture, "hidden directories must not be sent to the endpoint"


def test_expected_project_name_is_read_from_the_fixture(adapter: ModuleType) -> None:
    assert adapter.expected_project_name("Project name: demo fixture.") == "demo fixture"
    assert adapter.expected_project_name("no expectation here") is None


def test_score_passes_when_the_answer_reports_the_project_name(adapter: ModuleType) -> None:
    outcome, reason = adapter.score("The project is demo fixture", "Project name: demo fixture.")
    assert (outcome, reason) == ("passed", "project_name_reported")


def test_score_is_case_insensitive(adapter: ModuleType) -> None:
    outcome, _ = adapter.score("DEMO FIXTURE", "Project name: demo fixture.")
    assert outcome == "passed"


def test_score_fails_when_the_project_name_is_absent(adapter: ModuleType) -> None:
    outcome, reason = adapter.score("I could not tell", "Project name: demo fixture.")
    assert (outcome, reason) == ("failed", "project_name_absent")


def test_score_falls_back_when_the_fixture_carries_no_expectation(
    adapter: ModuleType,
) -> None:
    outcome, reason = adapter.score("some answer", "a fixture with no declared name")
    assert (outcome, reason) == ("passed", "answer_returned")


def test_scored_reasons_satisfy_the_pipeline_contract(adapter: ModuleType) -> None:
    contract = re.compile(r"[a-z][a-z0-9_.-]{0,127}")
    for answer, fixture in (
        ("demo fixture", "Project name: demo fixture."),
        ("nope", "Project name: demo fixture."),
        ("anything", "no declared name"),
    ):
        outcome, reason = adapter.score(answer, fixture)
        assert outcome in {"passed", "failed"}
        assert contract.fullmatch(reason)
