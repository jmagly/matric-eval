"""HELMET external adapter and overlap assessment tests."""

import pytest

from matric_eval.tasks.helmet import (
    HELMET_CATEGORIES,
    build_helmet_command,
    helmet_coverage_report,
    load_helmet_score,
    pearson_correlation,
    spearman_correlation,
)


def test_all_seven_categories_use_pinned_official_configs() -> None:
    assert len(HELMET_CATEGORIES) == 7
    for category in HELMET_CATEGORIES:
        command = build_helmet_command(
            "/helmet",
            category=category,
            model_name_or_path="model",
            output_dir="/results",
            short=True,
            max_test_samples=3,
        )
        assert f"/helmet/configs/{category}_short.yaml" in command
        assert command[-2:] == ["--max_test_samples", "3"]


def test_correlation_fixture_matches_expected_ranking() -> None:
    assert pearson_correlation([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert spearman_correlation([10, 20, 20, 40], [1, 2, 2, 4]) == pytest.approx(1.0)


def test_coverage_decision_keeps_longproc_out_of_scope() -> None:
    report = helmet_coverage_report({"recall", "rag"})
    assert report["covered"] == ["rag", "recall"]
    assert set(report["incremental"]) == set(HELMET_CATEGORIES) - {"recall", "rag"}
    assert report["decision"] == "integrate-gated"
    assert report["longproc_included"] is False


def test_official_score_file_retains_category_metrics(tmp_path) -> None:
    path = tmp_path / "recall.json.score"
    path.write_text('{"exact_match": 0.75, "count": 100}', encoding="utf-8")
    summary = load_helmet_score(path, category="recall", context_length=32768)
    assert summary["by_category"]["recall"]["32768"] == {
        "exact_match": 0.75,
        "count": 100.0,
    }
    assert summary["longproc_included"] is False
