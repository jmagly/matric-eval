"""Wave 3 external benchmark protocol tests."""

import pytest

from matric_eval.tasks.memorybench import (
    MEMORYBENCH_DATASET_REVISION,
    build_memorybench_command,
    published_memorybench_summary_rows,
    summarize_memorybench_results,
)
from matric_eval.tasks.nolima import (
    NOLIMA_DATASET_REVISION,
    build_nolima_command,
    load_nolima_results,
    summarize_nolima_results,
)
from matric_eval.tasks.tulving import (
    TULVING_REVISION,
    build_tulving_command,
    chronological_awareness_score,
    summarize_tulving_results,
)


def test_memorybench_keeps_off_and_on_policy_protocols_separate() -> None:
    off = build_memorybench_command(
        "/memorybench",
        regime="off-policy",
        memory_system="mem0",
        dataset_type="task",
        set_name="Long-Short",
    )
    on = build_memorybench_command(
        "/memorybench",
        regime="on-policy",
        memory_system="mem0",
        dataset_type="domain",
        set_name="Legal",
    )
    assert "src.off-policy" in off
    assert "src.on-policy" in on
    rows = published_memorybench_summary_rows(
        {"summary": {"average": {"mem0": 0.4}, "z_score": {"mem0": 0.2}}},
        regime="off-policy",
        dataset_type="task",
        set_name="Long-Short",
        baseline="mem0",
    )
    rows.append({"regime": "on-policy", "domain": "Legal", "metric": "average", "score": 0.7})
    summary = summarize_memorybench_results(rows)
    assert summary["by_regime"]["off-policy"]["Long-Short"]["average"] == 0.4
    assert summary["by_regime"]["off-policy"]["Long-Short"]["z_score"] == 0.2
    assert summary["dataset_revision"] == MEMORYBENCH_DATASET_REVISION


def test_nolima_preserves_context_depth_overlap_and_85_percent_rule() -> None:
    rows = [
        {
            "context_length": 4096,
            "document_depth_percent": 0,
            "lexical_overlap": "none",
            "score": 1.0,
        },
        {
            "context_length": 8192,
            "document_depth_percent": 50,
            "lexical_overlap": "none",
            "score": 0.9,
        },
        {
            "context_length": 16384,
            "document_depth_percent": 100,
            "lexical_overlap": "partial",
            "score": 0.84,
        },
    ]
    summary = summarize_nolima_results(rows)
    assert summary["effective_context_length"] == 8192
    assert summary["by_needle_position"] == {0.0: 1.0, 50.0: 0.9, 100.0: 0.84}
    assert summary["dataset_revision"] == NOLIMA_DATASET_REVISION
    command = build_nolima_command("/nolima", config="configs/test.yaml")
    assert command[-1] == "/nolima/configs/test.yaml"


def test_nolima_loads_official_nested_result_contract(tmp_path) -> None:
    path = tmp_path / "result.json"
    path.write_text(
        """{
          "context_length": 8192,
          "test_name": "0001_direct",
          "results": [
            {"metric": 1, "placement_metadata": {"depth": 0.0}},
            {"metric": 0, "placement_metadata": {"depth": 1.0}}
          ]
        }""",
        encoding="utf-8",
    )
    summary = load_nolima_results(path)
    assert summary["by_context_length"] == {8192: 0.5}
    assert summary["by_needle_position"] == {0.0: 1.0, 100.0: 0.0}
    assert summary["by_lexical_overlap"] == {"minimal": 0.5}
    assert summary["by_test"] == {"0001_direct": 0.5}


def test_tulving_released_score_formula_and_event_slices() -> None:
    assert (
        chronological_awareness_score(latest_state=0.8, exact_set_rate=0.5, kendall_tau=-0.4) == 0.4
    )
    rows = [
        {"event_count": 200, "get": "all", "event_bin": name, "f1_score_lenient": score}
        for name, score in zip(("0", "1", "2", "3-5", "6+"), (1.0, 0.8, 0.6, 0.4, 0.2), strict=True)
    ]
    rows.extend(
        (
            {"event_count": 200, "get": "latest", "f1_score_lenient": 0.8},
            {"event_count": 200, "get": "chronological", "exact_set": 0.5, "kendall_tau": 0.6},
        )
    )
    summary = summarize_tulving_results(rows)
    assert summary["by_event_count"][200]["simple_recall"] == pytest.approx(0.6)
    assert summary["by_event_count"][200]["chronological_awareness"] == pytest.approx(0.55)
    assert summary["evaluator_revision"] == TULVING_REVISION
    command = build_tulving_command(
        "/tulving", data_folder="/data", env_file="/secrets/env", event_count=200
    )
    assert command[command.index("--book_nb_events") + 1] == "200"
