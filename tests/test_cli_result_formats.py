"""Actual Click entry and deterministic offline consumer commands."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click import ClickException
from click.testing import CliRunner

from matric_eval.cli import cli, run_evaluation
from matric_eval.results.consumer import read_consumer_result

FIXTURES = Path(__file__).parent / "fixtures/results/consumer"


def test_read_convert_commands_and_exclusive_output(tmp_path):
    source = FIXTURES / "legacy-null.json"
    before = source.read_bytes()
    runner = CliRunner()
    read = runner.invoke(cli, ["read-result", str(source)])
    assert read.exit_code == 0, read.output
    assert read_consumer_result(read.output).payload["overall_score"] is None
    output = tmp_path / "output with spaces.json"
    converted = runner.invoke(cli, ["convert-result", str(source), "--output", str(output)])
    assert converted.exit_code == 0, converted.output
    assert (
        runner.invoke(cli, ["convert-result", str(source), "--output", str(output)]).exit_code != 0
    )
    assert source.read_bytes() == before


def test_recommend_legacy_default_returns_explicit_exclusions(tmp_path):
    (tmp_path / "model.json").write_bytes((FIXTURES / "legacy-null.json").read_bytes())
    result = CliRunner().invoke(
        cli, ["recommend", "--results-dir", str(tmp_path), "--output-format", "json"]
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["status"] == "no_recommendation"
    assert report["exclusions"][0]["reasons"] == ["legacy_unverified"]
    assert report["sources"][0]["payload"]["overall_score"] is None


def test_ollama_slash_alias_is_not_mistaken_for_native_provider(tmp_path):
    with patch("matric_eval.cli.EvaluationEngine") as engine:
        run_evaluation("hf.co/user/model", benchmarks=["gsm8k"], output_dir=tmp_path)
    assert engine.call_args.kwargs["model"] == "ollama/hf.co/user/model"


def test_versioned_selection_reaches_engine_without_adding_legacy_fields(tmp_path):
    with patch("matric_eval.cli.EvaluationEngine") as engine:
        run_evaluation(
            "mockllm/model",
            benchmarks=["consumer_fixture"],
            output_dir=tmp_path,
            result_format="v2",
        )
    assert engine.call_args.kwargs["model"] == "mockllm/model"
    assert engine.return_value.run_all.call_args.kwargs["result_format"] == "v2"


def test_public_trend_commands_preserve_native_nulls(tmp_path):
    source = FIXTURES / "../v2/named-metrics.json"
    database = tmp_path / "history.sqlite"
    runner = CliRunner()
    imported = runner.invoke(cli, ["trend-import", str(source), "--database", str(database)])
    assert imported.exit_code == 0, imported.output
    native = read_consumer_result(source.read_text())
    series = runner.invoke(
        cli,
        [
            "trend-series",
            "--database",
            str(database),
            "--model",
            native.model_id,
            "--benchmark",
            "benchmark",
            "--metric",
            "exact/stderr",
            "--comparison-sha256",
            native.comparability.sha256,
        ],
    )
    assert series.exit_code == 0, series.output
    report = json.loads(series.output)
    assert not report["points"]
    assert report["excluded"]


def test_matrix_v2_failure_log_and_artifact_do_not_echo_provider_payload(tmp_path):
    from matric_eval.cli import _run_matrix_evaluation

    matrix = Mock(tier="smoke")
    matrix.get_runs.return_value = [{"model": "fixture", "provider": "mock", "benchmark": "b"}]
    private = "PRIVATE_FIXTURE_PROVIDER_PAYLOAD"
    with (
        patch("matric_eval.cli.get_cli_logger") as logger_factory,
        patch("matric_eval.cli.get_provider", side_effect=ValueError(private)),
    ):
        with pytest.raises(ClickException, match="result_projection_unavailable"):
            _run_matrix_evaluation(matrix, tmp_path, "json", "off", "smoke", result_format="v2")
    error_call = logger_factory.return_value.error.call_args
    assert error_call.kwargs["extra"]["error"] == "result_projection_unavailable"
    assert private not in str(error_call)
    summaries = list(tmp_path.glob("run-*/summary.json"))
    assert len(summaries) == 1
    assert private not in summaries[0].read_text()
    result = read_consumer_result(summaries[0].read_text())
    assert result.failures[0].reason == "result_projection_unavailable"
    assert not result.results
