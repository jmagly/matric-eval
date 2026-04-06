"""
Pass@k scoring utilities for code generation benchmarks.

Implements the unbiased estimator from Chen et al. 2021:
"Evaluating Large Language Models Trained on Code"
https://arxiv.org/abs/2107.03374

pass@k = 1 - C(n-c, k) / C(n, k)

Where:
- n: total number of samples generated
- c: number of correct samples
- k: k value (samples to consider)
"""

import math
from typing import Union


def pass_at_k(n: int, c: int, k: int) -> float:
    """Compute pass@k metric using the unbiased estimator (Chen et al. 2021).

    Uses the numerically stable formula:
        pass@k = 1 - C(n-c, k) / C(n, k)

    which avoids overflow via Python's arbitrary-precision integers in
    math.comb, then converts to float at the final division.

    Args:
        n: total number of samples generated
        c: number of correct samples (0 <= c <= n)
        k: k value (1 <= k <= n)

    Returns:
        pass@k probability in [0.0, 1.0]

    Examples:
        >>> pass_at_k(10, 5, 1)
        0.5
        >>> pass_at_k(10, 10, 1)
        1.0
        >>> pass_at_k(10, 0, 1)
        0.0
    """
    if n == 0:
        return 0.0

    # When k > n-c, there are no ways to choose k non-correct samples,
    # so C(n-c, k) = 0, meaning pass@k = 1.0
    if k > n - c:
        return 1.0

    # Unbiased estimator: 1 - C(n-c, k) / C(n, k)
    # Use integer arithmetic from math.comb for precision, divide at end
    numerator = math.comb(n - c, k)
    denominator = math.comb(n, k)

    if denominator == 0:
        return 0.0

    return float(1.0 - numerator / denominator)


def pass_power_k(results: list[bool]) -> float:
    """Compute pass^k: all k independent runs must pass.

    This is the strict "all pass" criterion — a single failure disqualifies
    the sample. Useful for measuring reliability over k runs.

    Args:
        results: list of pass/fail booleans for k independent runs

    Returns:
        1.0 if ALL results are True (or list is empty), 0.0 otherwise

    Examples:
        >>> pass_power_k([True, True, True])
        1.0
        >>> pass_power_k([True, False, True])
        0.0
        >>> pass_power_k([])
        1.0
    """
    return 1.0 if all(results) else 0.0


def aggregate_pass_k_results(
    all_results: list[list[bool]], k: int
) -> dict[str, float]:
    """Aggregate pass@k results across multiple samples.

    For each sample, computes the number of correct runs (c) and uses
    the unbiased pass@k estimator. The final pass@k is the mean over
    all samples (expected value interpretation).

    Args:
        all_results: list of per-sample result lists. Each inner list
            contains pass/fail booleans for n runs of that sample.
        k: k value for pass@k computation

    Returns:
        dict with:
        - pass_at_k (float): mean pass@k across all samples
        - total_samples (int): number of samples evaluated
        - total_correct (int): number of samples with at least one correct run

    Examples:
        >>> agg = aggregate_pass_k_results([[True, False], [True, True]], k=2)
        >>> agg["total_samples"]
        2
    """
    if not all_results:
        return {
            "pass_at_k": 0.0,
            "total_samples": 0,
            "total_correct": 0,
        }

    total_samples = len(all_results)
    total_correct = sum(1 for sample_results in all_results if any(sample_results))

    # Compute pass@k for each sample and average
    per_sample_pass_k = []
    for sample_results in all_results:
        n = len(sample_results)
        c = sum(sample_results)
        effective_k = min(k, n)
        per_sample_pass_k.append(pass_at_k(n, c, effective_k))

    mean_pass_k = sum(per_sample_pass_k) / total_samples if total_samples > 0 else 0.0

    return {
        "pass_at_k": mean_pass_k,
        "total_samples": total_samples,
        "total_correct": total_correct,
    }
