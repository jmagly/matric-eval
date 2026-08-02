"""GAIA2 external runtime and evaluator contract tests."""

import json

import pytest

from matric_eval.tasks.gaia2 import (
    GAIA2_ARE_REVISION,
    GAIA2_DATASET_REVISION,
    build_gaia2_command,
    gaia2,
    load_gaia2,
    record_to_sample,
    summarize_gaia2_results,
)
from matric_eval.tasks.registry import BenchmarkStatus, BenchmarkUnavailableError


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    pass


def _scenario_record() -> dict:
    scenario = {
        "metadata": {"definition": {"duration": 1000}},
        "version": "are_simulation_v1",
        "events": [
            {
                "class_name": "Event",
                "event_type": "USER",
                "action": {
                    "function": "send_message_to_agent",
                    "args": [{"name": "content", "value": "Send the report."}],
                },
            },
            {
                "class_name": "OracleEvent",
                "event_type": "AGENT",
                "action": {
                    "function": "send_message_to_user",
                    "args": [{"name": "content", "value": "done"}],
                },
            },
        ],
    }
    return {"scenario_id": "scenario-1", "scenario": json.dumps(scenario)}


def test_manifest_conversion_records_all_runtime_revisions() -> None:
    sample = record_to_sample(_scenario_record(), split="execution")
    assert sample.input == "Send the report."
    assert sample.target == "done"
    assert sample.metadata["dataset_revision"] == GAIA2_DATASET_REVISION
    assert sample.metadata["are_revision"] == GAIA2_ARE_REVISION
    assert sample.metadata["execution"] == "external-gaia2-runner"


def test_loader_selects_deterministically_across_splits() -> None:
    from inspect_ai.dataset import Sample

    def fixture(*args, **kwargs):
        split = kwargs["subset"]
        return [Sample(id=f"{split}-1", input=split, target="")]

    from unittest.mock import patch

    with (
        patch("matric_eval.tasks.gaia2.load_hf_dataset", side_effect=fixture),
        patch("matric_eval.tasks.gaia2.get_sample_count", return_value=2),
    ):
        first = load_gaia2(splits=["execution", "search", "time"])
        second = load_gaia2(splits=["execution", "search", "time"])
    assert [sample.id for sample in first] == [sample.id for sample in second]
    assert len(first) == 2


def test_official_command_uses_python_312_and_run_config() -> None:
    command = build_gaia2_command("/are", config="config.toml")
    assert command[command.index("--python") + 1] == "3.12"
    assert "run-config" in command
    assert command[-1] == "/are/config.toml"


def test_official_success_false_null_semantics() -> None:
    summary = summarize_gaia2_results(
        [
            {"scenario_id": "a", "success": True, "split": "search"},
            {"scenario_id": "b", "success": False, "split": "search"},
            {"scenario_id": "c", "success": None, "split": "search"},
        ]
    )
    assert summary["completed"] == 2
    assert summary["infrastructure_errors"] == 1
    assert summary["average_reward"] == 0.5
    assert summary["by_split"]["search"] == 0.5


def test_unsupported_inspect_provider_fails_explicitly() -> None:
    with pytest.raises(BenchmarkUnavailableError, match="Python 3.12, Podman"):
        gaia2()
    assert gaia2._benchmark_metadata.status == BenchmarkStatus.GATED
