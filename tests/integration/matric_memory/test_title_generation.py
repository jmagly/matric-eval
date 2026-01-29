"""
Title generation evaluation tests for matric-memory.

These tests validate the title generation test data ported from matric-memory
and can be extended to run actual evaluations against LLM models.

Each test case contains:
- Content: A note or document to generate a title for
- Ideal titles: Examples of good, descriptive titles
- Bad titles: Examples of vague or non-descriptive titles
"""

import json
from pathlib import Path

import pytest

# Path to test data
DATA_DIR = Path(__file__).parent / "data"
TITLE_CASES_FILE = DATA_DIR / "title_cases.json"


@pytest.fixture
def title_cases():
    """Load title cases from JSON."""
    with open(TITLE_CASES_FILE) as f:
        return json.load(f)


class TestTitleCasesData:
    """Tests for title cases data integrity."""

    def test_file_exists(self):
        """Verify title cases file exists."""
        assert TITLE_CASES_FILE.exists(), f"Missing: {TITLE_CASES_FILE}"

    def test_data_loads_correctly(self, title_cases):
        """Verify data loads as valid JSON."""
        assert isinstance(title_cases, list)
        assert len(title_cases) > 0

    def test_cases_have_required_fields(self, title_cases):
        """Each case must have id, content, ideal_titles, bad_titles."""
        required_fields = ["id", "content", "ideal_titles", "bad_titles"]

        for case in title_cases:
            for field in required_fields:
                assert field in case, f"Missing '{field}' in case {case.get('id', 'unknown')}"

    def test_case_ids_are_unique(self, title_cases):
        """Case IDs must be unique."""
        ids = [c["id"] for c in title_cases]
        assert len(ids) == len(set(ids)), "Duplicate case IDs found"

    def test_content_is_substantial(self, title_cases):
        """Content should be substantial enough for title generation."""
        for case in title_cases:
            word_count = len(case["content"].split())
            assert word_count >= 30, \
                f"Case {case['id']} content too short ({word_count} words), need at least 30"

    def test_ideal_titles_are_non_empty(self, title_cases):
        """Each case should have at least 2 ideal titles."""
        for case in title_cases:
            assert isinstance(case["ideal_titles"], list)
            assert len(case["ideal_titles"]) >= 2, \
                f"Case {case['id']} needs at least 2 ideal titles"
            for title in case["ideal_titles"]:
                assert isinstance(title, str)
                assert len(title) > 5, f"Ideal title too short in case {case['id']}"

    def test_bad_titles_are_non_empty(self, title_cases):
        """Each case should have at least 2 bad titles."""
        for case in title_cases:
            assert isinstance(case["bad_titles"], list)
            assert len(case["bad_titles"]) >= 2, \
                f"Case {case['id']} needs at least 2 bad titles"
            for title in case["bad_titles"]:
                assert isinstance(title, str)
                assert len(title) > 0, f"Bad title is empty in case {case['id']}"


class TestTitleQualityDistinction:
    """Tests for quality distinction between ideal and bad titles."""

    def test_ideal_titles_are_descriptive(self, title_cases):
        """Ideal titles should contain specific, descriptive words."""
        for case in title_cases:
            for title in case["ideal_titles"]:
                word_count = len(title.split())
                # Good titles usually have 4-10 words
                assert word_count >= 3, \
                    f"Ideal title '{title}' in case {case['id']} is too short"
                # Ideal titles shouldn't be generic
                generic_phrases = ["notes", "misc", "stuff", "thing", "update"]
                is_generic = any(
                    g in title.lower() and len(title.split()) <= 3
                    for g in generic_phrases
                )
                assert not is_generic, \
                    f"Ideal title '{title}' in case {case['id']} seems generic"

    def test_bad_titles_are_vague(self, title_cases):
        """Bad titles should be clearly vague or non-descriptive."""
        # Generic/vague words that indicate a low-quality title
        vague_indicators = [
            # Meta words
            "notes", "misc", "stuff", "today", "my", "new", "update",
            "#", "untitled", "note", "meeting", "project", "issue",
            # Generic topic names without specificity
            "programming", "development", "technology", "learning", "memory",
            "security", "process", "workflow", "habits", "techniques",
            "skills", "practice", "system", "architecture", "design",
        ]

        for case in title_cases:
            for title in case["bad_titles"]:
                title_lower = title.lower()
                word_count = len(title.split())

                # Bad titles are usually short (<=3 words) or contain vague/generic words
                is_short = word_count <= 3
                has_vague_word = any(v in title_lower for v in vague_indicators)

                assert is_short or has_vague_word, \
                    f"Bad title '{title}' in case {case['id']} doesn't seem vague enough"

    def test_ideal_and_bad_titles_dont_overlap(self, title_cases):
        """Ideal and bad titles should not overlap."""
        for case in title_cases:
            ideal_set = set(t.lower() for t in case["ideal_titles"])
            bad_set = set(t.lower() for t in case["bad_titles"])
            overlap = ideal_set & bad_set
            assert len(overlap) == 0, \
                f"Case {case['id']} has overlapping titles: {overlap}"


class TestTitleCasesCoverage:
    """Tests for coverage of different content types."""

    def test_covers_technical_content(self, title_cases):
        """Dataset should cover technical/programming content."""
        technical_keywords = ["code", "api", "database", "rust", "typescript", "docker", "git"]

        technical_cases = 0
        for case in title_cases:
            content_lower = case["content"].lower()
            if any(kw in content_lower for kw in technical_keywords):
                technical_cases += 1

        assert technical_cases >= 5, \
            f"Only {technical_cases} technical cases, need at least 5"

    def test_covers_learning_content(self, title_cases):
        """Dataset should cover learning/knowledge content."""
        learning_keywords = ["learn", "memory", "spaced repetition", "cognitive", "study"]

        learning_cases = 0
        for case in title_cases:
            content_lower = case["content"].lower()
            if any(kw in content_lower for kw in learning_keywords):
                learning_cases += 1

        assert learning_cases >= 2, \
            f"Only {learning_cases} learning cases, need at least 2"

    def test_covers_productivity_content(self, title_cases):
        """Dataset should cover productivity/workflow content."""
        productivity_keywords = ["workflow", "journal", "deep work", "focus", "routine", "writing"]

        productivity_cases = 0
        for case in title_cases:
            content_lower = case["content"].lower()
            if any(kw in content_lower for kw in productivity_keywords):
                productivity_cases += 1

        assert productivity_cases >= 2, \
            f"Only {productivity_cases} productivity cases, need at least 2"

    def test_sufficient_sample_size(self, title_cases):
        """Should have at least 15 title cases for reliable evaluation."""
        assert len(title_cases) >= 15, \
            f"Only {len(title_cases)} cases, need at least 15"
