# Software Architecture Document (SAD)

**Project**: matric-eval - Model Evaluation Framework
**Version**: 2.0
**Date**: 2026-04-01
**Status**: Released

## 1. Architecture Overview

### 1.1 Purpose

matric-eval is a consolidated model evaluation framework for the matric ecosystem. It provides standardized benchmarking of LLM models across multiple inference providers (Ollama, vLLM, llama.cpp, OpenRouter, Chutes) using public benchmarks (HumanEval, MBPP, GSM8K, etc.) and custom application-specific tests.

### 1.2 Goals

| Goal | Description | Priority |
|------|-------------|----------|
| **Consolidation** | Eliminate duplicate evaluation code across matric-cli (TypeScript) and matric-memory (Rust) | P0 |
| **Resilience** | 100% recovery from failures with checkpoint/resume | P0 |
| **Standardization** | Consistent evaluation methodology across projects | P0 |
| **Extensibility** | Support custom app-specific tests via JSONL format | P1 |
| **Automation** | Generate model configuration recommendations | P1 |
| **Performance** | Tiered evaluation: smoke (<2m), quick (<20m), full (<2h) | P1 |

### 1.3 Non-Goals

- Multi-GPU distributed evaluation (v1.0 is single-machine; multi-GPU via vLLM server config)
- Cloud-hosted evaluation service (local/CI only)
- Web UI for results (CLI + JSON/Markdown reports)
- Model training or fine-tuning (evaluation only)

## 2. Component Architecture

### 2.1 High-Level Component Diagram

```
+------------------------------------------------------------------------+
|                           matric-eval                                   |
+------------------------------------------------------------------------+
|                                                                         |
|  +-------------------+    +-------------------+                         |
|  |       CLI         |    |    State Manager  |                         |
|  |  (cli.py)         |--->|  (state/)         |                         |
|  +-------------------+    +-------------------+                         |
|          |                        |                                     |
|          v                        v                                     |
|  +-------------------+    +-------------------+                         |
|  | EvaluationEngine  |    |  Recovery Engine  |                         |
|  |  (core/engine.py) |--->|  (recovery.py)    |                         |
|  +-------------------+    +-------------------+                         |
|          |                                                              |
|          v                                                              |
|  +-------------------+    +-------------------+                         |
|  | Provider Layer    |--->|   Inspect AI      |                         |
|  |  (providers/)     |    |   Framework       |                         |
|  +-------------------+    +-------------------+                         |
|    |   |   |   |   |             |                                      |
|    v   v   v   v   v             v                                      |
|  +---+ +---+ +---+ +---+ +---+  +---+                                  |
|  |Oll| |vLL| |lcp| |ORT| |Chu|  |Scr|                                  |
|  |ama| |M  | |p  | |   | |tes|  |ers|                                  |
|  +---+ +---+ +---+ +---+ +---+  +---+                                  |
|                                                                         |
|  +-------------------+    +-------------------+                         |
|  |  Matrix Config    |    | Config Generator  |                         |
|  |  (matrix.py)      |    |  (recommendation) |                         |
|  +-------------------+    +-------------------+                         |
|                                                                         |
+------------------------------------------------------------------------+
          |                         |
          v                         v
+-------------------+    +-------------------+
|  TypeScript       |    |    Rust           |
|  Bindings (npm)   |    |  Bindings (crate) |
+-------------------+    +-------------------+

Provider Key: Oll=Ollama, vLLM=vLLM, lcp=llama.cpp, ORT=OpenRouter, Chu=Chutes
```

#### 2.1.1 Provider Abstraction Layer

The provider layer (`src/matric_eval/providers/`) abstracts inference backends behind a common `Provider` protocol:

```python
class Provider(Protocol):
    name: str                    # e.g., "ollama", "vllm"
    display_name: str            # e.g., "Ollama", "vLLM"
    def is_available() -> bool
    def list_models(max_size_gb) -> list[ModelInfo]
    def get_model_info(model) -> ModelInfo
    def format_model_id(model) -> str   # e.g., "ollama/llama3.2:3b"
    def get_eval_kwargs(model) -> dict  # base_url, api_key, etc.
```

Providers are registered in a `ProviderRegistry` and accessed via `get_provider("name")`. The `EvaluationEngine` accepts an optional `provider` parameter; when omitted, it falls back to the legacy `ollama/` prefix behavior for backwards compatibility.

### 2.2 Component Descriptions

#### 2.2.1 CLI (`cli.py`)

**Responsibility**: Command-line interface and argument parsing

**Key Functions**:
- Parse evaluation commands (--tier, --model, --benchmark)
- Handle resume commands (--resume, --fill-gaps, --validate)
- Configure logging and output formats
- Entry point for all operations

**Dependencies**: Click or Typer for CLI parsing

#### 2.2.2 State Manager (`state.py`)

**Responsibility**: Checkpoint/resume state persistence

**Key Functions**:
- Write run metadata (seed, config, tier)
- Track model/benchmark/problem completion status
- Atomic state updates (temp file + rename)
- Lock file management for concurrent run prevention

**Data Structures**:
```python
@dataclass
class RunState:
    run_id: str           # e.g., "run-2026-01-24T10-30-15"
    tier: Tier            # smoke | quick | full
    seed: int             # reproducibility
    models: list[str]     # Ollama model names
    benchmarks: list[str] # benchmark IDs
    status: RunStatus     # running | completed | failed | cancelled
    started_at: datetime
    updated_at: datetime

@dataclass
class ModelState:
    model: str
    benchmarks: dict[str, BenchmarkState]
    status: Status

@dataclass
class BenchmarkState:
    benchmark: str
    problems: dict[str, ProblemResult]
    score: float | None
    status: Status
```

#### 2.2.3 Orchestrator (`orchestrator.py`)

**Responsibility**: Coordinate evaluation workflow

**Key Functions**:
- Discover available Ollama models
- Filter models by size constraints
- Execute tiered evaluation (smoke -> quick -> full)
- Rank and filter top performers
- Invoke custom tests on top performers

**Workflow**:
```
DISCOVER -> FILTER -> EVALUATE -> RANK -> CUSTOM -> CONFIG
```

#### 2.2.4 Recovery Engine (`recovery.py`)

**Responsibility**: Error handling and recovery

**Key Functions**:
- Classify errors (transient vs fatal)
- Retry transient errors (EPIPE, timeout, connection reset)
- Skip failed models gracefully
- Gap detection (scan results, identify incomplete)
- Generate failure reports

**Error Classification**:
```python
class ErrorType(Enum):
    TRANSIENT = "transient"  # Retry: timeout, EPIPE, connection reset
    MODEL_ERROR = "model"    # Skip model: crash, OOM, invalid response
    FATAL = "fatal"          # Stop: disk full, config error
```

#### 2.2.5 Task Runner (`runner.py`)

**Responsibility**: Execute individual benchmark problems

**Key Functions**:
- Load benchmark tasks from Inspect AI or JSONL
- Submit prompts to Ollama via Inspect AI
- Collect model responses
- Handle per-problem timeouts
- Write individual problem results

**Integration**: Wraps Inspect AI framework for task execution

#### 2.2.6 Scorers (`scorers/`)

**Responsibility**: Validate model outputs and compute scores

**Built-in Scorers**:
- `code_execution.py`: Run generated code in sandbox, check tests pass
- `string_match.py`: Exact/fuzzy string matching
- `semantic.py`: Semantic similarity scoring
- `tool_calling.py`: Validate tool invocations

**Custom Scorer Interface**:
```python
class Scorer(Protocol):
    def score(self, response: str, expected: Any, context: dict) -> ScoreResult:
        ...

@dataclass
class ScoreResult:
    passed: bool
    score: float  # 0.0 to 1.0
    message: str
    artifacts: dict  # extracted code, test output, etc.
```

#### 2.2.7 Config Generator (`config.py`)

**Responsibility**: Generate model configuration recommendations

**Output**: `model-categories.json`
```json
{
  "code_generation": {
    "recommended": "codestral:22b",
    "alternatives": ["deepseek-coder:6.7b", "qwen2.5-coder:7b"],
    "scores": {"humaneval": 0.85, "mbpp": 0.78}
  },
  "reasoning": {
    "recommended": "qwen2.5:14b",
    "alternatives": ["llama3.3:70b"],
    "scores": {"gsm8k": 0.72, "arc": 0.68}
  }
}
```

### 2.3 Directory Structure

```
matric-eval/
├── pyproject.toml              # Python project (uv)
├── src/
│   └── matric_eval/
│       ├── __init__.py
│       ├── cli.py              # CLI entry point
│       ├── orchestrator.py     # Workflow coordination
│       ├── state.py            # Checkpoint/resume
│       ├── recovery.py         # Error handling
│       ├── runner.py           # Task execution
│       ├── config.py           # Config recommendation
│       ├── discovery.py        # External dataset auto-discovery
│       ├── tasks/              # Benchmark task definitions
│       │   ├── humaneval.py
│       │   ├── mbpp.py
│       │   ├── gsm8k.py
│       │   ├── mmlu.py
│       │   └── ...             # arc, ifeval, ds1000, livecodebench,
│       │                       # mtbench, tool_calling, matric_cli,
│       │                       # matric_memory, custom, builtin
│       └── scorers/            # Scoring logic
│           ├── code_execution.py
│           ├── llm_judge.py
│           └── multidimensional.py
│
├── datasets/                   # JSONL test data
│   ├── custom/                 # App-specific tests
│   │   ├── matric-cli/
│   │   └── matric-memory/
│   └── <external>/             # Auto-discovered external datasets
│       ├── dataset.yaml        # Optional manifest
│       └── data.jsonl          # JSONL with input/target fields
│
├── bindings/                   # Language integrations
│   ├── typescript/             # npm package
│   │   ├── package.json
│   │   └── src/index.ts
│   └── rust/                   # Crate
│       ├── Cargo.toml
│       └── src/lib.rs
│
├── results/                    # Evaluation results (gitignored)
│   └── run-{timestamp}/
│       ├── meta.json
│       ├── state.json
│       └── {model}/...
│
└── tests/                      # pytest tests
    ├── test_state.py
    ├── test_recovery.py
    └── ...
```

## 3. Data Flow

### 3.1 Evaluation Flow Diagram

```
                                    START
                                      |
                                      v
+------------------------------------------------------------------+
|  1. DISCOVER MODELS                                               |
|     - Query Ollama API: GET /api/tags                            |
|     - Filter by MAX_MODEL_SIZE_GB                                |
|     - Return: list[Model]                                        |
+------------------------------------------------------------------+
                                      |
                                      v
+------------------------------------------------------------------+
|  2. INITIALIZE RUN                                                |
|     - Generate run_id: run-{timestamp}                           |
|     - Create results/run-{id}/meta.json                          |
|     - Create results/run-{id}/state.json                         |
|     - Acquire lock file                                          |
+------------------------------------------------------------------+
                                      |
                                      v
+------------------------------------------------------------------+
|  3. FOR EACH MODEL                                                |
|     +----------------------------------------------------------+ |
|     | 3a. Check state.json - already complete?                 | |
|     |     - YES: Skip to next model                            | |
|     |     - NO: Continue                                       | |
|     +----------------------------------------------------------+ |
|     |                                                          | |
|     | 3b. FOR EACH BENCHMARK                                   | |
|     |     +--------------------------------------------------+ | |
|     |     | Check benchmark state - complete?                | | |
|     |     |     - YES: Skip to next benchmark                | | |
|     |     |     - NO: Continue                               | | |
|     |     +--------------------------------------------------+ | |
|     |     |                                                  | | |
|     |     | FOR EACH PROBLEM (tier-limited)                  | | |
|     |     |     +------------------------------------------+ | | |
|     |     |     | 1. Load prompt from dataset              | | | |
|     |     |     | 2. Submit to Ollama via Inspect AI       | | | |
|     |     |     | 3. Collect response                      | | | |
|     |     |     | 4. Score response (custom scorer)        | | | |
|     |     |     | 5. Write problem result                  | | | |
|     |     |     | 6. Update benchmark state.json           | | | |
|     |     |     +------------------------------------------+ | | |
|     |     |                                                  | | |
|     |     | Compute benchmark score                          | | |
|     |     | Write benchmark summary                          | | |
|     |     +--------------------------------------------------+ | |
|     |                                                          | |
|     | Compute model score                                      | |
|     | Write model summary                                      | |
|     +----------------------------------------------------------+ |
+------------------------------------------------------------------+
                                      |
                                      v
+------------------------------------------------------------------+
|  4. RANK MODELS                                                   |
|     - Aggregate scores by capability                             |
|     - Filter top N per capability                                |
+------------------------------------------------------------------+
                                      |
                                      v
+------------------------------------------------------------------+
|  5. CUSTOM TESTS (optional, on top performers)                    |
|     - Load app-specific JSONL tests                              |
|     - Execute against top performers                             |
|     - Score with custom scorers                                  |
+------------------------------------------------------------------+
                                      |
                                      v
+------------------------------------------------------------------+
|  6. GENERATE CONFIG                                               |
|     - Map capability -> recommended model                        |
|     - Write model-categories.json                                |
+------------------------------------------------------------------+
                                      |
                                      v
                                     END
```

### 3.2 Resume Flow Diagram

```
                           matric-eval --resume run-{id}
                                      |
                                      v
+------------------------------------------------------------------+
|  1. LOAD RUN STATE                                                |
|     - Read results/run-{id}/meta.json                            |
|     - Read results/run-{id}/state.json                           |
|     - Verify lock file not held by another process               |
+------------------------------------------------------------------+
                                      |
                                      v
+------------------------------------------------------------------+
|  2. GAP DETECTION                                                 |
|     - Scan all model directories                                 |
|     - Check each benchmark state.json                            |
|     - Identify: incomplete models, incomplete benchmarks         |
|     - Build resume queue                                         |
+------------------------------------------------------------------+
                                      |
                                      v
+------------------------------------------------------------------+
|  3. RESUME EXECUTION                                              |
|     - Skip completed models/benchmarks                           |
|     - Resume from first incomplete problem                       |
|     - Continue normal evaluation flow                            |
+------------------------------------------------------------------+
```

### 3.3 State File Structure

```
results/run-2026-01-24T10-30-15/
├── meta.json                    # Immutable run configuration
│   {
│     "run_id": "run-2026-01-24T10-30-15",
│     "tier": "quick",
│     "seed": 42,
│     "models": ["llama3.2:3b", "codestral:22b"],
│     "benchmarks": ["humaneval", "mbpp", "gsm8k"],
│     "started_at": "2026-01-24T10:30:15Z",
│     "config": { ... }
│   }
│
├── state.json                   # Current run progress
│   {
│     "status": "running",
│     "current_model": "codestral:22b",
│     "current_benchmark": "mbpp",
│     "completed_models": ["llama3.2:3b"],
│     "updated_at": "2026-01-24T11:45:22Z"
│   }
│
├── lock                         # Lock file (empty, presence indicates active)
│
├── llama3.2:3b/                 # Completed model
│   ├── meta.json               # Model metadata (size, quant)
│   ├── state.json              # {"status": "completed", "benchmarks": {...}}
│   ├── summary.json            # Aggregated scores
│   ├── humaneval/
│   │   ├── state.json          # {"status": "completed", "score": 0.45}
│   │   └── problems/
│   │       ├── HE001.json      # Individual problem results
│   │       ├── HE002.json
│   │       └── ...
│   ├── mbpp/
│   │   └── ...
│   └── gsm8k/
│       └── ...
│
└── codestral:22b/               # In-progress model
    ├── meta.json
    ├── state.json              # {"status": "running", ...}
    ├── humaneval/              # Completed benchmark
    │   ├── state.json          # {"status": "completed", ...}
    │   └── problems/...
    └── mbpp/                   # In-progress benchmark
        ├── state.json          # {"status": "running", "completed": 45}
        └── problems/
            ├── MBPP001.json    # Completed
            ├── ...
            └── MBPP045.json    # Last completed
```

## 4. Technology Stack

### 4.1 Core Technologies

| Component | Technology | Version | Justification |
|-----------|------------|---------|---------------|
| **Language** | Python | 3.11+ | Evaluation framework ecosystem, type hints |
| **Package Manager** | uv | Latest | Modern, fast, reproducible |
| **Eval Framework** | Inspect AI | Latest | Native Ollama, agent evals (see ADR-002) |
| **Model Backend** | Ollama | Latest | Local LLM inference |
| **CLI Framework** | Click/Typer | Latest | Clean command-line interface |
| **Testing** | pytest | Latest | Standard Python testing |
| **Type Checking** | mypy | Latest | Static type safety |
| **Linting** | ruff | Latest | Fast, comprehensive linting |

### 4.2 Binding Technologies

| Binding | Technology | Distribution |
|---------|------------|--------------|
| **TypeScript** | Node subprocess | npm package |
| **Rust** | std::process | crates.io |

### 4.3 Data Formats

| Data Type | Format | Justification |
|-----------|--------|---------------|
| **Test datasets** | JSONL | Streaming, framework-compatible (see ADR-003) |
| **State files** | JSON | Human-readable, atomic updates |
| **Results** | JSON | Structured, queryable |
| **Reports** | Markdown | Human-readable summaries |

## 5. Integration Patterns

### 5.1 Ollama Integration

```
+-------------------+         +-------------------+
|   matric-eval     |  HTTP   |      Ollama       |
|                   |-------->|  localhost:11434  |
|   (Inspect AI)    |         |                   |
+-------------------+         +-------------------+

API Endpoints Used:
- GET  /api/tags          # List available models
- POST /api/generate      # Generate completion
- POST /api/chat          # Chat completion (if needed)
```

**Configuration**:
```python
# Environment variable for Ollama endpoint
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

# Inspect AI model syntax
model = "ollama/llama3.2:3b"
```

### 5.2 TypeScript Binding Pattern

```
+-------------------+         +-------------------+
|   matric-cli      | spawn   |   matric-eval     |
|   (TypeScript)    |-------->|   (Python CLI)    |
|                   |  stdout |                   |
|                   |<--------|   JSON results    |
+-------------------+         +-------------------+
```

**TypeScript Interface**:
```typescript
interface EvalOptions {
  tier: 'smoke' | 'quick' | 'full';
  models?: string[];
  benchmarks?: string[];
}

interface EvalResult {
  runId: string;
  status: 'completed' | 'failed';
  models: ModelResult[];
}

async function evaluate(options: EvalOptions): Promise<EvalResult> {
  const proc = spawn('matric-eval', ['--tier', options.tier, '--json']);
  // Stream stdout, parse JSON results
}
```

### 5.3 Rust Binding Pattern

```rust
pub struct EvalOptions {
    pub tier: Tier,
    pub models: Option<Vec<String>>,
    pub benchmarks: Option<Vec<String>>,
}

pub async fn evaluate(options: EvalOptions) -> Result<EvalResult, Error> {
    let output = Command::new("matric-eval")
        .args(["--tier", &options.tier.to_string(), "--json"])
        .output()
        .await?;

    serde_json::from_slice(&output.stdout)
}
```

## 6. Security Architecture

### 6.1 Security Posture

**Level**: Baseline (internal development tool)

**Rationale**: No PII, no user authentication, no network exposure. Code execution is sandboxed by Ollama.

### 6.2 Security Controls

| Control | Implementation |
|---------|----------------|
| **Authentication** | None required (local CLI) |
| **Authorization** | File system permissions |
| **Data Protection** | No encryption (public datasets) |
| **Secrets** | Environment variables for Ollama endpoint |
| **Code Execution** | Ollama sandbox + problem timeouts |
| **Dependencies** | SBOM via uv.lock, CI scanning |

### 6.3 Execution Safety

```python
# Per-problem timeout to prevent runaway inference
PROBLEM_TIMEOUT_SECONDS = {
    'humaneval': 60,
    'mbpp': 60,
    'gsm8k': 30,
    'arc': 30,
}

# Code execution (if not using Ollama sandbox)
def safe_execute(code: str, test: str, timeout: int = 30) -> ExecutionResult:
    # Subprocess with timeout, no network, memory limit
    ...
```

## 7. Deployment Architecture

### 7.1 Local Development

```
Developer Machine
├── Ollama (localhost:11434)
├── matric-eval (installed via uv/pip)
├── datasets/ (symlinked or downloaded)
└── results/ (local evaluation output)
```

### 7.2 CI/CD Pipeline

```
CI Runner (GitHub Actions / GitLab CI)
│
├── Stage: Lint & Type Check
│   - ruff check
│   - mypy
│
├── Stage: Unit Tests
│   - pytest (mocked Ollama)
│
├── Stage: Integration Test (with Ollama)
│   - Start Ollama container
│   - Run smoke evaluation (5 samples)
│   - Verify checkpoint/resume
│
└── Stage: Publish
    - Build wheel
    - Publish to PyPI
    - Build npm package
    - Publish to npm
    - Build crate
    - Publish to crates.io
```

### 7.3 Distribution

| Target | Package | Installation |
|--------|---------|--------------|
| **Python** | matric-eval | `uv add matric-eval` or `pip install matric-eval` |
| **TypeScript** | @matric/eval | `npm install @matric/eval` |
| **Rust** | matric-eval | `cargo add matric-eval` |

## 8. Scalability Considerations

### 8.1 Current Scope (v1.0)

- Single machine execution
- Sequential model evaluation
- Parallel problem execution within benchmark (if framework supports)
- File system state storage

### 8.2 Future Scalability (v2.0+)

| Capability | Approach |
|------------|----------|
| **Multi-model parallel** | Separate Ollama instances per model |
| **Distributed evaluation** | Message queue (Redis/RabbitMQ) for task distribution |
| **Result aggregation** | SQLite/PostgreSQL for historical tracking |
| **Large dataset streaming** | JSONL streaming, chunked processing |

## 9. Monitoring and Observability

### 9.1 Logging

```python
# Structured logging for CI parsing
import logging
import json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "model": getattr(record, 'model', None),
            "benchmark": getattr(record, 'benchmark', None),
            "problem": getattr(record, 'problem', None),
        })
```

### 9.2 Progress Reporting

```
$ matric-eval --tier quick

[10:30:15] Starting evaluation run-2026-01-24T10-30-15
[10:30:15] Tier: quick (75 samples per benchmark)
[10:30:15] Models: llama3.2:3b, codestral:22b
[10:30:15] Benchmarks: humaneval, mbpp, gsm8k

[10:30:16] llama3.2:3b | humaneval [==========] 75/75 (100%) | Score: 0.45
[10:31:42] llama3.2:3b | mbpp      [======    ] 45/75 (60%)  | ETA: 2m
```

### 9.3 Health Checks

```bash
# Validate run completeness
matric-eval --validate run-2026-01-24T10-30-15

# Output:
# Run: run-2026-01-24T10-30-15
# Status: incomplete
#
# Gaps detected:
# - codestral:22b / mbpp: 30/75 problems remaining
# - codestral:22b / gsm8k: not started
#
# Resume with: matric-eval --resume run-2026-01-24T10-30-15
```

## 10. Key Architectural Decisions

See individual ADR documents for detailed rationale:

| ADR | Decision | Status |
|-----|----------|--------|
| [ADR-001](ADR-001-python-core-with-bindings.md) | Python core with language bindings | Accepted |
| [ADR-002](ADR-002-inspect-ai-framework.md) | Inspect AI as evaluation framework | Proposed |
| [ADR-003](ADR-003-jsonl-test-format.md) | JSONL as universal test format | Accepted |
| [ADR-004](ADR-004-tiered-evaluation.md) | Tiered evaluation (smoke/quick/full) | Accepted |
| [ADR-005](ADR-005-checkpoint-resume-design.md) | Checkpoint/resume state management | Accepted |

## 11. References

- [PLANNING.md](/home/roctinam/dev/matric-eval/PLANNING.md) - Project planning document
- [Inspect AI Documentation](https://inspect.aisi.org.uk/)
- [Ollama API Reference](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [matric-cli evaluation code](/home/roctinam/dev/matric-cli/source/eval/)
- [matric-memory evaluation code](/home/roctinam/dev/matric-memory/crates/matric-inference/src/bin/eval.rs)
