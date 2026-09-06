"""Tests for immutable refusal and over-refusal benchmark adapters."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from matric_eval.tasks import refusal


def test_classify_refusal_prefix_reproduces_published_baseline() -> None:
    assert refusal.classify_refusal_prefix("I'm sorry, but I cannot help.") == "full_refusal"
    assert refusal.classify_refusal_prefix("Here is a direct answer.") == "compliance"
    assert refusal.classify_refusal_prefix("  AS AN AI, I cannot do that") == "full_refusal"


def test_xstest_subsets_have_stable_ids_and_expected_behavior(monkeypatch) -> None:
    records = [
        {"id": "1", "prompt": "safe prompt", "type": "safe_contexts", "label": "safe"},
        {
            "id": "2",
            "prompt": "unsafe contrast",
            "type": "contrast_safe_contexts",
            "label": "unsafe",
        },
    ]
    monkeypatch.setattr(refusal, "_load_verified_csv", lambda **kwargs: records)
    monkeypatch.setattr(refusal, "get_sample_count", lambda benchmark, tier: 10)

    safe = refusal.load_xstest(subset="safe")
    unsafe = refusal.load_xstest(subset="unsafe")

    assert [sample.id for sample in safe] == ["xstest-1"]
    assert [sample.id for sample in unsafe] == ["xstest-2"]
    assert safe[0].target == "comply"
    assert unsafe[0].target == "refuse"
    assert safe[0].metadata["dataset_revision"] == refusal.XSTEST_REVISION


def test_or_bench_and_strongreject_ids_do_not_use_python_hash(monkeypatch) -> None:
    monkeypatch.setattr(refusal, "get_sample_count", lambda benchmark, tier: 10)
    monkeypatch.setattr(
        refusal,
        "_load_verified_csv",
        lambda **kwargs: (
            [{"prompt": "benign difficult prompt", "category": "privacy"}]
            if kwargs["benchmark"] == "or_bench_hard"
            else [
                {
                    "forbidden_prompt": "harmful evaluation prompt",
                    "category": "Non-violent crimes",
                    "source": "test",
                }
            ]
        ),
    )

    or_sample = refusal.load_or_bench_hard()[0]
    strong_sample = refusal.load_strongreject()[0]

    assert or_sample.id == "orbench-" + hashlib.sha256(b"benign difficult prompt").hexdigest()[:20]
    assert (
        strong_sample.id
        == "strongreject-" + hashlib.sha256(b"harmful evaluation prompt").hexdigest()[:20]
    )
    assert or_sample.target == "comply"
    assert strong_sample.target == "refuse"


def test_verified_csv_rejects_checksum_mismatch(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "data.csv"
    path.write_text("prompt,category\nhello,test\n", encoding="utf-8")
    monkeypatch.setattr(refusal, "get_dataset_path", lambda benchmark: str(path))

    with pytest.raises(ValueError, match="checksum mismatch"):
        refusal._load_verified_csv(
            benchmark="test",
            filename="data.csv",
            url="https://invalid.example/data.csv",
            expected_sha256="0" * 64,
        )


def test_registry_metadata_discloses_diagnostic_only_scoring() -> None:
    metadata = refusal.strongreject._benchmark_metadata

    assert metadata.dataset_revision == refusal.STRONGREJECT_REVISION
    assert metadata.total_samples == 313
    assert metadata.status.value == "experimental"
    assert "external_dual_judge" in metadata.scoring_type


def test_refusal_tier_count_falls_back_for_new_benchmarks(monkeypatch) -> None:
    monkeypatch.setattr(refusal, "get_sample_count", lambda benchmark, tier: 0)

    assert refusal._tier_count("strongreject", "smoke", 313) == 5
    assert refusal._tier_count("strongreject", "quick", 313) == 50
    assert refusal._tier_count("strongreject", "full", 313) == 313
