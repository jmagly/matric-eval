"""
Tests for LoCoMo (Long-term Conversational Memory) benchmark task (matric_eval.tasks.locomo).

Covers:
- Conversation formatting
- Sample conversion from QA records with conversation context
- Dataset loading with tiered sampling
- Category filtering
- Task definition
- Tier configuration
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.locomo import (
    VALID_CATEGORIES,
    format_conversation,
    load_locomo,
    locomo,
    record_to_sample,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clean EVAL_* environment variables and reset settings singleton."""
    monkeypatch.delenv("EVAL_LOCOMO_SAMPLES", raising=False)
    monkeypatch.delenv("EVAL_SEED", raising=False)

    import matric_eval.config.settings as settings_module
    settings_module._settings = None


@pytest.fixture
def sample_conversation() -> list[dict]:
    """Create a sample multi-session conversation."""
    return [
        {
            "session_id": 1,
            "turns": [
                {"speaker": "user", "text": "Hey, I just moved to Seattle last week."},
                {"speaker": "assistant", "text": "Welcome to Seattle! How are you finding it?"},
                {"speaker": "user", "text": "It rains a lot but I love the coffee scene."},
            ],
        },
        {
            "session_id": 2,
            "turns": [
                {"speaker": "user", "text": "I started my new job at Amazon today."},
                {"speaker": "assistant", "text": "Congratulations! What team are you on?"},
                {"speaker": "user", "text": "I'm on the AWS Lambda team."},
            ],
        },
        {
            "session_id": 3,
            "turns": [
                {"speaker": "user", "text": "My sister visited me this weekend from Portland."},
                {"speaker": "assistant", "text": "That sounds nice! Did you show her around?"},
                {"speaker": "user", "text": "Yes, we went to Pike Place Market."},
            ],
        },
    ]


@pytest.fixture
def sample_qa_records() -> list[dict]:
    """Create sample QA records for a conversation."""
    return [
        {
            "question": "Where did the user move to?",
            "answer": "Seattle",
            "category": "single-hop",
            "evidence": [{"session_id": 1, "turn_id": 1}],
        },
        {
            "question": "What team does the user work on at their new job?",
            "answer": "AWS Lambda",
            "category": "multi-hop",
            "evidence": [{"session_id": 2, "turn_id": 1}, {"session_id": 2, "turn_id": 3}],
        },
        {
            "question": "When did the user's sister visit relative to starting the new job?",
            "answer": "After starting the new job",
            "category": "temporal",
            "evidence": [{"session_id": 2, "turn_id": 1}, {"session_id": 3, "turn_id": 1}],
        },
        {
            "question": "What is the capital of France?",
            "answer": "Paris",
            "category": "open-domain",
            "evidence": [],
        },
        {
            "question": "Did the user say they hate coffee?",
            "answer": "No, the user said they love the coffee scene.",
            "category": "adversarial",
            "evidence": [{"session_id": 1, "turn_id": 3}],
        },
    ]


@pytest.fixture
def sample_locomo_data(sample_conversation, sample_qa_records) -> list[dict]:
    """Create a full LoCoMo dataset with multiple conversations."""
    return [
        {
            "sample_id": "conv_01",
            "conversation": sample_conversation,
            "qa": sample_qa_records,
        },
        {
            "sample_id": "conv_02",
            "conversation": [
                {
                    "session_id": 1,
                    "turns": [
                        {"speaker": "user", "text": "I adopted a cat named Whiskers."},
                        {"speaker": "assistant", "text": "How cute! What breed?"},
                        {"speaker": "user", "text": "A tabby."},
                    ],
                },
            ],
            "qa": [
                {
                    "question": "What is the cat's name?",
                    "answer": "Whiskers",
                    "category": "single-hop",
                    "evidence": [{"session_id": 1, "turn_id": 1}],
                },
            ],
        },
    ]


@pytest.fixture
def locomo_json_file(sample_locomo_data: list[dict], tmp_path: Path) -> Path:
    """Create a temporary LoCoMo JSON file."""
    locomo_dir = tmp_path / "locomo"
    locomo_dir.mkdir()
    json_file = locomo_dir / "locomo10.json"
    with open(json_file, "w") as f:
        json.dump(sample_locomo_data, f)
    return locomo_dir


# =============================================================================
# Conversation Formatting Tests
# =============================================================================


@pytest.mark.unit
class TestFormatConversation:
    """Tests for format_conversation() function."""

    def test_includes_session_headers(self, sample_conversation: list[dict]) -> None:
        """Should include session headers."""
        transcript = format_conversation(sample_conversation)
        assert "Session 1" in transcript
        assert "Session 2" in transcript
        assert "Session 3" in transcript

    def test_includes_speaker_labels(self, sample_conversation: list[dict]) -> None:
        """Should include speaker labels."""
        transcript = format_conversation(sample_conversation)
        assert "user:" in transcript
        assert "assistant:" in transcript

    def test_includes_turn_text(self, sample_conversation: list[dict]) -> None:
        """Should include turn text content."""
        transcript = format_conversation(sample_conversation)
        assert "moved to Seattle" in transcript
        assert "Pike Place Market" in transcript

    def test_truncates_long_conversations(self) -> None:
        """Should truncate very long conversations, keeping recent context."""
        long_conversation = [
            {
                "session_id": i,
                "turns": [
                    {"speaker": "user", "text": f"This is turn {j} of session {i}. " * 50}
                    for j in range(20)
                ],
            }
            for i in range(10)
        ]
        transcript = format_conversation(long_conversation, max_tokens=500)
        assert "[earlier conversation truncated]" in transcript

    def test_handles_empty_conversation(self) -> None:
        """Should handle empty conversation list."""
        transcript = format_conversation([])
        assert transcript == ""


# =============================================================================
# Record to Sample Tests
# =============================================================================


@pytest.mark.unit
class TestRecordToSample:
    """Tests for record_to_sample() function."""

    def test_converts_single_hop_qa(
        self, sample_conversation: list[dict], sample_qa_records: list[dict]
    ) -> None:
        """Should convert a single-hop QA record to Sample."""
        qa = sample_qa_records[0]
        sample = record_to_sample(qa, sample_conversation, "conv_01")
        assert isinstance(sample, Sample)
        assert "Where did the user move to?" in sample.input
        assert sample.target == "Seattle"

    def test_includes_conversation_context(
        self, sample_conversation: list[dict], sample_qa_records: list[dict]
    ) -> None:
        """Should include conversation context in the input."""
        qa = sample_qa_records[0]
        sample = record_to_sample(qa, sample_conversation, "conv_01")
        assert "Seattle" in sample.input
        assert "AWS Lambda" in sample.input

    def test_stores_category_in_metadata(
        self, sample_conversation: list[dict], sample_qa_records: list[dict]
    ) -> None:
        """Should store QA category in metadata."""
        qa = sample_qa_records[0]
        sample = record_to_sample(qa, sample_conversation, "conv_01")
        assert sample.metadata["category"] == "single-hop"

    def test_stores_evidence_in_metadata(
        self, sample_conversation: list[dict], sample_qa_records: list[dict]
    ) -> None:
        """Should store evidence references in metadata."""
        qa = sample_qa_records[1]  # multi-hop with 2 evidence refs
        sample = record_to_sample(qa, sample_conversation, "conv_01")
        assert len(sample.metadata["evidence"]) == 2
        assert sample.metadata["evidence"][0]["session_id"] == 2

    def test_stores_conversation_id(
        self, sample_conversation: list[dict], sample_qa_records: list[dict]
    ) -> None:
        """Should store conversation ID in metadata."""
        qa = sample_qa_records[0]
        sample = record_to_sample(qa, sample_conversation, "conv_01")
        assert sample.metadata["conversation_id"] == "conv_01"

    def test_generates_sample_id(
        self, sample_conversation: list[dict], sample_qa_records: list[dict]
    ) -> None:
        """Should generate a unique sample ID."""
        qa = sample_qa_records[0]
        sample = record_to_sample(qa, sample_conversation, "conv_01")
        assert sample.id is not None
        assert "conv_01" in sample.id
        assert "single-hop" in sample.id

    def test_includes_question_in_metadata(
        self, sample_conversation: list[dict], sample_qa_records: list[dict]
    ) -> None:
        """Should store question text in metadata."""
        qa = sample_qa_records[0]
        sample = record_to_sample(qa, sample_conversation, "conv_01")
        assert sample.metadata["question"] == "Where did the user move to?"


# =============================================================================
# Dataset Loading Tests
# =============================================================================


@pytest.mark.unit
class TestLoadLocomo:
    """Tests for load_locomo() function."""

    def test_loads_from_json(self, locomo_json_file: Path) -> None:
        """Should load samples from JSON file."""
        with patch("matric_eval.tasks.locomo.LOCOMO_PATH", str(locomo_json_file)):
            samples = load_locomo(tier="smoke")
            assert len(samples) == 6  # 5 QAs from conv_01 + 1 from conv_02
            assert all(isinstance(s, Sample) for s in samples)

    def test_raises_when_file_missing(self, tmp_path: Path) -> None:
        """Should raise FileNotFoundError when dataset missing."""
        with patch("matric_eval.tasks.locomo.LOCOMO_PATH", str(tmp_path / "nonexistent")):
            with pytest.raises(FileNotFoundError, match="LoCoMo dataset not found"):
                load_locomo(tier="smoke")

    def test_returns_empty_for_zero_samples(self, locomo_json_file: Path) -> None:
        """Should return empty list when tier has 0 samples."""
        with patch("matric_eval.tasks.locomo.LOCOMO_PATH", str(locomo_json_file)):
            with patch("matric_eval.tasks.locomo.get_sample_count", return_value=0):
                samples = load_locomo(tier="smoke")
                assert samples == []

    def test_reproducible_sampling(self, locomo_json_file: Path) -> None:
        """Should produce same samples with same seed."""
        with patch("matric_eval.tasks.locomo.LOCOMO_PATH", str(locomo_json_file)):
            with patch("matric_eval.tasks.locomo.get_sample_count", return_value=3):
                samples_1 = load_locomo(tier="smoke")
                samples_2 = load_locomo(tier="smoke")
                assert [s.id for s in samples_1] == [s.id for s in samples_2]

    def test_raises_on_empty_dataset(self, tmp_path: Path) -> None:
        """Should raise ValueError on empty dataset."""
        locomo_dir = tmp_path / "locomo"
        locomo_dir.mkdir()
        json_file = locomo_dir / "locomo10.json"
        json_file.write_text("[]")
        with patch("matric_eval.tasks.locomo.LOCOMO_PATH", str(locomo_dir)):
            with pytest.raises(ValueError, match="empty"):
                load_locomo(tier="smoke")


# =============================================================================
# Category Filtering Tests
# =============================================================================


@pytest.mark.unit
class TestCategoryFiltering:
    """Tests for category filtering in load_locomo()."""

    def test_filter_single_hop(self, locomo_json_file: Path) -> None:
        """Should filter to only single-hop questions."""
        with patch("matric_eval.tasks.locomo.LOCOMO_PATH", str(locomo_json_file)):
            samples = load_locomo(tier="smoke", categories=["single-hop"])
            assert len(samples) == 2  # 1 from conv_01 + 1 from conv_02
            assert all(s.metadata["category"] == "single-hop" for s in samples)

    def test_filter_multiple_categories(self, locomo_json_file: Path) -> None:
        """Should filter to multiple categories."""
        with patch("matric_eval.tasks.locomo.LOCOMO_PATH", str(locomo_json_file)):
            samples = load_locomo(tier="smoke", categories=["single-hop", "multi-hop"])
            assert len(samples) == 3  # 2 single-hop + 1 multi-hop
            categories = {s.metadata["category"] for s in samples}
            assert categories == {"single-hop", "multi-hop"}

    def test_no_filter_returns_all(self, locomo_json_file: Path) -> None:
        """Should return all categories when no filter specified."""
        with patch("matric_eval.tasks.locomo.LOCOMO_PATH", str(locomo_json_file)):
            samples = load_locomo(tier="smoke", categories=None)
            assert len(samples) == 6

    def test_invalid_category_raises(self, locomo_json_file: Path) -> None:
        """Should raise ValueError for invalid category."""
        with patch("matric_eval.tasks.locomo.LOCOMO_PATH", str(locomo_json_file)):
            with pytest.raises(ValueError, match="Invalid category"):
                load_locomo(tier="smoke", categories=["nonexistent"])

    def test_valid_categories_list(self) -> None:
        """Should have the expected valid categories."""
        assert "single-hop" in VALID_CATEGORIES
        assert "multi-hop" in VALID_CATEGORIES
        assert "temporal" in VALID_CATEGORIES
        assert "open-domain" in VALID_CATEGORIES
        assert "adversarial" in VALID_CATEGORIES


# =============================================================================
# Task Definition Tests
# =============================================================================


@pytest.mark.unit
class TestLocomoTask:
    """Tests for locomo() task definition."""

    def test_creates_task(self, locomo_json_file: Path) -> None:
        """Should create a valid Inspect AI Task."""
        with patch("matric_eval.tasks.locomo.LOCOMO_PATH", str(locomo_json_file)):
            task = locomo(tier="smoke")
            assert isinstance(task, Task)

    def test_task_has_scorer(self, locomo_json_file: Path) -> None:
        """Should include match scorer."""
        with patch("matric_eval.tasks.locomo.LOCOMO_PATH", str(locomo_json_file)):
            task = locomo(tier="smoke")
            assert task.scorer is not None

    def test_task_name(self, locomo_json_file: Path) -> None:
        """Should name task 'locomo'."""
        with patch("matric_eval.tasks.locomo.LOCOMO_PATH", str(locomo_json_file)):
            task = locomo(tier="smoke")
            assert task.name == "locomo"

    def test_task_with_categories(self, locomo_json_file: Path) -> None:
        """Should create task with category filter."""
        with patch("matric_eval.tasks.locomo.LOCOMO_PATH", str(locomo_json_file)):
            task = locomo(tier="smoke", categories=["single-hop"])
            assert isinstance(task, Task)


# =============================================================================
# Tier Configuration Tests
# =============================================================================


@pytest.mark.unit
class TestLocomoTierConfig:
    """Tests for LoCoMo tier configuration."""

    def test_smoke_tier_has_locomo(self) -> None:
        """Smoke tier should have LoCoMo samples configured."""
        from matric_eval.config import get_tier
        tier = get_tier("smoke")
        assert tier.locomo > 0

    def test_smoke_tier_value(self) -> None:
        """Smoke tier should have 10 LoCoMo samples."""
        from matric_eval.config import get_tier
        tier = get_tier("smoke")
        assert tier.locomo == 10

    def test_quick_tier_has_locomo(self) -> None:
        """Quick tier should have LoCoMo samples configured."""
        from matric_eval.config import get_tier
        tier = get_tier("quick")
        assert tier.locomo > 0

    def test_quick_tier_value(self) -> None:
        """Quick tier should have 50 LoCoMo samples."""
        from matric_eval.config import get_tier
        tier = get_tier("quick")
        assert tier.locomo == 50

    def test_full_tier_locomo(self) -> None:
        """Full tier should have 0 (all available) LoCoMo samples."""
        from matric_eval.config import get_tier
        tier = get_tier("full")
        assert tier.locomo == 0
