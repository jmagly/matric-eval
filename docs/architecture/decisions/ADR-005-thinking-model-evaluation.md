# ADR-005: Thinking Model Evaluation Strategy

## Status
Proposed

## Context

During evaluation of the `quick` tier on 2026-02-01, we discovered that thinking-capable models (e.g., Qwen3-14B) generate extensive reasoning chains that significantly impact evaluation performance:

### Observed Behavior

| Metric | Value |
|--------|-------|
| Sample | leetcode/2827 (livecodebench) |
| Reasoning block | 34,275 chars (~8,500 tokens) |
| Text block | 4,052 chars (~1,000 tokens) |
| Total output tokens | 10,436 |
| Working time per sample | ~9 minutes |
| Projected time for 50 samples | ~7.5 hours |

### Root Cause Analysis

1. **Extended thinking enabled**: Qwen3 models output structured responses with `reasoning` and `text` blocks
2. **Reasoning cycles**: The model exhibits repetitive patterns ("Wait," ×18, "So the" ×42 in one sample)
3. **No output limits**: Current prompts don't constrain reasoning depth
4. **Token overhead**: Reasoning tokens count toward generation time even though only `text` block is scored

### Current Prompt (livecodebench)

```
System: You are an expert competitive programmer. Solve the programming problem
by writing clean, efficient code. Read the problem carefully, understand the
constraints, and provide a working solution. Return only the code implementation.
```

This prompt is ignored by thinking models which output reasoning regardless.

## Decision

Implement a **dual-mode evaluation strategy** for thinking-capable models:

### 1. Thinking Parameter

Add an optional `--thinking` parameter to the CLI:

```bash
# Default: auto-detect and run appropriate mode
matric-eval run --tier quick --model qwen3:14b

# Explicit: run both modes for thinking models
matric-eval run --tier quick --model qwen3:14b --thinking both

# Explicit: thinking off only
matric-eval run --tier quick --model qwen3:14b --thinking off

# Explicit: thinking on only
matric-eval run --tier quick --model qwen3:14b --thinking on
```

### 2. Model Capability Detection

Detect thinking capability from Ollama model info:

```python
def has_thinking_capability(model: str) -> bool:
    """Check if model supports extended thinking."""
    info = get_ollama_model_info(model)
    return "thinking" in info.get("capabilities", [])
```

### 3. Thinking Toggle via Ollama

Control thinking mode through generation parameters:

```python
# Thinking OFF - add /no_think tag or use parameter
generate_config = GenerateConfig(
    extra_body={"enable_thinking": False}  # If supported
)

# Or via prompt prefix
prompt_prefix = "/no_think\n" if not thinking_enabled else ""
```

### 4. Improved Prompts

Create thinking-aware prompts that reduce cycling:

**For thinking ON:**
```
You are an expert competitive programmer.

TASK: Solve the problem below by writing Python code.

THINKING GUIDELINES:
- Identify the core algorithm needed (1-2 sentences)
- Note key constraints that affect approach
- Do NOT re-explain or second-guess your approach
- Once you have a solution, implement it

OUTPUT: Provide ONLY the Python code implementation in a ```python block.
Do not include explanations in your final answer.
```

**For thinking OFF:**
```
You are an expert competitive programmer.
Solve this problem with Python code.
Output ONLY the code in a ```python block. No explanations.
```

### 5. Results Structure

Store results separately for comparison:

```
results/run-YYYY-MM-DD/
├── model-name/
│   ├── thinking-on/
│   │   ├── livecodebench.json
│   │   └── humaneval.json
│   └── thinking-off/
│       ├── livecodebench.json
│       └── humaneval.json
```

### 6. Metrics Captured

For thinking-enabled runs, capture additional metrics:

```python
@dataclass
class ThinkingMetrics:
    reasoning_tokens: int
    reasoning_chars: int
    text_tokens: int
    text_chars: int
    reasoning_cycles: int  # Count of "Wait,", "Actually," etc.
    total_time: float
    reasoning_time: float  # Estimated from token ratio
```

## Consequences

### Positive

1. **Representative results**: Compare thinking vs non-thinking fairly
2. **Research value**: Understand when thinking helps/hurts
3. **Faster iteration**: Non-thinking mode for quick tests
4. **Better prompts**: Reduce wasted reasoning cycles
5. **Preserved data**: Full thinking captured for analysis

### Negative

1. **Doubled test time**: Thinking models run twice (mitigated by making optional)
2. **Complexity**: More configuration options
3. **Storage**: More result files

### Neutral

1. **Prompt changes**: May affect reproducibility with older results

## Implementation Plan

1. **Phase 1**: Prompt engineering improvements (immediate)
2. **Phase 2**: Thinking toggle implementation
3. **Phase 3**: Dual-mode automation
4. **Phase 4**: Metrics and analysis tooling

## References

- Investigation session: 2026-02-01
- Sample analyzed: `results/run-2026-02-01T01-56-34/logs/*livecodebench*`
- Model: `hf.co/mradermacher/Qwen3-14B-Nexa-Uncensored-i1-GGUF:Q4_K_M`

## Related Issues

- [#23: Add thinking model dual-mode evaluation](https://git.integrolabs.net/roctinam/matric-eval/issues/23)
- [#24: Improve prompts to reduce reasoning cycles](https://git.integrolabs.net/roctinam/matric-eval/issues/24)
- [#25: Capture and analyze thinking model metrics](https://git.integrolabs.net/roctinam/matric-eval/issues/25)
