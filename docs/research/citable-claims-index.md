# Citable Claims Index - matric-eval

This document indexes claims made in the matric-eval framework that are backed by research papers from the [research-papers](https://git.integrolabs.net/roctinam/research-papers) repository.

**Last Updated**: 2026-01-25
**Status**: Complete - All core benchmark papers acquired

## Evaluation & Benchmarking

### Code Generation Evaluation

| Claim | REF | Citation | Status |
|-------|-----|----------|--------|
| HumanEval provides standardized code generation evaluation with 164 hand-written problems | REF-040 | Chen et al., "Evaluating Large Language Models Trained on Code" (2021) | ✅ ACQUIRED |
| MBPP tests basic Python programming with 974 crowd-sourced problems | REF-041 | Austin et al., "Program Synthesis with Large Language Models" (2021) | ✅ ACQUIRED |
| Pass@k metric accounts for sampling variance in code generation | REF-040 | Chen et al., 2021 - Section 4.1 | ✅ ACQUIRED |
| Code execution with sandbox provides ground truth evaluation | REF-040 | HumanEval methodology | ✅ ACQUIRED |
| LiveCodeBench prevents data contamination via temporal splits | REF-046 | Jain et al., "LiveCodeBench" (2024) | ✅ ACQUIRED |
| DS-1000 evaluates data science skills across 7 Python libraries | REF-047 | Lai et al., "DS-1000" (2022) | ✅ ACQUIRED |

### Reasoning & Math Evaluation

| Claim | REF | Citation | Status |
|-------|-----|----------|--------|
| GSM8K tests grade school math reasoning with 8.5K problems | REF-042 | Cobbe et al., "Training Verifiers to Solve Math Word Problems" (2021) | ✅ ACQUIRED |
| Chain-of-thought prompting improves math performance | REF-016 | Wei et al., "Chain-of-Thought Prompting" (2022) | ✅ AVAILABLE |
| Self-consistency improves reasoning via multiple sampling paths | REF-017 | Wang et al., "Self-Consistency Improves Chain of Thought Reasoning" (2022) | ✅ AVAILABLE |
| CoT only benefits models >100B parameters | REF-016 | Wei et al., 2022 - Section 3.2 | ✅ AVAILABLE |
| ARC Challenge tests science reasoning with multiple choice format | REF-044 | Clark et al., "Think you have Solved Question Answering?" (2018) | ✅ ACQUIRED |

### Instruction Following

| Claim | REF | Citation | Status |
|-------|-----|----------|--------|
| IFEval tests verifiable instruction following with 541 prompts | REF-045 | Zhou et al., "Instruction-Following Evaluation" (2023) | ✅ ACQUIRED |
| Constraint verification enables automated IF evaluation without LLM judge | REF-045 | IFEval methodology | ✅ ACQUIRED |
| Strict vs loose accuracy captures different compliance levels | REF-045 | Zhou et al., 2023 - Section 3 | ✅ ACQUIRED |

### Multi-turn Conversation

| Claim | REF | Citation | Status |
|-------|-----|----------|--------|
| MT-Bench evaluates multi-turn conversation with LLM-as-judge | REF-043 | Zheng et al., "Judging LLM-as-a-Judge" (2023) | ✅ ACQUIRED |
| LLM-as-judge achieves >85% agreement with human preference | REF-043 | Zheng et al., 2023 - Table 2 | ✅ ACQUIRED |
| Position bias in LLM judges can be mitigated by swapping | REF-043 | Zheng et al., 2023 - Section 4.2 | ✅ ACQUIRED |

### Tool Use & Agentic Evaluation

| Claim | REF | Citation | Status |
|-------|-----|----------|--------|
| Tool calling evaluation requires function correctness verification | REF-019 | Schick et al., "Toolformer" (2023) | ✅ AVAILABLE |
| ReAct pattern enables interleaved reasoning and tool use | REF-018 | Yao et al., "ReAct: Reasoning and Acting" (2022) | ✅ AVAILABLE |
| SWE-Bench tests real-world software engineering tasks | REF-014 | Jimenez et al., "SWE-bench" (2024) | ✅ AVAILABLE |

## Framework Design

### Scaling & Model Selection

| Claim | REF | Citation | Status |
|-------|-----|----------|--------|
| Performance scales as power-law with model size | REF-050 | Kaplan et al., "Scaling Laws for Neural Language Models" (2020) | ✅ ACQUIRED |
| Compute-optimal training balances model size and data | REF-051 | Hoffmann et al., "Training Compute-Optimal LLMs" (2022) | ✅ ACQUIRED |
| In-context learning emerges with sufficient scale | REF-052 | Brown et al., "Language Models are Few-Shot Learners" (2020) | ✅ ACQUIRED |
| Open models can match closed models with proper training | REF-054 | Touvron et al., "LLaMA" (2023) | ✅ ACQUIRED |

### Code Model Foundations

| Claim | REF | Citation | Status |
|-------|-----|----------|--------|
| Code Llama achieves 67% on HumanEval with instruction tuning | REF-053 | Rozière et al., "Code Llama" (2023) | ✅ ACQUIRED |
| Long context (100k tokens) enables repository-level understanding | REF-053 | Code Llama paper | ✅ ACQUIRED |
| Infilling capability requires specialized training | REF-053 | Code Llama paper - Section 3 | ✅ ACQUIRED |

### Alignment & Safety

| Claim | REF | Citation | Status |
|-------|-----|----------|--------|
| RLHF improves instruction following over scale alone | REF-055 | Ouyang et al., "Training language models to follow instructions" (2022) | ✅ ACQUIRED |
| 1.3B aligned model can outperform 175B unaligned model | REF-055 | InstructGPT paper | ✅ ACQUIRED |
| Constitutional AI provides principle-based alignment | REF-025 | Bai et al., "Constitutional AI" (2022) | ✅ AVAILABLE |

### Holistic Evaluation

| Claim | REF | Citation | Status |
|-------|-----|----------|--------|
| No single model dominates across all evaluation dimensions | REF-048 | Liang et al., "Holistic Evaluation of Language Models" (2022) | ✅ ACQUIRED |
| Multi-metric evaluation captures capability trade-offs | REF-048 | HELM framework | ✅ ACQUIRED |
| Emergent abilities appear unpredictably at scale | REF-049 | Srivastava et al., "BIG-bench" (2023) | ✅ ACQUIRED |

## Research Paper Coverage

### Acquired Papers (in research-papers repo)

| REF | Paper | Year | Category |
|-----|-------|------|----------|
| REF-014 | SWE-Bench | 2024 | Evaluation |
| REF-016 | Chain-of-Thought | 2022 | Prompting |
| REF-017 | Self-Consistency | 2022 | Prompting |
| REF-018 | ReAct | 2022 | Tool Use |
| REF-019 | Toolformer | 2023 | Tool Use |
| REF-025 | Constitutional AI | 2022 | Alignment |
| REF-040 | HumanEval | 2021 | Code Evaluation |
| REF-041 | MBPP | 2021 | Code Evaluation |
| REF-042 | GSM8K | 2021 | Math Evaluation |
| REF-043 | MT-Bench | 2023 | Multi-turn Evaluation |
| REF-044 | ARC Challenge | 2018 | Reasoning Evaluation |
| REF-045 | IFEval | 2023 | Instruction Following |
| REF-046 | LiveCodeBench | 2024 | Code Evaluation |
| REF-047 | DS-1000 | 2022 | Data Science Evaluation |
| REF-048 | HELM | 2022 | Framework |
| REF-049 | BigBench | 2023 | Comprehensive Evaluation |
| REF-050 | Scaling Laws | 2020 | Foundations |
| REF-051 | Chinchilla | 2022 | Foundations |
| REF-052 | GPT-3 | 2020 | Foundations |
| REF-053 | Code Llama | 2023 | Code Models |
| REF-054 | LLaMA | 2023 | Foundations |
| REF-055 | InstructGPT | 2022 | Alignment |

### Coverage Summary

| Category | Papers | Coverage |
|----------|--------|----------|
| Code Generation Benchmarks | 5 | Complete |
| Reasoning Benchmarks | 3 | Complete |
| Instruction Following | 1 | Complete |
| Multi-turn Evaluation | 1 | Complete |
| Scaling Foundations | 4 | Complete |
| Code Model Foundations | 2 | Complete |
| Framework Design | 2 | Complete |
| Alignment | 2 | Complete |
| **Total** | **22** | **100%** |

## Usage

When making claims in matric-eval documentation or code comments:

1. Reference this index for the REF-XXX number
2. Include page number for specific claims when available
3. Link to full paper documentation in research-papers repo

### Example

```python
# HumanEval Pass@k calculation (REF-040, Section 4.1)
# Uses numerically stable unbiased estimator
def pass_at_k(n: int, c: int, k: int) -> float:
    """
    Unbiased estimator for pass@k metric.

    Reference: Chen et al., "Evaluating Large Language Models Trained on Code"
    (2021), arXiv:2107.03374, Section 4.1
    """
    if n - c < k:
        return 1.0
    return 1.0 - np.prod(1.0 - k / np.arange(n - c + 1, n + 1))
```

## Cross-References

- **Research Papers Repo**: https://git.integrolabs.net/roctinam/research-papers
- **Self-Evaluation**: `.aiwg/research/self-evaluation-research-based.md`
- **Gap Analysis**: `.aiwg/research/research-gap-analysis.md`

## Revision History

| Date | Change |
|------|--------|
| 2026-01-24 | Initial draft with pending papers |
| 2026-01-25 | All papers acquired, REF numbers finalized |
