"""
Tests for pass@k scoring utilities (matric_eval.scorers.pass_k).

Covers:
- pass_at_k against known Chen et al. 2021 values
- Edge cases: perfect score (n=c), zero correct (c=0)
- k=1 vs k=10 comparison
- pass_power_k all True, one False
- aggregate_pass_k_results with mixed results
"""

import math
import pytest

from matric_eval.scorers.pass_k import (
    aggregate_pass_k_results,
    pass_at_k,
    pass_power_k,
)


# =============================================================================
# pass_at_k Tests
# =============================================================================


@pytest.mark.unit
class TestPassAtK:
    """Tests for pass_at_k() unbiased estimator from Chen et al. 2021."""

    def test_pass_at_1_with_half_correct(self) -> None:
        """pass@1 with n=10, c=5 should equal 0.5."""
        result = pass_at_k(n=10, c=5, k=1)
        assert abs(result - 0.5) < 1e-9

    def test_pass_at_k_known_value_n10_c5_k10(self) -> None:
        """pass@10 with n=10, c=5 should be 1 - C(5,10)/C(10,10) = 1 - 5/10... verify formula."""
        # Using unbiased estimator: 1 - C(n-c, k) / C(n, k)
        # 1 - C(5, 10) / C(10, 10)
        # C(5, 10) = 0 since k=10 > n-c=5
        # So pass@10 = 1.0 when n=10, c=5, k=10
        result = pass_at_k(n=10, c=5, k=10)
        assert abs(result - 1.0) < 1e-9

    def test_pass_at_1_all_correct(self) -> None:
        """Perfect score: n=c should yield 1.0 for any k <= n."""
        result = pass_at_k(n=10, c=10, k=1)
        assert abs(result - 1.0) < 1e-9

    def test_pass_at_k_all_correct_larger_k(self) -> None:
        """Perfect score: n=c, k=5 should still yield 1.0."""
        result = pass_at_k(n=10, c=10, k=5)
        assert abs(result - 1.0) < 1e-9

    def test_pass_at_k_none_correct(self) -> None:
        """Zero correct: c=0 should yield 0.0 for any k."""
        result = pass_at_k(n=10, c=0, k=1)
        assert abs(result - 0.0) < 1e-9

    def test_pass_at_k_none_correct_k5(self) -> None:
        """Zero correct: c=0, k=5 should yield 0.0."""
        result = pass_at_k(n=10, c=0, k=5)
        assert abs(result - 0.0) < 1e-9

    def test_pass_at_1_vs_pass_at_10(self) -> None:
        """pass@10 should be >= pass@1 for same n, c."""
        p1 = pass_at_k(n=10, c=3, k=1)
        p10 = pass_at_k(n=10, c=3, k=10)
        assert p10 >= p1

    def test_pass_at_k_monotone_in_c(self) -> None:
        """More correct samples → higher pass@k."""
        p_low = pass_at_k(n=10, c=2, k=3)
        p_high = pass_at_k(n=10, c=8, k=3)
        assert p_high > p_low

    def test_pass_at_k_result_in_range(self) -> None:
        """Result should always be in [0.0, 1.0]."""
        for c in range(0, 11):
            result = pass_at_k(n=10, c=c, k=3)
            assert 0.0 <= result <= 1.0, f"Out of range for c={c}: {result}"

    def test_pass_at_k_n1_c1_k1(self) -> None:
        """Minimal case: n=1, c=1, k=1 → 1.0."""
        result = pass_at_k(n=1, c=1, k=1)
        assert abs(result - 1.0) < 1e-9

    def test_pass_at_k_n1_c0_k1(self) -> None:
        """Minimal fail case: n=1, c=0, k=1 → 0.0."""
        result = pass_at_k(n=1, c=0, k=1)
        assert abs(result - 0.0) < 1e-9

    def test_pass_at_k_formula_verification(self) -> None:
        """Verify formula matches manual calculation for n=4, c=2, k=2."""
        # 1 - C(n-c, k) / C(n, k)
        # 1 - C(2, 2) / C(4, 2)
        # 1 - 1 / 6 = 5/6
        expected = 1.0 - (math.comb(2, 2) / math.comb(4, 2))
        result = pass_at_k(n=4, c=2, k=2)
        assert abs(result - expected) < 1e-9

    def test_pass_at_k_returns_float(self) -> None:
        """Return type should be float."""
        result = pass_at_k(n=10, c=5, k=3)
        assert isinstance(result, float)

    def test_pass_at_k_large_n(self) -> None:
        """Should handle large n values without overflow."""
        result = pass_at_k(n=200, c=100, k=1)
        assert 0.0 <= result <= 1.0


# =============================================================================
# pass_power_k Tests
# =============================================================================


@pytest.mark.unit
class TestPassPowerK:
    """Tests for pass_power_k() — all-or-nothing k-run scoring."""

    def test_all_pass(self) -> None:
        """All True → 1.0."""
        result = pass_power_k([True, True, True])
        assert abs(result - 1.0) < 1e-9

    def test_one_fail(self) -> None:
        """One False → 0.0."""
        result = pass_power_k([True, True, False])
        assert abs(result - 0.0) < 1e-9

    def test_all_fail(self) -> None:
        """All False → 0.0."""
        result = pass_power_k([False, False, False])
        assert abs(result - 0.0) < 1e-9

    def test_single_pass(self) -> None:
        """Single True → 1.0."""
        result = pass_power_k([True])
        assert abs(result - 1.0) < 1e-9

    def test_single_fail(self) -> None:
        """Single False → 0.0."""
        result = pass_power_k([False])
        assert abs(result - 0.0) < 1e-9

    def test_empty_list(self) -> None:
        """Empty results → 1.0 (vacuously true)."""
        result = pass_power_k([])
        assert abs(result - 1.0) < 1e-9

    def test_returns_float(self) -> None:
        """Return type should be float."""
        result = pass_power_k([True, True])
        assert isinstance(result, float)

    def test_first_false_fails(self) -> None:
        """First element False → 0.0 regardless of rest."""
        result = pass_power_k([False, True, True, True])
        assert abs(result - 0.0) < 1e-9


# =============================================================================
# aggregate_pass_k_results Tests
# =============================================================================


@pytest.mark.unit
class TestAggregatePassKResults:
    """Tests for aggregate_pass_k_results() function."""

    def test_all_pass_returns_1(self) -> None:
        """All samples all-correct → pass_at_k near 1.0."""
        all_results = [
            [True, True, True],
            [True, True, True],
        ]
        agg = aggregate_pass_k_results(all_results, k=3)
        assert abs(agg["pass_at_k"] - 1.0) < 1e-6

    def test_none_pass_returns_0(self) -> None:
        """All samples all-fail → pass_at_k = 0.0."""
        all_results = [
            [False, False, False],
            [False, False, False],
        ]
        agg = aggregate_pass_k_results(all_results, k=3)
        assert abs(agg["pass_at_k"] - 0.0) < 1e-6

    def test_returns_total_samples(self) -> None:
        """total_samples should equal len(all_results)."""
        all_results = [[True, False], [False, True], [True, True]]
        agg = aggregate_pass_k_results(all_results, k=2)
        assert agg["total_samples"] == 3

    def test_returns_total_correct(self) -> None:
        """total_correct should count samples with at least one correct."""
        all_results = [
            [True, False],   # at least one correct
            [False, False],  # no correct
            [True, True],    # all correct
        ]
        agg = aggregate_pass_k_results(all_results, k=2)
        # total_correct = count of samples that have ≥1 correct
        assert agg["total_correct"] == 2

    def test_result_keys_present(self) -> None:
        """Result dict must have pass_at_k, total_samples, total_correct keys."""
        agg = aggregate_pass_k_results([[True, False]], k=1)
        assert "pass_at_k" in agg
        assert "total_samples" in agg
        assert "total_correct" in agg

    def test_pass_at_k_in_range(self) -> None:
        """pass_at_k result should be in [0.0, 1.0]."""
        all_results = [[True, False, True], [False, False, True]]
        agg = aggregate_pass_k_results(all_results, k=3)
        assert 0.0 <= agg["pass_at_k"] <= 1.0

    def test_mixed_results(self) -> None:
        """Mixed results → pass_at_k between 0.0 and 1.0."""
        all_results = [
            [True, False, False],
            [False, False, False],
            [True, True, True],
        ]
        agg = aggregate_pass_k_results(all_results, k=3)
        assert 0.0 < agg["pass_at_k"] < 1.0

    def test_empty_results(self) -> None:
        """Empty all_results → total_samples=0, pass_at_k=0.0."""
        agg = aggregate_pass_k_results([], k=3)
        assert agg["total_samples"] == 0
        assert agg["pass_at_k"] == 0.0
