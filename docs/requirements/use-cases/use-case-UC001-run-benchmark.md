# Use Case UC001: Run Benchmark Evaluation

**Document ID**: REQ-UC-001
**Version**: 1.0
**Date**: 2026-01-24
**Status**: Planning Phase
**Priority**: P1 - Critical

## Use Case Overview

| Attribute | Value |
|-----------|-------|
| Use Case ID | UC001 |
| Use Case Name | Run Benchmark Evaluation |
| Created By | Claude Opus 4.5 |
| Created Date | 2026-01-24 |
| Last Updated | 2026-01-24 |
| Priority | P1 - Critical |
| Complexity | High |

## Traceability

**Traced to Gitea Issues**:
- #1: Add code execution scoring for HumanEval and MBPP
- #2: Integrate inspect-evals for public benchmarks
- #3: Implement IFEval constraint checking scorer
- #4: Implement LiveCodeBench competitive programming scorer
- #5: Implement DS-1000 data science scorer
- #6: Implement tiered CLI with smoke/quick/full modes
- #10: Implement 5-dimensional scoring framework

**Traced to Business Requirements**:
- BR-002: Evaluation Accuracy
- BR-003: Resource Efficiency

## Actors

### Primary Actor

**Developer/Researcher**: Person evaluating Ollama models for selection or benchmarking purposes.

**Role**: Initiates evaluation, interprets results, makes model selection decisions.

**Characteristics**:
- Familiar with command-line tools
- Understands model evaluation concepts
- Needs reproducible, accurate results
- Time-constrained (prefers faster tiers for iteration)

### Secondary Actors

**Ollama Service**: Local Ollama server providing model inference.

**Role**: Executes model inference requests, returns completions.

**Characteristics**:
- Running at localhost:11434
- Models already pulled/available
- Handles concurrent requests
- Provides streaming responses

**Evaluation Framework (Inspect AI)**: Underlying evaluation orchestration system.

**Role**: Manages task execution, scoring, and result aggregation.

**Characteristics**:
- Executes evaluation tasks
- Applies scorers to model outputs
- Collects metrics and generates reports

### Supporting Actors

**CI/CD Pipeline**: Automated system running smoke tests on code changes.

**File System**: Storage for datasets, checkpoints, and results.

**Sandbox Environment**: Isolated execution context for code evaluation.

## Preconditions

### System State

1. **Ollama Service Running**: Ollama server accessible at localhost:11434
2. **Model Available**: Target model(s) pulled and ready (e.g., `llama3.2:3b`)
3. **matric-eval Installed**: Python environment with `uv sync` completed
4. **Datasets Present**: Public benchmark data at `/home/roctinam/data/evals/` (for full evaluations)
5. **Sufficient Resources**: Adequate RAM (16GB+), disk space (10GB+), and CPU

### User State

1. **Authentication**: User has access to local Ollama instance
2. **Permissions**: Read access to datasets, write access to output directory
3. **Knowledge**: Understands tier selection (smoke/quick/full)

### Data State

1. **Benchmark Datasets**: Valid, uncorrupted benchmark files
2. **Configuration**: Default or custom evaluation config available
3. **Output Directory**: Writable location for results

## Postconditions

### Success Postconditions

1. **Evaluation Complete**: All selected benchmarks executed successfully
2. **Results Generated**: JSON report with scores, metrics, and metadata
3. **Artifacts Preserved**: Generated code, model outputs, and intermediate results saved
4. **Exit Code 0**: Process completes without errors
5. **Reproducible State**: Seeded random ensures same results on repeat execution

### Failure Postconditions

1. **Partial Results**: Any completed benchmarks are saved (if checkpoint enabled)
2. **Error Log**: Detailed error message and stack trace written to log
3. **Exit Code Non-Zero**: Indicates failure type (1=validation, 2=runtime, 3=resource)
4. **System State Unchanged**: No corruption of datasets or configuration

## Main Success Scenario

### Tier: Smoke (Fast Validation)

**Goal**: Quickly verify model is functional and meets minimum quality bar.

**Duration**: <5 minutes

**Steps**:

1. **Invoke CLI**: User executes `matric-eval --tier smoke --model llama3.2:3b`
2. **Validate Inputs**: System checks Ollama connectivity, model availability
3. **Load Smoke Suite**: System selects 10 HumanEval + 10 MBPP samples (seeded random)
4. **Execute HumanEval**:
   - Generate code completions from function signatures
   - Extract code from markdown fences
   - Execute in sandbox with timeout (5s per test)
   - Score with pass@1 metric
5. **Execute MBPP**:
   - Extract function name from test assertions
   - Include function name in prompt
   - Generate code completions
   - Execute tests in sandbox
   - Score with pass@1 metric
6. **Aggregate Scores**: Calculate weighted average (50% HumanEval, 50% MBPP)
7. **Generate Report**: Create JSON with scores, timing, and sample outputs
8. **Display Summary**: Print pass rates and total duration to console
9. **Exit Successfully**: Return code 0 if pass rate >40%, code 1 if below threshold

**Expected Output**:
```json
{
  "model": "llama3.2:3b",
  "tier": "smoke",
  "duration_seconds": 180,
  "benchmarks": {
    "humaneval": {
      "pass_at_1": 0.50,
      "samples": 10,
      "passed": 5,
      "failed": 5
    },
    "mbpp": {
      "pass_at_1": 0.60,
      "samples": 10,
      "passed": 6,
      "failed": 4
    }
  },
  "overall_score": 0.55,
  "timestamp": "2026-01-24T10:30:00Z",
  "seed": 42
}
```

### Tier: Quick (Common Use Cases)

**Goal**: Evaluate model across representative tasks for selection decisions.

**Duration**: <30 minutes

**Steps**:

1. **Invoke CLI**: User executes `matric-eval --tier quick --model llama3.2:3b`
2. **Validate Inputs**: System checks Ollama connectivity, model availability
3. **Load Quick Suite**: System selects:
   - 50 HumanEval samples (30% of full dataset)
   - 100 MBPP samples (10% of full dataset)
   - 50 GSM8K samples (math reasoning)
   - 20 IFEval samples (instruction following)
4. **Execute Code Benchmarks** (HumanEval, MBPP):
   - Generate completions with temperature=0.2
   - Extract code with markdown fence handling
   - Execute in sandbox (timeout: 10s per test)
   - Preserve artifacts (generatedCode field)
   - Score with pass@1 metric
5. **Execute GSM8K**:
   - Generate solutions with chain-of-thought
   - Extract final numerical answer
   - Compare against reference answer
   - Score with exact match
6. **Execute IFEval**:
   - Generate responses to instructions with constraints
   - Apply constraint checking scorer (e.g., "use word X at least 3 times")
   - Score with constraint satisfaction rate
7. **Calculate 5-Dimensional Scores**:
   - Accuracy: Pass rates across benchmarks
   - Efficiency: Tokens per solution
   - Reasoning: GSM8K chain quality
   - Instruction Following: IFEval constraint adherence
   - Code Quality: Syntax errors, style issues
8. **Generate Detailed Report**: JSON with per-benchmark scores, distributions, and samples
9. **Display Recommendations**: Suggest model suitability for use cases
10. **Exit Successfully**: Return code 0

**Expected Output**:
```json
{
  "model": "llama3.2:3b",
  "tier": "quick",
  "duration_seconds": 1200,
  "benchmarks": {
    "humaneval": {
      "pass_at_1": 0.48,
      "samples": 50,
      "avg_tokens": 150,
      "syntax_errors": 3
    },
    "mbpp": {
      "pass_at_1": 0.55,
      "samples": 100,
      "avg_tokens": 120,
      "function_name_preserved": true
    },
    "gsm8k": {
      "exact_match": 0.42,
      "samples": 50,
      "chain_of_thought_quality": 0.75
    },
    "ifeval": {
      "constraint_satisfaction": 0.68,
      "samples": 20,
      "strict_compliance": 0.55
    }
  },
  "dimensions": {
    "accuracy": 0.53,
    "efficiency": 0.72,
    "reasoning": 0.58,
    "instruction_following": 0.68,
    "code_quality": 0.64
  },
  "recommendations": {
    "suitable_for": ["scripting", "simple_automation"],
    "not_suitable_for": ["production_code", "complex_algorithms"]
  },
  "timestamp": "2026-01-24T11:00:00Z",
  "seed": 42
}
```

### Tier: Full (Comprehensive Evaluation)

**Goal**: Exhaustive evaluation across all benchmarks for publication-quality results.

**Duration**: 2-4 hours (depending on model speed)

**Steps**:

1. **Invoke CLI**: User executes `matric-eval --tier full --model llama3.2:3b --output results/llama3.2-3b.json`
2. **Validate Inputs**: System checks Ollama connectivity, model availability, dataset integrity
3. **Load Full Suite**: System includes:
   - 164 HumanEval samples (100%)
   - 974 MBPP samples (100%)
   - 1,319 GSM8K samples (100%)
   - 541 IFEval samples (100%)
   - 100 LiveCodeBench samples (competitive programming)
   - 100 DS-1000 samples (data science)
4. **Enable Checkpointing**: Initialize checkpoint file at `/tmp/matric-eval-<uuid>.checkpoint`
5. **Execute Benchmarks in Parallel** (if `--parallel` flag set):
   - Process pool with N workers (default: CPU count / 2)
   - Each worker executes independent samples
   - Results aggregated in thread-safe manner
6. **Execute Code Benchmarks** (HumanEval, MBPP, LiveCodeBench, DS-1000):
   - Generate completions with temperature=0.2
   - Extract code with language tag handling
   - Execute in Docker sandbox (timeout: 30s per test)
   - Capture stdout, stderr, exit codes
   - Preserve all artifacts (prompts, completions, execution results)
   - Score with pass@1, pass@10, pass@100 metrics
7. **Execute Reasoning Benchmarks** (GSM8K):
   - Generate solutions with chain-of-thought
   - Extract final answer with regex patterns
   - Compare against reference with fuzzy matching
   - Score with exact match and partial credit
8. **Execute Instruction Following** (IFEval):
   - Generate responses to 25+ constraint types
   - Apply strict and loose constraint checking
   - Score with constraint satisfaction and violation analysis
9. **Calculate Comprehensive Metrics**:
   - 5-dimensional scoring (accuracy, efficiency, reasoning, instruction following, code quality)
   - Per-category breakdowns (e.g., loops, recursion, string manipulation)
   - Difficulty stratification (easy, medium, hard)
   - Token usage statistics
   - Latency percentiles (p50, p95, p99)
10. **Generate Publication Report**: JSON with full details, HTML summary, CSV export
11. **Checkpoint Cleanup**: Remove checkpoint file on success
12. **Display Executive Summary**: Print key metrics and comparison to reference models
13. **Exit Successfully**: Return code 0

**Expected Output** (abbreviated):
```json
{
  "model": "llama3.2:3b",
  "tier": "full",
  "duration_seconds": 7200,
  "benchmarks": {
    "humaneval": {
      "pass_at_1": 0.451,
      "pass_at_10": 0.623,
      "pass_at_100": 0.782,
      "samples": 164,
      "by_difficulty": {
        "easy": 0.68,
        "medium": 0.42,
        "hard": 0.21
      }
    },
    "mbpp": {
      "pass_at_1": 0.542,
      "samples": 974,
      "by_category": {
        "string_manipulation": 0.61,
        "list_operations": 0.58,
        "math": 0.49,
        "algorithms": 0.32
      }
    },
    "gsm8k": {
      "exact_match": 0.387,
      "partial_credit": 0.512,
      "samples": 1319
    },
    "ifeval": {
      "strict_compliance": 0.623,
      "loose_compliance": 0.741,
      "samples": 541
    },
    "livecodebench": {
      "pass_at_1": 0.210,
      "samples": 100
    },
    "ds1000": {
      "pass_at_1": 0.340,
      "samples": 100
    }
  },
  "dimensions": {
    "accuracy": 0.426,
    "efficiency": 0.701,
    "reasoning": 0.512,
    "instruction_following": 0.682,
    "code_quality": 0.589
  },
  "performance": {
    "latency_p50_ms": 1200,
    "latency_p95_ms": 3400,
    "latency_p99_ms": 5800,
    "avg_tokens_per_completion": 145,
    "total_tokens": 412000
  },
  "timestamp": "2026-01-24T15:00:00Z",
  "seed": 42
}
```

## Extensions and Alternate Flows

### Extension 1a: Ollama Service Unavailable

**Trigger**: Step 2 detects Ollama not running.

**Steps**:
1. System logs error: "Ollama service not reachable at localhost:11434"
2. Display user-friendly message: "Please start Ollama with 'ollama serve'"
3. Exit with code 2 (configuration error)

**Postcondition**: No evaluation attempted, clear guidance provided.

### Extension 1b: Model Not Available

**Trigger**: Step 2 detects model not pulled.

**Steps**:
1. System logs error: "Model 'llama3.2:3b' not found in Ollama"
2. Display available models: "Available: llama3.2:1b, codellama:7b, ..."
3. Optionally prompt: "Pull model with 'ollama pull llama3.2:3b'? (y/n)"
4. If user confirms, execute pull and retry
5. If user declines, exit with code 2

**Postcondition**: Model available or user informed of manual action required.

### Extension 2a: Dataset Missing

**Trigger**: Step 3 (full tier) cannot find benchmark dataset.

**Steps**:
1. System logs error: "Dataset not found: /home/roctinam/data/evals/humaneval/"
2. Check if using embedded minimal dataset (for smoke/quick)
3. If embedded available, use embedded dataset with warning
4. If not available, exit with code 2 and download instructions

**Postcondition**: Graceful degradation or clear error.

### Extension 3a: Sample Execution Timeout

**Trigger**: Individual test exceeds timeout during step 4/5.

**Steps**:
1. Sandbox kills process after timeout (5s smoke, 10s quick, 30s full)
2. Mark sample as "timeout" with partial score (0.0)
3. Log timeout event with sample ID and generated code
4. Continue to next sample
5. Include timeout count in final report

**Postcondition**: Evaluation continues, timeout counted as failure.

### Extension 3b: Sandbox Execution Error

**Trigger**: Code execution raises exception (syntax error, runtime error).

**Steps**:
1. Sandbox captures exception details (type, message, traceback)
2. Mark sample as "runtime_error" with score 0.0
3. Preserve error details in artifacts
4. Log error with sample ID
5. Continue to next sample
6. Include error breakdown in final report (syntax vs. runtime vs. timeout)

**Postcondition**: Error categorized, evaluation continues.

### Extension 3c: Code Extraction Failure

**Trigger**: Cannot extract code from model output (no markdown fences, malformed response).

**Steps**:
1. Apply fallback extraction heuristics:
   - Try language tags: ```python, ```py, ```
   - Try indentation-based extraction
   - Try raw output if single function
2. If all heuristics fail, mark as "extraction_error"
3. Log extraction failure with raw output
4. Score as 0.0
5. Continue to next sample

**Postcondition**: Extraction failure handled gracefully.

### Extension 4a: Resource Exhaustion

**Trigger**: System runs out of memory or disk space during evaluation.

**Steps**:
1. Monitor resource usage (memory, disk) periodically
2. If memory >90% utilized, trigger garbage collection
3. If memory still >95%, pause evaluation and checkpoint
4. Display warning: "Resource constraints detected, checkpointing..."
5. Save checkpoint and exit with code 3 (resource error)
6. Provide resume instructions

**Postcondition**: State preserved, resume possible after resource freed.

### Extension 5a: Interrupted Evaluation (Ctrl+C)

**Trigger**: User sends SIGINT during evaluation.

**Steps**:
1. Catch signal gracefully
2. Display message: "Interrupt received, saving checkpoint..."
3. Save current progress to checkpoint file
4. Complete current sample (don't abort mid-execution)
5. Exit with code 130 (SIGINT)
6. Print resume command: "Resume with: matric-eval --resume /tmp/checkpoint-<uuid>.json"

**Postcondition**: Clean shutdown, state preserved.

### Extension 6a: Parallel Execution Failure

**Trigger**: Worker process crashes during parallel execution.

**Steps**:
1. Detect worker failure via process pool monitor
2. Log error with worker PID and last processed sample
3. Re-queue failed sample to available worker
4. If worker repeatedly fails (3+ times), mark sample as "worker_error"
5. Continue with remaining workers
6. Include worker failure count in report

**Postcondition**: Fault tolerance via retry, degraded performance.

### Extension 7a: Invalid Benchmark Configuration

**Trigger**: Custom configuration file has invalid parameters.

**Steps**:
1. Validate configuration against schema during step 2
2. Log specific validation errors (e.g., "timeout must be positive integer")
3. Display helpful error message with example
4. Exit with code 1 (validation error)

**Postcondition**: User corrects configuration and retries.

### Extension 8a: Model Size Filter

**Trigger**: Model exceeds MAX_MODEL_SIZE_GB (preserve matric-cli behavior).

**Steps**:
1. Query Ollama for model size metadata
2. If size >MAX_MODEL_SIZE_GB (default: 20GB), display warning
3. Optionally skip with `--skip-large-models` flag
4. Otherwise, prompt user: "Model is 35GB, continue? (y/n)"
5. Proceed based on user choice

**Postcondition**: Large models handled gracefully, resource awareness.

### Extension 9a: Reproducibility Validation

**Trigger**: User passes `--validate-reproducibility` flag.

**Steps**:
1. Run evaluation twice with same seed
2. Compare scores with tolerance (±0.001)
3. If scores differ, log warning and diff
4. Include reproducibility report in output
5. Exit with code 1 if non-reproducible

**Postcondition**: Reproducibility verified or issues flagged.

### Extension 10a: Custom Output Format

**Trigger**: User specifies `--format csv` or `--format html`.

**Steps**:
1. Execute evaluation normally
2. Generate internal JSON representation
3. Transform to requested format:
   - CSV: Flattened scores, one row per benchmark
   - HTML: Interactive report with charts
   - Markdown: Summary table for documentation
4. Write to specified output file
5. Optionally write JSON as well with `--also-json`

**Postcondition**: Results available in user's preferred format.

## Special Requirements

### Performance Requirements

- **Smoke Tier**: Complete in <5 minutes (300 seconds)
- **Quick Tier**: Complete in <30 minutes (1800 seconds)
- **Full Tier**: Complete in <4 hours (14400 seconds)
- **Latency Overhead**: <10% overhead vs. raw Ollama inference
- **Memory Footprint**: <2GB for framework, <8GB for evaluation state
- **Disk Usage**: <1GB for checkpoints, <5GB for full results with artifacts

### Reliability Requirements

- **Deterministic Scoring**: Same seed produces identical scores (±0.001)
- **Fault Tolerance**: Resume from checkpoint with <1% data loss
- **Error Recovery**: Continue evaluation on individual sample failures
- **Graceful Degradation**: Use embedded datasets if external unavailable

### Usability Requirements

- **Clear Error Messages**: User-actionable guidance for all failure modes
- **Progress Indication**: Real-time progress bar with ETA
- **Comprehensive Logging**: Debug logs for troubleshooting
- **Self-Documenting**: `--help` provides complete usage documentation

### Security Requirements

- **Code Isolation**: Execute generated code in sandbox (no network, limited filesystem)
- **Resource Limits**: Enforce CPU, memory, and time limits per execution
- **Input Validation**: Sanitize all user inputs (model names, file paths)
- **Artifact Safety**: Do not execute artifacts, only store for analysis

## Assumptions and Dependencies

### Assumptions

1. Ollama service is locally hosted (localhost:11434)
2. Models are already pulled before evaluation
3. Datasets are static and uncorrupted
4. User has basic CLI proficiency
5. Python 3.11+ is available
6. Sufficient compute resources (16GB RAM, 4+ cores)

### Dependencies

- **Inspect AI**: Core evaluation framework
- **inspect-evals**: Pre-built benchmark implementations
- **Ollama**: Local model serving
- **Docker** (optional): Enhanced sandboxing for full tier
- **pytest**: Validation and testing
- **Public Datasets**: HumanEval, MBPP, GSM8K, IFEval, LiveCodeBench, DS-1000

## Validation Criteria

### Acceptance Criteria

- [ ] Smoke tier completes in <5 minutes for llama3.2:3b
- [ ] Quick tier completes in <30 minutes for llama3.2:3b
- [ ] HumanEval scores match matric-cli implementation (±0.5%)
- [ ] MBPP scores match matric-cli implementation (±0.5%)
- [ ] Function names extracted correctly for MBPP (100% accuracy)
- [ ] Code extraction handles markdown fences, language tags
- [ ] Sandbox prevents network access, enforces timeout
- [ ] Artifacts preserved for all samples (generatedCode field)
- [ ] Seeded random produces reproducible scores
- [ ] JSON output schema validated
- [ ] CLI `--help` documents all options
- [ ] Error messages are actionable (no raw stack traces)

### Non-Acceptance Criteria

- [ ] Evaluation completes but produces incorrect scores
- [ ] Sandbox allows network access or filesystem escape
- [ ] Artifacts missing or incomplete
- [ ] Non-reproducible scores with same seed
- [ ] Cryptic error messages without guidance
- [ ] Memory leaks or resource exhaustion
- [ ] Scoring drift vs. reference implementations

## Notes

### Implementation Guidance

1. **Preserve matric-cli Logic**: Function name extraction, code parsing, artifact structure
2. **Extend Inspect AI**: Use custom scorers for code execution, constraint checking
3. **Tiered Sampling**: Seeded random for subset selection, document sampling strategy
4. **Progress Feedback**: Use rich/tqdm for progress bars, log to file for debugging
5. **Fail Fast**: Validate inputs before expensive operations

### Testing Strategy

1. **Unit Tests**: Scorer logic, code extraction, sandbox behavior
2. **Integration Tests**: End-to-end smoke tier with known model
3. **Validation Tests**: Compare scores against matric-cli reference
4. **Performance Tests**: Verify tier duration targets
5. **Reproducibility Tests**: Multiple runs with same seed

### Future Enhancements

- Multi-model comparison in single run
- Interactive mode with model selection
- Web UI for result visualization
- Streaming results during evaluation
- Distributed evaluation across multiple machines

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-24 | Claude Opus 4.5 | Initial use case specification |
