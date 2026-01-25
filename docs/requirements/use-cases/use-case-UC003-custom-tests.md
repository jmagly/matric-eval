# Use Case UC003: Custom Test Integration

**Document ID**: REQ-UC-003
**Version**: 1.0
**Date**: 2026-01-24
**Status**: Planning Phase
**Priority**: P1 - Critical

## Use Case Overview

| Attribute | Value |
|-----------|-------|
| Use Case ID | UC003 |
| Use Case Name | Custom Test Integration |
| Created By | Claude Opus 4.5 |
| Created Date | 2026-01-24 |
| Last Updated | 2026-01-24 |
| Priority | P1 - Critical |
| Complexity | High |

## Traceability

**Traced to Gitea Issues**:
- #7: Port matric-cli evaluations (TypeScript eval code)
- #8: Port matric-memory evaluations (Rust eval code)
- #21: matric-cli TypeScript bindings
- #22: matric-memory Rust bindings

**Traced to Business Requirements**:
- BR-001: Unified Evaluation (custom tests are app-specific requirements)
- BR-002: Extensibility (enable domain-specific evaluation)
- BR-004: Developer Experience (easy custom test integration)

**Traced to Other Use Cases**:
- UC001: Run Benchmark Evaluation (custom tests extend standard benchmarks)
- UC004: Model Recommendation (custom tests inform config generation)

## Actors

### Primary Actor

**Application Developer**: Developer of matric-cli, matric-memory, or other matric ecosystem project.

**Role**: Creates and integrates custom evaluation tests for their specific application domain.

**Characteristics**:
- Familiar with their application's model usage patterns
- Needs to validate models for specific use cases (e.g., tool calling, memory retrieval, code generation)
- May not be ML expert, needs simple test authoring
- Values quick iteration and feedback on test effectiveness
- Wants consistent evaluation methodology across applications

### Secondary Actors

**Model Researcher**: Person benchmarking models for comparative analysis.

**Role**: Extends matric-eval with novel evaluation tasks.

**Characteristics**:
- Deep ML knowledge
- May contribute tests back to community
- Needs flexibility for custom scoring logic
- Values reproducibility and statistical rigor

**matric-eval Framework**: Core evaluation orchestrator.

**Role**: Executes custom tests using standard infrastructure.

### Supporting Actors

**CI/CD Pipeline**: Automated testing system that runs custom tests on PRs.

**File System**: Storage for custom test datasets and scorer implementations.

**Ollama Service**: Model inference backend for custom test execution.

## Preconditions

### System State

1. **matric-eval Installed**: Core framework available with standard benchmarks working
2. **Ollama Available**: Service running and accessible
3. **Model Pulled**: Target model available in Ollama
4. **Directory Structure**: Custom test location writable (e.g., `datasets/custom/` and `src/matric_eval/tasks/custom/`)

### User State

1. **Test Requirements Defined**: Developer knows what capability to test
2. **Test Data Prepared**: JSONL dataset created or ready to create
3. **Scoring Logic Defined**: Clear pass/fail criteria or scoring rubric
4. **Environment Access**: Permissions to install packages and run evaluations

### Data State

1. **Test Dataset Format**: JSONL with required fields (`input`, `target`, `metadata`)
2. **Baseline Exists** (optional): Previous evaluation results for comparison
3. **Dependencies Available**: Any external tools needed for scoring (e.g., code execution sandbox)

## Postconditions

### Success Postconditions

1. **Test Integrated**: Custom test discoverable by matric-eval
2. **Test Runnable**: Can execute via `matric-eval --custom-test <name>`
3. **Results Consistent**: Scoring reproducible across runs with same seed
4. **Results Interpretable**: Clear metrics and pass/fail criteria
5. **Test Documented**: README or docstring explains test purpose and scoring
6. **CI Integration Ready**: Test can run in automated pipelines

### Failure Postconditions

1. **Clear Error Messages**: User understands why integration failed
2. **State Unchanged**: Failed integration doesn't corrupt existing tests
3. **Rollback Possible**: Can revert custom test changes easily

## Main Success Scenario

### Scenario 1: Integrate matric-cli Tool Calling Test

**Context**: matric-cli uses models for tool calling (function selection and parameter extraction). Developer needs to validate models handle complex multi-tool scenarios.

**Steps**:

1. **Define Test Requirement**:
   - **Capability**: Tool calling accuracy
   - **Input**: User query requiring tool use
   - **Expected Output**: Correct tool selection + valid JSON parameters
   - **Example**:
     - Input: "What's the weather in Tokyo tomorrow and remind me about the forecast at 8am?"
     - Expected: Call `get_weather(location="Tokyo", when="tomorrow")` and `set_reminder(time="08:00", message="Check Tokyo weather forecast")`

2. **Create Test Dataset**:
   - Navigate to `datasets/custom/matric-cli/`
   - Create `tool-calling-v1.jsonl`:
     ```jsonl
     {"id": "tool_001", "input": "What's the weather in Tokyo tomorrow and remind me about the forecast at 8am?", "expected_tools": [{"name": "get_weather", "params": {"location": "Tokyo", "when": "tomorrow"}}, {"name": "set_reminder", "params": {"time": "08:00", "message": "Check Tokyo weather forecast"}}], "available_tools": [...tool_definitions...], "difficulty": "hard", "tags": ["multi-tool", "temporal"]}
     {"id": "tool_002", "input": "Calculate 15% tip on $87.50", "expected_tools": [{"name": "calculate", "params": {"expression": "87.50 * 0.15"}}], "available_tools": [...], "difficulty": "easy", "tags": ["single-tool", "math"]}
     ...
     ```
   - Total: 50 samples (10 easy, 20 medium, 20 hard)

3. **Register Dataset**:
   - Edit `src/matric_eval/tasks/custom/matric_cli_tools.py`:
     ```python
     from inspect_ai import Task, task
     from inspect_ai.dataset import json_dataset
     from inspect_ai.scorer import match
     from inspect_ai.solver import generate, system_message

     @task
     def matric_cli_tool_calling():
         """
         Evaluate tool calling accuracy for matric-cli.

         Tests model's ability to select correct tools and extract
         parameters from natural language queries.

         Difficulty distribution: 10 easy, 20 medium, 20 hard
         Scoring: Exact match on tool names + fuzzy match on params
         """
         return Task(
             dataset=json_dataset("datasets/custom/matric-cli/tool-calling-v1.jsonl"),
             plan=[
                 system_message("You are a helpful assistant with access to tools."),
                 generate()
             ],
             scorer=tool_calling_scorer(),
             max_messages=3
         )
     ```

4. **Implement Custom Scorer**:
   - Create `src/matric_eval/scorers/tool_calling.py`:
     ```python
     from inspect_ai.scorer import Score, Scorer, Target, scorer, accuracy, stderr
     from inspect_ai.model import ChatMessageAssistant
     import json
     import re

     @scorer(metrics=[accuracy(), stderr()])
     def tool_calling_scorer():
         """
         Score tool calling based on:
         1. Correct tool selection (name match)
         2. Parameter accuracy (fuzzy JSON match)
         3. Multi-tool completeness (all expected tools called)
         """
         async def score(state, target):
             # Extract tool calls from model response
             response = state.output.completion
             called_tools = extract_tool_calls(response)
             expected_tools = target.text  # JSON-encoded expected_tools

             # Parse expected tools
             expected = json.loads(expected_tools)

             # Scoring logic
             tool_names_match = set(c['name'] for c in called_tools) == set(e['name'] for e in expected)
             params_match = all(
                 fuzzy_param_match(c['params'], e['params'])
                 for c, e in zip(sorted(called_tools, key=lambda x: x['name']),
                                 sorted(expected, key=lambda x: x['name']))
             )

             # Full credit only if both correct
             score_value = 1.0 if (tool_names_match and params_match) else 0.0

             # Partial credit for correct tool names
             if tool_names_match and not params_match:
                 score_value = 0.5

             return Score(
                 value=score_value,
                 explanation=f"Tools: {called_tools}, Expected: {expected}",
                 metadata={
                     "called_tools": called_tools,
                     "expected_tools": expected,
                     "tool_names_correct": tool_names_match,
                     "params_correct": params_match
                 }
             )

         return score

     def extract_tool_calls(text: str) -> list[dict]:
         """Extract tool calls from various response formats."""
         # Handle JSON function calling format
         if "```json" in text:
             match = re.search(r'```json\n(.*?)\n```', text, re.DOTALL)
             if match:
                 return json.loads(match.group(1))

         # Handle plain text tool syntax
         # e.g., "get_weather(location='Tokyo', when='tomorrow')"
         tool_pattern = r'(\w+)\((.*?)\)'
         matches = re.findall(tool_pattern, text)
         tools = []
         for name, params_str in matches:
             params = parse_params(params_str)
             tools.append({"name": name, "params": params})
         return tools

     def fuzzy_param_match(actual: dict, expected: dict) -> bool:
         """Fuzzy match allowing for minor variations."""
         if set(actual.keys()) != set(expected.keys()):
             return False

         for key in expected.keys():
             actual_val = str(actual[key]).lower().strip()
             expected_val = str(expected[key]).lower().strip()

             # Allow synonyms (e.g., "tomorrow" vs "2026-01-25")
             if not (actual_val == expected_val or
                     semantically_equivalent(actual_val, expected_val)):
                 return False

         return True
     ```

5. **Test Locally**:
   ```bash
   # Run custom test on single model
   matric-eval --custom-test matric_cli_tool_calling --model llama3.2:3b --output results/tool-calling-llama3.2-3b.json
   ```

6. **Verify Output**:
   - Check results JSON:
     ```json
     {
       "model": "llama3.2:3b",
       "test": "matric_cli_tool_calling",
       "samples": 50,
       "accuracy": 0.76,
       "scores": [
         {"id": "tool_001", "score": 1.0, "passed": true, "called_tools": [...]},
         {"id": "tool_002", "score": 1.0, "passed": true},
         {"id": "tool_003", "score": 0.5, "passed": false, "error": "Incorrect parameters"},
         ...
       ],
       "by_difficulty": {
         "easy": {"accuracy": 0.90, "samples": 10},
         "medium": {"accuracy": 0.75, "samples": 20},
         "hard": {"accuracy": 0.65, "samples": 20}
       },
       "by_tag": {
         "multi-tool": {"accuracy": 0.62, "samples": 25},
         "single-tool": {"accuracy": 0.88, "samples": 25}
       }
     }
     ```

7. **Document Test**:
   - Create `datasets/custom/matric-cli/README.md`:
     ```markdown
     # matric-cli Tool Calling Evaluation

     ## Purpose
     Validate models can accurately select and invoke tools with correct parameters.

     ## Dataset
     - **File**: `tool-calling-v1.jsonl`
     - **Samples**: 50 (10 easy, 20 medium, 20 hard)
     - **Difficulty Criteria**:
       - Easy: Single tool, simple parameters
       - Medium: Single tool, complex parameters or multiple tools, simple parameters
       - Hard: Multiple tools with complex parameters, temporal reasoning, or ambiguity

     ## Scoring
     - **1.0**: Correct tool names AND correct parameters
     - **0.5**: Correct tool names, incorrect parameters
     - **0.0**: Incorrect tool names

     ## Baseline Performance
     - llama3.2:3b: 76% accuracy (90% easy, 75% medium, 65% hard)
     - codellama:7b: 82% accuracy
     - Target: >85% accuracy for production use

     ## Usage
     ```bash
     matric-eval --custom-test matric_cli_tool_calling --model <model>
     ```
     ```

8. **Integrate with Full Evaluation**:
   - Add to `src/matric_eval/config/tiers.py`:
     ```python
     CUSTOM_TESTS = {
         "matric-cli": [
             "matric_cli_tool_calling",
             "matric_cli_code_generation",  # Future
             "matric_cli_instruction_following"  # Future
         ],
         "matric-memory": [
             "matric_memory_retrieval",  # Future
             "matric_memory_summarization"  # Future
         ]
     }

     def get_tier_tasks(tier: str, app: str = None):
         tasks = PUBLIC_BENCHMARKS[tier]

         if app and app in CUSTOM_TESTS:
             tasks.extend(CUSTOM_TESTS[app])

         return tasks
     ```

9. **Run Full Evaluation with Custom Tests**:
   ```bash
   # Run full public benchmarks + matric-cli custom tests
   matric-eval --tier full --app matric-cli --model llama3.2:3b
   ```

10. **Verify CI Integration**:
    - Add to `.github/workflows/model-eval.yml` (or equivalent):
      ```yaml
      - name: Run Custom Tests
        run: |
          matric-eval --tier smoke --app matric-cli --model llama3.2:3b --output results/smoke-custom.json

      - name: Check Baseline
        run: |
          python scripts/check_baseline.py results/smoke-custom.json --min-accuracy 0.70
      ```

**Expected Duration**: 1-2 hours for initial integration, <30 minutes for subsequent tests.

**Outcome**: Custom test integrated, runnable in isolation or as part of full evaluation, with clear scoring and CI integration.

### Scenario 2: Port matric-memory Retrieval Test from Rust

**Context**: matric-memory has Rust evaluation code in `crates/matric-inference/src/bin/eval.rs`. Developer needs to port this to matric-eval Python framework.

**Steps**:

1. **Analyze Existing Rust Code**:
   - Read `matric-memory/crates/matric-inference/src/bin/eval.rs`
   - Identify test structure:
     - Input: User query + document corpus
     - Model task: Generate embedding or retrieval query
     - Scoring: Precision@k, Recall@k, MRR
   - Extract test data from `matric-memory/evals/retrieval-samples.json`

2. **Extract Test Data to JSONL**:
   - Convert Rust JSON format to matric-eval JSONL:
     ```python
     # scripts/convert_matric_memory_evals.py
     import json

     with open('/home/roctinam/dev/matric-memory/evals/retrieval-samples.json') as f:
         rust_data = json.load(f)

     with open('datasets/custom/matric-memory/retrieval-v1.jsonl', 'w') as f:
         for sample in rust_data['samples']:
             jsonl_row = {
                 "id": sample['id'],
                 "input": sample['query'],
                 "corpus": sample['documents'],
                 "relevant_doc_ids": sample['relevant_ids'],
                 "metadata": {
                     "domain": sample.get('domain', 'general'),
                     "difficulty": sample.get('difficulty', 'medium')
                 }
             }
             f.write(json.dumps(jsonl_row) + '\n')
     ```

3. **Implement Retrieval Task**:
   - Create `src/matric_eval/tasks/custom/matric_memory_retrieval.py`:
     ```python
     @task
     def matric_memory_retrieval():
         """
         Port of matric-memory retrieval evaluation.

         Evaluates model's ability to generate effective retrieval queries
         or embeddings for document ranking.
         """
         return Task(
             dataset=json_dataset("datasets/custom/matric-memory/retrieval-v1.jsonl"),
             plan=[
                 system_message("Generate a retrieval query for the following:"),
                 generate()
             ],
             scorer=retrieval_scorer(),
             max_messages=1
         )
     ```

4. **Implement Retrieval Scorer**:
   - Create `src/matric_eval/scorers/retrieval.py`:
     ```python
     @scorer(metrics=[accuracy(), precision_at_k(), recall_at_k(), mrr()])
     def retrieval_scorer():
         """
         Score retrieval quality using:
         - Precision@k (k=1,5,10)
         - Recall@k
         - MRR (Mean Reciprocal Rank)
         """
         async def score(state, target):
             query = state.output.completion
             corpus = state.metadata['corpus']
             relevant_ids = set(state.metadata['relevant_doc_ids'])

             # Use embedding model to rank documents
             ranked_docs = rank_documents(query, corpus)

             # Calculate metrics
             precision_1 = 1.0 if ranked_docs[0]['id'] in relevant_ids else 0.0
             precision_5 = len([d for d in ranked_docs[:5] if d['id'] in relevant_ids]) / 5
             recall_5 = len([d for d in ranked_docs[:5] if d['id'] in relevant_ids]) / len(relevant_ids)

             # MRR: reciprocal rank of first relevant document
             mrr_value = 0.0
             for i, doc in enumerate(ranked_docs, 1):
                 if doc['id'] in relevant_ids:
                     mrr_value = 1.0 / i
                     break

             return Score(
                 value=mrr_value,  # Primary metric
                 explanation=f"MRR: {mrr_value:.3f}, P@5: {precision_5:.3f}, R@5: {recall_5:.3f}",
                 metadata={
                     "precision@1": precision_1,
                     "precision@5": precision_5,
                     "recall@5": recall_5,
                     "mrr": mrr_value,
                     "ranked_doc_ids": [d['id'] for d in ranked_docs[:10]]
                 }
             )

         return score
     ```

5. **Validate Against Rust Baseline**:
   - Run matric-eval version:
     ```bash
     matric-eval --custom-test matric_memory_retrieval --model llama3.2:3b
     ```
   - Compare results with Rust eval output:
     ```bash
     # Rust version (from matric-memory repo)
     cd /home/roctinam/dev/matric-memory
     cargo run --bin eval -- --test retrieval --model llama3.2:3b

     # Compare outputs
     python scripts/compare_eval_results.py \
       matric-memory-rust-output.json \
       matric-eval-python-output.json \
       --tolerance 0.01
     ```
   - Expect: MRR scores within ±0.01 (accounting for floating point and randomness)

6. **Document Migration**:
   - Update `datasets/custom/matric-memory/README.md`:
     ```markdown
     # matric-memory Retrieval Evaluation

     ## Migration
     Ported from Rust implementation in `matric-memory/crates/matric-inference/src/bin/eval.rs`

     ## Changes
     - Scoring logic identical to Rust version
     - Test data converted from JSON to JSONL format
     - Embedding model: same as Rust (sentence-transformers/all-MiniLM-L6-v2)

     ## Validation
     Validated against Rust baseline with <0.01 difference in MRR.
     ```

7. **Enable in CI**:
   - Add to matric-memory's CI pipeline:
     ```yaml
     - name: Install matric-eval
       run: pip install matric-eval

     - name: Run Retrieval Test
       run: |
         matric-eval --custom-test matric_memory_retrieval --model llama3.2:3b --output eval-results.json

     - name: Upload Results
       uses: actions/upload-artifact@v3
       with:
         name: eval-results
         path: eval-results.json
     ```

**Expected Duration**: 2-4 hours for porting and validation.

**Outcome**: Rust evaluation successfully ported to Python, validated against baseline, integrated into CI.

## Extensions and Alternate Flows

### Extension 1a: Custom Scorer Requires External Tool

**Trigger**: Step 4 - Scorer needs code execution, database, or external API.

**Steps**:
1. Identify external dependency (e.g., Python sandbox for code execution)
2. Check if dependency available in matric-eval (e.g., built-in sandbox)
3. If not available:
   - Add to `pyproject.toml` dependencies
   - Document requirement in test README
   - Add environment setup to scorer:
     ```python
     @scorer(metrics=[accuracy()])
     def code_execution_scorer():
         # Check sandbox available
         if not sandbox_available():
             raise RuntimeError("Code execution sandbox required. Install: pip install matric-eval[sandbox]")

         async def score(state, target):
             # Use sandbox
             result = execute_in_sandbox(state.output.completion)
             ...
     ```
4. Update CI to install extra dependencies:
   ```yaml
   - run: pip install matric-eval[sandbox]
   ```

**Postcondition**: External dependency documented and CI handles installation.

### Extension 1b: Dataset Too Large for Git

**Trigger**: Step 2 - Test dataset >100MB, exceeds Git LFS limits.

**Steps**:
1. Store dataset externally (e.g., cloud storage, shared drive)
2. Create dataset downloader:
   ```python
   # src/matric_eval/datasets/download.py
   def download_matric_cli_tools():
       url = "https://datasets.matric.io/tool-calling-v1.jsonl.gz"
       local_path = "datasets/custom/matric-cli/tool-calling-v1.jsonl"

       if os.path.exists(local_path):
           return local_path

       download_and_extract(url, local_path)
       return local_path
   ```
3. Modify task to download on-demand:
   ```python
   @task
   def matric_cli_tool_calling():
       dataset_path = download_matric_cli_tools()
       return Task(dataset=json_dataset(dataset_path), ...)
   ```
4. Document in README:
   ```markdown
   ## Dataset
   Large dataset (500MB) automatically downloaded on first run.
   Manual download: `matric-eval --download-dataset matric_cli_tool_calling`
   ```

**Postcondition**: Large dataset handled via download, not committed to Git.

### Extension 2a: Test Requires Specific Model Format

**Trigger**: Step 5 - Test only works with models supporting specific format (e.g., function calling).

**Steps**:
1. Add capability check to task:
   ```python
   @task
   def matric_cli_tool_calling():
       def validate_model(model_name: str):
           # Check model supports function calling
           capabilities = get_model_capabilities(model_name)
           if "function_calling" not in capabilities:
               raise ValueError(f"Model {model_name} does not support function calling. Required for this test.")

       return Task(
           dataset=...,
           validate=validate_model,
           ...
       )
   ```
2. Document requirement:
   ```markdown
   ## Model Requirements
   - Must support function calling API
   - Compatible models: llama3.2:*, mistral:*, etc.
   - Incompatible: llama2, codellama
   ```
3. In full evaluation, skip incompatible tests:
   ```python
   def run_custom_tests(model: str, app: str):
       for test in CUSTOM_TESTS[app]:
           try:
               run_task(test, model)
           except ValueError as e:
               logger.warning(f"Skipping {test} for {model}: {e}")
               continue
   ```

**Postcondition**: Incompatible models skip test gracefully with clear message.

### Extension 3a: Scorer Has Non-Deterministic Behavior

**Trigger**: Step 6 - Verification shows score variance across runs with same seed.

**Steps**:
1. Identify source of non-determinism:
   - External API calls
   - Uncontrolled randomness
   - Floating point arithmetic
   - Concurrent execution
2. Fix if possible:
   - Seed all RNGs
   - Use deterministic algorithms
   - Mock external APIs with cached responses
3. If non-determinism unavoidable, document:
   ```markdown
   ## Non-Determinism
   This test uses external API (OpenAI embedding) which may have minor score variations.
   Expected variance: ±0.02 on MRR metric.
   ```
4. Update validation criteria:
   ```python
   # scripts/check_baseline.py
   def validate_score(actual, baseline, tolerance=0.02):
       assert abs(actual - baseline) <= tolerance
   ```

**Postcondition**: Non-determinism documented and accounted for in validation.

### Extension 4a: Test Data Contains PII or Sensitive Info

**Trigger**: Step 2 - Dataset includes user data, proprietary code, or secrets.

**Steps**:
1. Anonymize dataset:
   - Replace names with pseudonyms
   - Redact sensitive info
   - Use synthetic data
2. Document anonymization:
   ```markdown
   ## Data Privacy
   Dataset contains anonymized user queries. Original data not included.
   Anonymization process: see scripts/anonymize_dataset.py
   ```
3. Store original data securely (not in Git):
   - Use encrypted storage
   - Limit access permissions
   - Document in team wiki, not public README
4. Add security scanning to CI:
   ```yaml
   - name: Scan for Secrets
     run: |
       pip install detect-secrets
       detect-secrets scan datasets/custom/ --baseline .secrets.baseline
   ```

**Postcondition**: Sensitive data protected, anonymized version safe for use.

### Extension 5a: Migrating Test with Complex Dependencies

**Trigger**: Scenario 2, Step 1 - Rust code has dependencies not available in Python.

**Steps**:
1. Identify Rust-specific dependencies:
   - Custom tokenizer
   - Specialized embeddings
   - Proprietary library
2. Find Python equivalents:
   - Search PyPI for similar libraries
   - Check if Rust library has Python bindings
   - Consider reimplementing in Python
3. If no equivalent:
   - Create Rust-Python bridge (PyO3)
   - Or, call Rust binary from Python:
     ```python
     import subprocess

     def rust_scorer(text: str) -> float:
         result = subprocess.run(
             ['./rust-scorer', text],
             capture_output=True,
             text=True
         )
         return float(result.stdout.strip())
     ```
4. Document dependency:
   ```markdown
   ## Dependencies
   Requires Rust binary `rust-scorer` for specialized scoring.
   Build: `cd rust-components && cargo build --release`
   ```

**Postcondition**: Rust functionality accessible from Python, test portable.

### Extension 6a: Test Needs Model Fine-Tuning or Specific Prompting

**Trigger**: Step 3 - Test requires specialized system prompt or few-shot examples.

**Steps**:
1. Define prompt template:
   ```python
   TOOL_CALLING_SYSTEM_PROMPT = """
   You are a helpful assistant with access to tools.

   Available tools:
   {tool_definitions}

   To use a tool, respond with JSON:
   {{"tool": "tool_name", "params": {{"param1": "value1"}}}}

   You can call multiple tools by returning a JSON array.
   """
   ```
2. Add few-shot examples if needed:
   ```python
   FEW_SHOT_EXAMPLES = [
       {
           "user": "What's 2+2?",
           "assistant": '{"tool": "calculate", "params": {"expression": "2+2"}}'
       },
       {
           "user": "Weather in NYC and set reminder",
           "assistant": '[{"tool": "get_weather", "params": {"location": "NYC"}}, {"tool": "set_reminder", "params": {...}}]'
       }
   ]
   ```
3. Incorporate into task:
   ```python
   @task
   def matric_cli_tool_calling():
       return Task(
           dataset=...,
           plan=[
               system_message(TOOL_CALLING_SYSTEM_PROMPT.format(tool_definitions=TOOLS)),
               *[message_pair(ex['user'], ex['assistant']) for ex in FEW_SHOT_EXAMPLES],
               generate()
           ],
           scorer=...
       )
   ```
4. Document prompting strategy:
   ```markdown
   ## Prompting
   Uses 2-shot prompting with examples of single-tool and multi-tool calling.
   System prompt includes explicit JSON format instructions.
   ```

**Postcondition**: Test includes specialized prompting, documented for reproducibility.

### Extension 7a: Parallel Test Execution

**Trigger**: Step 5 - Test suite has 500+ samples, sequential execution too slow.

**Steps**:
1. Enable parallel execution in task:
   ```python
   @task
   def matric_cli_tool_calling():
       return Task(
           dataset=...,
           plan=...,
           scorer=...,
           parallel=True,
           max_workers=8  # Concurrent samples
       )
   ```
2. Ensure scorer is thread-safe:
   - No shared mutable state
   - Use thread-local storage if needed
   - Lock external resources (files, DBs)
3. Configure in CLI:
   ```bash
   matric-eval --custom-test matric_cli_tool_calling --model llama3.2:3b --parallel --workers 8
   ```
4. Monitor resource usage:
   - Memory: 8 concurrent samples may use 8x memory
   - Ollama: May rate-limit concurrent requests
   - Disk I/O: Parallel writes to results file
5. Add throttling if needed:
   ```python
   async def score_with_throttle(state, target):
       async with rate_limiter.acquire():
           return await score(state, target)
   ```

**Postcondition**: Test runs in parallel, execution time reduced proportionally.

### Extension 8a: Test Requires Human Evaluation

**Trigger**: Step 4 - Some aspects need human judgment (e.g., code quality, creativity).

**Steps**:
1. Implement automatic metrics where possible:
   ```python
   @scorer(metrics=[accuracy(), bleu(), rouge()])
   def hybrid_scorer():
       async def score(state, target):
           # Automatic metrics
           auto_score = calculate_automatic_metrics(state.output, target)

           # Flag for human review if ambiguous
           if auto_score.value > 0.4 and auto_score.value < 0.6:
               auto_score.metadata['needs_human_review'] = True

           return auto_score

       return score
   ```
2. Export samples needing review:
   ```python
   # After evaluation
   samples_for_review = [
       s for s in results['scores']
       if s.get('metadata', {}).get('needs_human_review')
   ]

   with open('human_review_queue.jsonl', 'w') as f:
       for sample in samples_for_review:
           f.write(json.dumps(sample) + '\n')
   ```
3. Create review interface:
   ```bash
   # CLI for human scoring
   matric-eval-review human_review_queue.jsonl --output human_scores.json
   ```
4. Merge automatic and human scores:
   ```python
   def merge_scores(auto_scores, human_scores):
       for sample in auto_scores:
           if sample['id'] in human_scores:
               sample['score'] = human_scores[sample['id']]
               sample['score_type'] = 'human'
       return auto_scores
   ```

**Postcondition**: Hybrid scoring implemented, human review process defined.

## Special Requirements

### Performance Requirements

- **Test Execution**: <5 seconds per sample for simple tests, <30 seconds for code execution
- **Dataset Loading**: <10 seconds for 1000-sample dataset
- **Scorer Overhead**: <10% of total execution time
- **Parallel Scaling**: Linear speedup up to 8 workers

### Reliability Requirements

- **Reproducibility**: Same seed produces identical scores (±0.001 for deterministic, ±0.02 for non-deterministic)
- **Error Handling**: Scorer errors don't crash evaluation, logged and reported
- **Partial Results**: Failed samples marked as such, rest of evaluation continues
- **Validation**: Dataset schema validated before execution

### Usability Requirements

- **Clear Documentation**: Every custom test has README with purpose, scoring, and baseline
- **Easy Integration**: Single command to add test to evaluation suite
- **Debugging Support**: Verbose mode shows sample-by-sample execution
- **Error Messages**: Actionable errors for common issues (missing dataset, incompatible model)

### Extensibility Requirements

- **Scorer Plugins**: Support for external scorer implementations
- **Dataset Formats**: Support JSONL, CSV, JSON, Parquet
- **Custom Metrics**: Easy to define new metrics beyond accuracy
- **Hooks**: Pre/post-test hooks for setup and teardown

## Assumptions and Dependencies

### Assumptions

1. **JSONL Format**: Custom tests use JSONL for datasets (one JSON object per line)
2. **Inspect AI Compatible**: Custom tests can be expressed as Inspect AI tasks
3. **Deterministic Possible**: Most test logic can be made deterministic with seeding
4. **File System Access**: Custom tests stored in `datasets/custom/` and `src/matric_eval/tasks/custom/`
5. **Python Proficiency**: Test authors comfortable writing Python scorers

### Dependencies

- **Inspect AI**: Core framework for task definition and execution
- **Dataset Files**: JSONL datasets in standardized location
- **Scorer Implementations**: Python code for custom scoring logic
- **External Tools** (optional): Code sandbox, embedding models, external APIs
- **Documentation**: README files for each custom test

## Validation Criteria

### Acceptance Criteria

- [ ] Custom test discoverable via `matric-eval --list-tests`
- [ ] Test runnable with `matric-eval --custom-test <name>`
- [ ] Scores reproducible across runs (same seed, same scores)
- [ ] Clear error if dataset missing or malformed
- [ ] README documents test purpose, scoring, and baseline
- [ ] CI can run custom test and validate against baseline
- [ ] Full evaluation (`--tier full --app <app>`) includes custom tests
- [ ] Custom tests integrated from both matric-cli and matric-memory
- [ ] Language bindings allow calling custom tests from TypeScript and Rust
- [ ] Scorer errors logged but don't crash evaluation
- [ ] Test results include per-sample explanations
- [ ] Custom metrics (beyond accuracy) work correctly

### Non-Acceptance Criteria

- [ ] Custom test not discoverable (missing registration)
- [ ] Scores vary across runs with same seed (non-determinism)
- [ ] Unclear error messages on failure
- [ ] No documentation or baseline data
- [ ] Test requires manual setup steps not documented
- [ ] Scorer crashes on edge cases (empty input, malformed JSON)
- [ ] Dataset schema not validated, causing runtime errors

## Notes

### Implementation Guidance

1. **Standardize Dataset Format**: Enforce JSONL with required fields (`id`, `input`, `target`)
2. **Scorer Template**: Provide template scorer with error handling, logging, metrics
3. **Registration Pattern**: Auto-discover tests via naming convention (`matric_*_*.py`)
4. **Validation Schema**: JSON schema for dataset validation before execution
5. **Testing**: Unit tests for scorers, integration tests for full custom test flow

### Dataset Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["id", "input", "target"],
  "properties": {
    "id": {
      "type": "string",
      "description": "Unique sample identifier"
    },
    "input": {
      "type": "string",
      "description": "Prompt or input to model"
    },
    "target": {
      "type": ["string", "object"],
      "description": "Expected output or reference for scoring"
    },
    "metadata": {
      "type": "object",
      "description": "Additional context (difficulty, tags, etc.)",
      "properties": {
        "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
        "tags": {"type": "array", "items": {"type": "string"}}
      }
    }
  }
}
```

### Example Custom Test Structure

```
datasets/custom/matric-cli/
  README.md                    # Documentation
  tool-calling-v1.jsonl        # Test data
  tool-calling-baseline.json   # Expected scores for validation

src/matric_eval/tasks/custom/
  matric_cli_tools.py          # Task definition
  matric_cli_code.py           # Another task

src/matric_eval/scorers/
  tool_calling.py              # Scorer implementation
  code_quality.py              # Another scorer
```

### Testing Strategy

1. **Unit Tests**: Test scorers with known inputs, verify scores
2. **Integration Tests**: Run custom test end-to-end, validate output format
3. **Regression Tests**: Compare scores against baseline, flag deviations
4. **Compatibility Tests**: Verify ported tests match original implementation
5. **CI Tests**: Run smoke tier custom tests on PRs, full tier on merge

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-24 | Claude Opus 4.5 | Initial custom test integration use case |
