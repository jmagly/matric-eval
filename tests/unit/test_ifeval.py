"""
Tests for IFEval (Instruction Following Evaluation) benchmark task.

Covers:
- Constraint checking functions for various instruction types
- Dataset loading from JSONL
- Tiered sampling (smoke/quick/full)
- Sample format conversion
- Task definition
- Custom constraint scorer
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from inspect_ai import Task
from inspect_ai.dataset import Sample

from matric_eval.tasks.ifeval import (
    check_constraint,
    format_ifeval_prompt,
    ifeval,
    load_ifeval,
    record_to_sample,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clean EVAL_* environment variables and reset settings singleton before each test."""
    # Clear environment variables
    monkeypatch.delenv("EVAL_IFEVAL_SAMPLES", raising=False)
    monkeypatch.delenv("EVAL_SEED", raising=False)

    # Reset the settings singleton so it re-reads from environment
    import matric_eval.config.settings as settings_module

    settings_module._settings = None


# =============================================================================
# Constraint Checking Tests - Length Constraints
# =============================================================================


@pytest.mark.unit
class TestConstraintCheckingLengthConstraints:
    """Tests for length_constraints:* constraint checkers."""

    def test_number_paragraphs_exact_match(self) -> None:
        """Should pass when response has exact number of paragraphs."""
        response = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        result = check_constraint(
            response, "length_constraints:number_paragraphs", {"num_paragraphs": 3}
        )
        assert result is True

    def test_number_paragraphs_too_few(self) -> None:
        """Should fail when response has too few paragraphs."""
        response = "Only one paragraph."
        result = check_constraint(
            response, "length_constraints:number_paragraphs", {"num_paragraphs": 3}
        )
        assert result is False

    def test_number_paragraphs_too_many(self) -> None:
        """Should fail when response has too many paragraphs."""
        response = "First.\n\nSecond.\n\nThird.\n\nFourth.\n\nFifth."
        result = check_constraint(
            response, "length_constraints:number_paragraphs", {"num_paragraphs": 3}
        )
        assert result is False

    def test_number_paragraphs_with_markdown_separator(self) -> None:
        """Should count paragraphs separated by markdown divider (***) correctly."""
        response = "First paragraph.\n***\nSecond paragraph."
        result = check_constraint(
            response, "length_constraints:number_paragraphs", {"num_paragraphs": 2}
        )
        assert result is True

    def test_number_words_at_least_relation(self) -> None:
        """Should pass when word count meets 'at least' requirement."""
        response = "This is a test response with exactly ten words here now."
        result = check_constraint(
            response,
            "length_constraints:number_words",
            {"relation": "at least", "num_words": 10},
        )
        assert result is True

    def test_number_words_at_least_fails_when_too_few(self) -> None:
        """Should fail when word count is below 'at least' requirement."""
        response = "Too few words."
        result = check_constraint(
            response,
            "length_constraints:number_words",
            {"relation": "at least", "num_words": 300},
        )
        assert result is False

    def test_number_words_less_than_relation(self) -> None:
        """Should pass when word count is below 'less than' limit."""
        response = "Short response."
        result = check_constraint(
            response,
            "length_constraints:number_words",
            {"relation": "less than", "num_words": 300},
        )
        assert result is True

    def test_number_words_less_than_fails_when_too_many(self) -> None:
        """Should fail when word count exceeds 'less than' limit."""
        response = " ".join(["word"] * 400)
        result = check_constraint(
            response,
            "length_constraints:number_words",
            {"relation": "less than", "num_words": 300},
        )
        assert result is False

    def test_number_sentences_exact_count(self) -> None:
        """Should pass when sentence count matches requirement."""
        response = "First sentence. Second sentence. Third sentence."
        result = check_constraint(
            response,
            "length_constraints:number_sentences",
            {"relation": "at least", "num_sentences": 3},
        )
        assert result is True

    def test_number_sentences_handles_multiple_punctuation(self) -> None:
        """Should count sentences ending with ., !, ?."""
        response = "Statement. Question? Exclamation!"
        result = check_constraint(
            response,
            "length_constraints:number_sentences",
            {"relation": "at least", "num_sentences": 3},
        )
        assert result is True


# =============================================================================
# Constraint Checking Tests - Keywords
# =============================================================================


@pytest.mark.unit
class TestConstraintCheckingKeywords:
    """Tests for keywords:* constraint checkers."""

    def test_keywords_existence_all_present(self) -> None:
        """Should pass when all required keywords are present."""
        response = "This text is correlated with experiencing great success."
        result = check_constraint(
            response, "keywords:existence", {"keywords": ["correlated", "experiencing"]}
        )
        assert result is True

    def test_keywords_existence_case_insensitive(self) -> None:
        """Should check keywords case-insensitively."""
        response = "This text is CORRELATED with EXPERIENCING great success."
        result = check_constraint(
            response, "keywords:existence", {"keywords": ["correlated", "experiencing"]}
        )
        assert result is True

    def test_keywords_existence_missing_one(self) -> None:
        """Should fail when any keyword is missing."""
        response = "This text is correlated with success."
        result = check_constraint(
            response, "keywords:existence", {"keywords": ["correlated", "experiencing"]}
        )
        assert result is False

    def test_keywords_frequency_minimum_occurrences(self) -> None:
        """Should pass when keyword appears minimum number of times."""
        response = "The ocean is vast. The ocean is blue. The ocean is deep."
        result = check_constraint(
            response,
            "keywords:frequency",
            {"keyword": "ocean", "relation": "at least", "frequency": 3},
        )
        assert result is True

    def test_keywords_frequency_below_minimum(self) -> None:
        """Should fail when keyword appears too few times."""
        response = "The ocean is vast."
        result = check_constraint(
            response,
            "keywords:frequency",
            {"keyword": "ocean", "relation": "at least", "frequency": 3},
        )
        assert result is False

    def test_keywords_letter_frequency_hashtags(self) -> None:
        """Should count letter/character frequency (e.g., hashtags)."""
        response = "Check out #coding #python #dev #tech"
        result = check_constraint(
            response,
            "keywords:letter_frequency",
            {"let_relation": "at least", "letter": "#", "let_frequency": 4},
        )
        assert result is True

    def test_keywords_forbidden_words_all_avoided(self) -> None:
        """Should pass when all forbidden words are absent."""
        response = "This is a perfectly clean response."
        result = check_constraint(
            response, "keywords:forbidden_words", {"forbidden_words": ["bad", "wrong"]}
        )
        assert result is True

    def test_keywords_forbidden_words_contains_forbidden(self) -> None:
        """Should fail when any forbidden word is present."""
        response = "This contains a bad word."
        result = check_constraint(
            response, "keywords:forbidden_words", {"forbidden_words": ["bad", "wrong"]}
        )
        assert result is False


# =============================================================================
# Constraint Checking Tests - Format
# =============================================================================


@pytest.mark.unit
class TestConstraintCheckingFormat:
    """Tests for detectable_format:* constraint checkers."""

    def test_json_format_valid_json(self) -> None:
        """Should pass for valid JSON response."""
        response = '{"key": "value", "number": 42}'
        result = check_constraint(response, "detectable_format:json_format", {})
        assert result is True

    def test_json_format_valid_json_array(self) -> None:
        """Should pass for valid JSON array."""
        response = '["item1", "item2", "item3"]'
        result = check_constraint(response, "detectable_format:json_format", {})
        assert result is True

    def test_json_format_invalid_json(self) -> None:
        """Should fail for invalid JSON."""
        response = "This is not JSON"
        result = check_constraint(response, "detectable_format:json_format", {})
        assert result is False

    def test_json_format_json_with_extra_text(self) -> None:
        """Should extract and validate JSON from response with extra text."""
        response = 'Here is the data: {"key": "value"}\nThat was the JSON.'
        result = check_constraint(response, "detectable_format:json_format", {})
        assert result is True

    def test_number_bullet_lists_exact_count(self) -> None:
        """Should pass when response has exact number of bullet points."""
        response = "* First point.\n* Second point.\n* Third point."
        result = check_constraint(
            response, "detectable_format:number_bullet_lists", {"num_bullets": 3}
        )
        assert result is True

    def test_number_bullet_lists_dash_bullets(self) -> None:
        """Should accept dash-style bullets."""
        response = "- First point.\n- Second point.\n- Third point."
        result = check_constraint(
            response, "detectable_format:number_bullet_lists", {"num_bullets": 3}
        )
        assert result is True

    def test_number_bullet_lists_wrong_count(self) -> None:
        """Should fail when bullet count doesn't match."""
        response = "* Only one point."
        result = check_constraint(
            response, "detectable_format:number_bullet_lists", {"num_bullets": 3}
        )
        assert result is False

    def test_title_with_double_angular_brackets(self) -> None:
        """Should pass when title wrapped in <<title>> is present."""
        response = "Email:\n<<Important Notice>>\nThis is the content."
        result = check_constraint(response, "detectable_format:title", {})
        assert result is True

    def test_title_missing(self) -> None:
        """Should fail when no title in <<>> format is present."""
        response = "Email content without a title."
        result = check_constraint(response, "detectable_format:title", {})
        assert result is False

    def test_number_highlighted_sections_markdown(self) -> None:
        """Should count *highlighted* sections in markdown."""
        response = "Text with *section 1*, *section 2*, and *section 3* highlighted."
        result = check_constraint(
            response,
            "detectable_format:number_highlighted_sections",
            {"num_highlights": 3},
        )
        assert result is True

    def test_number_highlighted_sections_too_few(self) -> None:
        """Should fail when not enough highlighted sections."""
        response = "Text with *section 1* highlighted."
        result = check_constraint(
            response,
            "detectable_format:number_highlighted_sections",
            {"num_highlights": 3},
        )
        assert result is False

    def test_multiple_sections_with_labels(self) -> None:
        """Should detect multiple sections with specific labels."""
        response = "PARAGRAPH 1\nContent here.\n\nPARAGRAPH 2\nMore content."
        result = check_constraint(
            response,
            "detectable_format:multiple_sections",
            {"section_spliter": "PARAGRAPH", "num_sections": 2},
        )
        assert result is True


# =============================================================================
# Constraint Checking Tests - Case Changes
# =============================================================================


@pytest.mark.unit
class TestConstraintCheckingCaseChanges:
    """Tests for change_case:* constraint checkers."""

    def test_english_lowercase_all_lowercase(self) -> None:
        """Should pass when all English letters are lowercase."""
        response = "this is all lowercase text with no capitals."
        result = check_constraint(response, "change_case:english_lowercase", {})
        assert result is True

    def test_english_lowercase_allows_numbers_punctuation(self) -> None:
        """Should allow numbers and punctuation in lowercase text."""
        response = "test 123, with punctuation!"
        result = check_constraint(response, "change_case:english_lowercase", {})
        assert result is True

    def test_english_lowercase_fails_with_capitals(self) -> None:
        """Should fail when any uppercase letter is present."""
        response = "This has One capital letter."
        result = check_constraint(response, "change_case:english_lowercase", {})
        assert result is False

    def test_english_capital_all_uppercase(self) -> None:
        """Should pass when all English letters are uppercase."""
        response = "THIS IS ALL UPPERCASE TEXT."
        result = check_constraint(response, "change_case:english_capital", {})
        assert result is True

    def test_english_capital_fails_with_lowercase(self) -> None:
        """Should fail when any lowercase letter is present."""
        response = "MOSTLY UPPERCASE but not all."
        result = check_constraint(response, "change_case:english_capital", {})
        assert result is False

    def test_capital_word_frequency_at_least(self) -> None:
        """Should pass when enough all-caps words are present."""
        response = "This has SOME words in ALL caps like THESE."
        result = check_constraint(
            response,
            "change_case:capital_word_frequency",
            {"capital_relation": "at least", "capital_frequency": 3},
        )
        assert result is True

    def test_capital_word_frequency_less_than(self) -> None:
        """Should pass when all-caps word count is below limit."""
        response = "This has ONE all-caps word: HELLO."
        result = check_constraint(
            response,
            "change_case:capital_word_frequency",
            {"capital_relation": "less than", "capital_frequency": 10},
        )
        assert result is True


# =============================================================================
# Constraint Checking Tests - Punctuation
# =============================================================================


@pytest.mark.unit
class TestConstraintCheckingPunctuation:
    """Tests for punctuation:* constraint checkers."""

    def test_no_comma_clean_text(self) -> None:
        """Should pass when no commas are present."""
        response = "This is text without any commas in it at all."
        result = check_constraint(response, "punctuation:no_comma", {})
        assert result is True

    def test_no_comma_fails_with_comma(self) -> None:
        """Should fail when any comma is present."""
        response = "This has a comma, right here."
        result = check_constraint(response, "punctuation:no_comma", {})
        assert result is False


# =============================================================================
# Constraint Checking Tests - Start/End
# =============================================================================


@pytest.mark.unit
class TestConstraintCheckingStartEnd:
    """Tests for startend:* constraint checkers."""

    def test_quotation_wrapped_in_double_quotes(self) -> None:
        """Should pass when entire response is wrapped in double quotes."""
        response = '"This entire response is quoted."'
        result = check_constraint(response, "startend:quotation", {})
        assert result is True

    def test_quotation_not_wrapped(self) -> None:
        """Should fail when response is not quoted."""
        response = "This response has no quotes."
        result = check_constraint(response, "startend:quotation", {})
        assert result is False

    def test_quotation_partial_quotes(self) -> None:
        """Should fail when quotes are partial or internal."""
        response = 'This has "internal quotes" but not wrapped.'
        result = check_constraint(response, "startend:quotation", {})
        assert result is False

    def test_end_checker_ends_with_phrase(self) -> None:
        """Should pass when response ends with specified phrase."""
        response = "This is a response.\n\nP.S. Check the appendix."
        result = check_constraint(response, "startend:end_checker", {"end_phrase": "P.S."})
        assert result is True

    def test_end_checker_missing_end_phrase(self) -> None:
        """Should fail when response doesn't end with phrase."""
        response = "This is a response without the ending."
        result = check_constraint(response, "startend:end_checker", {"end_phrase": "P.S."})
        assert result is False


# =============================================================================
# Constraint Checking Tests - Detectable Content
# =============================================================================


@pytest.mark.unit
class TestConstraintCheckingDetectableContent:
    """Tests for detectable_content:* constraint checkers."""

    def test_number_placeholders_sufficient_count(self) -> None:
        """Should pass when enough [placeholders] are present."""
        response = "Dear [name], your [address] is [city], [state] [zip]."
        result = check_constraint(
            response, "detectable_content:number_placeholders", {"num_placeholders": 5}
        )
        assert result is True

    def test_number_placeholders_too_few(self) -> None:
        """Should fail when not enough placeholders."""
        response = "Dear [name], welcome!"
        result = check_constraint(
            response, "detectable_content:number_placeholders", {"num_placeholders": 12}
        )
        assert result is False

    def test_postscript_present(self) -> None:
        """Should pass when P.S. or P.P.S. is present."""
        response = "Main content here.\n\nP.S. Don't forget this note."
        result = check_constraint(response, "detectable_content:postscript", {})
        assert result is True

    def test_postscript_pps_variant(self) -> None:
        """Should accept P.P.S. variant."""
        response = "Main content.\n\nP.P.S. Another postscript."
        result = check_constraint(response, "detectable_content:postscript", {})
        assert result is True

    def test_postscript_missing(self) -> None:
        """Should fail when no postscript is present."""
        response = "Main content without any postscript."
        result = check_constraint(response, "detectable_content:postscript", {})
        assert result is False


# =============================================================================
# Constraint Checking Tests - Combination
# =============================================================================


@pytest.mark.unit
class TestConstraintCheckingCombination:
    """Tests for combination:* constraint checkers."""

    def test_repeat_prompt_verbatim_repeat(self) -> None:
        """Should pass when prompt is repeated verbatim at start."""
        original_prompt = "Write an email to my boss."
        response = "Write an email to my boss.\n\nDear Boss, I am writing..."
        result = check_constraint(
            response, "combination:repeat_prompt", {"prompt_to_repeat": original_prompt}
        )
        assert result is True

    def test_repeat_prompt_missing(self) -> None:
        """Should fail when prompt is not repeated."""
        original_prompt = "Write an email to my boss."
        response = "Dear Boss, I am writing to inform you..."
        result = check_constraint(
            response, "combination:repeat_prompt", {"prompt_to_repeat": original_prompt}
        )
        assert result is False

    def test_two_responses_separated_correctly(self) -> None:
        """Should pass when two responses separated by 6 asterisks."""
        response = "First response here.\n******\nSecond response here."
        result = check_constraint(response, "combination:two_responses", {})
        assert result is True

    def test_two_responses_wrong_separator(self) -> None:
        """Should fail when separator is not exactly 6 asterisks."""
        response = "First response.\n***\nSecond response."
        result = check_constraint(response, "combination:two_responses", {})
        assert result is False


# =============================================================================
# Constraint Checking Tests - Language
# =============================================================================


@pytest.mark.unit
class TestConstraintCheckingLanguage:
    """Tests for language:* constraint checkers."""

    def test_response_language_detection_english(self) -> None:
        """Should detect English language correctly."""
        response = "This is a response in English."
        result = check_constraint(
            response, "language:response_language", {"language": "en"}
        )
        assert result is True

    def test_response_language_kannada_text(self) -> None:
        """Should detect Kannada language (example)."""
        response = "ಇದು ಕನ್ನಡ ಭಾಷೆಯಲ್ಲಿ ಪ್ರತಿಕ್ರಿಯೆ"
        result = check_constraint(
            response, "language:response_language", {"language": "kn"}
        )
        assert result is True

    def test_response_language_wrong_language(self) -> None:
        """Should fail when response is in wrong language."""
        response = "This is English text."
        result = check_constraint(
            response, "language:response_language", {"language": "kn"}
        )
        assert result is False


# =============================================================================
# Constraint Checking Tests - Unsupported/Unknown
# =============================================================================


@pytest.mark.unit
class TestConstraintCheckingUnsupported:
    """Tests for unknown/unsupported constraint types."""

    def test_unknown_constraint_returns_false(self) -> None:
        """Should return False for unknown constraint types."""
        response = "Any response."
        result = check_constraint(response, "unknown:constraint_type", {})
        assert result is False

    def test_empty_constraint_id_returns_false(self) -> None:
        """Should handle empty constraint ID gracefully."""
        response = "Any response."
        result = check_constraint(response, "", {})
        assert result is False


# =============================================================================
# Dataset Loading Tests
# =============================================================================


@pytest.mark.unit
class TestLoadIFEval:
    """Tests for load_ifeval() function."""

    def test_load_ifeval_smoke_returns_10_samples(self) -> None:
        """Should load exactly 10 samples for smoke tier."""
        samples = load_ifeval(tier="smoke")
        assert len(samples) == 10

    def test_load_ifeval_quick_returns_100_samples(self) -> None:
        """Should load exactly 100 samples for quick tier."""
        samples = load_ifeval(tier="quick")
        assert len(samples) == 100

    def test_load_ifeval_full_returns_all_samples(self) -> None:
        """Should load all 541 samples for full tier."""
        samples = load_ifeval(tier="full")
        assert len(samples) == 541

    def test_load_ifeval_default_is_smoke(self) -> None:
        """Should default to smoke tier if no tier specified."""
        samples = load_ifeval()
        assert len(samples) == 10

    def test_load_ifeval_unknown_tier_defaults_to_smoke(self) -> None:
        """Should fall back to smoke tier for unknown tier names."""
        samples = load_ifeval(tier="unknown_tier")
        assert len(samples) == 10

    def test_load_ifeval_samples_are_sample_objects(self) -> None:
        """Should return list of Sample objects."""
        samples = load_ifeval(tier="smoke")
        assert all(isinstance(s, Sample) for s in samples)

    def test_load_ifeval_samples_have_required_fields(self) -> None:
        """Should have input, target, id, and metadata fields."""
        samples = load_ifeval(tier="smoke")
        for sample in samples:
            assert sample.input is not None
            assert sample.target is not None  # Empty string is valid
            assert sample.id is not None
            assert sample.metadata is not None

    def test_load_ifeval_samples_have_unique_ids(self) -> None:
        """Should have unique IDs for all samples."""
        samples = load_ifeval(tier="full")
        ids = [s.id for s in samples]
        assert len(ids) == len(set(ids))

    def test_load_ifeval_reproducible_with_seed(self) -> None:
        """Should return same samples for same tier (reproducible sampling)."""
        samples1 = load_ifeval(tier="quick")
        samples2 = load_ifeval(tier="quick")

        ids1 = [s.id for s in samples1]
        ids2 = [s.id for s in samples2]

        assert ids1 == ids2

    def test_load_ifeval_smoke_subset_of_quick(self) -> None:
        """Smoke samples should be subset of quick samples (nested sampling)."""
        smoke_samples = load_ifeval(tier="smoke")
        quick_samples = load_ifeval(tier="quick")

        smoke_ids = {s.id for s in smoke_samples}
        quick_ids = {s.id for s in quick_samples}

        assert smoke_ids.issubset(quick_ids)

    def test_load_ifeval_quick_subset_of_full(self) -> None:
        """Quick samples should be subset of full samples."""
        quick_samples = load_ifeval(tier="quick")
        full_samples = load_ifeval(tier="full")

        quick_ids = {s.id for s in quick_samples}
        full_ids = {s.id for s in full_samples}

        assert quick_ids.issubset(full_ids)

    def test_load_ifeval_file_not_found_raises_error(self) -> None:
        """Should raise FileNotFoundError if dataset file missing."""
        with patch("matric_eval.tasks.ifeval.IFEVAL_PATH", "/nonexistent/path.jsonl"):
            with pytest.raises(FileNotFoundError):
                load_ifeval()

    def test_load_ifeval_invalid_json_raises_error(self) -> None:
        """Should raise error for malformed JSONL."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as f:
            f.write("invalid json line\n")
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.ifeval.IFEVAL_PATH", temp_path):
                with pytest.raises(json.JSONDecodeError):
                    load_ifeval()
        finally:
            Path(temp_path).unlink()


# =============================================================================
# Record Conversion Tests
# =============================================================================


@pytest.mark.unit
class TestRecordToSample:
    """Tests for record_to_sample() conversion function."""

    def test_record_to_sample_basic_conversion(self) -> None:
        """Should convert IFEval record to Sample."""
        record = {
            "key": 1234,
            "prompt": "Write exactly 3 paragraphs about cats.",
            "instruction_id_list": ["length_constraints:number_paragraphs"],
            "kwargs": [{"num_paragraphs": 3}],
        }

        sample = record_to_sample(record)

        assert isinstance(sample, Sample)
        assert sample.id == "1234"

    def test_record_to_sample_includes_prompt_in_input(self) -> None:
        """Should include the instruction prompt in input field."""
        record = {
            "key": 1234,
            "prompt": "Write exactly 3 paragraphs about cats.",
            "instruction_id_list": ["length_constraints:number_paragraphs"],
            "kwargs": [{"num_paragraphs": 3}],
        }

        sample = record_to_sample(record)

        assert "Write exactly 3 paragraphs" in sample.input
        assert "cats" in sample.input

    def test_record_to_sample_target_is_empty(self) -> None:
        """Should use empty string as target (no ground truth for instruction following)."""
        record = {
            "key": 1234,
            "prompt": "Write exactly 3 paragraphs about cats.",
            "instruction_id_list": ["length_constraints:number_paragraphs"],
            "kwargs": [{"num_paragraphs": 3}],
        }

        sample = record_to_sample(record)

        assert sample.target == ""

    def test_record_to_sample_includes_metadata(self) -> None:
        """Should include instruction_id_list and kwargs in metadata."""
        record = {
            "key": 1234,
            "prompt": "Write exactly 3 paragraphs about cats.",
            "instruction_id_list": ["length_constraints:number_paragraphs"],
            "kwargs": [{"num_paragraphs": 3}],
        }

        sample = record_to_sample(record)

        assert sample.metadata is not None
        assert "instruction_id_list" in sample.metadata
        assert "kwargs" in sample.metadata
        assert sample.metadata["instruction_id_list"] == [
            "length_constraints:number_paragraphs"
        ]
        assert sample.metadata["kwargs"] == [{"num_paragraphs": 3}]

    def test_record_to_sample_multiple_constraints(self) -> None:
        """Should preserve multiple constraints in metadata."""
        record = {
            "key": 1069,
            "prompt": "Write 500+ words. Include 'correlated' and 'experiencing'. No commas.",
            "instruction_id_list": [
                "keywords:existence",
                "length_constraints:number_words",
                "punctuation:no_comma",
            ],
            "kwargs": [
                {"keywords": ["correlated", "experiencing"]},
                {"relation": "at least", "num_words": 500},
                {},
            ],
        }

        sample = record_to_sample(record)

        assert len(sample.metadata["instruction_id_list"]) == 3
        assert len(sample.metadata["kwargs"]) == 3

    def test_record_to_sample_missing_required_field_raises_error(self) -> None:
        """Should raise KeyError if required field missing."""
        incomplete_record = {
            "key": 1234,
            "prompt": "Write something.",
            # Missing instruction_id_list and kwargs
        }

        with pytest.raises(KeyError):
            record_to_sample(incomplete_record)


# =============================================================================
# Prompt Formatting Tests
# =============================================================================


@pytest.mark.unit
class TestFormatIFEvalPrompt:
    """Tests for format_ifeval_prompt() function."""

    def test_format_ifeval_prompt_returns_unchanged_prompt(self) -> None:
        """Should return the prompt as-is (no special formatting needed)."""
        prompt = "Write exactly 3 paragraphs about cats."
        formatted = format_ifeval_prompt(prompt)
        assert formatted == prompt

    def test_format_ifeval_prompt_preserves_newlines(self) -> None:
        """Should preserve newlines in original prompt."""
        prompt = "Write an email.\n\nInclude a title in <<title>> format."
        formatted = format_ifeval_prompt(prompt)
        assert "\n\n" in formatted

    def test_format_ifeval_prompt_handles_unicode(self) -> None:
        """Should handle unicode characters."""
        prompt = "Write about π and include emoji 🎉"
        formatted = format_ifeval_prompt(prompt)
        assert "π" in formatted
        assert "🎉" in formatted


# =============================================================================
# Sample Content Quality Tests
# =============================================================================


@pytest.mark.unit
class TestIFEvalSampleQuality:
    """Tests for quality and correctness of loaded samples."""

    def test_samples_have_constraints_metadata(self) -> None:
        """Should have constraint metadata for all samples."""
        samples = load_ifeval(tier="smoke")
        for sample in samples:
            assert "instruction_id_list" in sample.metadata
            assert "kwargs" in sample.metadata
            assert len(sample.metadata["instruction_id_list"]) > 0

    def test_samples_have_matching_constraint_and_kwargs_lengths(self) -> None:
        """Instruction list and kwargs should have same length."""
        samples = load_ifeval(tier="smoke")
        for sample in samples:
            assert len(sample.metadata["instruction_id_list"]) == len(
                sample.metadata["kwargs"]
            )

    def test_samples_have_empty_targets(self) -> None:
        """IFEval samples should have empty targets (constraint-based scoring)."""
        samples = load_ifeval(tier="smoke")
        for sample in samples:
            assert sample.target == ""


# =============================================================================
# Task Definition Tests
# =============================================================================


@pytest.mark.unit
class TestIFEvalTask:
    """Tests for ifeval() task definition."""

    def test_ifeval_task_creation(self) -> None:
        """Should create valid Task object."""
        task = ifeval(tier="smoke")
        assert isinstance(task, Task)

    def test_ifeval_task_name(self) -> None:
        """Should have correct task name."""
        task = ifeval(tier="smoke")
        assert task.name == "ifeval"

    def test_ifeval_task_has_dataset(self) -> None:
        """Should have dataset configured."""
        task = ifeval(tier="smoke")
        assert task.dataset is not None
        assert len(task.dataset) == 10

    def test_ifeval_task_has_solver(self) -> None:
        """Should have solver configured."""
        task = ifeval(tier="smoke")
        assert task.solver is not None

    def test_ifeval_task_has_scorer(self) -> None:
        """Should have scorer configured."""
        task = ifeval(tier="smoke")
        assert task.scorer is not None

    def test_ifeval_task_respects_tier_parameter(self) -> None:
        """Should create tasks with different sample counts per tier."""
        smoke_task = ifeval(tier="smoke")
        quick_task = ifeval(tier="quick")
        full_task = ifeval(tier="full")

        assert len(smoke_task.dataset) == 10
        assert len(quick_task.dataset) == 100
        assert len(full_task.dataset) == 541

    def test_ifeval_task_default_tier_is_smoke(self) -> None:
        """Should default to smoke tier."""
        task = ifeval()
        assert len(task.dataset) == 10

    def test_ifeval_task_immutability(self) -> None:
        """Should create fresh task instances each call."""
        task1 = ifeval(tier="smoke")
        task2 = ifeval(tier="smoke")

        # Should be separate instances
        assert task1 is not task2


# =============================================================================
# Integration with Config System
# =============================================================================


@pytest.mark.unit
class TestIFEvalConfigIntegration:
    """Tests for integration with matric_eval.config."""

    def test_load_ifeval_uses_config_tier(self) -> None:
        """Should use TierConfig for sample counts."""
        from matric_eval.config import TIERS

        smoke_count = TIERS["smoke"].ifeval
        quick_count = TIERS["quick"].ifeval
        full_count = TIERS["full"].ifeval

        assert len(load_ifeval(tier="smoke")) == smoke_count
        assert len(load_ifeval(tier="quick")) == quick_count
        assert len(load_ifeval(tier="full")) == full_count

    def test_load_ifeval_respects_environment_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should respect EVAL_IFEVAL_SAMPLES environment variable."""
        monkeypatch.setenv("EVAL_IFEVAL_SAMPLES", "25")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module

        settings_module._settings = None

        # Should load 25 samples instead of default tier counts
        samples = load_ifeval(tier="smoke")
        assert len(samples) == 25

    def test_load_ifeval_uses_reproducible_seed(self) -> None:
        """Should use get_seed() for reproducible sampling."""
        from matric_eval.config import get_seed

        seed = get_seed()
        assert isinstance(seed, int)

        # Samples should be reproducible
        samples1 = load_ifeval(tier="quick")
        samples2 = load_ifeval(tier="quick")

        assert [s.id for s in samples1] == [s.id for s in samples2]


# =============================================================================
# Error Handling Tests
# =============================================================================


@pytest.mark.unit
class TestIFEvalErrorHandling:
    """Tests for error handling in dataset loading and constraint checking."""

    def test_load_ifeval_empty_file_raises_error(self) -> None:
        """Should raise error for empty JSONL file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as f:
            # Write nothing
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.ifeval.IFEVAL_PATH", temp_path):
                with pytest.raises((ValueError, IndexError)):
                    load_ifeval()
        finally:
            Path(temp_path).unlink()

    def test_load_ifeval_corrupted_jsonl_raises_error(self) -> None:
        """Should raise error for corrupted JSONL."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as f:
            f.write('{"key": 1234, "incomplete": \n')
            temp_path = f.name

        try:
            with patch("matric_eval.tasks.ifeval.IFEVAL_PATH", temp_path):
                with pytest.raises(json.JSONDecodeError):
                    load_ifeval()
        finally:
            Path(temp_path).unlink()

    def test_check_constraint_handles_empty_response(self) -> None:
        """Should handle empty response gracefully."""
        result = check_constraint("", "length_constraints:number_words", {"num_words": 10})
        assert result is False

    def test_check_constraint_handles_none_kwargs(self) -> None:
        """Should handle missing/None kwargs gracefully."""
        result = check_constraint("test", "punctuation:no_comma", {})
        assert result is True  # No commas in "test"


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.unit
class TestIFEvalEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_load_ifeval_sample_count_exceeds_dataset_size(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should return all available samples if requested count exceeds dataset size."""
        monkeypatch.setenv("EVAL_IFEVAL_SAMPLES", "10000")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module

        settings_module._settings = None

        samples = load_ifeval()
        # Should return all 541 samples, not 10000
        assert len(samples) == 541

    def test_load_ifeval_zero_samples_requested(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Should handle zero sample request gracefully."""
        monkeypatch.setenv("EVAL_IFEVAL_SAMPLES", "0")
        # Reset singleton to pick up new env var
        import matric_eval.config.settings as settings_module

        settings_module._settings = None

        samples = load_ifeval()
        assert len(samples) == 0

    def test_record_to_sample_with_unicode_characters(self) -> None:
        """Should handle unicode characters in prompts."""
        record = {
            "key": 9999,
            "prompt": "Write about π and include emoji 🎉",
            "instruction_id_list": ["keywords:existence"],
            "kwargs": [{"keywords": ["π"]}],
        }

        sample = record_to_sample(record)
        assert "π" in sample.input
        assert "🎉" in sample.input

    def test_check_constraint_with_very_long_response(self) -> None:
        """Should handle very long responses efficiently."""
        long_response = "word " * 10000
        result = check_constraint(
            long_response,
            "length_constraints:number_words",
            {"relation": "at least", "num_words": 5000},
        )
        assert result is True
