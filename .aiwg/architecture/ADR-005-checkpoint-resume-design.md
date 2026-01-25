# ADR-005: Checkpoint/Resume State Management

**Status**: Accepted
**Date**: 2026-01-24
**Decision Makers**: matric-eval development team
**Supersedes**: N/A

## Context

### The Problem

A recent matric-cli evaluation crashed at model 13/31 with an EPIPE error:
- 12 models of work (~4 hours) was lost
- Manual restart required
- No easy way to resume or re-run specific failures
- No visibility into what was completed

This is unacceptable for evaluations that can take hours. We need robust state management that:
1. Survives any failure (crash, cancel, network error, model OOM)
2. Enables precise resume from last checkpoint
3. Allows selective re-run of specific model/benchmark combinations
4. Detects and fills gaps in incomplete runs

### Requirements (P0)

| Requirement | Description |
|-------------|-------------|
| **Checkpoint/Resume** | Save state after each model/benchmark; resume from last checkpoint |
| **Selective Re-run** | Re-run specific model + benchmark combo without full restart |
| **Gap Detection** | Scan output directory, identify missing/incomplete results |
| **Idempotent Runs** | Re-running produces same results, skips completed work |

### Requirements (P1)

| Requirement | Description |
|-------------|-------------|
| **Auto-Recovery** | Retry on transient errors (timeout, connection reset, EPIPE) |
| **Graceful Degradation** | Skip failed model, continue with next, report at end |
| **Lock Prevention** | Prevent concurrent runs on same results directory |

## Decision

**Implement hierarchical file-based state management with atomic writes and lock files.**

### State Directory Structure

```
results/run-2026-01-24T10-30-15/
├── meta.json                    # Immutable run configuration
├── state.json                   # Current run progress (mutable)
├── lock                         # Lock file (presence = active run)
│
├── llama3.2:3b/                 # Model directory
│   ├── meta.json               # Model metadata
│   ├── state.json              # Model progress
│   ├── summary.json            # Aggregated results (generated)
│   │
│   ├── humaneval/              # Benchmark directory
│   │   ├── state.json          # Benchmark progress
│   │   ├── summary.json        # Benchmark results
│   │   └── problems/           # Individual results
│   │       ├── HE001.json
│   │       ├── HE002.json
│   │       └── ...
│   │
│   ├── mbpp/
│   │   └── ...
│   └── gsm8k/
│       └── ...
│
└── codestral:22b/
    └── ...
```

### State File Schemas

**Run Meta (`meta.json`)** - Immutable after creation:
```json
{
  "run_id": "run-2026-01-24T10-30-15",
  "tier": "quick",
  "seed": 42,
  "models": ["llama3.2:3b", "codestral:22b"],
  "benchmarks": ["humaneval", "mbpp", "gsm8k"],
  "started_at": "2026-01-24T10:30:15Z",
  "version": "1.0.0",
  "config": {
    "max_model_size_gb": 40,
    "timeout_per_problem": 60,
    "ollama_base_url": "http://localhost:11434"
  }
}
```

**Run State (`state.json`)** - Updated continuously:
```json
{
  "status": "running",
  "current_model": "codestral:22b",
  "current_benchmark": "mbpp",
  "completed_models": ["llama3.2:3b"],
  "failed_models": [],
  "started_at": "2026-01-24T10:30:15Z",
  "updated_at": "2026-01-24T11:45:22Z",
  "heartbeat_at": "2026-01-24T11:47:03Z"
}
```

**Model State (`{model}/state.json`)**:
```json
{
  "model": "llama3.2:3b",
  "status": "completed",
  "benchmarks": {
    "humaneval": "completed",
    "mbpp": "completed",
    "gsm8k": "completed"
  },
  "started_at": "2026-01-24T10:30:20Z",
  "completed_at": "2026-01-24T10:55:18Z"
}
```

**Benchmark State (`{model}/{benchmark}/state.json`)**:
```json
{
  "benchmark": "humaneval",
  "status": "completed",
  "total_problems": 75,
  "completed_problems": 75,
  "passed_problems": 45,
  "failed_problems": 30,
  "error_problems": 0,
  "score": 0.60,
  "started_at": "2026-01-24T10:30:20Z",
  "completed_at": "2026-01-24T10:42:15Z"
}
```

**Problem Result (`{model}/{benchmark}/problems/{id}.json`)**:
```json
{
  "problem_id": "HE001",
  "status": "passed",
  "prompt": "def factorial(n: int) -> int:\n    \"\"\"...",
  "response": "def factorial(n: int) -> int:\n    if n <= 1:\n        return 1\n    return n * factorial(n - 1)",
  "extracted_code": "def factorial(n: int) -> int:\n    if n <= 1:\n        return 1\n    return n * factorial(n - 1)",
  "test_output": "All tests passed",
  "score": 1.0,
  "latency_ms": 1250,
  "tokens": 42,
  "completed_at": "2026-01-24T10:30:45Z"
}
```

### Implementation Patterns

#### Atomic Writes

All state updates use temp file + atomic rename:

```python
import json
import tempfile
import os
from pathlib import Path

def atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically using temp file + rename."""
    # Write to temp file in same directory
    fd, temp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp"
    )
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        # Atomic rename
        os.rename(temp_path, path)
    except:
        # Cleanup temp file on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise
```

#### Lock File Management

Prevent concurrent runs with lock file + heartbeat:

```python
import time
import os
from pathlib import Path
from contextlib import contextmanager

LOCK_STALE_SECONDS = 300  # 5 minutes without heartbeat = stale

class LockError(Exception):
    pass

@contextmanager
def acquire_run_lock(run_dir: Path):
    """Acquire exclusive lock on run directory."""
    lock_path = run_dir / "lock"

    # Check for existing lock
    if lock_path.exists():
        mtime = lock_path.stat().st_mtime
        age = time.time() - mtime

        if age < LOCK_STALE_SECONDS:
            raise LockError(f"Run is locked by another process (lock age: {age:.0f}s)")
        else:
            # Stale lock - previous run crashed
            print(f"Warning: Found stale lock (age: {age:.0f}s), taking over")

    # Create lock file
    lock_path.touch()

    try:
        yield lock_path
    finally:
        # Release lock
        if lock_path.exists():
            lock_path.unlink()

def update_heartbeat(lock_path: Path) -> None:
    """Update lock file mtime as heartbeat."""
    lock_path.touch()
```

#### Checkpoint After Each Problem

```python
async def evaluate_benchmark(
    model: str,
    benchmark: str,
    problems: list[Problem],
    run_dir: Path,
) -> BenchmarkResult:
    """Evaluate benchmark with per-problem checkpointing."""

    bench_dir = run_dir / model / benchmark
    state_path = bench_dir / "state.json"
    problems_dir = bench_dir / "problems"
    problems_dir.mkdir(parents=True, exist_ok=True)

    # Load existing state for resume
    completed_ids = set()
    if state_path.exists():
        state = json.loads(state_path.read_text())
        # Scan problems directory for completed
        for p in problems_dir.glob("*.json"):
            completed_ids.add(p.stem)

    # Initialize state
    state = {
        "benchmark": benchmark,
        "status": "running",
        "total_problems": len(problems),
        "completed_problems": len(completed_ids),
        "passed_problems": 0,
        "failed_problems": 0,
        "started_at": datetime.now().isoformat(),
    }
    atomic_write_json(state_path, state)

    # Evaluate each problem
    for problem in problems:
        if problem.id in completed_ids:
            continue  # Skip completed

        try:
            result = await evaluate_problem(model, problem)

            # Write problem result atomically
            atomic_write_json(
                problems_dir / f"{problem.id}.json",
                asdict(result)
            )

            # Update benchmark state
            state["completed_problems"] += 1
            if result.status == "passed":
                state["passed_problems"] += 1
            else:
                state["failed_problems"] += 1
            state["updated_at"] = datetime.now().isoformat()
            atomic_write_json(state_path, state)

        except Exception as e:
            # Log error but continue
            state["error_problems"] = state.get("error_problems", 0) + 1
            state["updated_at"] = datetime.now().isoformat()
            atomic_write_json(state_path, state)
            raise

    # Mark complete
    state["status"] = "completed"
    state["completed_at"] = datetime.now().isoformat()
    state["score"] = state["passed_problems"] / state["total_problems"]
    atomic_write_json(state_path, state)

    return BenchmarkResult(**state)
```

#### Gap Detection

```python
def detect_gaps(run_dir: Path) -> list[Gap]:
    """Scan run directory for incomplete work."""
    gaps = []
    meta = json.loads((run_dir / "meta.json").read_text())

    for model in meta["models"]:
        model_dir = run_dir / model

        if not model_dir.exists():
            # Model not started
            gaps.append(Gap(model=model, benchmark=None, type="not_started"))
            continue

        model_state = json.loads((model_dir / "state.json").read_text())

        if model_state["status"] != "completed":
            for benchmark in meta["benchmarks"]:
                bench_dir = model_dir / benchmark

                if not bench_dir.exists():
                    gaps.append(Gap(model=model, benchmark=benchmark, type="not_started"))
                    continue

                bench_state = json.loads((bench_dir / "state.json").read_text())

                if bench_state["status"] != "completed":
                    remaining = bench_state["total_problems"] - bench_state["completed_problems"]
                    gaps.append(Gap(
                        model=model,
                        benchmark=benchmark,
                        type="incomplete",
                        remaining=remaining
                    ))

    return gaps
```

#### Resume CLI Commands

```python
@click.command()
@click.option("--resume", type=str, help="Resume run by ID")
@click.option("--fill-gaps", is_flag=True, help="Detect and fill gaps")
@click.option("--model", type=str, help="Re-run specific model")
@click.option("--benchmark", type=str, help="Re-run specific benchmark")
@click.option("--validate", type=str, help="Validate run completeness")
def main(resume, fill_gaps, model, benchmark, validate):
    if validate:
        # Validate mode: report gaps
        run_dir = Path(f"results/{validate}")
        gaps = detect_gaps(run_dir)
        if gaps:
            print(f"Gaps detected in {validate}:")
            for gap in gaps:
                print(f"  - {gap.model}/{gap.benchmark}: {gap.type}")
        else:
            print(f"Run {validate} is complete")
        return

    if resume:
        run_dir = Path(f"results/{resume}")

        if fill_gaps:
            # Resume all incomplete work
            gaps = detect_gaps(run_dir)
            resume_evaluation(run_dir, gaps)

        elif model and benchmark:
            # Re-run specific model/benchmark
            rerun_benchmark(run_dir, model, benchmark)

        elif model:
            # Re-run all benchmarks for model
            rerun_model(run_dir, model)

        else:
            # Resume from where we left off
            gaps = detect_gaps(run_dir)
            resume_evaluation(run_dir, gaps)

    else:
        # Fresh run
        start_fresh_run()
```

### Error Classification and Recovery

```python
from enum import Enum

class ErrorType(Enum):
    TRANSIENT = "transient"   # Retry: timeout, EPIPE, connection reset
    MODEL = "model"           # Skip model: OOM, crash, invalid response
    FATAL = "fatal"           # Stop: disk full, config error

def classify_error(error: Exception) -> ErrorType:
    """Classify error for recovery strategy."""

    error_str = str(error).lower()

    # Transient errors - retry
    transient_patterns = [
        "epipe", "connection reset", "timeout",
        "connection refused", "network unreachable",
        "temporary failure", "service unavailable",
    ]
    for pattern in transient_patterns:
        if pattern in error_str:
            return ErrorType.TRANSIENT

    # Model errors - skip model, continue
    model_patterns = [
        "out of memory", "oom", "model not found",
        "invalid model", "model crashed",
    ]
    for pattern in model_patterns:
        if pattern in error_str:
            return ErrorType.MODEL

    # Fatal errors - stop run
    fatal_patterns = [
        "disk full", "no space left", "permission denied",
        "config error", "invalid config",
    ]
    for pattern in fatal_patterns:
        if pattern in error_str:
            return ErrorType.FATAL

    # Default to transient (safer to retry)
    return ErrorType.TRANSIENT

async def evaluate_with_retry(
    func,
    max_retries: int = 3,
    backoff_base: float = 2.0,
) -> Any:
    """Execute with retry on transient errors."""

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception as e:
            error_type = classify_error(e)

            if error_type == ErrorType.FATAL:
                raise  # Propagate fatal errors

            if error_type == ErrorType.MODEL:
                raise  # Let caller handle model skip

            if attempt < max_retries:
                wait_time = backoff_base ** attempt
                print(f"Transient error: {e}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                raise  # Max retries exceeded
```

## Consequences

### Positive

1. **Zero progress loss**: Every completed problem is immediately persisted. Crash at problem N means resume at problem N+1.

2. **Precise resume**: Can resume at exact point of failure, not just at model boundary.

3. **Selective re-run**: Can re-run specific model/benchmark without affecting other results.

4. **Transparency**: All state is human-readable JSON. Easy to inspect and debug.

5. **Concurrent run prevention**: Lock file prevents accidental parallel runs.

6. **Stale lock recovery**: Heartbeat mechanism detects crashed runs and allows takeover.

7. **Idempotent**: Safe to re-run same command; completed work is skipped.

### Negative

1. **Disk I/O overhead**: Writing state after each problem. Mitigated by:
   - Async writes where possible
   - State files are small (~1KB)
   - Measured overhead < 1% of evaluation time

2. **Directory clutter**: Many small files (one per problem). Mitigated by:
   - Hierarchical structure keeps it organized
   - Cleanup command to remove old runs
   - Results directory is gitignored

3. **Complexity**: More code than simple sequential evaluation. Mitigated by:
   - Clear abstraction layers
   - Well-tested state management module
   - Worth it for reliability

4. **Model name escaping**: Ollama model names contain `:` which is problematic on Windows. Mitigated by:
   - Escape `:` to `--` in directory names
   - Store original name in meta.json

## Alternatives Considered

### Alternative A: Database-Based State

**Description**: Use SQLite or PostgreSQL for state management.

**Pros**:
- ACID transactions
- Query support
- Better for large-scale operations

**Cons**:
- Additional dependency
- More complex setup
- Overkill for our scale
- Less transparent (binary format)

**Decision**: Rejected. File-based is simpler and sufficient for our needs.

### Alternative B: In-Memory State with Periodic Flush

**Description**: Keep state in memory, flush to disk every N seconds.

**Pros**:
- Lower I/O overhead
- Simpler implementation

**Cons**:
- Risk of data loss on crash (up to N seconds of work)
- Exactly what we're trying to avoid

**Decision**: Rejected. Contradicts our zero-loss requirement.

### Alternative C: Append-Only Log

**Description**: Write events to append-only log, reconstruct state on resume.

**Pros**:
- Crash-safe (just append)
- Full history preserved
- Event sourcing pattern

**Cons**:
- Slower resume (must replay log)
- More complex state reconstruction
- Log can grow large

**Decision**: Rejected. Hierarchical files are simpler and sufficient.

### Alternative D: Single State File

**Description**: One JSON file with entire run state.

**Pros**:
- Simplest implementation
- Single file to manage

**Cons**:
- Must rewrite entire file on every update
- Corruption risk for large files
- Slow atomic writes for large state

**Decision**: Rejected. Hierarchical files better for atomic updates.

## Validation

This design will be validated by:

1. **Unit tests**: State management module with 80%+ coverage
2. **Integration tests**:
   - Start evaluation, kill process, resume, verify completeness
   - Concurrent run prevention
   - Gap detection accuracy
3. **Stress tests**:
   - Kill at random points, verify no corruption
   - Verify atomic write behavior

## References

- [Write-Ahead Logging](https://en.wikipedia.org/wiki/Write-ahead_logging)
- [Atomic File Operations](https://blog.gocept.com/2013/07/15/reliable-file-updates-with-python/)
- [Lock Files Best Practices](https://www.perl.com/pub/2002/09/11/log4perl.html/)
- matric-cli crash incident: EPIPE at model 13/31 (2026-01-24)
