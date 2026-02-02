# Thinking Model Evaluation Guide

This document describes how matric-eval handles thinking-capable models like Qwen3.

## Background

Some modern LLMs include "extended thinking" or "chain-of-thought" capabilities where the model outputs its reasoning process separately from its final answer. This creates unique challenges for evaluation:

1. **Token overhead**: Reasoning tokens count toward generation time
2. **Cycling behavior**: Models may loop through self-correction patterns
3. **Scoring complexity**: Only the final answer should be scored, not reasoning
4. **Comparison fairness**: Thinking vs non-thinking models need appropriate comparison

## Investigation Summary (2026-02-01)

Analysis of Qwen3-14B on livecodebench revealed:

| Metric | Value |
|--------|-------|
| Reasoning block | 34,275 chars |
| Text (answer) block | 4,052 chars |
| Output tokens | 10,436 |
| Working time per sample | ~9 minutes |
| Self-correction patterns ("Wait,") | 18 occurrences |
| Repetitive conclusions ("So the") | 42 occurrences |

The model outputs a structured response:
```python
[
    {"type": "reasoning", "reasoning": "...34K chars of chain-of-thought..."},
    {"type": "text", "text": "...4K char final answer..."}
]
```

## Planned Features

### 1. Dual-Mode Evaluation (#23)

Test thinking models with both modes:

```bash
# Run both thinking ON and OFF
matric-eval run --tier quick --model qwen3:14b --thinking both

# Explicit single mode
matric-eval run --tier quick --model qwen3:14b --thinking off
```

### 2. Improved Prompts (#24)

Reduce cycling with structured prompts:

**Thinking ON:**
```
THINKING APPROACH:
1. Identify the algorithm needed (1-2 sentences max)
2. Note critical constraints
3. Implement directly - do not second-guess

OUTPUT: Only Python code in a ```python block.
```

**Thinking OFF:**
```
Output ONLY code in a ```python block. No explanations.
```

### 3. Thinking Metrics (#25)

Capture and analyze reasoning patterns:

```python
@dataclass
class ThinkingMetrics:
    reasoning_chars: int
    reasoning_cycles: int
    backtrack_count: int  # "Wait,", "Actually," etc.
    reasoning_to_text_ratio: float
```

## Model Detection

Thinking capability is detected from Ollama model info:

```bash
$ ollama show qwen3:14b
Capabilities
    completion
    tools
    thinking      # <-- This indicates thinking support
```

## Results Structure

```
results/run-YYYY-MM-DD/
├── qwen3-14b/
│   ├── thinking-on/
│   │   ├── livecodebench.json
│   │   └── humaneval.json
│   └── thinking-off/
│       ├── livecodebench.json
│       └── humaneval.json
├── llama3.2-3b/          # Non-thinking model
│   ├── livecodebench.json
│   └── humaneval.json
```

## Related Documentation

- [ADR-005: Thinking Model Evaluation Strategy](../architecture/decisions/ADR-005-thinking-model-evaluation.md)

## Related Issues

- [#23: Add thinking model dual-mode evaluation](https://git.integrolabs.net/roctinam/matric-eval/issues/23)
- [#24: Improve prompts to reduce reasoning cycles](https://git.integrolabs.net/roctinam/matric-eval/issues/24)
- [#25: Capture and analyze thinking model metrics](https://git.integrolabs.net/roctinam/matric-eval/issues/25)
