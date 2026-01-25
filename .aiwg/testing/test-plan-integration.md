# Integration Test Plan - matric-eval

**Project**: matric-eval - Consolidated Model Evaluation Framework
**Test Level**: Integration (L2)
**Profile**: Production
**Coverage Target**: 100% of integration points
**Status**: Planning Phase
**Last Updated**: 2026-01-24

## Document Purpose

This document defines the integration testing approach for matric-eval, specifying how to test component interactions, external service integrations, and end-to-end data flows that cross module boundaries.

## Scope

### In Scope

**External Integrations**:
- Ollama API (model loading, inference, error handling)
- Inspect AI framework (task execution, scoring, reporting)
- File system (state persistence, checkpoint I/O, dataset loading)
- Process management (sandbox execution, timeout enforcement)

**Component Interactions**:
- CLI → Core library → Ollama
- State manager → File system → Recovery
- Scorer → Extractor → Validator
- Task loader → Dataset → Sampler

**Data Flows**:
- Complete evaluation run (discover → execute → score → save)
- Checkpoint/resume workflow
- Gap detection and recovery
- Benchmark validation against reference implementations

### Out of Scope

- Individual function behavior (unit tests)
- Full CLI workflows (system tests)
- Performance benchmarking (performance tests)
- Language bindings (binding tests)

## Test Environment

### Required Services

**Ollama**:
- Version: Latest stable
- Models: Small test models (<1GB)
  - `qwen2.5-coder:1.5b` (code generation, 1GB)
  - `llama3.2:1b` (general purpose, 1.2GB)
- Configuration: Local instance on `http://localhost:11434`

**File System**:
- Temporary directories for test isolation
- Sample datasets (subset of public benchmarks)
- Mock checkpoint states

**Python Environment**:
- Python 3.11+
- Dependencies installed via `uv sync`
- Test dependencies available

### Docker Compose Setup

```yaml
# docker-compose.test.yml
version: '3.8'

services:
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama-data:/root/.ollama
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 10s
      timeout: 5s
      retries: 5

  matric-eval-test:
    build:
      context: .
      dockerfile: Dockerfile.test
    depends_on:
      ollama:
        condition: service_healthy
    environment:
      - OLLAMA_API_BASE=http://ollama:11434
      - MATRIC_EVAL_TEST_MODE=true
    volumes:
      - ./tests:/app/tests
      - ./src:/app/src
      - test-data:/app/data
    command: pytest tests/integration/

volumes:
  ollama-data:
  test-data:
```

### Environment Setup Script

```bash
#!/bin/bash
# scripts/setup-integration-tests.sh

set -e

echo "Setting up integration test environment..."

# Start Ollama
docker compose -f docker-compose.test.yml up -d ollama

# Wait for Ollama to be ready
echo "Waiting for Ollama..."
timeout 60 bash -c 'until curl -f http://localhost:11434/api/tags; do sleep 2; done'

# Pull test models
echo "Pulling test models..."
docker exec $(docker ps -qf "name=ollama") ollama pull qwen2.5-coder:1.5b
docker exec $(docker ps -qf "name=ollama") ollama pull llama3.2:1b

# Prepare test datasets
echo "Preparing test datasets..."
python scripts/prepare-test-datasets.py

echo "Integration test environment ready!"
```

## Test Categories

### 1. Ollama Integration Tests

**Purpose**: Verify Ollama API integration works correctly.

**Coverage Requirement**: 100% of Ollama interaction code

#### Test Cases

```python
# tests/integration/test_ollama_integration.py

import pytest
from matric_eval.ollama import OllamaClient, OllamaError

@pytest.fixture(scope="module")
def ollama_client():
    """Real Ollama client for integration tests."""
    return OllamaClient(base_url="http://localhost:11434")

@pytest.fixture(scope="module")
def test_model():
    """Small model for testing."""
    return "qwen2.5-coder:1.5b"

class TestOllamaConnection:
    """Test Ollama connection and health."""

    def test_health_check(self, ollama_client):
        """Verify Ollama is accessible."""
        assert ollama_client.health_check() is True

    def test_list_models(self, ollama_client, test_model):
        """Verify model listing."""
        models = ollama_client.list_models()
        model_names = [m["name"] for m in models]
        assert test_model in model_names

    def test_model_info(self, ollama_client, test_model):
        """Verify model info retrieval."""
        info = ollama_client.get_model_info(test_model)
        assert info["name"] == test_model
        assert "size" in info
        assert "modified_at" in info

class TestOllamaInference:
    """Test model inference."""

    def test_generate_simple(self, ollama_client, test_model):
        """Test simple generation."""
        prompt = "Write a Python function to add two numbers."

        response = ollama_client.generate(
            model=test_model,
            prompt=prompt,
            options={"temperature": 0.1, "seed": 42}
        )

        assert "response" in response
        assert len(response["response"]) > 0
        assert response["done"] is True

    def test_generate_with_system_prompt(self, ollama_client, test_model):
        """Test generation with system prompt."""
        system = "You are a helpful coding assistant."
        prompt = "Write a function to multiply two numbers."

        response = ollama_client.generate(
            model=test_model,
            prompt=prompt,
            system=system,
            options={"temperature": 0.1, "seed": 42}
        )

        assert "def" in response["response"].lower()

    def test_generate_reproducible(self, ollama_client, test_model):
        """Test deterministic generation with seed."""
        prompt = "Write a hello world function."
        options = {"temperature": 0.0, "seed": 42}

        response1 = ollama_client.generate(test_model, prompt, options=options)
        response2 = ollama_client.generate(test_model, prompt, options=options)

        # With temp=0 and same seed, should be identical
        assert response1["response"] == response2["response"]

    def test_generate_handles_timeout(self, ollama_client, test_model):
        """Test timeout handling."""
        prompt = "Write a very long explanation..." * 100

        with pytest.raises(OllamaError, match="timeout"):
            ollama_client.generate(
                model=test_model,
                prompt=prompt,
                timeout=1  # 1 second timeout
            )

    def test_generate_handles_invalid_model(self, ollama_client):
        """Test error handling for invalid model."""
        with pytest.raises(OllamaError, match="not found"):
            ollama_client.generate(
                model="nonexistent-model:latest",
                prompt="test"
            )

    def test_generate_handles_connection_error(self):
        """Test error handling for connection failure."""
        client = OllamaClient(base_url="http://localhost:99999")

        with pytest.raises(OllamaError, match="connection"):
            client.generate(model="test", prompt="test")

class TestOllamaModelManagement:
    """Test model loading and management."""

    def test_ensure_model_loaded(self, ollama_client, test_model):
        """Verify model loading."""
        # Should not raise if model available
        ollama_client.ensure_model_loaded(test_model)

    def test_ensure_model_pulls_if_missing(self, ollama_client):
        """Test auto-pull for missing models."""
        # This test is expensive, marked as slow
        pytest.skip("Requires pulling model from registry")

        model = "qwen2.5-coder:0.5b"  # Very small model
        ollama_client.ensure_model_loaded(model, auto_pull=True)

        models = ollama_client.list_models()
        assert model in [m["name"] for m in models]

class TestOllamaRetry:
    """Test retry logic for transient failures."""

    def test_retry_on_epipe(self, ollama_client, test_model, mocker):
        """Test retry on EPIPE error."""
        # Simulate EPIPE on first call, success on second
        mock_generate = mocker.patch.object(
            ollama_client,
            "_raw_generate",
            side_effect=[
                OllamaError("Broken pipe (EPIPE)"),
                {"response": "success", "done": True}
            ]
        )

        response = ollama_client.generate(
            model=test_model,
            prompt="test",
            retry_on_error=True
        )

        assert response["response"] == "success"
        assert mock_generate.call_count == 2

    def test_retry_max_attempts(self, ollama_client, test_model, mocker):
        """Test max retry attempts."""
        # Always fail
        mocker.patch.object(
            ollama_client,
            "_raw_generate",
            side_effect=OllamaError("Persistent error")
        )

        with pytest.raises(OllamaError, match="Persistent error"):
            ollama_client.generate(
                model=test_model,
                prompt="test",
                retry_on_error=True,
                max_retries=3
            )
```

### 2. Checkpoint/Resume Integration Tests

**Purpose**: Verify checkpoint and resume workflows work end-to-end.

**Coverage Requirement**: 100% of recovery scenarios

#### Test Cases

```python
# tests/integration/test_checkpoint_resume.py

import pytest
import time
from pathlib import Path
from matric_eval import MatricEval
from matric_eval.state import Checkpoint, Recovery

@pytest.fixture
def eval_run(tmp_path, ollama_client, test_model):
    """Create evaluation run setup."""
    return MatricEval(
        models=[test_model],
        benchmarks=["humaneval"],
        tier="smoke",  # 5 problems
        output_dir=tmp_path / "results",
        checkpoint_frequency="problem"  # Checkpoint after each problem
    )

class TestCheckpointSave:
    """Test checkpoint persistence during evaluation."""

    def test_checkpoint_after_each_problem(self, eval_run):
        """Verify checkpoint saved after each problem."""
        # Start evaluation
        eval_run.run(max_problems=3)

        # Verify checkpoints exist
        checkpoint_dir = eval_run.output_dir / eval_run.run_id
        assert (checkpoint_dir / "state.json").exists()

        # Load checkpoint
        checkpoint = Checkpoint(
            run_id=eval_run.run_id,
            base_dir=checkpoint_dir
        )
        state = checkpoint.load()

        assert state["completed_problems"] == 3
        assert state["current_benchmark"] == "humaneval"

    def test_checkpoint_preserves_progress(self, eval_run):
        """Verify checkpoint contains all progress data."""
        eval_run.run(max_problems=2)

        checkpoint_dir = eval_run.output_dir / eval_run.run_id
        checkpoint = Checkpoint(run_id=eval_run.run_id, base_dir=checkpoint_dir)
        state = checkpoint.load()

        # Verify state contains expected fields
        assert "run_id" in state
        assert "models" in state
        assert "benchmarks" in state
        assert "completed_problems" in state
        assert "timestamp" in state

    def test_checkpoint_atomic_write(self, eval_run, tmp_path):
        """Verify checkpoint writes are atomic."""
        # This test verifies no partial writes even if interrupted

        eval_run.run(max_problems=1)

        checkpoint_dir = eval_run.output_dir / eval_run.run_id
        checkpoint_file = checkpoint_dir / "state.json"

        # Verify no temp files left behind
        temp_files = list(checkpoint_dir.glob("*.tmp"))
        assert len(temp_files) == 0

        # Verify checkpoint is valid JSON
        checkpoint = Checkpoint(run_id=eval_run.run_id, base_dir=checkpoint_dir)
        state = checkpoint.load()
        assert state is not None

class TestResumeInterrupted:
    """Test resuming interrupted evaluations."""

    def test_resume_continues_from_checkpoint(self, eval_run):
        """Verify resume continues where left off."""
        # Run partial evaluation
        eval_run.run(max_problems=2)
        checkpoint_dir = eval_run.output_dir / eval_run.run_id

        # Create new eval instance with resume
        resumed_eval = MatricEval.resume(checkpoint_dir)

        # Continue evaluation
        resumed_eval.run(max_problems=5)  # Complete all 5 problems

        # Verify total progress
        checkpoint = Checkpoint(
            run_id=resumed_eval.run_id,
            base_dir=checkpoint_dir
        )
        state = checkpoint.load()
        assert state["completed_problems"] == 5

    def test_resume_skips_completed(self, eval_run):
        """Verify resume skips already completed problems."""
        # Complete 2 problems
        eval_run.run(max_problems=2)
        checkpoint_dir = eval_run.output_dir / eval_run.run_id

        # Resume and track what gets executed
        resumed_eval = MatricEval.resume(checkpoint_dir)

        # Mock the scorer to track calls
        executed_problems = []
        original_score = resumed_eval.scorer.score

        def track_score(problem, response):
            executed_problems.append(problem["id"])
            return original_score(problem, response)

        resumed_eval.scorer.score = track_score

        # Run to completion
        resumed_eval.run(max_problems=5)

        # Verify only problems 3-5 were executed
        assert len(executed_problems) == 3
        assert "humaneval/0" not in executed_problems
        assert "humaneval/1" not in executed_problems

    def test_resume_handles_corrupted_checkpoint(self, eval_run, tmp_path):
        """Verify error handling for corrupted checkpoint."""
        # Run partial evaluation
        eval_run.run(max_problems=2)
        checkpoint_dir = eval_run.output_dir / eval_run.run_id

        # Corrupt checkpoint
        checkpoint_file = checkpoint_dir / "state.json"
        checkpoint_file.write_text("invalid json {{{")

        # Attempt resume
        with pytest.raises(Exception, match="corrupted"):
            MatricEval.resume(checkpoint_dir)

    def test_resume_with_different_config_warns(self, eval_run):
        """Verify warning when resuming with different config."""
        # Run with initial config
        eval_run.run(max_problems=2)
        checkpoint_dir = eval_run.output_dir / eval_run.run_id

        # Try to resume with different model
        with pytest.warns(UserWarning, match="config mismatch"):
            resumed_eval = MatricEval.resume(
                checkpoint_dir,
                models=["different-model:latest"]
            )

class TestRecoveryFromFailure:
    """Test recovery from various failure scenarios."""

    def test_recover_from_model_crash(self, tmp_path, ollama_client):
        """Verify recovery when model crashes mid-evaluation."""
        eval_run = MatricEval(
            models=["qwen2.5-coder:1.5b", "llama3.2:1b"],
            benchmarks=["humaneval"],
            tier="smoke",
            output_dir=tmp_path / "results"
        )

        # Simulate crash after first model
        eval_run.run(max_models=1)

        # Verify checkpoint saved
        checkpoint_dir = eval_run.output_dir / eval_run.run_id
        checkpoint = Checkpoint(run_id=eval_run.run_id, base_dir=checkpoint_dir)
        state = checkpoint.load()

        assert len(state["completed_models"]) == 1

        # Resume should continue with second model
        resumed_eval = MatricEval.resume(checkpoint_dir)
        resumed_eval.run()

        # Verify both models completed
        final_state = checkpoint.load()
        assert len(final_state["completed_models"]) == 2

    def test_recover_from_epipe_error(self, eval_run, mocker):
        """Verify recovery from EPIPE error during inference."""
        # Mock Ollama to fail with EPIPE, then succeed
        call_count = 0

        def mock_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Broken pipe (EPIPE)")
            return {"response": "def add(a,b): return a+b", "done": True}

        mocker.patch.object(
            eval_run.ollama_client,
            "generate",
            side_effect=mock_generate
        )

        # Run evaluation with retry enabled
        eval_run.run(max_problems=1, retry_on_error=True)

        # Verify problem completed despite initial failure
        checkpoint_dir = eval_run.output_dir / eval_run.run_id
        checkpoint = Checkpoint(run_id=eval_run.run_id, base_dir=checkpoint_dir)
        state = checkpoint.load()

        assert state["completed_problems"] == 1
        assert call_count == 2  # Failed once, retried successfully

    def test_recover_with_lock_file_cleanup(self, eval_run):
        """Verify stale lock files are cleaned up."""
        # Start evaluation
        eval_run.run(max_problems=1)
        checkpoint_dir = eval_run.output_dir / eval_run.run_id

        # Create stale lock file (simulate crashed run)
        lock_file = checkpoint_dir / ".lock"
        lock_file.write_text("stale-pid-12345")

        # Modify timestamp to be old (2 hours ago)
        import os
        old_time = time.time() - 7200  # 2 hours ago
        os.utime(lock_file, (old_time, old_time))

        # Resume should clean up stale lock and continue
        resumed_eval = MatricEval.resume(checkpoint_dir)
        resumed_eval.run(max_problems=2)

        # Verify no lock file after completion
        assert not lock_file.exists()

class TestGapDetection:
    """Test gap detection in incomplete runs."""

    def test_detect_missing_benchmarks(self, tmp_path):
        """Verify detection of missing benchmarks."""
        # Create incomplete run structure
        run_dir = tmp_path / "run-123"
        run_dir.mkdir()

        model_dir = run_dir / "qwen2.5-coder-1.5b"
        model_dir.mkdir()

        # Only humaneval completed, mbpp missing
        (model_dir / "humaneval").mkdir()
        (model_dir / "humaneval" / "meta.json").write_text(
            '{"status": "complete", "problems": 5}'
        )

        # Detect gaps
        recovery = Recovery(run_dir=run_dir)
        gaps = recovery.detect_gaps()

        assert len(gaps) > 0
        assert any(g["benchmark"] == "mbpp" for g in gaps)

    def test_detect_partial_benchmark(self, tmp_path):
        """Verify detection of partially completed benchmark."""
        run_dir = tmp_path / "run-123"
        model_dir = run_dir / "model"
        benchmark_dir = model_dir / "humaneval"
        benchmark_dir.mkdir(parents=True)

        # Create checkpoint showing partial progress
        checkpoint = Checkpoint(run_id="run-123", base_dir=run_dir)
        checkpoint.save({
            "benchmark": "humaneval",
            "total_problems": 5,
            "completed_problems": 3,
            "completed": ["humaneval/0", "humaneval/1", "humaneval/2"]
        })

        # Detect gaps
        recovery = Recovery(run_dir=run_dir)
        gaps = recovery.detect_gaps()

        assert len(gaps) == 1
        assert gaps[0]["completed"] == 3
        assert gaps[0]["remaining"] == 2

    def test_fill_gaps_completes_missing(self, tmp_path, ollama_client):
        """Verify fill-gaps mode completes missing work."""
        # Create run with gaps
        run_dir = tmp_path / "run-incomplete"
        run_dir.mkdir()

        # Create partial structure
        checkpoint = Checkpoint(run_id="run-incomplete", base_dir=run_dir)
        checkpoint.save({
            "models": ["qwen2.5-coder:1.5b"],
            "benchmarks": ["humaneval"],
            "tier": "smoke",
            "completed_problems": 3,
            "total_problems": 5
        })

        # Fill gaps
        recovery = Recovery(run_dir=run_dir)
        plan = recovery.create_plan(strategy="fill_gaps")

        # Execute plan
        filled_eval = MatricEval.from_recovery_plan(plan)
        filled_eval.run()

        # Verify gaps filled
        final_state = checkpoint.load()
        assert final_state["completed_problems"] == 5
```

### 3. Benchmark Validation Tests

**Purpose**: Verify benchmark implementations match reference implementations.

**Coverage Requirement**: 100% of public benchmarks

#### Test Cases

```python
# tests/integration/test_benchmark_validation.py

import pytest
from pathlib import Path
from matric_eval.benchmarks import HumanEval, MBPP, GSM8K
from matric_eval.validation import BenchmarkValidator

class TestHumanEvalValidation:
    """Validate HumanEval implementation."""

    @pytest.fixture
    def humaneval_validator(self):
        """HumanEval validator with reference data."""
        return BenchmarkValidator(
            benchmark="humaneval",
            reference_data_path="/home/roctinam/data/evals/humaneval"
        )

    def test_problem_count(self, humaneval_validator):
        """Verify correct number of problems."""
        benchmark = HumanEval()
        problems = benchmark.load_problems()

        assert len(problems) == 164

    def test_smoke_subset_selection(self, humaneval_validator):
        """Verify smoke tier selects correct problems."""
        benchmark = HumanEval(tier="smoke")
        problems = benchmark.load_problems()

        # Smoke tier should have 5 problems
        assert len(problems) == 5

        # Should use consistent seeded selection
        problems2 = HumanEval(tier="smoke", seed=42).load_problems()
        assert [p["id"] for p in problems] == [p["id"] for p in problems2]

    def test_prompt_format_matches_reference(self, humaneval_validator):
        """Verify prompt format matches reference implementation."""
        benchmark = HumanEval()
        problems = benchmark.load_problems()

        # Test first problem
        problem = problems[0]
        reference = humaneval_validator.get_reference_problem(problem["id"])

        # Prompt should match
        assert problem["prompt"] == reference["prompt"]

    def test_test_cases_match_reference(self, humaneval_validator):
        """Verify test cases match reference."""
        benchmark = HumanEval()
        problems = benchmark.load_problems()

        for problem in problems[:5]:  # Test first 5
            reference = humaneval_validator.get_reference_problem(problem["id"])
            assert problem["test"] == reference["test"]

    def test_scoring_matches_reference(self, humaneval_validator, ollama_client):
        """Verify scoring logic matches reference."""
        benchmark = HumanEval(tier="smoke")

        # Run benchmark
        results = benchmark.run(model="qwen2.5-coder:1.5b")

        # Compare with reference results (if available)
        # This is a smoke test - results may vary slightly due to model
        for result in results:
            reference_result = humaneval_validator.get_reference_result(
                problem_id=result["problem_id"],
                model="qwen2.5-coder:1.5b"
            )

            # Score should be in same range (+/- 10% for model variance)
            if reference_result:
                assert abs(result["score"] - reference_result["score"]) < 0.1

class TestMBPPValidation:
    """Validate MBPP implementation."""

    def test_function_name_extraction(self):
        """Verify function names extracted correctly (critical bug fix)."""
        benchmark = MBPP()
        problems = benchmark.load_problems()

        # Test problem with complex function name
        test_case = 'assert similar_elements((3,4,5,6),(5,7,4,10)) == (4,5)'
        function_name = benchmark.extract_function_name(test_case)

        assert function_name == "similar_elements"

    def test_function_name_in_prompt(self):
        """Verify function name included in prompt."""
        benchmark = MBPP()
        problems = benchmark.load_problems()

        problem = problems[0]

        # Prompt should contain the expected function name
        function_name = benchmark.extract_function_name(problem["test"])
        assert function_name in problem["prompt"]

    def test_problem_count(self):
        """Verify correct number of problems."""
        benchmark = MBPP()
        problems = benchmark.load_problems()

        assert len(problems) == 974

class TestGSM8KValidation:
    """Validate GSM8K implementation."""

    def test_answer_extraction(self):
        """Verify numeric answer extraction."""
        benchmark = GSM8K()

        test_cases = [
            ("The answer is 42", 42),
            ("#### 123", 123),
            ("So the total is $25.50", 25.50),
        ]

        for response, expected in test_cases:
            answer = benchmark.extract_answer(response)
            assert answer == expected

    def test_scoring_logic(self):
        """Verify scoring logic for math problems."""
        benchmark = GSM8K()

        # Exact match
        assert benchmark.score(answer=42, expected=42) == 1.0

        # Close enough (floating point)
        assert benchmark.score(answer=42.0001, expected=42.0) == 1.0

        # Wrong answer
        assert benchmark.score(answer=42, expected=43) == 0.0
```

### 4. CLI Integration Tests

**Purpose**: Verify CLI commands trigger correct core library flows.

**Coverage Requirement**: 100% of CLI commands

#### Test Cases

```python
# tests/integration/test_cli_integration.py

import pytest
import subprocess
import json
from pathlib import Path

class TestCLICommands:
    """Test CLI command execution."""

    def test_smoke_tier_execution(self, tmp_path):
        """Test smoke tier evaluation via CLI."""
        result = subprocess.run(
            [
                "matric-eval",
                "--tier", "smoke",
                "--model", "qwen2.5-coder:1.5b",
                "--output", str(tmp_path / "results")
            ],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes
        )

        assert result.returncode == 0
        assert "Evaluation complete" in result.stdout

        # Verify output created
        assert (tmp_path / "results").exists()

    def test_resume_command(self, tmp_path):
        """Test resume command."""
        # First run partial evaluation
        run1 = subprocess.run(
            [
                "matric-eval",
                "--tier", "smoke",
                "--model", "qwen2.5-coder:1.5b",
                "--output", str(tmp_path / "results"),
                "--max-problems", "2"
            ],
            capture_output=True,
            text=True,
            timeout=120
        )

        assert run1.returncode == 0

        # Find run directory
        run_dirs = list((tmp_path / "results").glob("run-*"))
        assert len(run_dirs) == 1
        run_dir = run_dirs[0]

        # Resume
        run2 = subprocess.run(
            [
                "matric-eval",
                "--resume", str(run_dir)
            ],
            capture_output=True,
            text=True,
            timeout=120
        )

        assert run2.returncode == 0
        assert "Resuming from checkpoint" in run2.stdout

    def test_validate_command(self, tmp_path):
        """Test validate command."""
        # Run evaluation
        subprocess.run(
            [
                "matric-eval",
                "--tier", "smoke",
                "--model", "qwen2.5-coder:1.5b",
                "--output", str(tmp_path / "results")
            ],
            timeout=300
        )

        # Validate
        run_dirs = list((tmp_path / "results").glob("run-*"))
        run_dir = run_dirs[0]

        result = subprocess.run(
            [
                "matric-eval",
                "--validate", str(run_dir)
            ],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0
        assert "complete" in result.stdout.lower()

    def test_fill_gaps_command(self, tmp_path):
        """Test fill-gaps command."""
        # Create incomplete run
        # ... setup code ...

        result = subprocess.run(
            [
                "matric-eval",
                "--resume", str(run_dir),
                "--fill-gaps"
            ],
            capture_output=True,
            text=True,
            timeout=300
        )

        assert result.returncode == 0
        assert "gaps filled" in result.stdout.lower() or "complete" in result.stdout.lower()
```

## Test Data Management

### Sample Datasets

Create minimal test datasets for fast execution:

```python
# scripts/prepare-test-datasets.py

"""Prepare minimal test datasets for integration tests."""

import json
from pathlib import Path

DATASETS_DIR = Path("tests/fixtures/datasets")
DATASETS_DIR.mkdir(parents=True, exist_ok=True)

# HumanEval smoke subset (5 problems)
humaneval_smoke = [
    {
        "task_id": "HumanEval/0",
        "prompt": "def has_close_elements(numbers: List[float], threshold: float) -> bool:\n    \"\"\" Check if in given list of numbers, are any two numbers closer to each other than\n    given threshold.\n    >>> has_close_elements([1.0, 2.0, 3.0], 0.5)\n    False\n    >>> has_close_elements([1.0, 2.8, 3.0, 4.0, 5.0, 2.0], 0.3)\n    True\n    \"\"\"\n",
        "entry_point": "has_close_elements",
        "canonical_solution": "    for idx, elem in enumerate(numbers):\n        for idx2, elem2 in enumerate(numbers):\n            if idx != idx2:\n                distance = abs(elem - elem2)\n                if distance < threshold:\n                    return True\n\n    return False\n",
        "test": "def check(candidate):\n    assert candidate([1.0, 2.0, 3.9, 4.0, 5.0, 2.2], 0.3) == True\n    assert candidate([1.0, 2.0, 3.9, 4.0, 5.0, 2.2], 0.05) == False\n"
    },
    # ... 4 more problems
]

with open(DATASETS_DIR / "humaneval-smoke.jsonl", "w") as f:
    for problem in humaneval_smoke:
        f.write(json.dumps(problem) + "\n")

print(f"Test datasets prepared in {DATASETS_DIR}")
```

### Fixtures

```python
# tests/integration/conftest.py

import pytest
from pathlib import Path

@pytest.fixture(scope="session")
def test_datasets_dir():
    """Path to test datasets."""
    return Path(__file__).parent.parent / "fixtures" / "datasets"

@pytest.fixture(scope="session")
def humaneval_smoke_data(test_datasets_dir):
    """Load HumanEval smoke test data."""
    import json
    data = []
    with open(test_datasets_dir / "humaneval-smoke.jsonl") as f:
        for line in f:
            data.append(json.loads(line))
    return data
```

## Execution

### Local Execution

```bash
# Start test environment
./scripts/setup-integration-tests.sh

# Run all integration tests
pytest tests/integration/ -v

# Run specific category
pytest tests/integration/test_ollama_integration.py -v

# Run with coverage
pytest tests/integration/ --cov=src/matric_eval

# Cleanup
docker compose -f docker-compose.test.yml down -v
```

### CI Execution

```yaml
# .github/workflows/test-integration.yml
name: Integration Tests

on: [push, pull_request]

jobs:
  integration-test:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Start Ollama
        run: |
          docker run -d --name ollama -p 11434:11434 ollama/ollama:latest
          docker exec ollama ollama pull qwen2.5-coder:1.5b
          docker exec ollama ollama pull llama3.2:1b

      - name: Install dependencies
        run: |
          pip install uv
          uv sync --all-extras

      - name: Run integration tests
        env:
          OLLAMA_API_BASE: http://localhost:11434
        run: |
          pytest tests/integration/ \
            --cov=src/matric_eval \
            --cov-report=xml \
            --junitxml=junit-integration.xml \
            -v

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
          flags: integration

      - name: Cleanup
        if: always()
        run: docker stop ollama && docker rm ollama
```

## Success Criteria

Integration test plan is successful when:

1. **Coverage Achieved**:
   - [ ] 100% of Ollama integration points tested
   - [ ] 100% of checkpoint/resume scenarios tested
   - [ ] 100% of benchmark validations passing

2. **Reliability Validated**:
   - [ ] All 10 recovery scenarios pass
   - [ ] No data loss in any failure scenario
   - [ ] Resume works consistently

3. **Benchmark Correctness**:
   - [ ] All benchmarks match reference implementations
   - [ ] Scoring logic validated
   - [ ] Edge cases handled

4. **Automation**:
   - [ ] Tests run on every PR
   - [ ] Docker environment reproducible
   - [ ] Fast execution (<30 min)

5. **Documentation**:
   - [ ] All test scenarios documented
   - [ ] Setup instructions clear
   - [ ] Failure debugging guide available

## References

- [Pytest Integration Testing](https://docs.pytest.org/en/stable/goodpractices.html)
- [Docker Compose for Testing](https://docs.docker.com/compose/)
- [Ollama API Documentation](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [HumanEval Reference](https://github.com/openai/human-eval)
- [MBPP Reference](https://github.com/google-research/google-research/tree/master/mbpp)
