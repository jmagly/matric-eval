"""The embedded smoke tasks must grade behaviour, not transcription.

`includes()` compared the response against a full reference implementation, so a
correct solution written differently scored zero while a verbatim reproduction of
one arbitrary solution scored one. See issue 224.
"""

from __future__ import annotations

import pytest

from matric_eval.scorers.code_execution import prepare_test_code
from matric_eval.tasks.builtin import (
    GSM8K_SAMPLES,
    HUMANEVAL_SAMPLES,
    MBPP_SAMPLES,
    _asserts_from_prompt,
    _executable,
)


def test_asserts_are_taken_from_the_prompt_the_model_was_given() -> None:
    """Deriving MBPP's tests from its prompt keeps them from drifting apart."""
    prompt = (
        "Write a Python function `is_even(n)`.\n\n"
        "Test cases:\n"
        "assert is_even(2) == True\n"
        "assert is_even(3) == False\n\n"
        "Return only the function code."
    )
    assert _asserts_from_prompt(prompt) == ("assert is_even(2) == True\nassert is_even(3) == False")


def test_asserts_from_prompt_without_any_is_empty() -> None:
    assert _asserts_from_prompt("Write a function. Return only code.") == ""


@pytest.mark.parametrize("sample", MBPP_SAMPLES, ids=lambda s: str(s.id))
def test_mbpp_samples_carry_an_executable_contract(sample) -> None:
    executable = _executable(sample)
    metadata = executable.metadata or {}
    assert metadata["entry_point"] == (sample.metadata or {})["function_name"]
    assert "assert" in metadata["test"]
    # The scorer must find runnable tests, otherwise the sample is silently unscored.
    assert prepare_test_code(metadata).strip()


@pytest.mark.parametrize("sample", HUMANEVAL_SAMPLES, ids=lambda s: str(s.id))
def test_humaneval_samples_carry_an_executable_contract(sample) -> None:
    executable = _executable(sample)
    metadata = executable.metadata or {}
    assert metadata["entry_point"]
    assert "assert" in metadata["test"]
    assert prepare_test_code(metadata).strip()
    # The declared entry point must be the function the prompt actually asks for.
    assert metadata["entry_point"] in str(sample.target)


@pytest.mark.parametrize("sample", GSM8K_SAMPLES, ids=lambda s: str(s.id))
def test_math_samples_are_left_alone(sample) -> None:
    """Only code samples get an execution contract; math keeps numeric matching."""
    executable = _executable(sample)
    metadata = executable.metadata or {}
    assert "test" not in metadata
    assert "entry_point" not in metadata


def test_every_code_sample_is_gradable() -> None:
    """A code sample without a contract would come back unscored rather than wrong,
    which is the failure this change exists to remove."""
    ungradable = [
        sample.id
        for sample in HUMANEVAL_SAMPLES + MBPP_SAMPLES
        if not prepare_test_code((_executable(sample).metadata or {})).strip()
    ]
    assert ungradable == []


def test_executable_is_idempotent_and_does_not_mutate_the_source_sample() -> None:
    original = MBPP_SAMPLES[0]
    before = dict(original.metadata or {})
    once = _executable(original)
    twice = _executable(once)
    assert (original.metadata or {}) == before, "source sample was mutated"
    assert (twice.metadata or {})["test"] == (once.metadata or {})["test"]


@pytest.mark.parametrize(
    ("factory_name", "expected_scorer"),
    [
        ("smoke_humaneval", "matric_eval/code_execution_scorer"),
        ("smoke_mbpp", "matric_eval/code_execution_scorer"),
        # Numeric answers are legitimately matched, not executed.
        ("smoke_gsm8k", "inspect_ai/match"),
        # The combined suite mixes kinds, so it routes per sample.
        ("smoke_suite", "matric_eval/smoke_mixed_scorer"),
    ],
)
def test_each_task_uses_a_scorer_that_can_measure_its_kind(
    factory_name: str, expected_scorer: str
) -> None:
    """Pins the scorer choice, not just the sample metadata.

    A substring scorer on a code task grades transcription; this assertion is what
    fails if one is reintroduced.
    """
    from inspect_ai._util.registry import registry_info

    from matric_eval.tasks import builtin

    task = getattr(builtin, factory_name)()
    scorer_obj = task.scorer[0] if isinstance(task.scorer, list) else task.scorer
    assert registry_info(scorer_obj).name == expected_scorer
