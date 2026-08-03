"""Tests for the matric-cli and matric-memory application benchmarks."""

import json
from importlib import import_module
from unittest.mock import Mock, patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Target

cli_module = import_module("matric_eval.tasks.matric_cli")
memory_module = import_module("matric_eval.tasks.matric_memory")


def _state(completion: str | None, metadata: dict) -> Mock:
    state = Mock()
    state.output = None if completion is None else Mock(completion=completion)
    state.metadata = metadata
    return state


def test_cli_json_loaders(tmp_path, monkeypatch) -> None:
    scenarios = [{"id": "one", "prompt": "Write code"}]
    (tmp_path / "code_generation_scenarios.json").write_text(json.dumps(scenarios))
    (tmp_path / "tool_calling_scenarios.json").write_text(json.dumps(scenarios))
    monkeypatch.setattr(cli_module, "DATA_DIR", tmp_path)

    assert cli_module.load_code_generation_scenarios() == scenarios
    assert cli_module.load_tool_calling_scenarios() == scenarios


def test_cli_json_loaders_report_missing_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli_module, "DATA_DIR", tmp_path)

    with pytest.raises(FileNotFoundError, match="Code generation scenarios"):
        cli_module.load_code_generation_scenarios()
    with pytest.raises(FileNotFoundError, match="Tool calling scenarios"):
        cli_module.load_tool_calling_scenarios()


def test_cli_scenario_to_sample_uses_defaults() -> None:
    sample = cli_module.scenario_to_sample({"id": "one", "prompt": "Prompt"}, "code")

    assert sample.id == "one"
    assert sample.input == "Prompt"
    assert sample.target == ""
    assert sample.metadata == {
        "category": "code",
        "difficulty": "medium",
        "required_checks": [],
        "tags": [],
    }


def test_load_cli_combines_sources_and_applies_seeded_limit() -> None:
    code = [{"id": "code", "prompt": "Code"}]
    tools = [{"id": "tool", "prompt": "Tool"}, {"id": "tool-2", "prompt": "Tool 2"}]
    with (
        patch.object(cli_module, "load_code_generation_scenarios", return_value=code),
        patch.object(cli_module, "load_tool_calling_scenarios", return_value=tools),
        patch.object(cli_module, "get_sample_count", return_value=2),
    ):
        first = cli_module.load_matric_cli("quick")
        second = cli_module.load_matric_cli("quick")

    assert len(first) == 2
    assert [sample.id for sample in first] == [sample.id for sample in second]


def test_load_cli_tolerates_missing_sources() -> None:
    with (
        patch.object(cli_module, "load_code_generation_scenarios", side_effect=FileNotFoundError),
        patch.object(cli_module, "load_tool_calling_scenarios", side_effect=FileNotFoundError),
        patch.object(cli_module, "get_sample_count", return_value=None),
    ):
        assert cli_module.load_matric_cli() == []


@pytest.mark.asyncio
async def test_cli_scorer_uses_basic_code_heuristic() -> None:
    scorer = cli_module.matric_cli_scorer()

    accepted = await scorer(_state("const answer = 42", {}), Target(target=""))
    rejected = await scorer(_state(None, {}), Target(target=""))

    assert accepted.value == 1.0
    assert rejected.value == 0.0


@pytest.mark.asyncio
async def test_cli_scorer_reports_pattern_fraction() -> None:
    scorer = cli_module.matric_cli_scorer()
    state = _state(
        "function findUserByEmail(users, email) { return users.find(u => u.email === email); }",
        {
            "required_checks": [
                "hasFunctionDeclaration",
                "hasParameters",
                "hasArraySearch",
                "hasEmailComparison",
                "hasValidJSON",
            ]
        },
    )

    result = await scorer(state, Target(target=""))

    assert result.value == 0.8
    assert result.explanation == "Passed 4/5 checks"


@pytest.mark.asyncio
async def test_cli_scorer_accepts_unrecognized_checks_for_compatibility() -> None:
    result = await cli_module.matric_cli_scorer()(
        _state("anything", {"required_checks": ["futureCheck"]}), Target(target="")
    )

    assert result.value == 1.0


def test_cli_task_is_configured() -> None:
    with patch.object(cli_module, "load_matric_cli", return_value=[Sample(input="prompt")]):
        configured = cli_module.matric_cli("full")

    assert isinstance(configured, Task)
    assert configured.name == "matric_cli"
    assert configured.scorer is not None


def test_memory_json_loaders(tmp_path, monkeypatch) -> None:
    cases = [{"id": "one", "content": "Content", "ideal_titles": ["Title"]}]
    pairs = [{"id": "pair", "text1": "a", "text2": "b"}]
    (tmp_path / "title_cases.json").write_text(json.dumps(cases))
    (tmp_path / "similarity_pairs.json").write_text(json.dumps(pairs))
    monkeypatch.setattr(memory_module, "DATA_DIR", tmp_path)

    assert memory_module.load_title_cases() == cases
    assert memory_module.load_similarity_pairs() == pairs


def test_memory_json_loaders_report_missing_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(memory_module, "DATA_DIR", tmp_path)

    with pytest.raises(FileNotFoundError, match="Title cases"):
        memory_module.load_title_cases()
    with pytest.raises(FileNotFoundError, match="Similarity pairs"):
        memory_module.load_similarity_pairs()


def test_memory_sample_converters() -> None:
    title = memory_module.title_case_to_sample(
        {
            "id": "one",
            "content": "Release checklist",
            "ideal_titles": ["Release Checklist"],
            "bad_titles": ["Note"],
        }
    )
    similarity = memory_module.similarity_to_sample(
        {"id": "pair", "text1": "alpha", "text2": "beta", "expected_similarity": 0.9},
        "similar",
    )

    assert title.id == "title-one"
    assert title.target == "Release Checklist"
    assert "Release checklist" in title.input
    assert similarity.target == "high"
    assert similarity.metadata["expected_similarity"] == 0.9
    assert (
        memory_module.similarity_to_sample(
            {"id": "low", "text1": "a", "text2": "b"}, "dissimilar"
        ).target
        == "low"
    )


def test_load_memory_combines_sources_and_applies_seeded_limit() -> None:
    cases = [{"id": str(index), "content": "Content", "ideal_titles": []} for index in range(3)]
    pairs = [{"id": str(index), "text1": "a", "text2": "b"} for index in range(12)]
    with (
        patch.object(memory_module, "load_title_cases", return_value=cases),
        patch.object(memory_module, "load_similarity_pairs", return_value=pairs),
        patch.object(memory_module, "get_sample_count", return_value=5),
    ):
        first = memory_module.load_matric_memory("quick")
        second = memory_module.load_matric_memory("quick")

    assert len(first) == 5
    assert [sample.id for sample in first] == [sample.id for sample in second]


def test_load_memory_tolerates_missing_sources() -> None:
    with (
        patch.object(memory_module, "load_title_cases", side_effect=FileNotFoundError),
        patch.object(memory_module, "load_similarity_pairs", side_effect=FileNotFoundError),
        patch.object(memory_module, "get_sample_count", return_value=None),
    ):
        assert memory_module.load_matric_memory() == []


@pytest.mark.asyncio
async def test_title_scorer_rewards_ideal_overlap_and_length() -> None:
    result = await memory_module.title_quality_scorer()(
        _state(
            "Quarterly Release Planning Checklist",
            {
                "category": "title_generation",
                "ideal_titles": ["Quarterly Release Planning Checklist"],
                "bad_titles": ["Untitled Note"],
            },
        ),
        Target(target=""),
    )

    assert result.value == 1.0
    assert "Ideal similarity: 1.00" in result.explanation


@pytest.mark.asyncio
async def test_title_scorer_penalizes_bad_title_overlap() -> None:
    result = await memory_module.title_quality_scorer()(
        _state(
            "Untitled Note",
            {
                "category": "title_generation",
                "ideal_titles": ["Release Plan"],
                "bad_titles": ["Untitled Note"],
            },
        ),
        Target(target=""),
    )

    assert result.value == 0.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("completion", "pair_type", "expected"),
    [
        ("8.5", "similar", 1.0),
        ("5", "similar", 0.5),
        ("2", "dissimilar", 1.0),
        ("6", "dissimilar", 0.4),
    ],
)
async def test_similarity_scorer(completion: str, pair_type: str, expected: float) -> None:
    result = await memory_module.title_quality_scorer()(
        _state(completion, {"category": "embedding_similarity", "pair_type": pair_type}),
        Target(target=""),
    )

    assert result.value == expected


@pytest.mark.asyncio
async def test_memory_scorer_handles_invalid_or_unknown_output() -> None:
    scorer = memory_module.title_quality_scorer()

    invalid = await scorer(
        _state("not a rating", {"category": "embedding_similarity"}), Target(target="")
    )
    unknown = await scorer(_state(None, {"category": "other"}), Target(target=""))

    assert invalid.value == 0.0
    assert unknown.value == 0.0


def test_memory_task_is_configured() -> None:
    with patch.object(memory_module, "load_matric_memory", return_value=[Sample(input="prompt")]):
        configured = memory_module.matric_memory("full")

    assert isinstance(configured, Task)
    assert configured.name == "matric_memory"
    assert configured.scorer is not None
