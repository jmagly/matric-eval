"""EvalPlus versioning, schema, and isolated scorer tests."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from inspect_ai.scorer import Target

from matric_eval.tasks.evalplus import (
    EVALPLUS_VERSION,
    evalplus_scorer,
    humaneval_plus,
    load_evalplus,
    mbpp_plus,
    parse_evalplus_output,
    record_to_sample,
)


@pytest.fixture(autouse=True)
def _isolated_registry(isolated_registry):
    pass


def _record() -> dict:
    return {
        "task_id": "HumanEval/0",
        "prompt": "def add(a, b):\n",
        "entry_point": "add",
        "canonical_solution": "    return a + b\n",
        "base_input": [[1, 2]],
        "plus_input": [[-1, 1]],
        "atol": 0,
    }


def test_schema_conversion_distinguishes_base_and_plus() -> None:
    sample = record_to_sample(_record(), dataset="humaneval")
    assert sample.metadata["base_test_count"] == 1
    assert sample.metadata["plus_test_count"] == 1
    assert sample.metadata["evaluator_version"] == EVALPLUS_VERSION


def test_tier_selection_is_deterministic() -> None:
    records = {
        f"HumanEval/{index}": {**_record(), "task_id": f"HumanEval/{index}"}
        for index in range(4)
    }
    with (
        patch("matric_eval.tasks.evalplus._suite", return_value=(records, {})),
        patch("matric_eval.tasks.evalplus.get_sample_count", return_value=2),
    ):
        first = load_evalplus("humaneval")
        second = load_evalplus("humaneval")
    assert [sample.id for sample in first] == [sample.id for sample in second]
    assert len(first) == 2


def test_upstream_schema_change_fails_explicitly() -> None:
    record = _record()
    del record["plus_input"]
    with pytest.raises(ValueError, match="plus_input"):
        record_to_sample(record, dataset="humaneval")


@pytest.mark.parametrize(
    ("base", "plus"),
    [("pass", "pass"), ("fail", "fail"), ("timeout", "timeout"), ("pass", "fail")],
)
def test_runner_output_preserves_failure_statuses(base: str, plus: str) -> None:
    result = parse_evalplus_output(
        "noise\nMATRIC_EVALPLUS_RESULT="
        f'{{"base_status":"{base}","plus_status":"{plus}",'
        '"base_details":[],"plus_details":[]}'
    )
    assert result["base_status"] == base
    assert result["plus_status"] == plus


def test_malformed_runner_output_is_rejected() -> None:
    with pytest.raises(ValueError, match="malformed"):
        parse_evalplus_output("SyntaxError")


@pytest.mark.asyncio
async def test_scorer_runs_upstream_checker_only_inside_sandbox() -> None:
    environment = Mock()
    environment.write_file = AsyncMock()
    environment.exec = AsyncMock(
        return_value=Mock(
            returncode=0,
            stdout=(
                "MATRIC_EVALPLUS_RESULT="
                '{"base_status":"pass","plus_status":"fail",'
                '"base_details":[true],"plus_details":[false]}\n'
            ),
            stderr="",
        )
    )
    state = Mock()
    state.output.completion = "```python\ndef add(a, b):\n    return a + b\n```"
    state.metadata = {"evalplus_dataset": "humaneval"}
    state.sample_id = "HumanEval/0"
    with (
        patch("matric_eval.tasks.evalplus._problem_payload", return_value={"trusted": True}),
        patch("matric_eval.tasks.evalplus.sandbox", return_value=environment),
    ):
        result = await evalplus_scorer()(state, Target(target=""))
    assert result.value == {"base_pass": 1.0, "plus_pass": 0.0}
    environment.exec.assert_awaited_once()
    assert environment.exec.await_args.args[0] == ["python", "/tmp/evalplus_runner.py"]


def test_legacy_names_are_not_reused() -> None:
    assert humaneval_plus._benchmark_metadata.name == "humaneval_plus"
    assert mbpp_plus._benchmark_metadata.name == "mbpp_plus"
