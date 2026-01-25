# Use Case UC002: Checkpoint and Resume Evaluation

**Document ID**: REQ-UC-002
**Version**: 1.0
**Date**: 2026-01-24
**Status**: Planning Phase
**Priority**: P2 - High

## Use Case Overview

| Attribute | Value |
|-----------|-------|
| Use Case ID | UC002 |
| Use Case Name | Checkpoint and Resume Evaluation |
| Created By | Claude Opus 4.5 |
| Created Date | 2026-01-24 |
| Last Updated | 2026-01-24 |
| Priority | P2 - High |
| Complexity | High |

## Traceability

**Traced to Gitea Issues**:
- #11: Implement checkpoint/resume for fault tolerance
- #12: Implement parallel model evaluation (checkpointing enables recovery)
- #14: Add comprehensive logging and observability (checkpoint logging)

**Traced to Business Requirements**:
- BR-005: Operational Excellence
- BR-003: Resource Efficiency (avoid wasting compute on re-runs)

**Traced to Other Use Cases**:
- UC001: Run Benchmark Evaluation (primary flow that benefits from checkpointing)

## Actors

### Primary Actor

**Developer/Researcher**: Person running long-duration evaluations who experiences interruptions.

**Role**: Initiates evaluation, experiences failure, resumes from checkpoint.

**Characteristics**:
- Running full-tier evaluations (hours of duration)
- May experience network issues, resource constraints, or manual interruptions
- Values compute time and reproducibility
- Needs confidence in result integrity after resume

### Secondary Actors

**System Watchdog**: Monitoring process that detects resource exhaustion or system issues.

**Role**: Triggers checkpoint on adverse conditions.

**Characteristics**:
- Monitors memory, disk, CPU usage
- Sends signals (SIGTERM, SIGINT) on threshold violations
- Allows graceful shutdown

**Evaluation Framework**: Inspect AI orchestrator managing task execution.

**Role**: Coordinates with checkpoint system to save/restore state.

### Supporting Actors

**File System**: Persistent storage for checkpoint files.

**Ollama Service**: May become unavailable, triggering checkpoint.

**CI/CD Pipeline**: May impose time limits, requiring checkpoint/resume across jobs.

## Preconditions

### System State

1. **Evaluation In Progress**: Long-running evaluation (full tier or custom tests)
2. **Checkpoint Enabled**: User passed `--checkpoint` flag or checkpoint enabled by default for full tier
3. **Writable Storage**: Checkpoint directory has write permissions and sufficient space
4. **State Serializable**: Current evaluation state can be captured in JSON/binary format

### User State

1. **Awareness**: User understands checkpoint behavior and resume command
2. **Permissions**: Write access to checkpoint directory (default: `/tmp/` or `~/.matric-eval/checkpoints/`)

### Data State

1. **Partial Progress**: Some benchmarks completed, others in progress or pending
2. **Artifacts Accumulated**: Generated code, model outputs, and intermediate results exist
3. **No Corruption**: Checkpoint file is not corrupted from previous failed attempts

## Postconditions

### Success Postconditions

1. **State Persisted**: Complete evaluation state saved to checkpoint file
2. **Resume Possible**: User can resume from checkpoint with exact continuation
3. **No Data Loss**: All completed samples preserved, no duplicate execution
4. **Reproducible Results**: Resumed evaluation produces identical results to uninterrupted run
5. **Checkpoint Cleanup**: Checkpoint file removed after successful completion

### Failure Postconditions

1. **Checkpoint Intact**: Even if resume fails, checkpoint remains for debugging
2. **Error Logged**: Resume failure details captured in logs
3. **Manual Recovery**: User can inspect checkpoint and decide on manual intervention
4. **State Rollback**: If resume fails, no partial state corruption

## Main Success Scenario

### Scenario 1: Graceful Checkpoint on User Interrupt

**Context**: User running full evaluation realizes they need to stop for system maintenance.

**Steps**:

1. **Evaluation Running**: Full tier evaluation in progress (Step 6 of UC001, 30% complete)
   - 164/164 HumanEval samples completed
   - 292/974 MBPP samples completed
   - GSM8K, IFEval, LiveCodeBench, DS-1000 pending
2. **User Sends SIGINT**: User presses Ctrl+C
3. **Signal Handler Triggered**: System catches SIGINT
4. **Display Checkpoint Message**: "Interrupt received. Checkpointing current progress..."
5. **Complete Current Sample**: Wait for active sample execution to finish (max 30s timeout)
6. **Collect State**:
   - Completed benchmarks: HumanEval (full), MBPP (partial)
   - Pending benchmarks: GSM8K, IFEval, LiveCodeBench, DS-1000
   - Current sample index per benchmark
   - Random seed and state
   - Model configuration and CLI arguments
   - Accumulated scores and artifacts
   - Execution metadata (start time, duration, resource usage)
7. **Serialize to JSON**:
   ```json
   {
     "version": "1.0",
     "checkpoint_id": "matric-eval-20260124-103000-abc123",
     "created_at": "2026-01-24T10:45:00Z",
     "model": "llama3.2:3b",
     "tier": "full",
     "seed": 42,
     "cli_args": ["--tier", "full", "--model", "llama3.2:3b", "--output", "results.json"],
     "progress": {
       "total_samples": 3298,
       "completed_samples": 456,
       "percent_complete": 13.8
     },
     "benchmarks": {
       "humaneval": {
         "status": "completed",
         "samples_total": 164,
         "samples_completed": 164,
         "results": [...]
       },
       "mbpp": {
         "status": "in_progress",
         "samples_total": 974,
         "samples_completed": 292,
         "current_index": 292,
         "results": [...]
       },
       "gsm8k": {
         "status": "pending",
         "samples_total": 1319
       },
       "ifeval": {
         "status": "pending",
         "samples_total": 541
       },
       "livecodebench": {
         "status": "pending",
         "samples_total": 100
       },
       "ds1000": {
         "status": "pending",
         "samples_total": 100
       }
     },
     "random_state": "<serialized_random_state>",
     "resource_usage": {
       "total_tokens": 87000,
       "total_duration_seconds": 2100
     }
   }
   ```
8. **Write Checkpoint File**: Save to `/tmp/matric-eval-20260124-103000-abc123.checkpoint`
9. **Verify Checkpoint**: Read back and validate JSON integrity
10. **Display Resume Command**: "Checkpoint saved. Resume with: matric-eval --resume /tmp/matric-eval-20260124-103000-abc123.checkpoint"
11. **Exit Gracefully**: Return code 130 (SIGINT)

**Expected Duration**: 5-10 seconds from interrupt to exit.

**User Resumes After System Maintenance**:

12. **Invoke Resume Command**: User executes `matric-eval --resume /tmp/matric-eval-20260124-103000-abc123.checkpoint`
13. **Validate Checkpoint**:
    - File exists and readable
    - JSON structure valid
    - Version compatible (warn if version mismatch)
    - Model still available in Ollama
    - Datasets still accessible
14. **Load State**:
    - Restore model configuration
    - Restore random state (ensures deterministic continuation)
    - Restore completed results
    - Identify next sample to execute (MBPP index 292)
15. **Display Resume Info**:
    ```
    Resuming evaluation:
      Model: llama3.2:3b
      Progress: 456/3298 samples (13.8%)
      Completed: HumanEval, MBPP (partial)
      Remaining: MBPP (682 samples), GSM8K, IFEval, LiveCodeBench, DS-1000
      Estimated time: ~4.5 hours
    ```
16. **Continue Evaluation**: Resume from MBPP sample 292
    - Skip already completed samples
    - Execute pending samples
    - Maintain same seed and configuration
17. **Periodic Auto-Checkpointing** (optional with `--auto-checkpoint`):
    - Save checkpoint every 10 minutes
    - Save checkpoint every 100 samples
    - Overwrite previous checkpoint to save space
18. **Complete Evaluation**: All benchmarks finish
19. **Merge Results**: Combine pre-checkpoint and post-checkpoint results
20. **Validate Consistency**: Ensure no duplicate samples, no gaps
21. **Generate Final Report**: Same output as uninterrupted evaluation
22. **Cleanup Checkpoint**: Delete checkpoint file
23. **Exit Successfully**: Return code 0

**Validation**: Scores identical to what uninterrupted run would produce.

### Scenario 2: Automatic Checkpoint on Resource Exhaustion

**Context**: System running low on memory during evaluation.

**Steps**:

1. **Evaluation Running**: Full tier, 60% complete
2. **Resource Monitor Detects Issue**: Memory usage >95%
3. **Trigger Checkpoint**:
   - Log warning: "Memory exhaustion detected, initiating emergency checkpoint"
   - Pause sample execution
   - Force garbage collection
4. **Save Checkpoint**: Same process as Scenario 1, steps 6-9
5. **Display Message**: "System resources exhausted. Checkpoint saved to: <path>. Please free resources and resume."
6. **Exit with Code 3**: Resource error code
7. **User Frees Resources**: Close other applications, increase swap, etc.
8. **User Resumes**: Execute `matric-eval --resume <checkpoint>`
9. **Continue Evaluation**: Same as Scenario 1, steps 13-23

**Expected Outcome**: Evaluation completes without data loss despite resource constraints.

### Scenario 3: Checkpoint Across CI/CD Jobs

**Context**: CI/CD pipeline has 2-hour job time limit, full evaluation takes 4 hours.

**Steps**:

1. **Job 1 - Initial Evaluation**:
   - Start evaluation with `--checkpoint --max-duration 7000` (1h 55m)
   - Execute for 7000 seconds
   - Automatic checkpoint triggered by max-duration
   - Save checkpoint to artifact storage (e.g., GitHub Actions artifacts)
   - Exit with code 0 (planned checkpoint)
2. **Job 2 - Resume Evaluation**:
   - Download checkpoint artifact from Job 1
   - Resume with `matric-eval --resume checkpoint.json --max-duration 7000`
   - Execute for another 7000 seconds
   - Save another checkpoint if not complete
3. **Job 3 - Final Completion**:
   - Download checkpoint from Job 2
   - Resume and complete
   - Upload final results as artifact
   - Cleanup checkpoint

**Expected Outcome**: Full evaluation completes across 3 CI/CD jobs with perfect continuity.

## Extensions and Alternate Flows

### Extension 1a: Checkpoint File Corrupted

**Trigger**: Step 13 detects invalid JSON or corrupted checkpoint.

**Steps**:
1. Log error: "Checkpoint file corrupted: <details>"
2. Attempt recovery:
   - Check for backup checkpoint (`.checkpoint.bak`)
   - Attempt partial JSON parsing
   - Extract salvageable state
3. If recovery fails, display error:
   ```
   ERROR: Cannot resume from corrupted checkpoint.

   Options:
   1. Restart evaluation from scratch
   2. Manually inspect checkpoint at: <path>
   3. Use --force-resume to attempt partial state recovery
   ```
4. Exit with code 4 (checkpoint error)

**Postcondition**: User informed, can choose recovery strategy.

### Extension 1b: Checkpoint Version Mismatch

**Trigger**: Step 13 detects checkpoint from different matric-eval version.

**Steps**:
1. Log warning: "Checkpoint created with version 0.2.0, current version 0.3.0"
2. Attempt version migration:
   - Apply transformation rules (e.g., add new fields with defaults)
   - Validate migrated state
3. If migration succeeds, display warning and continue
4. If migration fails, display error:
   ```
   ERROR: Checkpoint version incompatible.

   Created with: matric-eval 0.2.0
   Current version: matric-eval 0.3.0

   Please install compatible version or restart evaluation.
   ```
5. Exit with code 4 or continue with user confirmation

**Postcondition**: Backward compatibility handled gracefully.

### Extension 2a: Model No Longer Available

**Trigger**: Step 14 detects model from checkpoint is not available.

**Steps**:
1. Query Ollama for available models
2. Display error:
   ```
   ERROR: Model 'llama3.2:3b' from checkpoint not found.

   Available models:
   - llama3.2:1b
   - codellama:7b

   Please pull model: ollama pull llama3.2:3b
   ```
3. Optionally prompt: "Pull model automatically? (y/n)"
4. If yes, execute `ollama pull` and continue
5. If no, exit with code 2

**Postcondition**: Model availability ensured before resume.

### Extension 3a: Dataset Modified Since Checkpoint

**Trigger**: Step 14 detects dataset checksum mismatch.

**Steps**:
1. Calculate current dataset checksum
2. Compare with checksum in checkpoint
3. Log warning: "Dataset 'humaneval' has changed since checkpoint creation"
4. Display options:
   ```
   WARNING: Dataset modified since checkpoint.

   This may invalidate results. Options:
   1. Continue anyway (--force-resume)
   2. Restart evaluation with new dataset
   3. Restore original dataset
   ```
5. Exit with code 5 (data integrity error) unless `--force-resume`

**Postcondition**: User aware of data integrity risk.

### Extension 4a: Duplicate Execution Detection

**Trigger**: Step 20 detects samples executed twice (pre and post resume).

**Steps**:
1. During merge, compare sample IDs
2. If overlap detected, log error:
   ```
   ERROR: Duplicate execution detected.

   Sample 'humaneval_42' executed twice:
   - Pre-checkpoint: pass, score=1.0
   - Post-checkpoint: fail, score=0.0

   This indicates checkpoint corruption or logic error.
   ```
3. Apply deduplication strategy (configurable):
   - Keep pre-checkpoint result (default)
   - Keep post-checkpoint result
   - Flag as error and exclude
4. Log all duplicates in report
5. If >1% duplicates, exit with code 6 (logic error)

**Postcondition**: Data integrity maintained, issues surfaced.

### Extension 5a: Checkpoint Storage Full

**Trigger**: Step 8 fails to write checkpoint due to disk space.

**Steps**:
1. Catch write error (DiskFullError)
2. Log error: "Cannot write checkpoint, disk full: <path>"
3. Attempt alternate locations:
   - Try `/tmp/` if using custom path
   - Try `~/.matric-eval/checkpoints/`
   - Try current working directory
4. If all fail, display error:
   ```
   CRITICAL: Cannot save checkpoint, disk full.

   Evaluation will exit without saving progress.
   Free disk space and restart, or use --checkpoint-dir <path>.
   ```
5. Exit with code 3 (resource error)

**Postcondition**: Progress lost, user informed to free space.

### Extension 6a: Multiple Checkpoint Files

**Trigger**: User has multiple checkpoint files in directory.

**Steps**:
1. When resuming without explicit checkpoint path, search for checkpoints
2. If multiple found, display interactive selection:
   ```
   Multiple checkpoints found:

   1. matric-eval-20260124-103000-abc123.checkpoint
      Model: llama3.2:3b, Progress: 13.8%, Created: 2 hours ago

   2. matric-eval-20260124-080000-def456.checkpoint
      Model: codellama:7b, Progress: 45.2%, Created: 5 hours ago

   Select checkpoint to resume (1-2):
   ```
3. Resume selected checkpoint
4. Optionally provide `--checkpoint-latest` to auto-select most recent

**Postcondition**: User selects correct checkpoint, no ambiguity.

### Extension 7a: Parallel Execution State

**Trigger**: Checkpoint during parallel execution (multiple workers).

**Steps**:
1. On checkpoint trigger, signal all workers to pause
2. Wait for all workers to finish current sample (max 30s)
3. Collect state from all workers:
   - Completed samples per worker
   - In-progress samples (mark as pending)
   - Worker-specific random states
4. Merge worker states into unified checkpoint
5. On resume, distribute pending samples to workers
6. Restore random state per worker for determinism

**Postcondition**: Parallel execution state fully captured.

### Extension 8a: Checkpoint Encryption (Future)

**Trigger**: User passes `--encrypt-checkpoint` for sensitive data.

**Steps**:
1. Prompt for encryption passphrase
2. Encrypt checkpoint JSON with AES-256
3. Save encrypted file with `.checkpoint.enc` extension
4. On resume, prompt for passphrase
5. Decrypt and validate
6. Continue normal resume flow

**Postcondition**: Checkpoint protected from unauthorized access.

### Extension 9a: Cloud Checkpoint Storage (Future)

**Trigger**: User configures `--checkpoint-s3 s3://bucket/path`.

**Steps**:
1. On checkpoint, upload to S3/cloud storage
2. Store cloud URL in local metadata file
3. On resume, download from cloud
4. Cache locally for performance
5. Delete local cache after completion

**Postcondition**: Checkpoints persistent across machines, cloud backup.

### Extension 10a: Checkpoint Inspection Without Resume

**Trigger**: User executes `matric-eval --inspect-checkpoint <path>`.

**Steps**:
1. Load checkpoint file
2. Parse and validate structure
3. Display human-readable summary:
   ```
   Checkpoint: matric-eval-20260124-103000-abc123.checkpoint
   Created: 2026-01-24 10:45:00 UTC (2 hours ago)
   Version: 1.0
   Model: llama3.2:3b
   Tier: full
   Progress: 456/3298 samples (13.8%)

   Benchmarks:
     ✓ HumanEval: 164/164 (100%)
     ⋯ MBPP: 292/974 (30%)
     ⧗ GSM8K: 0/1319 (pending)
     ⧗ IFEval: 0/541 (pending)
     ⧗ LiveCodeBench: 0/100 (pending)
     ⧗ DS-1000: 0/100 (pending)

   Estimated completion time: 4.5 hours
   ```
4. Exit with code 0

**Postcondition**: User understands checkpoint state, can decide on resume.

## Special Requirements

### Performance Requirements

- **Checkpoint Creation**: <10 seconds for full-tier state (3000+ samples)
- **Checkpoint Size**: <50MB for full-tier checkpoint (compressed JSON)
- **Resume Latency**: <5 seconds to load and validate checkpoint
- **Auto-Checkpoint Frequency**: Every 10 minutes or 100 samples (configurable)
- **Storage Efficiency**: Incremental checkpointing (delta encoding) for large states

### Reliability Requirements

- **Atomicity**: Checkpoint write is atomic (temp file + rename)
- **Durability**: Checkpoint persists across system crashes
- **Consistency**: Resumed evaluation produces identical results to uninterrupted run
- **Idempotency**: Resuming multiple times from same checkpoint produces same result
- **Corruption Detection**: Checksum validation on load
- **Backup**: Optional automatic backup of previous checkpoint (`.bak`)

### Usability Requirements

- **Clear Messages**: User understands checkpoint/resume status at all times
- **Resume Command**: Displayed prominently after checkpoint creation
- **Progress Preservation**: User sees exact continuation, not restart
- **Automatic Cleanup**: Checkpoints deleted after successful completion
- **Manual Management**: User can list, inspect, delete checkpoints

### Security Requirements

- **Path Validation**: Sanitize checkpoint file paths to prevent traversal attacks
- **Permission Checks**: Verify write permissions before starting long evaluations
- **Sensitive Data**: Optionally exclude API keys, credentials from checkpoints
- **Encryption Support**: Optional encryption for checkpoints with sensitive model outputs

## Assumptions and Dependencies

### Assumptions

1. **Deterministic Execution**: Random seed ensures reproducible sampling and scoring
2. **Stateless Benchmarks**: Benchmarks don't depend on execution order (beyond random seed)
3. **Model Stability**: Model weights unchanged between checkpoint and resume
4. **Dataset Stability**: Dataset files unchanged between checkpoint and resume
5. **Single Process**: No concurrent modifications to checkpoint files
6. **Sufficient Storage**: Checkpoint directory has space for largest possible checkpoint

### Dependencies

- **JSON Serialization**: Python `json` module for checkpoint format
- **File System**: POSIX-compliant filesystem with atomic rename
- **Random State**: Python `random` and `numpy.random` state serialization
- **Signal Handling**: Unix signals (SIGINT, SIGTERM) for graceful shutdown
- **Inspect AI**: Framework supports state serialization and resumption

## Validation Criteria

### Acceptance Criteria

- [ ] User interrupt (Ctrl+C) triggers checkpoint within 10 seconds
- [ ] Checkpoint file is valid JSON and <50MB for full tier
- [ ] Resume command correctly loads checkpoint and continues from exact point
- [ ] Resumed evaluation produces identical scores to uninterrupted run (±0.001)
- [ ] No duplicate sample executions (0% overlap)
- [ ] No missing samples (100% coverage)
- [ ] Checkpoint deleted after successful completion
- [ ] Resource exhaustion triggers automatic checkpoint
- [ ] CI/CD pipeline can checkpoint/resume across jobs
- [ ] Corrupted checkpoint detected with clear error message
- [ ] Version mismatch handled gracefully
- [ ] Multiple checkpoints selectable with interactive menu
- [ ] Checkpoint inspection shows accurate progress summary
- [ ] Auto-checkpointing (every 10 min) works without performance degradation

### Non-Acceptance Criteria

- [ ] Checkpoint creation takes >30 seconds
- [ ] Checkpoint file >500MB (compression needed)
- [ ] Resume produces different scores than original run
- [ ] Duplicate or missing samples after resume
- [ ] Checkpoint survives but is corrupted (no validation)
- [ ] Confusing error messages on resume failure
- [ ] Checkpoints not cleaned up, accumulating over time

## Notes

### Implementation Guidance

1. **Atomic Writes**: Write checkpoint to `.checkpoint.tmp`, then rename to `.checkpoint`
2. **State Minimization**: Store only essential state, reference datasets by path/checksum
3. **Versioning**: Include checkpoint format version for backward compatibility
4. **Validation**: Checksum entire checkpoint file, validate on load
5. **Testing**: Fault injection tests (kill -9, disk full, corruption)

### Checkpoint File Format

```json
{
  "version": "1.0",
  "schema": "https://matric-eval.io/checkpoint-schema-v1.json",
  "metadata": {
    "checkpoint_id": "matric-eval-20260124-103000-abc123",
    "created_at": "2026-01-24T10:45:00Z",
    "hostname": "dev-machine",
    "pid": 12345,
    "matric_eval_version": "0.2.0"
  },
  "configuration": {
    "model": "llama3.2:3b",
    "tier": "full",
    "seed": 42,
    "cli_args": [...],
    "ollama_url": "http://localhost:11434"
  },
  "datasets": {
    "humaneval": {
      "path": "/home/roctinam/data/evals/humaneval/",
      "checksum": "sha256:abcdef123456..."
    },
    "mbpp": { ... }
  },
  "progress": {
    "total_samples": 3298,
    "completed_samples": 456,
    "percent_complete": 13.8,
    "elapsed_seconds": 2100,
    "estimated_remaining_seconds": 13200
  },
  "benchmarks": {
    "humaneval": {
      "status": "completed",
      "samples_total": 164,
      "samples_completed": 164,
      "results": [
        {
          "sample_id": "humaneval_0",
          "prompt": "...",
          "completion": "...",
          "score": 1.0,
          "passed": true,
          "execution_time_ms": 1200
        },
        ...
      ]
    },
    "mbpp": {
      "status": "in_progress",
      "samples_total": 974,
      "samples_completed": 292,
      "current_index": 292,
      "results": [ ... ]
    },
    "gsm8k": {
      "status": "pending"
    }
  },
  "random_state": {
    "python_random": "<base64_encoded_state>",
    "numpy_random": "<base64_encoded_state>"
  },
  "resource_usage": {
    "total_tokens": 87000,
    "total_duration_seconds": 2100,
    "peak_memory_mb": 4200
  },
  "checksum": "sha256:full_file_checksum_excluding_this_field"
}
```

### Testing Strategy

1. **Interrupt Tests**: Send SIGINT at various progress points, verify clean checkpoint
2. **Resume Tests**: Checkpoint at 25%, 50%, 75%, resume and verify completion
3. **Corruption Tests**: Corrupt checkpoint bytes, verify detection and error handling
4. **Resource Tests**: Simulate disk full, memory exhaustion, verify checkpoint behavior
5. **Reproducibility Tests**: Checkpoint/resume vs. uninterrupted, compare scores
6. **Parallel Tests**: Checkpoint during parallel execution, verify worker state
7. **CI/CD Tests**: Multi-job checkpoint/resume pipeline
8. **Performance Tests**: Measure checkpoint creation/loading overhead

### Future Enhancements

- Distributed checkpoints for multi-machine evaluation
- Incremental checkpointing (only delta since last checkpoint)
- Checkpoint compression (gzip, zstd)
- Cloud storage integration (S3, GCS, Azure Blob)
- Checkpoint encryption for sensitive data
- Checkpoint versioning (keep last N checkpoints)
- Web UI for checkpoint inspection and management

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-24 | Claude Opus 4.5 | Initial checkpoint/resume use case specification |
