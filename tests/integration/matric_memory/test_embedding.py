"""
Embedding evaluation tests for matric-memory.

These tests validate the embedding test data ported from matric-memory
and can be extended to run actual evaluations against embedding models.

Test categories:
- Similarity pairs: Text pairs that should have high semantic similarity
- Dissimilarity pairs: Text pairs that should have low semantic similarity
- Retrieval queries: Queries with ranked documents for retrieval evaluation
"""

import json
from pathlib import Path

import pytest

# Path to test data
DATA_DIR = Path(__file__).parent / "data"
SIMILARITY_FILE = DATA_DIR / "similarity_pairs.json"
DISSIMILARITY_FILE = DATA_DIR / "dissimilarity_pairs.json"
RETRIEVAL_FILE = DATA_DIR / "retrieval_queries.json"


@pytest.fixture
def similarity_pairs():
    """Load similarity pairs from JSON."""
    with open(SIMILARITY_FILE) as f:
        return json.load(f)


@pytest.fixture
def dissimilarity_pairs():
    """Load dissimilarity pairs from JSON."""
    with open(DISSIMILARITY_FILE) as f:
        return json.load(f)


@pytest.fixture
def retrieval_queries():
    """Load retrieval queries from JSON."""
    with open(RETRIEVAL_FILE) as f:
        return json.load(f)


class TestSimilarityPairsData:
    """Tests for similarity pairs data integrity."""

    def test_file_exists(self):
        """Verify similarity pairs file exists."""
        assert SIMILARITY_FILE.exists(), f"Missing: {SIMILARITY_FILE}"

    def test_data_loads_correctly(self, similarity_pairs):
        """Verify data loads as valid JSON."""
        assert isinstance(similarity_pairs, list)
        assert len(similarity_pairs) > 0

    def test_pairs_have_required_fields(self, similarity_pairs):
        """Each pair must have id, text1, text2, expected_similarity."""
        required_fields = ["id", "text1", "text2", "expected_similarity"]

        for pair in similarity_pairs:
            for field in required_fields:
                assert field in pair, f"Missing '{field}' in pair {pair.get('id', 'unknown')}"

    def test_similarity_expectation_is_high(self, similarity_pairs):
        """Similarity pairs should expect high similarity."""
        for pair in similarity_pairs:
            assert pair["expected_similarity"] == "high", \
                f"Similarity pair {pair['id']} should expect 'high' similarity"

    def test_texts_are_non_empty(self, similarity_pairs):
        """Both texts must be non-empty."""
        for pair in similarity_pairs:
            assert len(pair["text1"]) > 10, f"text1 too short in pair {pair['id']}"
            assert len(pair["text2"]) > 10, f"text2 too short in pair {pair['id']}"

    def test_pair_ids_are_unique(self, similarity_pairs):
        """Pair IDs must be unique."""
        ids = [p["id"] for p in similarity_pairs]
        assert len(ids) == len(set(ids)), "Duplicate pair IDs found"

    def test_sufficient_sample_size(self, similarity_pairs):
        """Should have at least 20 similarity pairs for reliable evaluation."""
        assert len(similarity_pairs) >= 20, f"Only {len(similarity_pairs)} pairs, need at least 20"


class TestDissimilarityPairsData:
    """Tests for dissimilarity pairs data integrity."""

    def test_file_exists(self):
        """Verify dissimilarity pairs file exists."""
        assert DISSIMILARITY_FILE.exists(), f"Missing: {DISSIMILARITY_FILE}"

    def test_data_loads_correctly(self, dissimilarity_pairs):
        """Verify data loads as valid JSON."""
        assert isinstance(dissimilarity_pairs, list)
        assert len(dissimilarity_pairs) > 0

    def test_pairs_have_required_fields(self, dissimilarity_pairs):
        """Each pair must have id, text1, text2, expected_similarity."""
        required_fields = ["id", "text1", "text2", "expected_similarity"]

        for pair in dissimilarity_pairs:
            for field in required_fields:
                assert field in pair, f"Missing '{field}' in pair {pair.get('id', 'unknown')}"

    def test_dissimilarity_expectation_is_low(self, dissimilarity_pairs):
        """Dissimilarity pairs should expect low similarity."""
        for pair in dissimilarity_pairs:
            assert pair["expected_similarity"] == "low", \
                f"Dissimilarity pair {pair['id']} should expect 'low' similarity"

    def test_texts_are_semantically_different(self, dissimilarity_pairs):
        """Dissimilar texts should cover clearly different topics."""
        # Simple heuristic: check that texts don't share many words
        for pair in dissimilarity_pairs:
            words1 = set(pair["text1"].lower().split())
            words2 = set(pair["text2"].lower().split())
            overlap = words1 & words2
            # Exclude common words
            common_words = {"the", "a", "an", "is", "are", "and", "or", "to", "in", "for", "of", "with"}
            meaningful_overlap = overlap - common_words
            # Should have less than 30% overlap
            max_meaningful = max(len(words1 - common_words), len(words2 - common_words), 1)
            overlap_ratio = len(meaningful_overlap) / max_meaningful
            assert overlap_ratio < 0.3, f"Pair {pair['id']} has too much word overlap ({overlap_ratio:.0%})"

    def test_sufficient_sample_size(self, dissimilarity_pairs):
        """Should have at least 20 dissimilarity pairs for reliable evaluation."""
        assert len(dissimilarity_pairs) >= 20, f"Only {len(dissimilarity_pairs)} pairs, need at least 20"


class TestRetrievalQueriesData:
    """Tests for retrieval queries data integrity."""

    def test_file_exists(self):
        """Verify retrieval queries file exists."""
        assert RETRIEVAL_FILE.exists(), f"Missing: {RETRIEVAL_FILE}"

    def test_data_loads_correctly(self, retrieval_queries):
        """Verify data loads as valid JSON."""
        assert isinstance(retrieval_queries, list)
        assert len(retrieval_queries) > 0

    def test_queries_have_required_fields(self, retrieval_queries):
        """Each query must have id, query, documents."""
        required_fields = ["id", "query", "documents"]

        for query in retrieval_queries:
            for field in required_fields:
                assert field in query, f"Missing '{field}' in query {query.get('id', 'unknown')}"

    def test_documents_have_required_fields(self, retrieval_queries):
        """Each document must have id, content, relevance."""
        for query in retrieval_queries:
            for doc in query["documents"]:
                assert "id" in doc, f"Missing 'id' in document for query {query['id']}"
                assert "content" in doc, f"Missing 'content' in document for query {query['id']}"
                assert "relevance" in doc, f"Missing 'relevance' in document for query {query['id']}"

    def test_relevance_scores_are_valid(self, retrieval_queries):
        """Relevance scores should be 1, 2, or 3."""
        valid_relevance = {1, 2, 3}

        for query in retrieval_queries:
            for doc in query["documents"]:
                assert doc["relevance"] in valid_relevance, \
                    f"Invalid relevance {doc['relevance']} in query {query['id']}"

    def test_queries_have_multiple_documents(self, retrieval_queries):
        """Each query should have at least 2 documents for ranking."""
        for query in retrieval_queries:
            assert len(query["documents"]) >= 2, \
                f"Query {query['id']} needs at least 2 documents, has {len(query['documents'])}"

    def test_queries_have_relevant_and_irrelevant_docs(self, retrieval_queries):
        """Queries should have both relevant (3) and less relevant (1) documents."""
        for query in retrieval_queries:
            relevances = {doc["relevance"] for doc in query["documents"]}
            assert 3 in relevances, f"Query {query['id']} needs a highly relevant (3) document"
            assert 1 in relevances or 2 in relevances, \
                f"Query {query['id']} needs lower relevance documents for contrast"

    def test_sufficient_sample_size(self, retrieval_queries):
        """Should have at least 10 retrieval queries for reliable evaluation."""
        assert len(retrieval_queries) >= 10, f"Only {len(retrieval_queries)} queries, need at least 10"


class TestEmbeddingDatasetBalance:
    """Tests for overall embedding dataset balance."""

    def test_similar_count_matches_dissimilar(self, similarity_pairs, dissimilarity_pairs):
        """Similarity and dissimilarity pairs should be roughly balanced."""
        sim_count = len(similarity_pairs)
        dissim_count = len(dissimilarity_pairs)
        ratio = sim_count / dissim_count if dissim_count > 0 else 0

        # Should be within 50% of each other
        assert 0.5 <= ratio <= 2.0, \
            f"Unbalanced dataset: {sim_count} similar vs {dissim_count} dissimilar pairs"

    def test_coverage_of_technical_topics(self, similarity_pairs):
        """Dataset should cover various technical domains."""
        all_text = " ".join(p["text1"] + " " + p["text2"] for p in similarity_pairs).lower()

        # Check for coverage of key technical areas
        domains = {
            "programming": any(w in all_text for w in ["rust", "python", "typescript", "function", "code"]),
            "databases": any(w in all_text for w in ["database", "sql", "query", "index"]),
            "devops": any(w in all_text for w in ["docker", "kubernetes", "ci/cd", "deploy"]),
            "api": any(w in all_text for w in ["api", "rest", "graphql", "endpoint"]),
            "testing": any(w in all_text for w in ["test", "tdd", "unit test"]),
        }

        covered = sum(domains.values())
        assert covered >= 3, f"Only covers {covered}/5 technical domains: {domains}"
