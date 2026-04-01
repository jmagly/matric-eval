"""
Tests for MMLU (Massive Multitask Language Understanding) benchmark task (matric_eval.tasks.mmlu).

Covers:
- Dataset loading from CSV files
- Tiered sampling (smoke/quick/full)
- Sample format conversion
- Multiple choice prompt formatting
- Task definition
- Scorer configuration
"""

import csv
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.mmlu import (
    ANSWER_LETTERS,
    format_mmlu_prompt,
    format_subject_name,
    load_mmlu,
    load_mmlu_csv,
    mmlu,
    record_to_sample,
)

from tests.conftest import requires_mmlu_data


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clean EVAL_* environment variables and reset settings singleton before each test."""
    monkeypatch.delenv("EVAL_MMLU_SAMPLES", raising=False)
    monkeypatch.delenv("EVAL_SEED", raising=False)

    import matric_eval.config.settings as settings_module
    settings_module._settings = None


@pytest.fixture
def sample_mmlu_record() -> dict[str, Any]:
    """A single MMLU record for testing."""
    return {
        "question": "What is the capital of France?",
        "choices": ["London", "Berlin", "Paris", "Madrid"],
        "answer": "C",
        "subject": "world_history",
    }


@pytest.fixture
def sample_mmlu_records() -> list[dict[str, Any]]:
    """Multiple MMLU records for testing."""
    return [
        {
            "question": "What is 2 + 2?",
            "choices": ["3", "4", "5", "6"],
            "answer": "B",
            "subject": "elementary_mathematics",
        },
        {
            "question": "Which planet is closest to the sun?",
            "choices": ["Venus", "Mercury", "Earth", "Mars"],
            "answer": "B",
            "subject": "astronomy",
        },
        {
            "question": "What is the chemical symbol for gold?",
            "choices": ["Ag", "Au", "Fe", "Cu"],
            "answer": "B",
            "subject": "college_chemistry",
        },
    ]


@pytest.fixture
def temp_mmlu_dir(sample_mmlu_records: list[dict[str, Any]]) -> Path:
    """Create a temporary directory with MMLU-style CSV files."""
    with tempfile.TemporaryDirectory(prefix="mmlu_test_") as tmp_dir:
        test_dir = Path(tmp_dir)

        # Group records by subject
        subjects: dict[str, list[dict[str, Any]]] = {}
        for record in sample_mmlu_records:
            subj = record["subject"]
            subjects.setdefault(subj, []).append(record)

        # Write CSV files
        for subject, records in subjects.items():
            csv_path = test_dir / f"{subject}_test.csv"
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                for record in records:
                    writer.writerow([
                        record["question"],
                        *record["choices"],
                        record["answer"],
                    ])

        yield test_dir


@pytest.fixture
def temp_mmlu_dir_large() -> Path:
    """Create a temporary directory with enough MMLU-style samples for tier testing."""
    with tempfile.TemporaryDirectory(prefix="mmlu_large_test_") as tmp_dir:
        test_dir = Path(tmp_dir)

        # Create 20 questions across 2 subjects
        for subject in ["math", "science"]:
            csv_path = test_dir / f"{subject}_test.csv"
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                for i in range(10):
                    writer.writerow([
                        f"{subject.title()} question {i}?",
                        f"Choice A{i}",
                        f"Choice B{i}",
                        f"Choice C{i}",
                        f"Choice D{i}",
                        "A",
                    ])

        yield test_dir


# =============================================================================
# Subject Name Formatting Tests
# =============================================================================


@pytest.mark.unit
class TestFormatSubjectName:
    """Tests for format_subject_name() function."""

    def test_single_word(self) -> None:
        assert format_subject_name("anatomy") == "Anatomy"

    def test_multi_word(self) -> None:
        assert format_subject_name("abstract_algebra") == "Abstract Algebra"

    def test_three_words(self) -> None:
        assert format_subject_name("college_computer_science") == "College Computer Science"


# =============================================================================
# Prompt Formatting Tests
# =============================================================================


@pytest.mark.unit
class TestFormatMmluPrompt:
    """Tests for format_mmlu_prompt() function."""

    def test_basic_structure(self) -> None:
        """Should format question with choices in A/B/C/D format."""
        question = "What is the capital of France?"
        choices = ["London", "Berlin", "Paris", "Madrid"]

        prompt = format_mmlu_prompt(question, choices)

        assert "What is the capital of France?" in prompt
        assert "A) London" in prompt
        assert "B) Berlin" in prompt
        assert "C) Paris" in prompt
        assert "D) Madrid" in prompt

    def test_includes_answer_line(self) -> None:
        """Should include 'Answer:' prompt at the end."""
        prompt = format_mmlu_prompt("Test?", ["A", "B", "C", "D"])
        assert prompt.endswith("Answer:")

    def test_with_subject(self) -> None:
        """Should include subject name when provided."""
        prompt = format_mmlu_prompt(
            "Test?",
            ["A", "B", "C", "D"],
            subject="abstract_algebra",
        )
        assert "Subject: Abstract Algebra" in prompt

    def test_without_subject(self) -> None:
        """Should not include subject line when not provided."""
        prompt = format_mmlu_prompt("Test?", ["A", "B", "C", "D"])
        assert "Subject:" not in prompt

    def test_preserves_choice_order(self) -> None:
        """Should preserve the order of choices A, B, C, D."""
        choices = ["First", "Second", "Third", "Fourth"]
        prompt = format_mmlu_prompt("Order test?", choices)

        a_pos = prompt.index("A) First")
        b_pos = prompt.index("B) Second")
        c_pos = prompt.index("C) Third")
        d_pos = prompt.index("D) Fourth")

        assert a_pos < b_pos < c_pos < d_pos


# =============================================================================
# Record to Sample Conversion Tests
# =============================================================================


@pytest.mark.unit
class TestRecordToSample:
    """Tests for record_to_sample() function."""

    def test_basic_conversion(self, sample_mmlu_record: dict[str, Any]) -> None:
        """Should convert a record to a Sample with correct fields."""
        sample = record_to_sample(sample_mmlu_record, index=0)

        assert isinstance(sample, Sample)
        assert sample.id == "mmlu_0"
        assert sample.target == "C"
        assert "What is the capital of France?" in sample.input

    def test_index_in_id(self, sample_mmlu_record: dict[str, Any]) -> None:
        """Should use the global index in the sample ID."""
        sample = record_to_sample(sample_mmlu_record, index=42)
        assert sample.id == "mmlu_42"

    def test_metadata_preserved(self, sample_mmlu_record: dict[str, Any]) -> None:
        """Should preserve full record data in metadata."""
        sample = record_to_sample(sample_mmlu_record, index=0)

        assert sample.metadata["question"] == "What is the capital of France?"
        assert sample.metadata["choices"] == ["London", "Berlin", "Paris", "Madrid"]
        assert sample.metadata["answer"] == "C"
        assert sample.metadata["subject"] == "world_history"

    def test_missing_subject_defaults_to_unknown(self) -> None:
        """Should default subject to 'unknown' if not provided."""
        record = {
            "question": "Test?",
            "choices": ["A", "B", "C", "D"],
            "answer": "A",
        }
        sample = record_to_sample(record, index=0)
        assert sample.metadata["subject"] == "unknown"

    def test_prompt_includes_all_choices(self, sample_mmlu_record: dict[str, Any]) -> None:
        """Should include all answer choices in the prompt."""
        sample = record_to_sample(sample_mmlu_record, index=0)

        assert "London" in sample.input
        assert "Berlin" in sample.input
        assert "Paris" in sample.input
        assert "Madrid" in sample.input


# =============================================================================
# CSV Loading Tests
# =============================================================================


@pytest.mark.unit
class TestLoadMmluCsv:
    """Tests for load_mmlu_csv() function."""

    def test_loads_from_csv_files(self, temp_mmlu_dir: Path) -> None:
        """Should load records from all CSV files in the directory."""
        records = load_mmlu_csv(temp_mmlu_dir)
        assert len(records) == 3

    def test_extracts_subject_from_filename(self, temp_mmlu_dir: Path) -> None:
        """Should extract subject name from CSV filename."""
        records = load_mmlu_csv(temp_mmlu_dir)
        subjects = {r["subject"] for r in records}
        assert "elementary_mathematics" in subjects
        assert "astronomy" in subjects
        assert "college_chemistry" in subjects

    def test_parses_question_and_choices(self, temp_mmlu_dir: Path) -> None:
        """Should correctly parse question, choices, and answer from CSV."""
        records = load_mmlu_csv(temp_mmlu_dir)
        # Find the astronomy question
        astro = [r for r in records if r["subject"] == "astronomy"][0]
        assert astro["question"] == "Which planet is closest to the sun?"
        assert astro["choices"] == ["Venus", "Mercury", "Earth", "Mars"]
        assert astro["answer"] == "B"

    def test_nonexistent_directory_raises(self) -> None:
        """Should raise FileNotFoundError for missing directory."""
        with pytest.raises(FileNotFoundError):
            load_mmlu_csv("/nonexistent/path/to/mmlu")

    def test_empty_directory_raises(self) -> None:
        """Should raise ValueError when no CSV files found."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with pytest.raises(ValueError, match="No MMLU CSV files"):
                load_mmlu_csv(tmp_dir)

    def test_skips_malformed_rows(self) -> None:
        """Should skip rows with fewer than 6 columns."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "test_subject_test.csv"
            with open(csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Q1", "A", "B", "C", "D", "A"])  # Valid
                writer.writerow(["Q2", "A", "B"])  # Malformed
                writer.writerow(["Q3", "A", "B", "C", "D", "B"])  # Valid

            records = load_mmlu_csv(tmp_dir)
            assert len(records) == 2

    def test_sorted_file_order(self, temp_mmlu_dir: Path) -> None:
        """Should load files in alphabetical order."""
        records = load_mmlu_csv(temp_mmlu_dir)
        subjects = [r["subject"] for r in records]
        # astronomy < college_chemistry < elementary_mathematics (alphabetical)
        assert subjects[0] == "astronomy"


# =============================================================================
# Load MMLU (Tiered) Tests
# =============================================================================


@pytest.mark.unit
class TestLoadMmlu:
    """Tests for load_mmlu() function."""

    def test_zero_samples_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return empty list when sample count is 0."""
        monkeypatch.setenv("EVAL_MMLU_SAMPLES", "0")
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        result = load_mmlu(tier="smoke")
        assert result == []

    def test_smoke_tier_returns_limited_samples(
        self, temp_mmlu_dir_large: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should return only smoke tier count of samples."""
        with patch("matric_eval.tasks.mmlu.MMLU_TEST_PATH", str(temp_mmlu_dir_large)):
            samples = load_mmlu(tier="smoke")
            assert len(samples) == 5  # smoke tier = 5

    def test_samples_are_sorted_by_id(
        self, temp_mmlu_dir_large: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should return samples sorted by ID after sampling."""
        with patch("matric_eval.tasks.mmlu.MMLU_TEST_PATH", str(temp_mmlu_dir_large)):
            samples = load_mmlu(tier="smoke")
            ids = [s.id for s in samples]
            assert ids == sorted(ids)

    def test_reproducible_sampling(
        self, temp_mmlu_dir_large: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should produce identical results with same seed."""
        with patch("matric_eval.tasks.mmlu.MMLU_TEST_PATH", str(temp_mmlu_dir_large)):
            samples1 = load_mmlu(tier="smoke")
            # Reset settings to ensure same seed
            import matric_eval.config.settings as settings_module
            settings_module._settings = None
            samples2 = load_mmlu(tier="smoke")

            ids1 = [s.id for s in samples1]
            ids2 = [s.id for s in samples2]
            assert ids1 == ids2

    def test_full_tier_returns_all(
        self, temp_mmlu_dir_large: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should return all samples when tier count exceeds dataset size."""
        monkeypatch.setenv("EVAL_MMLU_SAMPLES", "999")
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        with patch("matric_eval.tasks.mmlu.MMLU_TEST_PATH", str(temp_mmlu_dir_large)):
            samples = load_mmlu(tier="full")
            assert len(samples) == 20  # All 20 samples

    def test_env_override_respected(
        self, temp_mmlu_dir_large: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should respect EVAL_MMLU_SAMPLES environment override."""
        monkeypatch.setenv("EVAL_MMLU_SAMPLES", "3")
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        with patch("matric_eval.tasks.mmlu.MMLU_TEST_PATH", str(temp_mmlu_dir_large)):
            samples = load_mmlu(tier="smoke")
            assert len(samples) == 3

    def test_all_samples_have_valid_targets(
        self, temp_mmlu_dir_large: Path
    ) -> None:
        """All samples should have A/B/C/D as target."""
        with patch("matric_eval.tasks.mmlu.MMLU_TEST_PATH", str(temp_mmlu_dir_large)):
            samples = load_mmlu(tier="smoke")
            for sample in samples:
                assert sample.target in ANSWER_LETTERS

    def test_all_samples_have_unique_ids(
        self, temp_mmlu_dir_large: Path
    ) -> None:
        """All samples should have unique IDs."""
        with patch("matric_eval.tasks.mmlu.MMLU_TEST_PATH", str(temp_mmlu_dir_large)):
            samples = load_mmlu(tier="smoke")
            ids = [s.id for s in samples]
            assert len(ids) == len(set(ids))


# =============================================================================
# Real Dataset Tests (require MMLU data on disk)
# =============================================================================


@pytest.mark.unit
@requires_mmlu_data
class TestLoadMmluRealData:
    """Tests that require the actual MMLU dataset on disk."""

    def test_smoke_tier_loads(self) -> None:
        """Should load smoke tier from real MMLU data."""
        samples = load_mmlu(tier="smoke")
        assert len(samples) == 5
        assert all(isinstance(s, Sample) for s in samples)

    def test_quick_tier_loads(self) -> None:
        """Should load quick tier from real MMLU data."""
        samples = load_mmlu(tier="quick")
        assert len(samples) == 75

    def test_samples_have_valid_metadata(self) -> None:
        """Real samples should have valid metadata fields."""
        samples = load_mmlu(tier="smoke")
        for sample in samples:
            assert "question" in sample.metadata
            assert "choices" in sample.metadata
            assert "answer" in sample.metadata
            assert "subject" in sample.metadata
            assert sample.metadata["answer"] in ANSWER_LETTERS
            assert len(sample.metadata["choices"]) == 4

    def test_multiple_subjects_represented(self) -> None:
        """Quick tier should include samples from multiple subjects."""
        samples = load_mmlu(tier="quick")
        subjects = {s.metadata["subject"] for s in samples}
        assert len(subjects) > 1


# =============================================================================
# Task Definition Tests
# =============================================================================


@pytest.mark.unit
class TestMmluTask:
    """Tests for the mmlu() task function."""

    def test_returns_task(self, temp_mmlu_dir_large: Path) -> None:
        """Should return an Inspect AI Task object."""
        with patch("matric_eval.tasks.mmlu.MMLU_TEST_PATH", str(temp_mmlu_dir_large)):
            task = mmlu(tier="smoke")
            assert isinstance(task, Task)

    def test_task_name(self, temp_mmlu_dir_large: Path) -> None:
        """Task should have the name 'mmlu'."""
        with patch("matric_eval.tasks.mmlu.MMLU_TEST_PATH", str(temp_mmlu_dir_large)):
            task = mmlu(tier="smoke")
            assert task.name == "mmlu"

    def test_task_has_dataset(self, temp_mmlu_dir_large: Path) -> None:
        """Task should have a non-empty dataset."""
        with patch("matric_eval.tasks.mmlu.MMLU_TEST_PATH", str(temp_mmlu_dir_large)):
            task = mmlu(tier="smoke")
            assert task.dataset is not None
            assert len(task.dataset) > 0

    def test_task_has_solver(self, temp_mmlu_dir_large: Path) -> None:
        """Task should have solver configured."""
        with patch("matric_eval.tasks.mmlu.MMLU_TEST_PATH", str(temp_mmlu_dir_large)):
            task = mmlu(tier="smoke")
            assert task.solver is not None

    def test_task_has_scorer(self, temp_mmlu_dir_large: Path) -> None:
        """Task should have a scorer configured."""
        with patch("matric_eval.tasks.mmlu.MMLU_TEST_PATH", str(temp_mmlu_dir_large)):
            task = mmlu(tier="smoke")
            assert task.scorer is not None


# =============================================================================
# Integration: Config Registration Tests
# =============================================================================


@pytest.mark.unit
class TestMmluConfig:
    """Tests that MMLU is properly registered in config."""

    def test_mmlu_in_tier_config(self) -> None:
        """TierConfig should have an mmlu field."""
        from matric_eval.config.settings import TierConfig
        config = TierConfig()
        assert hasattr(config, "mmlu")

    def test_smoke_tier_has_mmlu(self) -> None:
        """Smoke tier should have mmlu samples configured."""
        from matric_eval.config.settings import TIERS
        assert TIERS["smoke"].mmlu == 5

    def test_quick_tier_has_mmlu(self) -> None:
        """Quick tier should have mmlu samples configured."""
        from matric_eval.config.settings import TIERS
        assert TIERS["quick"].mmlu == 75

    def test_full_tier_has_mmlu(self) -> None:
        """Full tier should have mmlu samples configured."""
        from matric_eval.config.settings import TIERS
        assert TIERS["full"].mmlu == 14042

    def test_mmlu_in_task_map(self) -> None:
        """MMLU should be in EvaluationEngine.TASK_MAP."""
        from matric_eval.core.engine import EvaluationEngine
        assert "mmlu" in EvaluationEngine.TASK_MAP
        assert EvaluationEngine.TASK_MAP["mmlu"] == "matric_eval.tasks.mmlu.mmlu"

    def test_mmlu_in_available_benchmarks(self) -> None:
        """MMLU should be listed in available benchmarks."""
        from matric_eval.cli import get_available_benchmarks
        benchmarks = get_available_benchmarks()
        assert "mmlu" in benchmarks

    def test_mmlu_has_description(self) -> None:
        """MMLU should have a description in available benchmarks."""
        from matric_eval.cli import get_available_benchmarks
        benchmarks = get_available_benchmarks(with_descriptions=True)
        assert "mmlu" in benchmarks
        assert "MMLU" in benchmarks["mmlu"]
        assert "57 subjects" in benchmarks["mmlu"]

    def test_mmlu_samples_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should support EVAL_MMLU_SAMPLES environment override."""
        monkeypatch.setenv("EVAL_MMLU_SAMPLES", "42")
        import matric_eval.config.settings as settings_module
        settings_module._settings = None

        from matric_eval.config import get_sample_count
        assert get_sample_count("mmlu", "smoke") == 42


# =============================================================================
# Import Tests
# =============================================================================


@pytest.mark.unit
class TestMmluImports:
    """Tests that MMLU is importable from the tasks package."""

    def test_import_mmlu_task(self) -> None:
        from matric_eval.tasks import mmlu as mmlu_task
        assert callable(mmlu_task)

    def test_import_load_mmlu(self) -> None:
        from matric_eval.tasks import load_mmlu as load_fn
        assert callable(load_fn)

    def test_import_record_to_sample(self) -> None:
        from matric_eval.tasks import mmlu_record_to_sample
        assert callable(mmlu_record_to_sample)

    def test_import_format_prompt(self) -> None:
        from matric_eval.tasks import format_mmlu_prompt as fmt
        assert callable(fmt)
