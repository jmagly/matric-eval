# ADR-002: Inspect AI as Evaluation Framework

**Status**: Proposed
**Date**: 2026-01-24
**Decision Makers**: matric-eval development team
**Supersedes**: N/A

## Context

Having decided to use Python for the evaluation core (ADR-001), we need to select an evaluation framework. The main contenders are:

| Framework | Maintainer | Ollama Support | Key Strengths |
|-----------|------------|----------------|---------------|
| **Inspect AI** | UK AI Safety Institute | Native (`ollama/model`) | Agent evals, MCP tools, 100+ tasks |
| **lm-eval-harness** | EleutherAI | Via local-completions | Industry standard, HF Leaderboard |
| **HELM** | Stanford CRFM | Limited | Holistic metrics, research-grade |

Our key requirements:
1. **Native Ollama support**: First-class integration without workarounds
2. **Agent evaluation**: Multi-step tool use scenarios (needed for matric-cli)
3. **Checkpoint/resume**: Ability to resume interrupted evaluations (P0 requirement)
4. **Pre-built benchmarks**: HumanEval, MBPP, GSM8K, ARC, IFEval, etc.
5. **Custom test support**: Ability to define app-specific tests
6. **Active maintenance**: Regular updates and bug fixes

## Decision

**Adopt Inspect AI as the primary evaluation framework, with the caveat that checkpoint/resume capabilities must be validated during prototyping.**

If Inspect AI's checkpoint/resume proves inadequate, we will:
1. Implement custom state management layer on top of Inspect AI, OR
2. Evaluate lm-eval-harness as fallback, OR
3. Build custom solution if both frameworks fail

### Rationale

#### 1. Native Ollama Support

Inspect AI provides first-class Ollama support with clean syntax:

```python
from inspect_ai import eval
from inspect_ai.model import get_model

# Native Ollama model syntax
model = get_model("ollama/llama3.2:3b")

# Run evaluation
results = eval(task, model=model)
```

Compare to lm-eval-harness which requires workarounds:

```bash
# lm-eval-harness requires local-completions adapter
lm_eval --model local-completions \
    --model_args model=llama3.2,base_url=http://localhost:11434/v1/completions
```

#### 2. Agent Evaluation Support

matric-cli needs to evaluate models on multi-step tool use scenarios. Inspect AI has built-in support for agent evaluation:

```python
from inspect_ai import Task
from inspect_ai.solver import generate, use_tools
from inspect_ai.tool import tool

@tool
def read_file(path: str) -> str:
    """Read a file from disk."""
    ...

@tool
def write_file(path: str, content: str) -> None:
    """Write content to a file."""
    ...

task = Task(
    dataset=my_dataset,
    solver=[use_tools([read_file, write_file]), generate()],
    scorer=tool_use_scorer(),
)
```

lm-eval-harness is primarily designed for single-turn completions and lacks native agent/tool support.

#### 3. MCP Tool Integration

Inspect AI supports Model Context Protocol (MCP) tools, which aligns with matric ecosystem's MCP usage:

```python
from inspect_ai.tool import mcp_tools

# Load MCP server tools
tools = mcp_tools("npx", ["-y", "@anthropic-ai/mcp-server-github"])
```

#### 4. UK Government Backing

Inspect AI is maintained by the UK AI Safety Institute with government funding, ensuring:
- Long-term maintenance commitment
- Safety-focused design
- Active development
- Professional documentation

#### 5. Modern Python Practices

Inspect AI uses modern Python tooling:
- `uv` for package management
- Type hints throughout
- Async support
- Clean API design

## Consequences

### Positive

1. **Immediate Ollama integration**: No workarounds needed for local models.

2. **Agent evaluation ready**: Built-in support for tool calling, multi-step scenarios.

3. **100+ pre-built tasks**: HumanEval, MBPP, GSM8K, and many more available out of box.

4. **Safety-focused**: Designed by AI Safety Institute with safety considerations built-in.

5. **Active community**: Growing community, regular updates, responsive maintainers.

6. **MCP compatibility**: Aligns with matric ecosystem's MCP server usage.

### Negative

1. **Checkpoint/resume uncertainty**: Native checkpoint/resume capabilities need validation. This is a P0 requirement and may require custom implementation.

2. **Smaller community than lm-eval-harness**: EleutherAI's framework powers HuggingFace Leaderboard and has larger community.

3. **Less benchmark coverage**: lm-eval-harness has more benchmarks (60+ vs 100+ in Inspect AI, but lm-eval covers more niche benchmarks).

4. **Newer framework**: Less battle-tested than lm-eval-harness in production environments.

### Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Checkpoint/resume inadequate | Prototype in week 1; build custom state layer if needed |
| Missing benchmark | Inspect AI is extensible; can implement custom tasks |
| Framework issues | lm-eval-harness as fallback; both use Python, migration possible |

## Alternatives Considered

### Alternative A: lm-eval-harness (EleutherAI)

**Description**: Industry-standard evaluation framework powering HuggingFace Leaderboard.

**Pros**:
- Industry standard, widely adopted
- Powers HuggingFace Open LLM Leaderboard
- Large community, extensive documentation
- 60+ pre-built tasks
- Battle-tested in production

**Cons**:
- Ollama support via workaround (local-completions)
- Limited agent/tool evaluation support
- Older Python patterns
- No MCP integration

**Evaluation**:
```bash
# lm-eval-harness Ollama usage
lm_eval --model local-completions \
    --model_args model=codestral:22b,base_url=http://localhost:11434/v1/completions \
    --tasks humaneval,mbpp
```

**Decision**: Consider as fallback if Inspect AI proves inadequate.

### Alternative B: HELM (Stanford)

**Description**: Holistic Evaluation of Language Models from Stanford CRFM.

**Pros**:
- Research-grade evaluation methodology
- Holistic metrics (accuracy, calibration, robustness, fairness, efficiency)
- Stanford backing

**Cons**:
- Limited Ollama support
- Heavyweight for our use case
- More research-focused than production-focused
- Slower development cycle

**Decision**: Rejected. Over-engineered for our needs, limited Ollama support.

### Alternative C: Custom Framework

**Description**: Build evaluation framework from scratch.

**Pros**:
- Full control over design
- No external dependencies
- Tailored to our exact needs

**Cons**:
- Massive development effort
- Must implement all benchmarks from scratch
- No community support
- Maintenance burden

**Decision**: Rejected. Would take months and duplicate existing work.

### Alternative D: Hybrid Approach

**Description**: Use lm-eval-harness for standard benchmarks, Inspect AI for agent evals.

**Pros**:
- Best of both worlds
- Industry-standard benchmarks
- Agent evaluation support

**Cons**:
- Two frameworks to maintain
- Inconsistent APIs
- Double the complexity
- Result format normalization needed

**Decision**: Rejected. Complexity not justified; Inspect AI covers our needs.

## Validation Criteria

This decision will be validated by prototyping the following:

### Week 1 Prototype

1. **Ollama Integration**
   - [ ] Connect to local Ollama instance
   - [ ] Run simple completion with `ollama/llama3.2:3b`
   - [ ] Verify response parsing

2. **Benchmark Execution**
   - [ ] Run HumanEval (5 samples)
   - [ ] Verify code extraction works
   - [ ] Verify scoring is accurate

3. **Checkpoint/Resume (Critical)**
   - [ ] Interrupt evaluation mid-run
   - [ ] Resume from checkpoint
   - [ ] Verify no duplicate work
   - [ ] Verify correct final results

4. **Custom Task**
   - [ ] Define custom JSONL task
   - [ ] Run with custom scorer
   - [ ] Verify extensibility

### Success Criteria

- All validation items pass: **Commit to Inspect AI**
- Checkpoint/resume fails: **Implement custom state layer**
- Multiple failures: **Evaluate lm-eval-harness**

## Prototype Code

```python
# prototype.py - Week 1 validation

from inspect_ai import eval, Task
from inspect_ai.dataset import json_dataset
from inspect_ai.scorer import model_graded_qa
from inspect_ai.solver import generate
from inspect_ai.model import get_model

# Test 1: Ollama connection
def test_ollama_connection():
    model = get_model("ollama/llama3.2:3b")
    response = model.generate("Say hello")
    assert response is not None
    print(f"Ollama connection: PASS")

# Test 2: Simple task execution
def test_simple_task():
    task = Task(
        dataset=[{"input": "What is 2+2?", "target": "4"}],
        solver=generate(),
        scorer=model_graded_qa(),
    )
    results = eval(task, model="ollama/llama3.2:3b")
    print(f"Simple task: PASS (score={results.score})")

# Test 3: Checkpoint/resume
def test_checkpoint_resume():
    # Run partial evaluation
    # Simulate interruption
    # Resume from checkpoint
    # Verify completeness
    pass

if __name__ == "__main__":
    test_ollama_connection()
    test_simple_task()
    test_checkpoint_resume()
```

## Decision Status

**Status**: Proposed

This decision requires validation through Week 1 prototyping. The decision will be updated to "Accepted" or "Rejected" based on prototype results.

**Validation Deadline**: End of Week 1 (implementation phase)

## References

- [Inspect AI Documentation](https://inspect.aisi.org.uk/)
- [Inspect AI GitHub](https://github.com/UKGovernmentBEIS/inspect_ai)
- [lm-eval-harness GitHub](https://github.com/EleutherAI/lm-evaluation-harness)
- [HELM Stanford](https://crfm.stanford.edu/helm/)
- [MCP Specification](https://modelcontextprotocol.io/)
