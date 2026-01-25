# ADR-004: Tiered Evaluation (Smoke/Quick/Full)

**Status**: Accepted
**Date**: 2026-01-24
**Decision Makers**: matric-eval development team
**Supersedes**: N/A

## Context

Model evaluation is time-consuming. Running all problems across all benchmarks can take hours per model. Different use cases have different time budgets:

| Use Case | Time Budget | Example |
|----------|-------------|---------|
| **Development feedback** | < 5 minutes | Developer testing prompt changes |
| **PR validation** | < 20 minutes | CI blocking merge |
| **Nightly evaluation** | 2+ hours | Comprehensive model ranking |
| **New model validation** | 10+ minutes | Testing newly downloaded model |

Running full evaluation for every use case wastes time and compute resources. We need a way to run appropriately-sized evaluations based on context.

Additionally, we want to minimize wasted effort on poorly-performing models. If a model fails basic tests, there's no point running comprehensive evaluation.

## Decision

**Implement three evaluation tiers with increasing sample sizes, plus capability-based filtering for custom tests.**

### Tier Definitions

| Tier | Samples per Benchmark | Total Problems* | Target Duration |
|------|----------------------|-----------------|-----------------|
| **smoke** | 5 | ~40 | < 2 minutes |
| **quick** | 75 | ~600 | < 20 minutes |
| **full** | all | ~5,000 | < 2 hours |

*Based on 8 benchmarks (HumanEval, MBPP, GSM8K, ARC, IFEval, LiveCodeBench, DS-1000, MTBench)

### Sampling Strategy

```python
import random

def sample_problems(
    problems: list[Problem],
    tier: Tier,
    seed: int,
) -> list[Problem]:
    """Sample problems based on tier with reproducible randomness."""

    samples = {
        Tier.SMOKE: 5,
        Tier.QUICK: 75,
        Tier.FULL: len(problems),  # All problems
    }

    n = min(samples[tier], len(problems))

    # Reproducible sampling
    rng = random.Random(seed)
    return rng.sample(problems, n)
```

### CLI Interface

```bash
# Smoke tier - fast feedback (development, debugging)
matric-eval --tier smoke --model llama3.2:3b

# Quick tier - PR validation (CI)
matric-eval --tier quick --model llama3.2:3b

# Full tier - comprehensive evaluation (nightly)
matric-eval --tier full

# Specific benchmarks
matric-eval --tier quick --benchmark humaneval,mbpp
```

### Tier Selection Guidelines

```
                    +-------------------+
                    |   Which tier?     |
                    +-------------------+
                            |
            +---------------+---------------+
            |               |               |
            v               v               v
     +-----------+   +-----------+   +-----------+
     |  smoke    |   |   quick   |   |   full    |
     |           |   |           |   |           |
     | - Local   |   | - CI/PR   |   | - Nightly |
     |   dev     |   |   checks  |   | - Release |
     | - Debug   |   | - New     |   | - Model   |
     | - Quick   |   |   model   |   |   ranking |
     |   test    |   |   test    |   |           |
     +-----------+   +-----------+   +-----------+
```

### Capability-Based Filtering

For custom tests, we filter to top-performing models from public benchmarks:

```
┌─────────────────────────────────────────────────────────────┐
│  EVALUATION FLOW WITH FILTERING                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. PUBLIC BENCHMARKS (all models)                         │
│     └── Run: HumanEval, MBPP, GSM8K, ARC, ...             │
│                                                             │
│  2. RANK BY CAPABILITY                                      │
│     ├── code_generation: Top 3 from HumanEval + MBPP       │
│     ├── reasoning: Top 3 from GSM8K + ARC                  │
│     └── instruction: Top 3 from IFEval                     │
│                                                             │
│  3. CUSTOM TESTS (top performers only)                     │
│     ├── tool_calling: Run on code_generation top 3        │
│     └── agent_scenarios: Run on code_generation top 3     │
│                                                             │
│  4. FINAL RANKING                                           │
│     └── Combine public + custom scores                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

Configuration:
```python
FILTER_CONFIG = {
    "top_n_per_capability": 3,
    "capability_benchmarks": {
        "code_generation": ["humaneval", "mbpp"],
        "reasoning": ["gsm8k", "arc"],
        "instruction_following": ["ifeval"],
    },
    "custom_test_capabilities": {
        "cli/tool_calling": "code_generation",
        "cli/agent_scenarios": "code_generation",
        "memory/title_generation": "instruction_following",
    }
}
```

## Consequences

### Positive

1. **Fast feedback loop**: Developers get results in < 2 minutes with smoke tier.

2. **Efficient CI**: Quick tier balances thoroughness with PR merge latency.

3. **Resource efficiency**: Don't waste compute on full evaluation when quick feedback is sufficient.

4. **Reproducible sampling**: Seeded random ensures same subset across runs with same seed.

5. **Statistically meaningful**: Even quick tier (75 samples) provides meaningful signal:
   ```
   Standard error = sqrt(p * (1-p) / n)
   For p=0.5, n=75: SE = 0.058 (5.8%)
   95% CI width: ~11.6%

   For smoke (n=5): SE = 0.22 (22%)
   Useful for pass/fail, not precise ranking
   ```

6. **Capability filtering**: Custom tests run only on promising models, saving significant time:
   ```
   Without filtering: 10 models * 5 custom tests = 50 runs
   With filtering: 3 models * 5 custom tests = 15 runs (70% reduction)
   ```

### Negative

1. **Smoke tier variance**: 5 samples has high variance; suitable only for quick sanity checks:
   ```
   Model could score 3/5 (60%) on smoke but 45/75 (60%) on quick
   Or: 4/5 (80%) on smoke, 50/75 (67%) on quick
   ```

2. **Sampling bias risk**: Random sampling might miss critical edge cases. Mitigation: Use stratified sampling by difficulty if metadata available.

3. **Tier selection confusion**: Users might not know which tier to use. Mitigation: Clear CLI help and documentation.

4. **Capability filtering risk**: Top 3 from public benchmarks might not be best for custom tests. Mitigation: Make filter configurable, allow override.

### Mitigation Strategies

| Concern | Mitigation |
|---------|------------|
| Smoke variance | Document as "sanity check only", not for ranking |
| Sampling bias | Stratified sampling by difficulty/category |
| Tier confusion | Clear CLI help: `matric-eval --help` |
| Filter misses | Configurable top_n, allow `--no-filter` |

## Alternatives Considered

### Alternative A: Time-Based Tiers

**Description**: Define tiers by time budget instead of sample count.

```bash
matric-eval --time-budget 5m   # Run as many as possible in 5 minutes
matric-eval --time-budget 20m  # Run as many as possible in 20 minutes
```

**Pros**:
- Intuitive for users (time is what they care about)
- Adapts to model speed
- Predictable duration

**Cons**:
- Different sample sizes per model (inconsistent comparison)
- Non-reproducible (timing depends on system load)
- Fast models get more samples (unfair comparison)

**Decision**: Rejected. Consistent sample sizes enable fair model comparison.

### Alternative B: Adaptive Sampling

**Description**: Start with few samples, increase if model shows promise.

```
1. Run 5 samples
2. If accuracy > 60%, run 20 more
3. If accuracy > 70%, run full benchmark
```

**Pros**:
- Efficient for both good and bad models
- Automatic tier selection
- No user decision needed

**Cons**:
- Non-reproducible (depends on intermediate results)
- Complex implementation
- Early stopping might miss late-blooming models

**Decision**: Rejected. Reproducibility more important than minor efficiency gains.

### Alternative C: Fixed Time Per Model

**Description**: Allocate fixed time per model, vary sample count.

```bash
matric-eval --per-model-time 10m  # 10 minutes per model, however many samples fit
```

**Pros**:
- Predictable total time: n_models * per_model_time
- Fair time allocation

**Cons**:
- Inconsistent sample sizes per benchmark
- Slower models get fewer samples
- Reproducibility issues

**Decision**: Rejected. Sample count consistency more important.

### Alternative D: No Tiers (Full Only)

**Description**: Always run full evaluation, parallelize for speed.

**Pros**:
- Simplest implementation
- Most accurate results
- No tier selection needed

**Cons**:
- Hours of wait time for development feedback
- Impractical for CI
- Wastes resources on failing models

**Decision**: Rejected. Incompatible with fast feedback requirements.

## Implementation Details

### Tier Configuration

```python
from dataclasses import dataclass
from enum import Enum

class Tier(Enum):
    SMOKE = "smoke"
    QUICK = "quick"
    FULL = "full"

@dataclass
class TierConfig:
    samples_per_benchmark: int
    description: str
    target_duration_minutes: int

TIER_CONFIGS = {
    Tier.SMOKE: TierConfig(
        samples_per_benchmark=5,
        description="Fast sanity check for development",
        target_duration_minutes=2,
    ),
    Tier.QUICK: TierConfig(
        samples_per_benchmark=75,
        description="Balanced evaluation for CI/PR validation",
        target_duration_minutes=20,
    ),
    Tier.FULL: TierConfig(
        samples_per_benchmark=-1,  # -1 = all problems
        description="Comprehensive evaluation for ranking",
        target_duration_minutes=120,
    ),
}
```

### Stratified Sampling (Optional Enhancement)

```python
def stratified_sample(
    problems: list[Problem],
    n: int,
    seed: int,
    stratify_by: str = "difficulty",
) -> list[Problem]:
    """Sample with stratification to ensure difficulty distribution."""

    rng = random.Random(seed)

    # Group by stratification key
    groups = defaultdict(list)
    for p in problems:
        key = getattr(p, stratify_by, "unknown")
        groups[key].append(p)

    # Proportional allocation
    result = []
    for key, group in groups.items():
        group_n = max(1, int(n * len(group) / len(problems)))
        result.extend(rng.sample(group, min(group_n, len(group))))

    # Fill remaining slots randomly
    remaining = n - len(result)
    if remaining > 0:
        pool = [p for p in problems if p not in result]
        result.extend(rng.sample(pool, min(remaining, len(pool))))

    return result[:n]
```

### CLI Integration

```python
import click

@click.command()
@click.option(
    "--tier",
    type=click.Choice(["smoke", "quick", "full"]),
    default="quick",
    help="Evaluation tier: smoke (5 samples, ~2min), quick (75 samples, ~20min), full (all, ~2h)",
)
@click.option(
    "--seed",
    type=int,
    default=42,
    help="Random seed for reproducible sampling",
)
def main(tier: str, seed: int):
    config = TIER_CONFIGS[Tier(tier)]
    # ... run evaluation
```

### CI Configuration Example

```yaml
# .github/workflows/eval.yml

name: Model Evaluation

on:
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 2 * * *'  # Nightly at 2 AM

jobs:
  smoke:
    # Always run smoke on PR
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: matric-eval --tier smoke

  quick:
    # Run quick on PR for model changes
    if: github.event_name == 'pull_request' && contains(github.event.pull_request.labels.*.name, 'model-eval')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: matric-eval --tier quick

  nightly:
    # Run full evaluation nightly
    if: github.event_name == 'schedule'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: matric-eval --tier full
```

## Statistical Considerations

### Sample Size vs. Confidence

| Samples | SE (p=0.5) | 95% CI Width | Use Case |
|---------|------------|--------------|----------|
| 5 | 22.4% | 44.7% | Sanity check only |
| 20 | 11.2% | 22.4% | Rough comparison |
| 75 | 5.8% | 11.5% | PR validation |
| 150 | 4.1% | 8.2% | Solid comparison |
| 500 | 2.2% | 4.5% | Precise ranking |
| 1000 | 1.6% | 3.2% | Publication-grade |

**Quick tier (75 samples) rationale**:
- 95% CI width of ~11.5% is sufficient to distinguish models with 15%+ performance difference
- Good enough for "is this model competitive?" questions
- Not suitable for fine-grained ranking of similar models

**Smoke tier (5 samples) rationale**:
- Can detect catastrophic failures (0/5 = definitely broken)
- Cannot distinguish 60% model from 80% model
- Suitable only for "does this work at all?" questions

## References

- [Statistical Power Analysis](https://en.wikipedia.org/wiki/Power_of_a_test)
- [Inspect AI Evaluation Options](https://inspect.aisi.org.uk/options.html)
- [lm-eval-harness Sampling](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/docs/interface.md)
- matric-cli comprehensive eval script: `/home/roctinam/dev/matric-cli/scripts/comprehensive-model-eval.ts`
