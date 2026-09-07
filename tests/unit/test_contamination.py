"""Overlap diagnostics distinguish local measurements from unknown exposure."""

import json

import pytest
from click.testing import CliRunner

from matric_eval.cli import cli
from matric_eval.contamination import (
    ContaminationReport,
    LegacyDiagnostic,
    NgramDetector,
    check_contamination,
    check_overlap,
    read_diagnostic,
    score_series_diagnostics,
    write_diagnostic,
)
from matric_eval.contamination.detector import _extract_ngrams
from matric_eval.recommendation import RecommendationEngine


def test_word_ngrams_normalize_case_whitespace_and_keep_occurrences():
    assert _extract_ngrams("The  QUICK\nbrown fox", 2) == [
        ("the", "quick"),
        ("quick", "brown"),
        ("brown", "fox"),
    ]
    assert NgramDetector(n=1).compute_overlap("a a b", "a") == pytest.approx(2 / 3)
    assert _extract_ngrams("short", 2) == []


@pytest.mark.parametrize(
    ("output", "reference", "exact", "ratio"),
    [
        ("The answer is forty two", "The answer is forty two", True, 1.0),
        ("Forty two solves it", "The answer is forty two", False, 0.0),
    ],
)
def test_independent_correct_answer_and_paraphrase_both_have_unknown_exposure(
    output, reference, exact, ratio
):
    report = check_overlap([output], [reference], n=3, raw_score=0.875)
    sample = report.samples[0]
    assert report.training_exposure == "unknown"
    assert sample.normalized_exact_match is exact
    assert sample.overlap_ratio == ratio
    assert report.status == "tested_with_method"
    assert read_diagnostic(write_diagnostic(report)).raw_score == 0.875
    serialized = report.to_dict()
    assert "recommendation" not in serialized
    assert "contamination_score" not in serialized
    assert "adjusted_score" not in serialized


@pytest.mark.parametrize(
    ("output", "reference", "exact", "status"),
    [
        ("", "", None, "insufficient_text"),
        ("", "reference", None, "insufficient_text"),
        ("42", "42", True, "tested_with_method"),
        ("42", "43", False, "tested_with_method"),
    ],
)
def test_empty_and_short_pairs_keep_unavailable_ngram_limits(output, reference, exact, status):
    report = check_overlap([output], [reference], raw_score=0.0)
    sample = report.samples[0]
    assert sample.normalized_exact_match is exact
    assert sample.status == status
    assert sample.overlap_ratio is None
    assert sample.exceeds_similarity_threshold is None
    assert "insufficient_words_for_ngram_method" in sample.limits
    assert read_diagnostic(write_diagnostic(report)) == report


def test_empty_batch_has_no_negative_exposure_finding():
    report = check_overlap([], [], raw_score=None)
    assert report.status == "empty_batch"
    assert report.training_exposure == "unknown"
    assert report.raw_score is None


def test_exact_is_normalized_local_match_with_original_content_identities():
    report = check_overlap([" FOO\nbar "], ["foo bar"], n=2)
    sample = report.samples[0]
    assert sample.normalized_exact_match
    assert sample.output.sha256 != sample.reference.sha256
    assert sample.output.normalized_sha256 == sample.reference.normalized_sha256
    assert report.method.normalization == "unicode-lower-whitespace-collapse/1"
    assert report.method.tokenization == "python-str-split-whitespace/1"
    assert report.method.denominator == "output-word-ngram-occurrences"


def test_known_supplied_train_eval_pair_overlap_does_not_prove_foundation_training():
    report = check_overlap(
        ["same"],
        ["same"],
        scope="provided_train_eval_datasets",
        output_source_id="local-training-dataset@revision",
        reference_source_id="local-evaluation-dataset@revision",
    )
    assert report.samples[0].normalized_exact_match
    assert report.scope == "provided_train_eval_datasets"
    assert report.training_exposure == "unknown"
    with pytest.raises(ValueError, match="source identities"):
        check_overlap(["same"], ["same"], scope="provided_train_eval_datasets")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"n": 0},
        {"n": True},
        {"threshold": 1.1},
        {"threshold": float("nan")},
        {"raw_score": float("inf")},
        {"sample_ids": []},
        {"sample_ids": ["a", "a"]},
    ],
)
def test_invalid_method_score_and_identity_inputs_fail(kwargs):
    with pytest.raises((ValueError, TypeError)):
        check_overlap(["one"], ["two"], **kwargs)


def test_mismatched_pair_lengths_fail():
    with pytest.raises(ValueError, match="same length"):
        check_overlap(["one"], [])


@pytest.mark.parametrize("mutation", ["version", "exposure", "ratio", "limits", "unknown"])
def test_reader_rejects_forged_or_unknown_diagnostics(mutation):
    value = check_overlap(["one two"], ["one two"], n=2).to_dict()
    if mutation == "version":
        value["diagnostic_schema_version"] = "99"
    elif mutation == "exposure":
        value["training_exposure"] = "clean"
    elif mutation == "ratio":
        value["samples"][0]["overlap_ratio"] = 0.0
    elif mutation == "limits":
        value["limits"] = []
    else:
        value["adjusted_score"] = 0.9
    with pytest.raises(ValueError):
        read_diagnostic(json.dumps(value))


@pytest.mark.parametrize(
    "payload",
    [
        '{"raw_score":NaN}',
        '{"raw_score":1e999,"contamination_score":0.1}',
        '{"contamination_score":0.1,"contamination_score":0.2}',
    ],
)
def test_nonfinite_and_duplicate_json_rejected(payload):
    with pytest.raises(ValueError):
        read_diagnostic(payload)


def test_legacy_artifact_keeps_original_score_and_flags_old_discounts():
    original = {
        "model": "m",
        "benchmark": "b",
        "contamination_score": 0.8,
        "recommendation": "likely_contaminated",
        "raw_score": 0.8,
        "adjusted_score": 0.4,
    }
    report = read_diagnostic(json.dumps(original))
    assert isinstance(report, LegacyDiagnostic)
    assert report.original_artifact == original
    assert report.raw_score == 0.8
    assert report.historical_adjusted_score == 0.4
    assert not report.comparison_eligible
    assert report.training_exposure == "unknown"
    assert set(report.flags) == {
        "legacy_adjusted_score_excluded",
        "legacy_heuristic_label_unverified",
    }
    assert read_diagnostic(write_diagnostic(report)) == report


@pytest.mark.parametrize("heuristic", [0.1, 0.35, 0.6, 0.9])
def test_deprecated_api_never_discounts_or_returns_trust_labels(heuristic):
    with pytest.warns(DeprecationWarning):
        report = ContaminationReport("m", "b", contamination_score=heuristic)
    with pytest.warns(DeprecationWarning):
        assert report.adjusted_score(0.83) == 0.83
    with pytest.warns(DeprecationWarning):
        assert report.recommendation == "unknown_training_exposure"
    assert report.to_dict()["comparison_eligible"] is False
    with pytest.warns(DeprecationWarning):
        current = check_contamination(["answer"], ["answer"])
    with pytest.warns(DeprecationWarning):
        assert current.adjusted_score(0.83) == 0.83


def test_likelihood_method_is_unsupported_not_a_negative_result():
    report = check_overlap(["different"], ["reference"])
    assert report.likelihood_test_status == "unsupported"
    assert report.likelihood_test_reason == "likelihood_method_not_implemented"
    assert report.training_exposure == "unknown"


def result(model="m"):
    return {
        "model": model,
        "status": "success",
        "benchmarks": {"humaneval": {"score": 0.8}},
        "overall_score": 0.8,
    }


def test_recommendation_excludes_legacy_series_and_exposes_diagnostic_method():
    current = result()
    current["overlap_diagnostics"] = check_overlap(["same"], ["same"], raw_score=0.8).to_dict()
    legacy = result("old")
    legacy["benchmarks"]["humaneval"]["adjusted_score"] = 0.4
    report = RecommendationEngine(legacy_exploratory=True).recommend([current, legacy])
    assert set(report.model_scores) == {"m"}
    assert report.model_scores["m"].benchmark_scores["humaneval"] == 0.8
    reviews = report.to_dict()["metadata"]["diagnostic_reviews"]
    assert reviews[0]["overlap_diagnostics"][0]["status"] == "tested_with_method"
    assert (
        reviews[0]["overlap_diagnostics"][0]["method"]["method_id"]
        == "normalized-exact-and-word-ngram/1"
    )
    assert reviews[1]["exclusion_reasons"] == ["legacy_adjusted_score_excluded"]
    assert report.to_model_categories()["diagnostic_reviews"] == reviews
    assert json.loads(report.to_json())["model_scores"]["m"]["overall_score"] == 0.8


def test_all_legacy_series_are_explicitly_excluded_even_if_raw_score_present():
    legacy = result()
    legacy["contamination"] = {"recommendation": "trustworthy", "raw_score": 0.8}
    report = RecommendationEngine(legacy_exploratory=True).recommend([legacy])
    assert not report.model_scores
    assert report.metadata["diagnostic_reviews"][0]["legacy_series_excluded"] is True
    assert score_series_diagnostics(legacy)["legacy_series_excluded"]


def test_cli_serialization_and_legacy_transition_preserve_input(tmp_path):
    source = tmp_path / "pairs.json"
    payload = {"outputs": ["42"], "references": ["42"], "raw_score": 0.875}
    source.write_text(json.dumps(payload))
    runner = CliRunner()
    response = runner.invoke(cli, ["overlap-diagnostics", str(source)])
    assert response.exit_code == 0, response.output
    parsed = read_diagnostic(response.output)
    assert parsed.raw_score == 0.875
    assert parsed.training_exposure == "unknown"
    assert source.read_text() == json.dumps(payload)
    overwrite = runner.invoke(cli, ["overlap-diagnostics", str(source), "--output", str(source)])
    assert overwrite.exit_code != 0
    legacy = tmp_path / "legacy.json"
    legacy.write_text('{"contamination_score":0.2,"adjusted_score":0.7}')
    response = runner.invoke(cli, ["overlap-diagnostics", str(legacy), "--artifact"])
    assert response.exit_code == 0, response.output
    assert read_diagnostic(response.output).comparison_eligible is False
