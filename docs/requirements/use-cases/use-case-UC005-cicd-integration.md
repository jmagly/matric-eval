# Use Case UC005: CI/CD Integration

**Document ID**: REQ-UC-005
**Version**: 1.0
**Date**: 2026-01-24
**Status**: Planning Phase
**Priority**: P2 - High

## Use Case Overview

| Attribute | Value |
|-----------|-------|
| Use Case ID | UC005 |
| Use Case Name | CI/CD Integration |
| Created By | Claude Opus 4.5 |
| Created Date | 2026-01-24 |
| Last Updated | 2026-01-24 |
| Priority | P2 - High |
| Complexity | Medium |

## Traceability

**Traced to Gitea Issues**:
- #13: Add CI/CD integration with Gitea

**Traced to Business Requirements**:
- BR-005: Operational Excellence (automated quality gates)
- BR-004: Developer Experience (fast feedback on model changes)
- BR-003: Resource Efficiency (efficient CI resource usage)

**Traced to Other Use Cases**:
- UC001: Run Benchmark Evaluation (CI runs evaluations automatically)
- UC002: Checkpoint and Resume Evaluation (CI may need checkpointing for long jobs)
- UC004: Model Recommendation (CI validates recommendations)

## Actors

### Primary Actor

**CI/CD Pipeline**: Automated system running on code commits, PRs, and merges.

**Role**: Executes evaluations, validates model performance, reports results.

**Characteristics**:
- Triggered by Git events (push, PR, merge, schedule)
- Limited time budget (typically 1-2 hours per job)
- Resource-constrained (shared runners)
- Needs deterministic, reproducible results
- Reports results to developers and project management tools

### Secondary Actors

**Developer**: Submits PR with model configuration changes.

**Role**: Reviews CI results, fixes issues if evaluation fails.

**Characteristics**:
- Wants fast feedback (<10 minutes for smoke tests)
- Needs clear pass/fail criteria
- May not be ML expert, needs interpretable results

**DevOps Engineer**: Configures and maintains CI/CD pipelines.

**Role**: Sets up evaluation jobs, manages resources, troubleshoots failures.

**Project Manager**: Reviews automated evaluation reports.

**Role**: Tracks model quality trends, approves model upgrades.

### Supporting Actors

**Gitea**: Source control and CI platform.

**Ollama Service**: Model inference backend (may be ephemeral or persistent).

**Artifact Storage**: Stores evaluation results for later analysis.

**Notification System**: Alerts team of evaluation failures.

## Preconditions

### System State

1. **CI Environment**: Gitea CI runners available with sufficient resources
2. **Ollama Available**: Service accessible to CI runners (persistent or per-job)
3. **matric-eval Installed**: Package available in CI environment (pip install or Docker)
4. **Test Data Available**: Benchmark datasets accessible (cached or downloaded)
5. **Baseline Defined**: Minimum acceptable scores for each tier

### CI Configuration

1. **Workflow Files**: `.gitea/workflows/` contains evaluation pipeline definitions
2. **Secrets Configured**: API tokens, credentials securely stored
3. **Resource Limits**: Job timeout, memory, CPU allocation defined
4. **Triggers Configured**: PR, merge, schedule events mapped to appropriate tiers

### Repository State

1. **Model Config**: Repository contains model configuration file
2. **Baseline Results**: Previous evaluation results for comparison (optional)

## Postconditions

### Success Postconditions

1. **Evaluation Complete**: Tests executed, results generated
2. **Results Uploaded**: Artifacts available for download and review
3. **Status Reported**: Pass/fail status visible in PR/commit
4. **Trends Tracked**: Historical results stored for analysis
5. **Team Notified**: Relevant stakeholders informed of results

### Failure Postconditions

1. **Clear Error Message**: Logs explain why evaluation failed
2. **Partial Results**: Any completed tests available for debugging
3. **Actionable Feedback**: Developer knows what to fix
4. **Build Blocked** (if critical): PR cannot merge until fixed

## Main Success Scenario

### Scenario 1: Pull Request with Smoke Tests

**Context**: Developer submits PR updating model configuration in matric-cli. CI runs smoke tests to validate basic functionality.

**Steps**:

1. **Developer Creates PR**:
   ```bash
   # Developer changes model in matric-cli config
   git checkout -b update-code-model
   # Edit config: code_generation_model = "qwen2.5-coder:7b"
   git add source/config/models.ts
   git commit -m "Update code generation model to qwen2.5-coder:7b"
   git push origin update-code-model
   gh pr create --title "Upgrade code generation model"
   ```

2. **Gitea Receives PR Event**:
   - Webhook triggered
   - CI pipeline identified: `.gitea/workflows/model-eval-pr.yml`

3. **CI Workflow Started**:
   ```yaml
   # .gitea/workflows/model-eval-pr.yml
   name: Model Evaluation - PR
   on:
     pull_request:
       paths:
         - 'source/config/models.ts'
         - 'source/eval/**'
   jobs:
     smoke-test:
       runs-on: ubuntu-latest
       timeout-minutes: 15
       steps:
         - name: Checkout code
           uses: actions/checkout@v3

         - name: Start Ollama service
           run: |
             docker run -d -p 11434:11434 --name ollama ollama/ollama
             sleep 5  # Wait for service startup

         - name: Pull model
           run: |
             docker exec ollama ollama pull qwen2.5-coder:7b

         - name: Install matric-eval
           run: |
             pip install matric-eval

         - name: Cache evaluation data
           uses: actions/cache@v3
           with:
             path: ~/.matric-eval/datasets
             key: eval-datasets-v1

         - name: Run smoke tests
           run: |
             matric-eval \
               --tier smoke \
               --model qwen2.5-coder:7b \
               --output results/smoke-test.json \
               --seed 42 \
               --verbose
           timeout-minutes: 10

         - name: Validate against baseline
           run: |
             python scripts/validate_baseline.py \
               --results results/smoke-test.json \
               --baseline baselines/qwen2.5-coder-7b-smoke.json \
               --tolerance 0.05 \
               --min-accuracy 0.60

         - name: Upload results
           uses: actions/upload-artifact@v3
           if: always()
           with:
             name: smoke-test-results
             path: results/

         - name: Comment on PR
           if: always()
           uses: actions/github-script@v6
           with:
             script: |
               const fs = require('fs');
               const results = JSON.parse(fs.readFileSync('results/smoke-test.json'));

               const comment = `
               ## Smoke Test Results

               **Model**: ${results.model}
               **Status**: ${results.passed ? '✅ PASS' : '❌ FAIL'}

               | Benchmark | Samples | Accuracy | Baseline | Status |
               |-----------|---------|----------|----------|--------|
               | HumanEval | 10 | ${(results.humaneval.accuracy * 100).toFixed(1)}% | 65% | ${results.humaneval.accuracy >= 0.65 ? '✅' : '❌'} |
               | MBPP | 10 | ${(results.mbpp.accuracy * 100).toFixed(1)}% | 70% | ${results.mbpp.accuracy >= 0.70 ? '✅' : '❌'} |
               | GSM8K | 10 | ${(results.gsm8k.accuracy * 100).toFixed(1)}% | 60% | ${results.gsm8k.accuracy >= 0.60 ? '✅' : '❌'} |

               **Duration**: ${results.duration_minutes} minutes

               <details>
               <summary>Full Results</summary>

               \`\`\`json
               ${JSON.stringify(results, null, 2)}
               \`\`\`
               </details>
               `;

               github.rest.issues.createComment({
                 issue_number: context.issue.number,
                 owner: context.repo.owner,
                 repo: context.repo.repo,
                 body: comment
               });

         - name: Set commit status
           if: always()
           run: |
             if [ "${{ job.status }}" == "success" ]; then
               echo "EVAL_STATUS=success" >> $GITHUB_ENV
             else
               echo "EVAL_STATUS=failure" >> $GITHUB_ENV
             fi
   ```

4. **Smoke Tests Execute**:
   - HumanEval: 10 samples (subset of 164)
   - MBPP: 10 samples (subset of 974)
   - GSM8K: 10 samples (subset of 1319)
   - Total: 30 samples
   - Duration: ~5-8 minutes

5. **Results Generated**:
   ```json
   {
     "model": "qwen2.5-coder:7b",
     "tier": "smoke",
     "timestamp": "2026-01-24T14:30:00Z",
     "passed": true,
     "duration_minutes": 6.5,
     "benchmarks": {
       "humaneval": {
         "samples": 10,
         "accuracy": 0.70,
         "baseline": 0.65,
         "status": "pass"
       },
       "mbpp": {
         "samples": 10,
         "accuracy": 0.80,
         "baseline": 0.70,
         "status": "pass"
       },
       "gsm8k": {
         "samples": 10,
         "accuracy": 0.60,
         "baseline": 0.60,
         "status": "pass"
       }
     },
     "overall_accuracy": 0.70,
     "seed": 42
   }
   ```

6. **Baseline Validation**:
   - Compare smoke test results with known baseline
   - Check: Each benchmark >= baseline threshold
   - Check: Overall accuracy >= minimum (60%)
   - Result: PASS (all benchmarks meet or exceed baseline)

7. **PR Comment Posted**:
   - CI bot comments on PR with results table
   - Includes pass/fail status for each benchmark
   - Links to full results artifact
   - Status check: ✅ Model Evaluation (smoke)

8. **Developer Reviews Results**:
   - Sees green check on PR
   - Reviews comment, confirms model performing well
   - Proceeds with code review

9. **PR Approved and Merged**:
   - After code review approval
   - Smoke tests passed, no blockers
   - Merge to main branch

**Expected Duration**: 6-10 minutes from PR creation to smoke test completion.

**Outcome**: Fast feedback to developer, model validated before merge.

### Scenario 2: Post-Merge Quick Evaluation

**Context**: PR merged to main. CI runs more comprehensive "quick" tier evaluation on merge.

**Steps**:

1. **Merge Event Triggered**:
   ```yaml
   # .gitea/workflows/model-eval-main.yml
   name: Model Evaluation - Main
   on:
     push:
       branches: [main]
       paths:
         - 'source/config/models.ts'
   jobs:
     quick-eval:
       runs-on: ubuntu-latest
       timeout-minutes: 60
       steps:
         - name: Setup (same as PR workflow)
           ...

         - name: Run quick evaluation
           run: |
             matric-eval \
               --tier quick \
               --model qwen2.5-coder:7b \
               --output results/quick-eval.json \
               --seed 42 \
               --parallel \
               --workers 4
           timeout-minutes: 45

         - name: Validate against baseline
           run: |
             python scripts/validate_baseline.py \
               --results results/quick-eval.json \
               --baseline baselines/qwen2.5-coder-7b-quick.json \
               --tolerance 0.03

         - name: Upload to artifact storage
           run: |
             # Upload to Gitea releases or artifact server
             gh release upload eval-results-$(date +%Y%m) results/quick-eval.json

         - name: Update metrics dashboard
           run: |
             python scripts/update_metrics.py \
               --results results/quick-eval.json \
               --dashboard https://metrics.integrolabs.net

         - name: Notify on failure
           if: failure()
           run: |
             curl -X POST $WEBHOOK_URL \
               -H 'Content-Type: application/json' \
               -d '{
                 "text": "❌ Quick evaluation failed for qwen2.5-coder:7b on main branch",
                 "link": "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
               }'
   ```

2. **Quick Evaluation Executes**:
   - HumanEval: 50 samples
   - MBPP: 100 samples
   - GSM8K: 100 samples
   - IFEval: 50 samples
   - Total: 300 samples
   - Duration: ~30-40 minutes (with parallelization)

3. **Results Uploaded**:
   - Artifact attached to GitHub release
   - Metrics sent to monitoring dashboard
   - Historical trend updated

4. **Notification Sent** (if failure):
   - Slack/Discord webhook notifies team
   - Email to maintainers
   - Gitea issue created automatically

**Expected Duration**: 30-45 minutes.

**Outcome**: Main branch quality validated, metrics tracked, team notified of issues.

### Scenario 3: Scheduled Full Evaluation

**Context**: Weekly cron job runs full evaluation to catch regressions and track trends.

**Steps**:

1. **Cron Trigger**:
   ```yaml
   # .gitea/workflows/model-eval-weekly.yml
   name: Model Evaluation - Weekly Full
   on:
     schedule:
       - cron: '0 2 * * 1'  # Every Monday at 2 AM UTC
     workflow_dispatch:  # Manual trigger
   jobs:
     full-eval:
       runs-on: ubuntu-latest
       timeout-minutes: 480  # 8 hours
       steps:
         - name: Setup environment
           ...

         - name: Pull all models
           run: |
             for model in llama3.2:3b qwen2.5-coder:7b codellama:13b; do
               docker exec ollama ollama pull $model
             done

         - name: Run full evaluation
           run: |
             matric-eval \
               --tier full \
               --models llama3.2:3b,qwen2.5-coder:7b,codellama:13b \
               --app matric-cli \
               --output results/full-eval-$(date +%Y%m%d).json \
               --seed 42 \
               --parallel \
               --workers 8 \
               --checkpoint \
               --auto-checkpoint-interval 30m
           timeout-minutes: 420  # 7 hours, allow 1 hour buffer

         - name: Generate recommendations
           run: |
             matric-eval \
               --recommend \
               --input results/full-eval-$(date +%Y%m%d).json \
               --app matric-cli \
               --output model-categories-new.json

         - name: Compare with current recommendations
           run: |
             python scripts/compare_recommendations.py \
               --current model-categories.json \
               --new model-categories-new.json \
               --output recommendation-diff.md

         - name: Create PR for recommendation updates
           if: steps.compare.outputs.has_changes == 'true'
           run: |
             git checkout -b update-model-recommendations-$(date +%Y%m%d)
             cp model-categories-new.json model-categories.json
             git add model-categories.json
             git commit -m "chore: update model recommendations (weekly eval)"
             git push origin update-model-recommendations-$(date +%Y%m%d)
             gh pr create \
               --title "Update Model Recommendations ($(date +%Y-%m-%d))" \
               --body "$(cat recommendation-diff.md)" \
               --label "automated" \
               --assignee "@maintainers"

         - name: Upload results and reports
           uses: actions/upload-artifact@v3
           with:
             name: full-eval-$(date +%Y%m%d)
             path: |
               results/
               *.md
               model-categories-new.json
             retention-days: 90

         - name: Publish metrics
           run: |
             python scripts/publish_metrics.py \
               --results results/full-eval-$(date +%Y%m%d).json \
               --grafana-url $GRAFANA_URL \
               --influxdb-url $INFLUXDB_URL
   ```

2. **Full Evaluation Runs**: 6-7 hours for 3 models
3. **Recommendations Generated**: New model-categories.json
4. **PR Created** (if changes detected)
5. **Metrics Published**: Time-series data to monitoring system

**Expected Duration**: 6-8 hours (overnight job).

**Outcome**: Weekly quality validation, automated recommendation updates, long-term trend tracking.

## Extensions and Alternate Flows

### Extension 1a: Evaluation Timeout

**Trigger**: Step 4 (Scenario 1) or Step 2 (Scenario 2) - Job exceeds time limit.

**Steps**:
1. CI system sends SIGTERM to process
2. matric-eval checkpoint handler catches signal
3. Save checkpoint (if `--checkpoint` enabled)
4. Upload checkpoint as artifact:
   ```yaml
   - name: Upload checkpoint on timeout
     if: cancelled()
     uses: actions/upload-artifact@v3
     with:
       name: checkpoint-timeout
       path: /tmp/*.checkpoint
   ```
5. Job marked as "timeout" (not failure)
6. Comment on PR/commit:
   ```
   ⏱️ Evaluation timed out after 60 minutes.
   Checkpoint saved. Results may be incomplete.

   To resume: Download checkpoint artifact and run locally.
   ```
7. Developer option to resume locally or increase timeout

**Postcondition**: Partial results saved, developer can continue evaluation locally.

### Extension 1b: Resource Exhaustion (OOM)

**Trigger**: Ollama or matric-eval runs out of memory.

**Steps**:
1. OOM killer terminates process
2. CI detects non-zero exit code
3. Parse logs for OOM indicator
4. Comment on PR:
   ```
   ❌ Evaluation failed: Out of memory

   Model 'qwen2.5-coder:7b' requires ~8GB RAM.
   CI runner has 7GB available.

   Solutions:
   1. Use smaller model for smoke tests (llama3.2:3b)
   2. Request larger runner
   3. Run full evaluation locally or on dedicated hardware
   ```
5. Job marked as failure
6. Suggest using smaller model tier for CI

**Postcondition**: Developer understands resource constraint, can adjust model or runner.

### Extension 2a: Baseline Not Met

**Trigger**: Step 6 (Scenario 1) - Validation detects accuracy below baseline.

**Steps**:
1. Validation script exits with non-zero code
2. CI job marked as failure
3. Comment on PR:
   ```
   ❌ Smoke tests failed: Below baseline

   | Benchmark | Actual | Baseline | Status |
   |-----------|--------|----------|--------|
   | HumanEval | 58% | 65% | ❌ -7% |
   | MBPP | 72% | 70% | ✅ +2% |
   | GSM8K | 55% | 60% | ❌ -5% |

   **Overall**: 61.7% (baseline: 65%)

   Possible causes:
   - Model degradation
   - Incorrect model configuration
   - Benchmark data changed
   - Random seed variation (expected ±2%)

   Actions:
   1. Verify model name is correct
   2. Run full evaluation locally to confirm
   3. Check if baseline needs updating
   ```
4. Block PR merge (required check fails)
5. Developer investigates and fixes

**Postcondition**: Quality gate enforced, subpar model changes blocked.

### Extension 2b: Baseline Tolerance Exceeded

**Trigger**: Step 6 - Results within baseline but outside tolerance.

**Steps**:
1. Validation detects: `abs(actual - baseline) > tolerance`
2. Example: Baseline 70%, actual 67%, tolerance 5%
3. Still within tolerance, but flagged for review
4. Comment with warning:
   ```
   ⚠️ Smoke tests passed, but close to baseline threshold

   HumanEval: 67% (baseline: 70%, tolerance: ±5%)

   This is acceptable but near the lower bound.
   Consider running full evaluation to validate.
   ```
5. Job passes (no merge block)
6. Team decides if further investigation needed

**Postcondition**: Borderline results flagged but don't block progress.

### Extension 3a: Model Not Available

**Trigger**: Step 3 (Scenario 1) - `ollama pull` fails, model not in registry.

**Steps**:
1. Docker exec returns error:
   ```
   Error: model 'qwen2.5-coder:7b' not found
   ```
2. CI captures error and comments:
   ```
   ❌ Evaluation failed: Model not available

   Model 'qwen2.5-coder:7b' could not be pulled from Ollama registry.

   Verify:
   1. Model name spelling: qwen2.5-coder:7b
   2. Model exists: https://ollama.com/library/qwen2.5-coder
   3. Ollama version supports this model

   Available alternatives:
   - qwen-coder:7b (older version)
   - deepseek-coder:6.7b (similar performance)
   ```
3. Job fails, PR blocked
4. Developer corrects model name or chooses alternative

**Postcondition**: Invalid model configuration caught before merge.

### Extension 4a: Parallel Execution on Matrix

**Trigger**: Scenario 3 - Multiple models evaluated in parallel jobs.

**Steps**:
1. Use CI matrix strategy:
   ```yaml
   jobs:
     full-eval:
       runs-on: ubuntu-latest
       strategy:
         matrix:
           model:
             - llama3.2:3b
             - qwen2.5-coder:7b
             - codellama:13b
         max-parallel: 3
       steps:
         - name: Run evaluation
           run: |
             matric-eval \
               --tier full \
               --model ${{ matrix.model }} \
               --output results/${{ matrix.model }}.json
   ```
2. Each model evaluated in separate job (parallel)
3. Results combined in subsequent job:
   ```yaml
   combine-results:
     needs: full-eval
     runs-on: ubuntu-latest
     steps:
       - name: Download all results
         uses: actions/download-artifact@v3
       - name: Merge results
         run: |
           python scripts/merge_results.py results/*.json --output combined.json
       - name: Generate recommendations
         run: |
           matric-eval --recommend --input combined.json
   ```

**Postcondition**: Faster total execution time, but more runner resources consumed.

### Extension 5a: Gitea API Integration

**Trigger**: Scenario 1, Step 7 - Need to report results to Gitea.

**Steps**:
1. Use Gitea API to post commit status:
   ```bash
   curl -X POST \
     -H "Authorization: token $GITEA_TOKEN" \
     -H "Content-Type: application/json" \
     https://git.integrolabs.net/api/v1/repos/roctinam/matric-cli/statuses/$COMMIT_SHA \
     -d '{
       "state": "success",
       "target_url": "https://git.integrolabs.net/roctinam/matric-cli/actions/runs/123",
       "description": "Smoke tests passed (70% accuracy)",
       "context": "matric-eval/smoke"
     }'
   ```
2. Create issue on failure:
   ```bash
   curl -X POST \
     -H "Authorization: token $GITEA_TOKEN" \
     https://git.integrolabs.net/api/v1/repos/roctinam/matric-cli/issues \
     -d '{
       "title": "Model evaluation failed: qwen2.5-coder:7b below baseline",
       "body": "See CI run: ...",
       "labels": ["model-quality", "automated"]
     }'
   ```

**Postcondition**: Results integrated with Gitea project tracking.

### Extension 6a: Flaky Test Detection

**Trigger**: Step 6 - Same model/seed produces different results across runs.

**Steps**:
1. Detect variance:
   ```python
   # Compare last 3 runs for same model
   variance = calculate_variance([run1, run2, run3])
   if variance > 0.05:
       flag_as_flaky()
   ```
2. Comment on PR:
   ```
   ⚠️ Flaky test detected

   HumanEval results vary across recent runs:
   - Run 1: 70%
   - Run 2: 68%
   - Run 3: 72%
   - Variance: 5.7% (threshold: 5%)

   Possible causes:
   - Non-deterministic model behavior
   - Random seed not properly set
   - Benchmark data changed
   - Ollama version difference

   Action: Investigation required before merge.
   ```
3. Mark PR for review but don't block
4. Team investigates root cause

**Postcondition**: Non-determinism surfaced, can be investigated.

### Extension 7a: Custom Test Validation

**Trigger**: Scenario 1 - PR includes custom test changes (UC003).

**Steps**:
1. Detect custom test changes:
   ```yaml
   on:
     pull_request:
       paths:
         - 'datasets/custom/**'
         - 'src/matric_eval/tasks/custom/**'
   ```
2. Validate custom test:
   ```bash
   # Verify dataset schema
   matric-eval --validate-dataset datasets/custom/new-test.jsonl

   # Dry-run test
   matric-eval --custom-test new_test --dry-run

   # Run on small sample
   matric-eval --custom-test new_test --model llama3.2:3b --max-samples 5
   ```
3. Report validation results
4. Require maintainer approval for custom test changes

**Postcondition**: Custom tests validated before merge.

### Extension 8a: Result Artifact Retention

**Trigger**: Scenario 3 - Need to manage artifact storage costs.

**Steps**:
1. Set retention policies:
   ```yaml
   - name: Upload smoke results
     uses: actions/upload-artifact@v3
     with:
       name: smoke-test-results
       path: results/
       retention-days: 30  # 30 days for PR tests

   - name: Upload full results
     uses: actions/upload-artifact@v3
     with:
       name: full-eval-results
       path: results/
       retention-days: 365  # 1 year for full evals
   ```
2. Archive important results to long-term storage:
   ```bash
   # Upload to S3/MinIO for permanent retention
   aws s3 cp results/full-eval-20260124.json \
     s3://matric-eval-archives/$(date +%Y)/ \
     --storage-class GLACIER
   ```
3. Cleanup old artifacts:
   ```bash
   # Monthly cleanup job
   gh api repos/roctinam/matric-cli/actions/artifacts \
     | jq '.artifacts[] | select(.created_at < "2025-12-01")' \
     | xargs -I {} gh api -X DELETE repos/roctinam/matric-cli/actions/artifacts/{}
   ```

**Postcondition**: Artifact storage managed, costs controlled.

## Special Requirements

### Performance Requirements

- **Smoke Tests**: Complete within 10 minutes
- **Quick Tests**: Complete within 60 minutes
- **Full Tests**: Complete within 8 hours (acceptable for scheduled jobs)
- **Parallel Speedup**: 3-4x with 4 workers (linear scaling)
- **Artifact Upload**: <1 minute for typical result files (<10MB)

### Reliability Requirements

- **Deterministic Results**: Same seed produces identical results (±1% for acceptable variance)
- **Checkpoint Recovery**: Long jobs resume from checkpoint on failure
- **Graceful Timeout**: Checkpoint on timeout, not abrupt termination
- **Partial Results**: Failed benchmarks don't prevent other benchmarks from completing

### Resource Requirements

- **Smoke Tests**: 4GB RAM, 2 CPU cores, 10GB disk
- **Quick Tests**: 8GB RAM, 4 CPU cores, 20GB disk
- **Full Tests**: 16GB RAM, 8 CPU cores, 50GB disk (for large models)

### Usability Requirements

- **Clear Status**: PR shows green/red check immediately
- **Actionable Feedback**: Error messages explain what to fix
- **Quick Access**: Results linked from PR comment
- **Historical Comparison**: Trends visible over time

### Security Requirements

- **Secrets Management**: API tokens, credentials in CI secrets (not code)
- **Isolated Execution**: Each job runs in clean environment
- **Artifact Access Control**: Results only accessible to authorized users
- **Model Integrity**: Verify model checksums before evaluation (optional)

## Assumptions and Dependencies

### Assumptions

1. **Ollama Availability**: CI runners can access Ollama (Docker or remote service)
2. **Dataset Access**: Public benchmarks downloadable or cached
3. **Stable Baselines**: Baseline scores updated when models/benchmarks change
4. **Deterministic Execution**: Same seed + model produces consistent results
5. **Resource Sufficiency**: CI runners meet minimum requirements for smoke/quick tiers

### Dependencies

- **CI Platform**: Gitea Actions, GitHub Actions, GitLab CI, or similar
- **Ollama**: Model inference service (Docker image or persistent server)
- **matric-eval Package**: Installed via pip or Docker
- **Benchmark Datasets**: Available locally or downloadable
- **Baseline Files**: Stored in repository or artifact storage
- **Notification System**: Webhooks, email, or Gitea API for alerts

## Validation Criteria

### Acceptance Criteria

- [ ] Smoke tests run on all PRs touching model config (<10 min)
- [ ] Quick tests run on merge to main (<60 min)
- [ ] Full tests run on weekly schedule (<8 hours)
- [ ] Results posted as PR comment with pass/fail per benchmark
- [ ] Commit status (green check / red X) reflects evaluation result
- [ ] Baseline validation fails CI if scores below threshold
- [ ] Results uploaded as artifacts and retained per policy
- [ ] Notifications sent on failure (Slack, email, Gitea issue)
- [ ] Parallel execution works (matrix strategy or workers)
- [ ] Checkpoint/resume works for long jobs
- [ ] Flaky tests detected and flagged
- [ ] Metrics published to monitoring dashboard

### Non-Acceptance Criteria

- [ ] CI job hangs indefinitely (no timeout)
- [ ] Failure without error message
- [ ] Results not accessible after job completes
- [ ] Non-deterministic results (high variance across runs)
- [ ] Secrets exposed in logs
- [ ] Resource exhaustion crashes runner

## Notes

### CI Workflow Templates

```
.gitea/workflows/
├── model-eval-pr.yml           # Smoke tests on PRs
├── model-eval-main.yml         # Quick tests on merge
├── model-eval-weekly.yml       # Full tests on schedule
└── model-eval-custom-test.yml  # Custom test validation
```

### Tier-to-CI Mapping

| Tier | Trigger | Duration | Samples | Purpose |
|------|---------|----------|---------|---------|
| Smoke | PR | 5-10 min | 30 | Fast feedback, basic validation |
| Quick | Merge to main | 30-60 min | 300 | Post-merge quality check |
| Full | Weekly schedule | 6-8 hours | 3000+ | Comprehensive validation, trend tracking |

### Baseline Management

- Store baselines in `baselines/` directory in repo
- Naming convention: `<model>-<tier>.json`
- Update baselines when:
  - Model upgraded intentionally
  - Benchmark definitions change
  - Evaluation framework updated
- Document baseline changes in commit message

### Monitoring and Alerting

- **Metrics to Track**:
  - Evaluation duration per tier
  - Pass/fail rate over time
  - Model accuracy trends
  - Resource usage (memory, CPU, disk)
  - Artifact storage consumption

- **Alerts**:
  - Evaluation failure on main branch (critical)
  - Baseline degradation >5% (warning)
  - CI timeout or OOM (operational)
  - Flaky test variance >5% (investigation)

### Testing Strategy

1. **CI Pipeline Tests**: Test CI workflows in staging environment
2. **Mock Evaluations**: Use synthetic results for CI logic testing
3. **Baseline Validation**: Test validation script with known good/bad results
4. **Artifact Tests**: Verify upload/download and retention
5. **Integration Tests**: End-to-end PR flow with real evaluation

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-24 | Claude Opus 4.5 | Initial CI/CD integration use case |
