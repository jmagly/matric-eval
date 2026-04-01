"""
Tests for external dataset auto-discovery (matric_eval.discovery).

Covers:
- Manifest parsing (full, partial, defaults)
- Dataset scanning (single, multiple, skip rules)
- Field auto-detection (all priority chains)
- Sample loading with field mapping
- Task factory (scorer resolution, tier sampling)
- Registry (lazy scan, cache, rescan)
- Engine integration (external task loading, builtin priority)
- CLI integration (external datasets in list)
"""

import json
import tempfile
from pathlib import Path
from typing import Any, Generator
from unittest.mock import patch

import pytest
import yaml
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.discovery import (
    DatasetManifest,
    DiscoveredDataset,
    TierSampling,
    create_external_task,
    detect_field_mapping,
    get_external_dataset,
    get_external_datasets,
    load_external_samples,
    load_manifest,
    reset_registry,
    scan_datasets_dir,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clean env vars and reset singletons."""
    monkeypatch.delenv("EVAL_DATASETS_DIR", raising=False)
    monkeypatch.delenv("EVAL_SEED", raising=False)

    import matric_eval.config.settings as settings_module
    settings_module._settings = None

    # Reset the discovery registry
    reset_registry()


@pytest.fixture
def tmp_datasets_dir() -> Generator[Path, None, None]:
    """Create a temporary datasets directory."""
    with tempfile.TemporaryDirectory(prefix="datasets_test_") as tmp_dir:
        yield Path(tmp_dir)


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Helper: write records as JSONL to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")


def _write_manifest(path: Path, data: dict[str, Any]) -> None:
    """Helper: write a dataset.yaml manifest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)


def _make_simple_dataset(
    datasets_dir: Path,
    name: str,
    records: list[dict[str, Any]] | None = None,
    manifest: dict[str, Any] | None = None,
    filename: str = "data.jsonl",
    subdir: str | None = None,
) -> Path:
    """Helper: create a dataset directory with JSONL and optional manifest."""
    ds_dir = datasets_dir / name
    ds_dir.mkdir(parents=True, exist_ok=True)

    if records is None:
        records = [
            {"input": f"Question {i}?", "target": f"Answer {i}", "id": f"q{i}"}
            for i in range(20)
        ]

    if subdir:
        _write_jsonl(ds_dir / subdir / filename, records)
    else:
        _write_jsonl(ds_dir / filename, records)

    if manifest:
        _write_manifest(ds_dir / "dataset.yaml", manifest)

    return ds_dir


# =============================================================================
# Manifest Tests
# =============================================================================


@pytest.mark.unit
class TestDatasetManifest:
    """Tests for DatasetManifest Pydantic model."""

    def test_defaults(self) -> None:
        """All fields should have sensible defaults."""
        m = DatasetManifest()
        assert m.name is None
        assert m.scorer == "match"
        assert m.tiers.smoke == 10
        assert m.tiers.quick == 50
        assert m.tiers.full == 0
        assert m.field_mapping == {"input": "input", "target": "target", "id": "id"}

    def test_full_manifest(self) -> None:
        """Should parse all fields when provided."""
        m = DatasetManifest(
            name="my-bench",
            description="Test benchmark",
            scorer="includes",
            system_prompt="Be precise.",
            field_mapping={"input": "question", "target": "answer", "id": "qid"},
            tiers=TierSampling(smoke=5, quick=25, full=100),
        )
        assert m.name == "my-bench"
        assert m.scorer == "includes"
        assert m.tiers.smoke == 5
        assert m.field_mapping["input"] == "question"

    def test_partial_manifest(self) -> None:
        """Missing fields should use defaults."""
        m = DatasetManifest(name="partial", scorer="pattern")
        assert m.name == "partial"
        assert m.scorer == "pattern"
        assert m.tiers.smoke == 10  # default
        assert m.system_prompt == "You are a helpful assistant. Answer concisely."


@pytest.mark.unit
class TestLoadManifest:
    """Tests for load_manifest() from YAML files."""

    def test_load_full_manifest(self, tmp_datasets_dir: Path) -> None:
        """Should load all fields from YAML."""
        manifest_data = {
            "name": "test-ds",
            "description": "A test dataset",
            "scorer": "includes",
            "tiers": {"smoke": 3, "quick": 30, "full": 0},
        }
        path = tmp_datasets_dir / "dataset.yaml"
        _write_manifest(path, manifest_data)

        m = load_manifest(path)
        assert m.name == "test-ds"
        assert m.scorer == "includes"
        assert m.tiers.smoke == 3

    def test_load_empty_yaml(self, tmp_datasets_dir: Path) -> None:
        """Empty YAML should produce default manifest."""
        path = tmp_datasets_dir / "dataset.yaml"
        path.write_text("")

        m = load_manifest(path)
        assert m.name is None
        assert m.scorer == "match"

    def test_load_minimal_yaml(self, tmp_datasets_dir: Path) -> None:
        """YAML with just name should use defaults for the rest."""
        path = tmp_datasets_dir / "dataset.yaml"
        _write_manifest(path, {"name": "minimal"})

        m = load_manifest(path)
        assert m.name == "minimal"
        assert m.tiers.smoke == 10


# =============================================================================
# Field Detection Tests
# =============================================================================


@pytest.mark.unit
class TestDetectFieldMapping:
    """Tests for detect_field_mapping() auto-detection."""

    def test_native_fields(self) -> None:
        """Should detect input/target/id fields."""
        record = {"input": "q", "target": "a", "id": "1"}
        mapping = detect_field_mapping(record)
        assert mapping == {"input": "input", "target": "target", "id": "id"}

    def test_prompt_expected_fields(self) -> None:
        """Should detect prompt/expected fields (custom format compat)."""
        record = {"prompt": "q", "expected": "a", "id": "1"}
        mapping = detect_field_mapping(record)
        assert mapping["input"] == "prompt"
        assert mapping["target"] == "expected"

    def test_question_answer_fields(self) -> None:
        """Should detect question/answer fields (academic format)."""
        record = {"question": "q", "answer": "a", "task_id": "1"}
        mapping = detect_field_mapping(record)
        assert mapping["input"] == "question"
        assert mapping["target"] == "answer"
        assert mapping["id"] == "task_id"

    def test_priority_order(self) -> None:
        """input should take priority over prompt."""
        record = {"input": "q1", "prompt": "q2", "target": "a"}
        mapping = detect_field_mapping(record)
        assert mapping["input"] == "input"

    def test_missing_id_field(self) -> None:
        """Should omit id mapping when no known id field found."""
        record = {"input": "q", "target": "a", "other": "x"}
        mapping = detect_field_mapping(record)
        assert "id" not in mapping

    def test_empty_record(self) -> None:
        """Should return empty mapping for empty record."""
        assert detect_field_mapping({}) == {}

    def test_no_input_field(self) -> None:
        """Should have no input mapping when no known field found."""
        record = {"data": "q", "label": "a"}
        mapping = detect_field_mapping(record)
        assert "input" not in mapping


# =============================================================================
# Sample Loading Tests
# =============================================================================


@pytest.mark.unit
class TestLoadExternalSamples:
    """Tests for load_external_samples() function."""

    def test_load_native_format(self, tmp_datasets_dir: Path) -> None:
        """Should load JSONL with input/target/id fields."""
        records = [
            {"input": "Q1?", "target": "A1", "id": "s1"},
            {"input": "Q2?", "target": "A2", "id": "s2"},
        ]
        path = tmp_datasets_dir / "test.jsonl"
        _write_jsonl(path, records)

        samples = load_external_samples(
            [path], {"input": "input", "target": "target", "id": "id"}, "test"
        )
        assert len(samples) == 2
        assert samples[0].input == "Q1?"
        assert samples[0].target == "A1"
        assert samples[0].id == "s1"

    def test_load_with_field_mapping(self, tmp_datasets_dir: Path) -> None:
        """Should apply field mapping when loading."""
        records = [{"question": "Q?", "answer": "A", "qid": "1"}]
        path = tmp_datasets_dir / "test.jsonl"
        _write_jsonl(path, records)

        samples = load_external_samples(
            [path], {"input": "question", "target": "answer", "id": "qid"}, "test"
        )
        assert samples[0].input == "Q?"
        assert samples[0].target == "A"
        assert samples[0].id == "1"

    def test_auto_generate_id(self, tmp_datasets_dir: Path) -> None:
        """Should auto-generate ID when id field not in mapping."""
        records = [{"input": "Q?", "target": "A"}]
        path = tmp_datasets_dir / "test.jsonl"
        _write_jsonl(path, records)

        samples = load_external_samples(
            [path], {"input": "input", "target": "target"}, "myds"
        )
        assert samples[0].id == "myds_0"

    def test_dict_target_serialized(self, tmp_datasets_dir: Path) -> None:
        """Should serialize dict targets to JSON string."""
        records = [{"input": "Q?", "target": {"tool": "read", "args": {}}, "id": "1"}]
        path = tmp_datasets_dir / "test.jsonl"
        _write_jsonl(path, records)

        samples = load_external_samples(
            [path], {"input": "input", "target": "target", "id": "id"}, "test"
        )
        assert samples[0].target == '{"tool": "read", "args": {}}'

    def test_extra_fields_in_metadata(self, tmp_datasets_dir: Path) -> None:
        """Should put non-mapped fields into metadata."""
        records = [{"input": "Q?", "target": "A", "id": "1", "difficulty": "hard", "category": "math"}]
        path = tmp_datasets_dir / "test.jsonl"
        _write_jsonl(path, records)

        samples = load_external_samples(
            [path], {"input": "input", "target": "target", "id": "id"}, "test"
        )
        assert samples[0].metadata["difficulty"] == "hard"
        assert samples[0].metadata["category"] == "math"

    def test_skips_malformed_json(self, tmp_datasets_dir: Path) -> None:
        """Should skip lines with invalid JSON."""
        path = tmp_datasets_dir / "test.jsonl"
        with open(path, "w") as f:
            f.write('{"input": "Q1?", "target": "A1", "id": "1"}\n')
            f.write("not valid json\n")
            f.write('{"input": "Q2?", "target": "A2", "id": "2"}\n')

        samples = load_external_samples(
            [path], {"input": "input", "target": "target", "id": "id"}, "test"
        )
        assert len(samples) == 2

    def test_skips_missing_input(self, tmp_datasets_dir: Path) -> None:
        """Should skip records missing the input field."""
        records = [
            {"input": "Q1?", "target": "A1", "id": "1"},
            {"target": "A2", "id": "2"},  # missing input
        ]
        path = tmp_datasets_dir / "test.jsonl"
        _write_jsonl(path, records)

        samples = load_external_samples(
            [path], {"input": "input", "target": "target", "id": "id"}, "test"
        )
        assert len(samples) == 1

    def test_multiple_files(self, tmp_datasets_dir: Path) -> None:
        """Should load and combine samples from multiple JSONL files."""
        path1 = tmp_datasets_dir / "a.jsonl"
        path2 = tmp_datasets_dir / "b.jsonl"
        _write_jsonl(path1, [{"input": "Q1?", "target": "A1", "id": "1"}])
        _write_jsonl(path2, [{"input": "Q2?", "target": "A2", "id": "2"}])

        samples = load_external_samples(
            [path1, path2], {"input": "input", "target": "target", "id": "id"}, "test"
        )
        assert len(samples) == 2


# =============================================================================
# Scanner Tests
# =============================================================================


@pytest.mark.unit
class TestScanDatasetsDir:
    """Tests for scan_datasets_dir() function."""

    def test_empty_dir(self, tmp_datasets_dir: Path) -> None:
        """Should return empty list for empty directory."""
        assert scan_datasets_dir(tmp_datasets_dir) == []

    def test_nonexistent_dir(self) -> None:
        """Should return empty list for nonexistent directory."""
        assert scan_datasets_dir(Path("/nonexistent/path")) == []

    def test_single_dataset_no_manifest(self, tmp_datasets_dir: Path) -> None:
        """Should auto-detect a dataset with no manifest."""
        _make_simple_dataset(tmp_datasets_dir, "my-bench")

        results = scan_datasets_dir(tmp_datasets_dir)
        assert len(results) == 1
        assert results[0].name == "my-bench"
        assert results[0].source_type == "auto-detected"
        assert results[0].total_samples == 20

    def test_single_dataset_with_manifest(self, tmp_datasets_dir: Path) -> None:
        """Should read manifest when present."""
        _make_simple_dataset(
            tmp_datasets_dir, "my-bench",
            manifest={"name": "My Benchmark", "scorer": "includes", "tiers": {"smoke": 3}},
        )

        results = scan_datasets_dir(tmp_datasets_dir)
        assert len(results) == 1
        assert results[0].source_type == "manifest"
        assert results[0].manifest.scorer == "includes"
        assert results[0].manifest.tiers.smoke == 3

    def test_multiple_datasets(self, tmp_datasets_dir: Path) -> None:
        """Should discover multiple datasets."""
        _make_simple_dataset(tmp_datasets_dir, "alpha")
        _make_simple_dataset(tmp_datasets_dir, "beta")

        results = scan_datasets_dir(tmp_datasets_dir)
        assert len(results) == 2
        names = [r.name for r in results]
        assert "alpha" in names
        assert "beta" in names

    def test_skips_custom_dir(self, tmp_datasets_dir: Path) -> None:
        """Should skip the reserved 'custom' directory."""
        _make_simple_dataset(tmp_datasets_dir, "custom")
        _make_simple_dataset(tmp_datasets_dir, "my-bench")

        results = scan_datasets_dir(tmp_datasets_dir)
        assert len(results) == 1
        assert results[0].name == "my-bench"

    def test_skips_public_dir(self, tmp_datasets_dir: Path) -> None:
        """Should skip the reserved 'public' directory."""
        _make_simple_dataset(tmp_datasets_dir, "public")
        _make_simple_dataset(tmp_datasets_dir, "my-bench")

        results = scan_datasets_dir(tmp_datasets_dir)
        assert len(results) == 1

    def test_skips_hidden_dirs(self, tmp_datasets_dir: Path) -> None:
        """Should skip directories starting with '.'."""
        _make_simple_dataset(tmp_datasets_dir, ".hidden")
        _make_simple_dataset(tmp_datasets_dir, "visible")

        results = scan_datasets_dir(tmp_datasets_dir)
        assert len(results) == 1
        assert results[0].name == "visible"

    def test_skips_underscore_dirs(self, tmp_datasets_dir: Path) -> None:
        """Should skip directories starting with '_'."""
        _make_simple_dataset(tmp_datasets_dir, "_internal")
        _make_simple_dataset(tmp_datasets_dir, "visible")

        results = scan_datasets_dir(tmp_datasets_dir)
        assert len(results) == 1

    def test_skips_empty_datasets(self, tmp_datasets_dir: Path) -> None:
        """Should skip directories with no JSONL files."""
        empty_dir = tmp_datasets_dir / "empty"
        empty_dir.mkdir()

        results = scan_datasets_dir(tmp_datasets_dir)
        assert len(results) == 0

    def test_skips_files_not_dirs(self, tmp_datasets_dir: Path) -> None:
        """Should skip files at the root level."""
        (tmp_datasets_dir / "readme.txt").write_text("hello")
        _make_simple_dataset(tmp_datasets_dir, "my-bench")

        results = scan_datasets_dir(tmp_datasets_dir)
        assert len(results) == 1

    def test_sorted_by_name(self, tmp_datasets_dir: Path) -> None:
        """Should return results sorted alphabetically by name."""
        _make_simple_dataset(tmp_datasets_dir, "charlie")
        _make_simple_dataset(tmp_datasets_dir, "alpha")
        _make_simple_dataset(tmp_datasets_dir, "bravo")

        results = scan_datasets_dir(tmp_datasets_dir)
        names = [r.name for r in results]
        assert names == ["alpha", "bravo", "charlie"]

    def test_discovers_jsonl_in_data_subdir(self, tmp_datasets_dir: Path) -> None:
        """Should find JSONL files in data/ subdirectory."""
        _make_simple_dataset(
            tmp_datasets_dir, "nested",
            subdir="data", filename="test.jsonl",
        )

        results = scan_datasets_dir(tmp_datasets_dir)
        assert len(results) == 1
        assert results[0].total_samples == 20

    def test_auto_detects_field_mapping(self, tmp_datasets_dir: Path) -> None:
        """Should auto-detect prompt/expected fields when no manifest."""
        records = [
            {"prompt": f"Q{i}", "expected": f"A{i}", "id": f"q{i}"}
            for i in range(5)
        ]
        _make_simple_dataset(tmp_datasets_dir, "custom-format", records=records)

        results = scan_datasets_dir(tmp_datasets_dir)
        assert len(results) == 1
        assert results[0].manifest.field_mapping["input"] == "prompt"
        assert results[0].manifest.field_mapping["target"] == "expected"


# =============================================================================
# Task Factory Tests
# =============================================================================


@pytest.mark.unit
class TestCreateExternalTask:
    """Tests for create_external_task() function."""

    def _make_discovered(
        self,
        tmp_datasets_dir: Path,
        name: str = "test-ds",
        records: list[dict[str, Any]] | None = None,
        manifest: DatasetManifest | None = None,
    ) -> DiscoveredDataset:
        """Helper to create a DiscoveredDataset."""
        if records is None:
            records = [
                {"input": f"Q{i}?", "target": f"A{i}", "id": f"q{i}"}
                for i in range(20)
            ]
        path = tmp_datasets_dir / f"{name}.jsonl"
        _write_jsonl(path, records)

        if manifest is None:
            manifest = DatasetManifest()

        return DiscoveredDataset(
            name=name,
            directory=tmp_datasets_dir,
            manifest=manifest,
            jsonl_files=[path],
            total_samples=len(records),
            source_type="auto-detected",
        )

    def test_returns_task(self, tmp_datasets_dir: Path) -> None:
        """Should return an Inspect AI Task."""
        ds = self._make_discovered(tmp_datasets_dir)
        task = create_external_task(ds, tier="smoke")
        assert isinstance(task, Task)

    def test_task_name(self, tmp_datasets_dir: Path) -> None:
        """Task should have the dataset name."""
        ds = self._make_discovered(tmp_datasets_dir, name="my-bench")
        task = create_external_task(ds, tier="smoke")
        assert task.name == "my-bench"

    def test_smoke_tier_sampling(self, tmp_datasets_dir: Path) -> None:
        """Smoke tier should limit samples to tier count."""
        ds = self._make_discovered(tmp_datasets_dir)
        task = create_external_task(ds, tier="smoke")
        assert len(task.dataset) == 10  # default smoke=10

    def test_full_tier_returns_all(self, tmp_datasets_dir: Path) -> None:
        """Full tier (0 = all) should return all samples."""
        ds = self._make_discovered(tmp_datasets_dir)
        task = create_external_task(ds, tier="full")
        assert len(task.dataset) == 20

    def test_custom_tier_counts(self, tmp_datasets_dir: Path) -> None:
        """Should respect manifest tier counts."""
        manifest = DatasetManifest(tiers=TierSampling(smoke=3, quick=7, full=0))
        ds = self._make_discovered(tmp_datasets_dir, manifest=manifest)

        task_smoke = create_external_task(ds, tier="smoke")
        assert len(task_smoke.dataset) == 3

        task_quick = create_external_task(ds, tier="quick")
        assert len(task_quick.dataset) == 7

    def test_scorer_from_manifest(self, tmp_datasets_dir: Path) -> None:
        """Should use scorer specified in manifest."""
        manifest = DatasetManifest(scorer="includes")
        ds = self._make_discovered(tmp_datasets_dir, manifest=manifest)
        task = create_external_task(ds, tier="smoke")
        assert task.scorer is not None

    def test_system_prompt_from_manifest(self, tmp_datasets_dir: Path) -> None:
        """Should use system prompt from manifest."""
        manifest = DatasetManifest(system_prompt="Be very precise.")
        ds = self._make_discovered(tmp_datasets_dir, manifest=manifest)
        task = create_external_task(ds, tier="smoke")
        assert task.solver is not None

    def test_reproducible_sampling(self, tmp_datasets_dir: Path) -> None:
        """Should produce identical results with same seed."""
        ds = self._make_discovered(tmp_datasets_dir)

        task1 = create_external_task(ds, tier="smoke")
        ids1 = [s.id for s in task1.dataset]

        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        task2 = create_external_task(ds, tier="smoke")
        ids2 = [s.id for s in task2.dataset]

        assert ids1 == ids2

    def test_unknown_scorer_falls_back_to_match(self, tmp_datasets_dir: Path) -> None:
        """Unknown scorer name should fall back to match()."""
        manifest = DatasetManifest(scorer="nonexistent_scorer")
        ds = self._make_discovered(tmp_datasets_dir, manifest=manifest)
        task = create_external_task(ds, tier="smoke")
        assert task.scorer is not None  # Should not raise


# =============================================================================
# Registry Tests
# =============================================================================


@pytest.mark.unit
class TestRegistry:
    """Tests for the discovery registry (lazy cache)."""

    def test_get_external_datasets_empty(self, tmp_datasets_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return empty dict when no external datasets."""
        monkeypatch.setenv("EVAL_DATASETS_DIR", str(tmp_datasets_dir))
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        result = get_external_datasets(force_rescan=True)
        assert result == {}

    def test_get_external_datasets_discovers(self, tmp_datasets_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should discover datasets in configured directory."""
        _make_simple_dataset(tmp_datasets_dir, "test-bench")
        monkeypatch.setenv("EVAL_DATASETS_DIR", str(tmp_datasets_dir))
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        result = get_external_datasets(force_rescan=True)
        assert "test-bench" in result

    def test_get_external_dataset_by_name(self, tmp_datasets_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should retrieve a single dataset by name."""
        _make_simple_dataset(tmp_datasets_dir, "my-ds")
        monkeypatch.setenv("EVAL_DATASETS_DIR", str(tmp_datasets_dir))
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        ds = get_external_dataset("my-ds")
        assert ds is not None
        assert ds.name == "my-ds"

    def test_get_external_dataset_not_found(self, tmp_datasets_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return None for unknown dataset."""
        monkeypatch.setenv("EVAL_DATASETS_DIR", str(tmp_datasets_dir))
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        assert get_external_dataset("nonexistent") is None

    def test_cache_is_used(self, tmp_datasets_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Second call should use cached results."""
        _make_simple_dataset(tmp_datasets_dir, "test-bench")
        monkeypatch.setenv("EVAL_DATASETS_DIR", str(tmp_datasets_dir))
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        result1 = get_external_datasets(force_rescan=True)
        # Add a new dataset — should NOT appear without rescan
        _make_simple_dataset(tmp_datasets_dir, "new-bench")
        result2 = get_external_datasets()  # no force_rescan

        assert "test-bench" in result2
        assert "new-bench" not in result2

    def test_force_rescan(self, tmp_datasets_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """force_rescan should re-scan the directory."""
        _make_simple_dataset(tmp_datasets_dir, "test-bench")
        monkeypatch.setenv("EVAL_DATASETS_DIR", str(tmp_datasets_dir))
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        get_external_datasets(force_rescan=True)
        _make_simple_dataset(tmp_datasets_dir, "new-bench")
        result = get_external_datasets(force_rescan=True)

        assert "new-bench" in result


# =============================================================================
# Engine Integration Tests
# =============================================================================


@pytest.mark.unit
class TestEngineIntegration:
    """Tests that EvaluationEngine can load external tasks."""

    def test_builtin_takes_priority(self) -> None:
        """Builtin benchmarks should always take priority."""
        from matric_eval.core.engine import EvaluationEngine
        assert "humaneval" in EvaluationEngine.TASK_MAP

    def test_load_external_task(self, tmp_datasets_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Engine should load external tasks not in TASK_MAP."""
        _make_simple_dataset(tmp_datasets_dir, "ext-bench")
        monkeypatch.setenv("EVAL_DATASETS_DIR", str(tmp_datasets_dir))
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        from matric_eval.core.engine import EvaluationEngine
        engine = EvaluationEngine(model="test/model", tier="smoke")
        task = engine._load_task("ext-bench")

        assert isinstance(task, Task)
        assert task.name == "ext-bench"

    def test_unknown_benchmark_raises(self, tmp_datasets_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should raise ValueError for unknown benchmark."""
        monkeypatch.setenv("EVAL_DATASETS_DIR", str(tmp_datasets_dir))
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        from matric_eval.core.engine import EvaluationEngine
        engine = EvaluationEngine(model="test/model", tier="smoke")

        with pytest.raises(ValueError, match="Unknown benchmark"):
            engine._load_task("nonexistent")


# =============================================================================
# CLI Integration Tests
# =============================================================================


@pytest.mark.unit
class TestCLIIntegration:
    """Tests that CLI includes external datasets."""

    def test_get_available_benchmarks_includes_external(
        self, tmp_datasets_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """External datasets should appear in available benchmarks."""
        _make_simple_dataset(
            tmp_datasets_dir, "ext-bench",
            manifest={"description": "My external benchmark"},
        )
        monkeypatch.setenv("EVAL_DATASETS_DIR", str(tmp_datasets_dir))
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        from matric_eval.cli import get_available_benchmarks
        benchmarks = get_available_benchmarks(with_descriptions=True)

        assert "ext-bench" in benchmarks
        assert "My external benchmark" in benchmarks["ext-bench"]

    def test_builtin_not_overridden(
        self, tmp_datasets_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """External dataset with builtin name should not override."""
        _make_simple_dataset(tmp_datasets_dir, "humaneval")
        monkeypatch.setenv("EVAL_DATASETS_DIR", str(tmp_datasets_dir))
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        from matric_eval.cli import get_available_benchmarks
        benchmarks = get_available_benchmarks(with_descriptions=True)

        # Should still have the builtin description
        assert "HumanEval" in benchmarks["humaneval"]

    def test_external_in_name_list(
        self, tmp_datasets_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """External datasets should appear in plain name list."""
        _make_simple_dataset(tmp_datasets_dir, "ext-bench")
        monkeypatch.setenv("EVAL_DATASETS_DIR", str(tmp_datasets_dir))
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        from matric_eval.cli import get_available_benchmarks
        names = get_available_benchmarks(with_descriptions=False)

        assert "ext-bench" in names


# =============================================================================
# Config Integration Tests
# =============================================================================


@pytest.mark.unit
class TestConfigIntegration:
    """Tests for datasets_dir configuration."""

    def test_default_datasets_dir(self) -> None:
        """Default datasets_dir should be 'datasets'."""
        from matric_eval.config import get_datasets_dir
        assert get_datasets_dir() == "datasets"

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should respect EVAL_DATASETS_DIR environment variable."""
        monkeypatch.setenv("EVAL_DATASETS_DIR", "/custom/path")
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        from matric_eval.config import get_datasets_dir
        assert get_datasets_dir() == "/custom/path"
