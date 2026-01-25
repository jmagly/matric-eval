# matric-eval Roadmap to Parity

## Current State (Day 1)
- 3 benchmarks (HumanEval, MBPP, GSM8K) with string-matching scorers
- 15 smoke samples (5 per benchmark)
- 40 models evaluated successfully
- **Seeded reproducible sampling** - IMPLEMENTED
  - `EVAL_SEED=42` environment variable (default: 42)
  - `EVAL_HUMANEVAL_SAMPLES=N` per-benchmark overrides
  - Isolated RNG to avoid global state pollution

## Phase 1: Core Benchmarks (Week 1-2)
**Goal: Match matric-cli's 7 public benchmarks with proper scoring**

### 1.1 Add inspect-evals Package
```bash
uv add inspect-evals
```
This gives us production-ready implementations of:
- [x] HumanEval (with code execution)
- [x] MBPP (with code execution)
- [x] GSM8K (with numeric extraction)
- [x] ARC-Challenge (multiple choice)
- [x] IFEval (constraint checking)
- [x] DS-1000 (data science)
- [ ] LiveCodeBench (need custom impl)

### 1.2 Enable Code Execution Scoring
Replace `includes()` with actual Python execution:
```python
from inspect_ai.solver import generate
from inspect_ai.tool import python

@task
def humaneval_exec():
    return Task(
        dataset=humaneval_dataset,
        solver=[generate()],
        scorer=code_execution(),  # Actually run the code
        sandbox="docker",  # Sandboxed execution
    )
```

### 1.3 Implement Tiered Sampling
```python
TIERS = {
    "smoke": {"humaneval": 5, "mbpp": 5, "gsm8k": 5, "arc": 5, "ifeval": 10},
    "quick": {"humaneval": 75, "mbpp": 75, "gsm8k": 75, "arc": 75, "ifeval": 100},
    "full": {"humaneval": 164, "mbpp": 974, "gsm8k": 1319, "arc": 2590, "ifeval": 541},
}
```

## Phase 2: Custom Matric Tests (Week 2-3)
**Goal: Port 282 matric-specific tests**

### 2.1 Data Migration
Copy from `/home/roctinam/data/evals/matric/`:
- format_compliance.jsonl (55 tests)
- semantic_similarity.jsonl (42 tests)
- tag_generation.jsonl (30 tests)
- content_revision.jsonl (44 tests)
- long_context.jsonl (18 tests)
- context_generation.jsonl (29 tests)
- title_generation.jsonl (64 tests)

### 2.2 Custom Scorers
```python
@scorer
def matric_format_scorer():
    """Validate title/content format compliance."""
    async def score(state, target):
        response = state.output.completion
        # Check format rules from matric-cli validator.ts
        valid = check_format_rules(response, target.metadata)
        return Score(value=1.0 if valid else 0.0)
    return score
```

## Phase 3: Tool Calling & Agent Eval (Week 3-4)
**Goal: Port 6 tool-calling scenarios + agent evaluation**

### 3.1 Tool Calling Scenarios
```python
from inspect_ai.tool import bash, python

TOOL_SCENARIOS = [
    ("simple-read", [read_file], "easy"),
    ("read-modify-write", [read_file, write_file], "medium"),
    ("search-read-act", [glob, grep, read_file], "hard"),
    ("error-handling", [read_file], "medium"),  # Test graceful failure
    ("parallel-execution", [read_file, read_file], "hard"),
    ("param-validation", [write_file], "medium"),  # Validate before destructive
]

@task
def tool_calling_eval():
    return Task(
        dataset=tool_scenarios_dataset(),
        solver=[use_tools(tools), generate()],
        scorer=tool_use_accuracy(),
    )
```

### 3.2 Agent Fixture Evaluation
Port `agentScenarios.ts` pattern:
```python
@task
def agent_fixture_eval():
    """Multi-step tasks with file/compilation validation."""
    return Task(
        dataset=agent_fixtures(),
        solver=[
            use_tools([bash(), python()]),
            generate(),
        ],
        scorer=multi_step_scorer(),  # File existence, content, compilation
        sandbox="docker",
    )
```

## Phase 4: MT-Bench & LLM-as-Judge (Week 4)
**Goal: Multi-turn conversation with judge scoring**

### 4.1 MT-Bench Implementation
```python
from inspect_ai.scorer import model_graded_fact

@task
def mt_bench():
    return Task(
        dataset=mtbench_dataset(),  # 80 multi-turn questions
        solver=[
            system_message("You are a helpful assistant."),
            generate(),
            # Second turn
            generate(),
        ],
        scorer=model_graded_fact(
            model="ollama/llama3.1:8b",
            template=MTBENCH_JUDGE_TEMPLATE,
        ),
    )
```

## Phase 5: Multi-Dimensional Scoring (Week 5)
**Goal: 5D scoring beyond simple accuracy**

### 5.1 Dimension Framework
```python
@scorer
def multi_dimensional_scorer():
    """5-dimensional evaluation like matric-cli."""
    async def score(state, target):
        return Score(
            value=weighted_average,
            metadata={
                "correctness": correctness_score,      # 30% weight
                "efficiency": efficiency_score,        # 20% weight
                "safety": safety_score,                # 15% weight
                "helpfulness": helpfulness_score,      # 20% weight
                "reasoning": reasoning_score,          # 15% weight
            }
        )
    return score
```

## Phase 6: Parity Validation (Week 6)
**Goal: Verify equivalent results to matric-cli**

### 6.1 Cross-Validation
1. Run same models on both matric-cli and matric-eval
2. Compare scores per benchmark
3. Identify discrepancies
4. Tune until <5% variance

### 6.2 Migration Complete Checklist
- [ ] All 7 public benchmarks working
- [ ] Code execution with sandboxing
- [ ] 282 custom matric tests ported
- [ ] 6 tool-calling scenarios
- [ ] MT-Bench with LLM judge
- [ ] 5D scoring
- [ ] Smoke/Quick/Full tiers
- [ ] Results parity with matric-cli (<5% variance)

## Beyond Parity (Future)

### Additional Benchmarks (from Inspect AI)
- **SWE-bench**: Real GitHub repo bug fixes
- **GPQA**: Graduate-level science questions
- **CyberSecEval**: Security evaluation
- **GAIA**: Complex agentic tasks

### Enhanced Features
- **Checkpointing**: Resume from failure (address EPIPE issue)
- **Parallel Execution**: Multiple models simultaneously
- **Cost Tracking**: Token usage and API costs
- **CI/CD Integration**: GitHub Actions for automated eval

## Data Layout

### Target Structure
```
matric-eval/
├── src/matric_eval/
│   ├── tasks/
│   │   ├── public/          # HumanEval, MBPP, GSM8K, ARC, IFEval, DS-1000
│   │   ├── matric/          # 282 custom tests
│   │   ├── tools/           # 6 tool-calling scenarios
│   │   └── mtbench/         # 80 multi-turn
│   ├── scorers/
│   │   ├── code_exec.py     # Python execution scorer
│   │   ├── format.py        # Matric format validation
│   │   ├── multi_dim.py     # 5D scoring
│   │   └── tool_use.py      # Tool calling accuracy
│   └── config/
│       └── tiers.py         # smoke/quick/full configs
├── datasets/
│   ├── public/              # Symlink to /home/roctinam/data/evals/
│   └── matric/              # Custom test JSONL files
└── results/
    └── run-{timestamp}/     # Per-run results
```

## Summary

| Aspect | matric-cli | matric-eval Target | Status |
|--------|------------|-------------------|--------|
| Public benchmarks | 7 | 7+ (107 available) | Planned |
| Code execution | Yes | Yes (sandbox) | Planned |
| Custom tests | 282 | 282 | Planned |
| Tool calling | 6 scenarios | 6+ | Planned |
| MT-Bench | 80 | 80 | Planned |
| 5D scoring | Yes | Yes | Planned |
| Checkpoint/resume | No | Yes | Planned |
| Parallel eval | No | Yes | Planned |

**Conclusion**: Inspect AI is fully capable of achieving parity and exceeding matric-cli's capabilities. The framework is extensible, well-documented, and actively maintained.
