"""Named metrics, comparison identities and native engine integration."""

import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from inspect_ai.log import EvalLog

from matric_eval.core.engine import EvaluationEngine
from matric_eval.results.comparison import attach_comparison, require_comparable
from matric_eval.results.contract import ResultEnvelope, read_result, write_result
from matric_eval.results.inspect_adapter import adapt_log, envelope
from matric_eval.results.policies import SuiteAggregation
from matric_eval.state import StateManager
from tests.unit.test_engine_accounting import task
from tests.unit.test_inspect_result_adapter import descriptor, native_log, sample
from tests.unit.test_result_reducers import benchmark


def metric_example() -> ResultEnvelope:
    source = native_log([sample("a", "C"), sample("b", "I")], value=0.5).model_dump()
    source["results"]["scores"][0]["metrics"]["stderr"] = {"name": "stderr", "value": 0.5}
    measured = adapt_log(
        EvalLog.model_validate(source),
        run_id="run",
        model_id="model",
        benchmark_id="benchmark",
        primary_metric_id="exact/accuracy",
        descriptors={"exact/accuracy": descriptor()},
    )
    return attach_comparison(envelope(measured, "run", "model"))


def test_shared_named_fixture_round_trip() -> None:
    path = Path(__file__).parents[1] / "fixtures/results/v2/named-metrics.json"
    payload = json.loads(path.read_text())
    result = read_result(json.dumps(payload))
    assert json.loads(write_result(result)) == payload
    assert result.benchmarks[0].metrics["exact/stderr"].estimate.denominator is None
    assert len(result.benchmarks[0].observations) == 2


def test_auxiliary_estimates_reference_inputs_without_fake_sample_measurements() -> None:
    result = metric_example()
    b = result.benchmarks[0]
    assert b.primary_estimate.value == 0.5
    assert b.metrics["exact/stderr"].estimate.value == 0.5
    assert b.metrics["exact/stderr"].native_estimate == 0.5
    assert b.metrics["exact/stderr"].estimate.denominator is None
    assert b.metrics["exact/stderr"].observation_metric_id == "exact/accuracy"
    assert len(b.observations) == 2
    assert {row.identity.metric_id for row in b.observations} == {"exact/accuracy"}
    assert read_result(write_result(result)) == result
    bad = result.model_dump()
    bad["benchmarks"][0]["metrics"]["exact/stderr"]["observation_metric_id"] = "missing"
    bad["comparability"] = None
    with pytest.raises(ValueError, match="direct observation"):
        ResultEnvelope.model_validate(bad)


def test_native_scorer_and_metric_order_do_not_choose_primary() -> None:
    source = native_log([sample("a", "C"), sample("b", "I")], value=0.5).model_dump()
    source["results"]["scores"][0]["metrics"]["stderr"] = {"name": "stderr", "value": 0.5}
    other = copy.deepcopy(source["results"]["scores"][0])
    other.update(name="other", scorer="other")
    source["results"]["scores"].append(other)
    for row in source["samples"]:
        row["scores"]["other"] = copy.deepcopy(row["scores"]["exact"])

    def convert(data: dict) -> dict:
        return adapt_log(
            EvalLog.model_validate(data),
            run_id="run",
            model_id="model",
            benchmark_id="benchmark",
            primary_metric_id="exact/accuracy",
            descriptors={"exact/accuracy": descriptor()},
        ).model_dump()

    expected = convert(source)
    source["results"]["scores"].reverse()
    for scorer in source["results"]["scores"]:
        scorer["metrics"] = dict(reversed(list(scorer["metrics"].items())))
    assert convert(source) == expected


def test_registry_primary_is_used_and_native_summary_is_retained(tmp_path: Path) -> None:
    source = native_log([sample("a", "C"), sample("b", "I")], value=0.9).model_dump()
    scorer = source["results"]["scores"][0]
    scorer.update(name="gsm8k_scorer", scorer="gsm8k_scorer")
    scorer["metrics"] = {"mean": {"name": "mean", "value": 0.9}}
    for row in source["samples"]:
        row["scores"]["gsm8k_scorer"] = row["scores"].pop("exact")
    runner = EvaluationEngine("ollama/model", log_dir=tmp_path)
    with patch("matric_eval.core.engine.eval", return_value=[EvalLog.model_validate(source)]):
        result = runner.run_benchmark("gsm8k", task=task())
    metric = result["observation_result"]["metrics"]["gsm8k_scorer/mean"]
    assert result["score"] == 0.5  # Hand-calculated accepted mean, not the synthetic native 0.9.
    assert metric["native_estimate"] == 0.9
    assert metric["estimate"]["numerator"] == 1
    assert metric["estimate"]["denominator"] == 2


def test_comparison_excludes_varied_model_and_values_but_checks_scope() -> None:
    first = envelope(benchmark("a", [0.0, 1.0]), "run", "model")
    first.benchmarks[0].protocol_sha256 = "c" * 64
    first.benchmarks[0].manifest_sha256 = "d" * 64
    first.configuration_sha256 = "a" * 64
    first = attach_comparison(first)
    assert first.comparability is not None and first.comparability.eligibility.eligible
    second = first.model_copy(deep=True)
    second.comparability = None
    second.model_id = "another-model"
    for row in second.benchmarks[0].observations:
        row.identity.model_id = second.model_id
        row.observation_id = row.identity.logical_id()
    second = attach_comparison(second)
    require_comparable(first, second)
    second.configuration_sha256 = "b" * 64
    second = attach_comparison(second)
    with pytest.raises(ValueError, match="identities differ"):
        require_comparable(first, second)
    unknown = metric_example()
    with pytest.raises(ValueError, match="unverified"):
        require_comparable(unknown, unknown)
    corrupt = first.model_dump()
    corrupt["benchmarks"][0]["protocol_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="payload differs"):
        ResultEnvelope.model_validate(corrupt)


def test_engine_declared_weighted_suite_keeps_native_benchmark_outputs(tmp_path: Path) -> None:
    runner = EvaluationEngine("model", log_dir=tmp_path)
    records = [benchmark("a", [1.0]), benchmark("b", [0.0])]
    for record in records:
        record.protocol_sha256 = "c" * 64
        record.manifest_sha256 = "d" * 64
    runner.run_id = "run"
    terms = [
        {
            "benchmark_id": name,
            "metric_id": "metric",
            "weight": weight,
            "transform": {
                "version": "1",
                "kind": "identity",
                "source_units": "fraction",
                "source_minimum": 0.0,
                "source_maximum": 1.0,
                "source_direction": "higher",
                "scale": 1.0,
                "offset": 0.0,
            },
        }
        for name, weight in [("a", 1.0), ("b", 3.0)]
    ]
    declaration = SuiteAggregation.model_validate(
        {
            "version": "1",
            "aggregation_id": "fixture/1",
            "target_units": "fraction",
            "target_direction": "higher",
            "missingness_policy": "require-complete",
            "terms": terms,
        }
    )
    outputs = [
        {
            "execution": "completed",
            "score": b.primary_estimate.value,
            "eligible": True,
            "eligibility_reasons": [],
            "observation_result": b.model_dump(),
        }
        for b in records
    ]
    with patch.object(runner, "run_benchmark", side_effect=outputs):
        result = runner.run_all(
            ["a", "b"],
            checkpoint=False,
            aggregation=declaration,
            comparison_configuration_sha256="a" * 64,
            result_format="v2",
        )
    assert result["overall_estimate"]["value"] == 0.25
    assert result["overall_estimate"]["numerator"] == 1.0
    assert result["overall_estimate"]["denominator"] == 4.0
    assert result["comparability"]["eligibility"]["eligible"]
    read_result(json.dumps(result))


def test_removed_metric_declaration_and_changed_configuration_invalidate_checkpoint(
    tmp_path: Path,
) -> None:
    runner = EvaluationEngine("ollama/model", log_dir=tmp_path / "logs")
    manager = StateManager(tmp_path / "state")
    manager.initialize_run("run", "smoke", 42, ["ollama/model"], ["synthetic"])
    native = native_log([sample("a"), sample("b", "I")], value=0.5).model_dump()
    native["results"]["scores"][0]["metrics"]["stderr"] = {"name": "stderr", "value": 0.5}
    auxiliary = descriptor().model_copy(
        update={"metric_id": "exact/stderr", "value_kind": "continuous"}
    )
    common = {"primary_metric_id": "exact/accuracy", "state_manager": manager}
    with (
        patch.object(runner, "_load_task", return_value=task()),
        patch(
            "matric_eval.core.engine.eval", return_value=[EvalLog.model_validate(native)]
        ) as evaluate,
    ):
        runner.run_all(
            ["synthetic"],
            metric_descriptors={"exact/accuracy": descriptor(), "exact/stderr": auxiliary},
            **common,
        )
        updated = runner.run_all(
            ["synthetic"], metric_descriptors={"exact/accuracy": descriptor()}, **common
        )
        assert evaluate.call_count == 1
        assert updated["benchmarks"]["synthetic"]["status"] == "legacy_unverified"
        assert updated["benchmarks"]["synthetic"]["score"] is None
        assert (
            updated["benchmarks"]["synthetic"]["historical_result"]["observation_result"][
                "metrics"
            ]["exact/stderr"]["descriptor"]["units"]
            == auxiliary.units
        )
        runner.run_all(["synthetic"], metric_descriptors={"exact/accuracy": descriptor()}, **common)
        assert evaluate.call_count == 1
        runner.run_all(
            ["synthetic"],
            metric_descriptors={"exact/accuracy": descriptor()},
            comparison_configuration_sha256="a" * 64,
            **common,
        )
        assert evaluate.call_count == 1
