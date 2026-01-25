# Unit Test Plan - matric-eval

**Project**: matric-eval - Consolidated Model Evaluation Framework
**Test Level**: Unit (L1)
**Profile**: Production
**Coverage Target**: 80% lines, 75% branches (100% for critical components)
**Status**: Planning Phase
**Last Updated**: 2026-01-24

## Document Purpose

This document defines the unit testing approach for matric-eval, specifying test structure, mocking strategies, coverage requirements, and test execution for individual components in isolation.

## Scope

### In Scope

**Core Components**:
- State management (checkpoint, recovery, validation)
- Custom scorers (code execution, constraint checking, LLM-as-judge)
- Extractors (code extraction, response parsing)
- Validators (result validation, schema checking)
- Utilities (sampling, filtering, formatting)
- Configuration (model configs, threshold management)
- CLI argument parsing and command routing

### Out of Scope

- External service integration (Ollama, Inspect AI) - covered in integration tests
- End-to-end CLI workflows - covered in system tests
- Performance benchmarking - covered in performance tests
- Multi-component interactions - covered in integration tests

## Test Framework Configuration

### Technology Stack

```python
# pyproject.toml
[project.optional-dependencies]
test = [
    "pytest>=8.0.0",
    "pytest-cov>=4.1.0",
    "pytest-mock>=3.12.0",
    "pytest-timeout>=2.2.0",
    "pytest-xdist>=3.5.0",
    "hypothesis>=6.92.0",
    "freezegun>=1.4.0",
    "pytest-benchmark>=4.0.0",
]
```

### pytest Configuration

```ini
# pyproject.toml
[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "--strict-markers",
    "--strict-config",
    "--cov=src/matric_eval",
    "--cov-report=term-missing",
    "--cov-report=html",
    "--cov-report=json",
    "--cov-fail-under=80",
    "--timeout=10",
    "-ra",
    "-v",
]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "critical: marks tests for critical components (100% coverage required)",
    "unit: unit tests",
    "integration: integration tests",
    "system: system tests",
]
```

### Coverage Configuration

```ini
# pyproject.toml
[tool.coverage.run]
source = ["src/matric_eval"]
branch = true
omit = [
    "*/tests/*",
    "*/__pycache__/*",
    "*/site-packages/*",
    "*/__init__.py",
]

[tool.coverage.report]
precision = 2
show_missing = true
skip_covered = false
sort = "Cover"
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
    "if typing.TYPE_CHECKING:",
    "@abstractmethod",
    "@overload",
]

[tool.coverage.html]
directory = "htmlcov"

[tool.coverage.json]
output = "coverage.json"
```

## Test Directory Structure

```
tests/
├── unit/                           # Unit tests
│   ├── __init__.py
│   ├── conftest.py                 # Shared fixtures
│   ├── test_checkpoint.py          # Checkpoint state management
│   ├── test_recovery.py            # Recovery logic
│   ├── test_scorers/               # Scorer tests
│   │   ├── test_code_scorer.py
│   │   ├── test_constraint_scorer.py
│   │   └── test_llm_judge_scorer.py
│   ├── test_extractors/            # Extractor tests
│   │   ├── test_code_extractor.py
│   │   └── test_response_parser.py
│   ├── test_validators/            # Validator tests
│   │   ├── test_result_validator.py
│   │   └── test_schema_validator.py
│   ├── test_utils/                 # Utility tests
│   │   ├── test_sampling.py
│   │   ├── test_filtering.py
│   │   └── test_formatting.py
│   ├── test_config/                # Config tests
│   │   ├── test_model_config.py
│   │   └── test_threshold_manager.py
│   └── test_cli.py                 # CLI argument parsing
│
├── integration/                    # Integration tests (separate plan)
├── system/                         # System tests (separate plan)
├── fixtures/                       # Test data
│   ├── checkpoints/                # Sample checkpoint files
│   ├── responses/                  # Sample LLM responses
│   ├── configs/                    # Sample configurations
│   └── datasets/                   # Sample test datasets
└── conftest.py                     # Global fixtures
```

## Critical Components (100% Coverage Required)

### 1. Checkpoint State Management

**Module**: `src/matric_eval/state/checkpoint.py`

**Coverage Requirement**: 100% lines, 100% branches

**Test Cases**:

```python
# tests/unit/test_checkpoint.py

import pytest
from pathlib import Path
from matric_eval.state import Checkpoint, CheckpointError

class TestCheckpointSave:
    """Test checkpoint state persistence."""

    @pytest.mark.critical
    def test_save_creates_file(self, tmp_path):
        """Verify checkpoint file is created."""
        checkpoint = Checkpoint(run_id="test-run", base_dir=tmp_path)
        state = {"model": "llama3.2:3b", "benchmark": "humaneval", "problem": 5}

        checkpoint.save(state)

        assert (tmp_path / "state.json").exists()

    @pytest.mark.critical
    def test_save_atomic_write(self, tmp_path, mocker):
        """Verify atomic write (temp file + rename)."""
        checkpoint = Checkpoint(run_id="test-run", base_dir=tmp_path)
        state = {"model": "test"}

        mock_rename = mocker.spy(Path, "rename")
        checkpoint.save(state)

        assert mock_rename.call_count == 1
        # Verify temp file pattern used
        call_args = mock_rename.call_args[0]
        assert ".tmp" in str(call_args[0])

    @pytest.mark.critical
    def test_save_preserves_data(self, tmp_path):
        """Verify saved data matches input."""
        checkpoint = Checkpoint(run_id="test-run", base_dir=tmp_path)
        state = {
            "model": "llama3.2:3b",
            "benchmark": "humaneval",
            "problem": 5,
            "completed": [1, 2, 3, 4]
        }

        checkpoint.save(state)
        loaded = checkpoint.load()

        assert loaded == state

    @pytest.mark.critical
    def test_save_handles_disk_full(self, tmp_path, mocker):
        """Verify graceful failure on disk full."""
        checkpoint = Checkpoint(run_id="test-run", base_dir=tmp_path)
        state = {"model": "test"}

        # Simulate disk full
        mocker.patch("builtins.open", side_effect=OSError("No space left on device"))

        with pytest.raises(CheckpointError, match="No space"):
            checkpoint.save(state)

    @pytest.mark.critical
    def test_save_creates_parent_dirs(self, tmp_path):
        """Verify parent directories are created."""
        nested_path = tmp_path / "run-123" / "model-abc" / "benchmark-xyz"
        checkpoint = Checkpoint(run_id="test-run", base_dir=nested_path)
        state = {"test": "data"}

        checkpoint.save(state)

        assert nested_path.exists()
        assert (nested_path / "state.json").exists()

class TestCheckpointLoad:
    """Test checkpoint state restoration."""

    @pytest.mark.critical
    def test_load_missing_file_returns_none(self, tmp_path):
        """Verify None returned when checkpoint doesn't exist."""
        checkpoint = Checkpoint(run_id="test-run", base_dir=tmp_path)

        result = checkpoint.load()

        assert result is None

    @pytest.mark.critical
    def test_load_corrupted_file_raises_error(self, tmp_path):
        """Verify error on corrupted checkpoint."""
        checkpoint = Checkpoint(run_id="test-run", base_dir=tmp_path)
        state_file = tmp_path / "state.json"
        state_file.write_text("invalid json {{{")

        with pytest.raises(CheckpointError, match="corrupted"):
            checkpoint.load()

    @pytest.mark.critical
    def test_load_validates_schema(self, tmp_path):
        """Verify loaded state validates against schema."""
        checkpoint = Checkpoint(run_id="test-run", base_dir=tmp_path)
        state_file = tmp_path / "state.json"
        # Missing required field
        state_file.write_text('{"model": "test"}')

        with pytest.raises(CheckpointError, match="schema"):
            checkpoint.load(validate=True)

class TestCheckpointLocking:
    """Test concurrent access prevention."""

    @pytest.mark.critical
    def test_lock_prevents_concurrent_access(self, tmp_path):
        """Verify lock file prevents concurrent runs."""
        checkpoint1 = Checkpoint(run_id="test-run", base_dir=tmp_path)
        checkpoint2 = Checkpoint(run_id="test-run", base_dir=tmp_path)

        with checkpoint1.lock():
            with pytest.raises(CheckpointError, match="locked"):
                with checkpoint2.lock():
                    pass

    @pytest.mark.critical
    def test_lock_released_on_exit(self, tmp_path):
        """Verify lock released after context exit."""
        checkpoint = Checkpoint(run_id="test-run", base_dir=tmp_path)

        with checkpoint.lock():
            assert (tmp_path / ".lock").exists()

        assert not (tmp_path / ".lock").exists()

    @pytest.mark.critical
    def test_lock_detects_zombie_runs(self, tmp_path, freezegun):
        """Verify stale locks are detected and cleared."""
        checkpoint = Checkpoint(run_id="test-run", base_dir=tmp_path)
        lock_file = tmp_path / ".lock"

        # Create stale lock (2 hours old)
        with freezegun.freeze_time("2026-01-24 10:00:00"):
            lock_file.write_text("old-pid-12345")

        # Try to acquire lock now
        with freezegun.freeze_time("2026-01-24 12:00:00"):
            with checkpoint.lock(timeout=3600):  # 1 hour timeout
                assert True  # Should succeed, stale lock cleared
```

### 2. Recovery Logic

**Module**: `src/matric_eval/state/recovery.py`

**Coverage Requirement**: 100% lines, 100% branches

**Test Cases**:

```python
# tests/unit/test_recovery.py

import pytest
from matric_eval.state import Recovery, RecoveryStrategy

class TestRecoveryGapDetection:
    """Test gap detection in incomplete runs."""

    @pytest.mark.critical
    def test_detect_missing_benchmarks(self, tmp_path, sample_incomplete_run):
        """Verify missing benchmarks are identified."""
        recovery = Recovery(run_dir=tmp_path)

        gaps = recovery.detect_gaps()

        assert len(gaps) == 2
        assert gaps[0] == {"model": "llama3.2:3b", "benchmark": "mbpp"}
        assert gaps[1] == {"model": "codestral:latest", "benchmark": "humaneval"}

    @pytest.mark.critical
    def test_detect_partial_benchmarks(self, tmp_path, sample_partial_benchmark):
        """Verify partially completed benchmarks detected."""
        recovery = Recovery(run_dir=tmp_path)

        gaps = recovery.detect_gaps()

        assert len(gaps) == 1
        gap = gaps[0]
        assert gap["benchmark"] == "humaneval"
        assert gap["completed"] == 82  # Out of 164
        assert gap["missing"] == [83, 84, ..., 164]

    @pytest.mark.critical
    def test_detect_corrupted_results(self, tmp_path, sample_corrupted_result):
        """Verify corrupted results flagged for re-run."""
        recovery = Recovery(run_dir=tmp_path)

        corrupted = recovery.detect_corrupted()

        assert len(corrupted) == 1
        assert corrupted[0]["problem_id"] == "humaneval/42"
        assert corrupted[0]["reason"] == "missing validation.json"

class TestRecoveryPlanning:
    """Test recovery plan generation."""

    @pytest.mark.critical
    def test_plan_resume_from_checkpoint(self, tmp_path, sample_checkpoint):
        """Verify resume plan starts from checkpoint."""
        recovery = Recovery(run_dir=tmp_path)

        plan = recovery.create_plan(strategy=RecoveryStrategy.RESUME)

        assert plan.start_model == "llama3.2:3b"
        assert plan.start_benchmark == "humaneval"
        assert plan.start_problem == 83

    @pytest.mark.critical
    def test_plan_fill_gaps(self, tmp_path, sample_incomplete_run):
        """Verify gap-fill plan includes all missing work."""
        recovery = Recovery(run_dir=tmp_path)

        plan = recovery.create_plan(strategy=RecoveryStrategy.FILL_GAPS)

        assert len(plan.tasks) == 2
        assert all(task.reason == "missing" for task in plan.tasks)

    @pytest.mark.critical
    def test_plan_selective_rerun(self, tmp_path):
        """Verify selective re-run plan."""
        recovery = Recovery(run_dir=tmp_path)

        plan = recovery.create_plan(
            strategy=RecoveryStrategy.SELECTIVE,
            model="llama3.2:3b",
            benchmark="humaneval"
        )

        assert len(plan.tasks) == 1
        assert plan.tasks[0].model == "llama3.2:3b"
        assert plan.tasks[0].benchmark == "humaneval"

class TestRecoveryExecution:
    """Test recovery execution."""

    @pytest.mark.critical
    def test_execute_skip_completed(self, tmp_path, sample_completed_work):
        """Verify completed work is skipped."""
        recovery = Recovery(run_dir=tmp_path)
        plan = recovery.create_plan(strategy=RecoveryStrategy.RESUME)

        executed = recovery.execute(plan, skip_completed=True)

        assert executed.skipped_count == 82
        assert executed.executed_count == 82  # Remaining problems

    @pytest.mark.critical
    def test_execute_idempotent(self, tmp_path, sample_checkpoint):
        """Verify re-execution produces same results."""
        recovery = Recovery(run_dir=tmp_path)
        plan = recovery.create_plan(strategy=RecoveryStrategy.RESUME)

        result1 = recovery.execute(plan)
        result2 = recovery.execute(plan)

        assert result1.results == result2.results
```

### 3. Custom Scorers

**Module**: `src/matric_eval/scorers/code_scorer.py`

**Coverage Requirement**: 100% lines, 100% branches

**Test Cases**:

```python
# tests/unit/test_scorers/test_code_scorer.py

import pytest
from hypothesis import given, strategies as st
from matric_eval.scorers import CodeScorer, ExecutionResult

class TestCodeExtraction:
    """Test code extraction from LLM responses."""

    @pytest.mark.critical
    def test_extract_markdown_fence(self):
        """Extract code from markdown fence."""
        scorer = CodeScorer()
        response = """
        Here's the solution:
        ```python
        def add(a, b):
            return a + b
        ```
        """

        code = scorer.extract_code(response)

        assert code == "def add(a, b):\n    return a + b"

    @pytest.mark.critical
    def test_extract_without_language_tag(self):
        """Extract code from fence without language tag."""
        scorer = CodeScorer()
        response = """
        ```
        def add(a, b):
            return a + b
        ```
        """

        code = scorer.extract_code(response)

        assert code == "def add(a, b):\n    return a + b"

    @pytest.mark.critical
    def test_extract_multiple_fences_uses_last(self):
        """Use last code fence when multiple present."""
        scorer = CodeScorer()
        response = """
        First attempt:
        ```python
        def add(a, b):
            return a + b + 1  # Wrong
        ```

        Corrected:
        ```python
        def add(a, b):
            return a + b
        ```
        """

        code = scorer.extract_code(response)

        assert "# Wrong" not in code
        assert code == "def add(a, b):\n    return a + b"

    @pytest.mark.critical
    def test_extract_no_fence_returns_full_response(self):
        """Return full response if no markdown fence."""
        scorer = CodeScorer()
        response = "def add(a, b):\n    return a + b"

        code = scorer.extract_code(response)

        assert code == response

    @pytest.mark.critical
    @given(st.text())
    def test_extract_never_crashes(self, response):
        """Property: extraction never crashes on any input."""
        scorer = CodeScorer()

        result = scorer.extract_code(response)

        assert isinstance(result, str)

class TestCodeExecution:
    """Test safe code execution."""

    @pytest.mark.critical
    def test_execute_simple_function(self):
        """Execute simple function successfully."""
        scorer = CodeScorer(timeout=1)
        code = "def add(a, b):\n    return a + b"
        test = "assert add(2, 3) == 5"

        result = scorer.execute(code, test)

        assert result.passed is True
        assert result.error is None

    @pytest.mark.critical
    def test_execute_timeout_enforced(self):
        """Verify timeout enforcement."""
        scorer = CodeScorer(timeout=1)
        code = """
import time
def slow():
    time.sleep(10)
    return True
"""
        test = "assert slow()"

        result = scorer.execute(code, test)

        assert result.passed is False
        assert "timeout" in result.error.lower()

    @pytest.mark.critical
    def test_execute_memory_limit_enforced(self):
        """Verify memory limit enforcement."""
        scorer = CodeScorer(timeout=5, memory_mb=100)
        code = """
def consume_memory():
    x = [0] * (200 * 1024 * 1024)  # 200MB
    return True
"""
        test = "assert consume_memory()"

        result = scorer.execute(code, test)

        assert result.passed is False
        assert "memory" in result.error.lower()

    @pytest.mark.critical
    def test_execute_no_network_access(self):
        """Verify network access blocked."""
        scorer = CodeScorer(timeout=1)
        code = """
import urllib.request
def fetch():
    urllib.request.urlopen('http://example.com')
    return True
"""
        test = "assert fetch()"

        result = scorer.execute(code, test)

        assert result.passed is False
        assert "network" in result.error.lower() or "blocked" in result.error.lower()

    @pytest.mark.critical
    def test_execute_no_file_write(self):
        """Verify file write blocked outside sandbox."""
        scorer = CodeScorer(timeout=1)
        code = """
def write_file():
    with open('/tmp/malicious.txt', 'w') as f:
        f.write('bad')
    return True
"""
        test = "assert write_file()"

        result = scorer.execute(code, test)

        # Allowed in sandbox temp dir, blocked outside
        assert result.passed is False or not Path('/tmp/malicious.txt').exists()

    @pytest.mark.critical
    def test_execute_syntax_error_reported(self):
        """Verify syntax errors reported."""
        scorer = CodeScorer(timeout=1)
        code = "def add(a, b)\n    return a + b"  # Missing colon
        test = "assert add(2, 3) == 5"

        result = scorer.execute(code, test)

        assert result.passed is False
        assert "syntax" in result.error.lower()

    @pytest.mark.critical
    def test_execute_runtime_error_reported(self):
        """Verify runtime errors reported."""
        scorer = CodeScorer(timeout=1)
        code = "def divide(a, b):\n    return a / b"
        test = "assert divide(10, 0) == 0"

        result = scorer.execute(code, test)

        assert result.passed is False
        assert "division" in result.error.lower() or "zero" in result.error.lower()

class TestMBPPFunctionNameExtraction:
    """Test MBPP function name extraction (critical bug from matric-cli)."""

    @pytest.mark.critical
    def test_extract_function_name_from_test(self):
        """Extract function name from test assertion."""
        scorer = CodeScorer()
        test = "assert similar_elements((3, 4, 5, 6),(5, 7, 4, 10)) == (4, 5)"

        function_name = scorer.extract_function_name(test)

        assert function_name == "similar_elements"

    @pytest.mark.critical
    def test_include_function_name_in_prompt(self):
        """Verify function name included in prompt."""
        scorer = CodeScorer()
        test = "assert add(2, 3) == 5"
        prompt_template = "Write a function called {function_name} that..."

        prompt = scorer.format_prompt(prompt_template, test)

        assert "add" in prompt

    @pytest.mark.critical
    def test_extract_complex_function_names(self):
        """Handle complex function names."""
        scorer = CodeScorer()
        test_cases = [
            ("assert my_func_123(x) == y", "my_func_123"),
            ("assert _private_func() == 1", "_private_func"),
            ("assert obj.method() == True", "method"),
        ]

        for test, expected in test_cases:
            result = scorer.extract_function_name(test)
            assert result == expected
```

## Mocking Strategy

### External Dependencies to Mock

1. **Ollama API**: Mock HTTP client
2. **Inspect AI**: Mock task execution
3. **File I/O**: Use tmp_path fixture
4. **Time**: Use freezegun
5. **Random**: Seed for reproducibility
6. **Network**: Block all network access
7. **Subprocess**: Mock execution

### Pytest Fixtures

```python
# tests/conftest.py

import pytest
import json
from pathlib import Path
from typing import Dict, Any

@pytest.fixture
def tmp_path(tmp_path_factory):
    """Temporary directory for test isolation."""
    return tmp_path_factory.mktemp("matric-eval-test")

@pytest.fixture
def sample_checkpoint(tmp_path) -> Path:
    """Sample checkpoint state."""
    state = {
        "run_id": "test-run-123",
        "model": "llama3.2:3b",
        "benchmark": "humaneval",
        "problem": 82,
        "completed": list(range(82)),
        "timestamp": "2026-01-24T10:00:00Z"
    }
    checkpoint_file = tmp_path / "state.json"
    checkpoint_file.write_text(json.dumps(state, indent=2))
    return tmp_path

@pytest.fixture
def sample_incomplete_run(tmp_path) -> Path:
    """Sample incomplete evaluation run."""
    run_dir = tmp_path / "run-123"
    run_dir.mkdir()

    # Model with some benchmarks complete
    model_dir = run_dir / "llama3.2-3b"
    model_dir.mkdir()

    # Completed benchmark
    (model_dir / "humaneval").mkdir()
    (model_dir / "humaneval" / "meta.json").write_text('{"status": "complete"}')

    # Missing benchmark (mbpp)

    return run_dir

@pytest.fixture
def sample_llm_response() -> str:
    """Sample LLM response with code."""
    return """
    Here's the solution:

    ```python
    def add(a: int, b: int) -> int:
        return a + b
    ```

    This function adds two numbers.
    """

@pytest.fixture
def mock_ollama(mocker):
    """Mock Ollama API client."""
    mock_client = mocker.Mock()
    mock_client.generate.return_value = {
        "response": "def add(a, b):\n    return a + b",
        "done": True
    }
    return mock_client

@pytest.fixture
def seed_random():
    """Seed random for reproducibility."""
    import random
    random.seed(42)
    yield
    random.seed()  # Reset
```

### Mocking Best Practices

1. **Mock at boundaries**: Mock external services, not internal functions
2. **Verify calls**: Use `assert_called_with()` to verify mocked calls
3. **Realistic data**: Use fixtures with realistic test data
4. **Avoid over-mocking**: Only mock what's necessary
5. **Side effects**: Test error scenarios with `side_effect`

## Property-Based Testing with Hypothesis

For scorers and extractors, use property-based testing:

```python
from hypothesis import given, strategies as st

class TestCodeExtractorProperties:
    """Property-based tests for code extractor."""

    @given(st.text())
    def test_extract_never_crashes(self, input_text):
        """Property: extractor never crashes."""
        extractor = CodeExtractor()
        result = extractor.extract(input_text)
        assert isinstance(result, str)

    @given(st.text(), st.text())
    def test_extract_idempotent(self, code, wrapper):
        """Property: extracting twice gives same result."""
        extractor = CodeExtractor()
        text = f"{wrapper}\n```python\n{code}\n```\n{wrapper}"

        result1 = extractor.extract(text)
        result2 = extractor.extract(text)

        assert result1 == result2

    @given(st.text(min_size=1))
    def test_extract_preserves_code_content(self, code):
        """Property: extracted code contains original content."""
        extractor = CodeExtractor()
        text = f"```python\n{code}\n```"

        result = extractor.extract(text)

        # Result should contain the code (may have whitespace changes)
        assert code.strip() in result or result in code
```

## Test Execution

### Local Development

```bash
# Run all unit tests
pytest tests/unit/

# Run with coverage
pytest tests/unit/ --cov=src/matric_eval --cov-report=html

# Run only critical tests
pytest tests/unit/ -m critical

# Run specific module
pytest tests/unit/test_checkpoint.py

# Run with verbose output
pytest tests/unit/ -v

# Run in parallel (faster)
pytest tests/unit/ -n auto

# Run with benchmark profiling
pytest tests/unit/ --benchmark-only
```

### Continuous Integration

```yaml
# .github/workflows/test-unit.yml
name: Unit Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install uv
          uv sync --all-extras

      - name: Run unit tests
        run: |
          pytest tests/unit/ \
            --cov=src/matric_eval \
            --cov-report=xml \
            --cov-fail-under=80 \
            --junitxml=junit.xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml

      - name: Check critical coverage
        run: |
          pytest tests/unit/ \
            -m critical \
            --cov=src/matric_eval/state \
            --cov=src/matric_eval/scorers \
            --cov-fail-under=100
```

## Coverage Enforcement

### Pre-commit Hook

```bash
# .git/hooks/pre-commit
#!/bin/bash

echo "Running unit tests with coverage..."
pytest tests/unit/ --cov=src/matric_eval --cov-fail-under=80 --quiet

if [ $? -ne 0 ]; then
    echo "ERROR: Unit tests failed or coverage below 80%"
    echo "Run: pytest tests/unit/ --cov=src/matric_eval --cov-report=html"
    echo "Then open: htmlcov/index.html"
    exit 1
fi

echo "Unit tests passed with sufficient coverage"
```

### Coverage Regression Prevention

```python
# tests/test_coverage.py

import json
import pytest
from pathlib import Path

def test_coverage_not_decreased():
    """Verify coverage hasn't decreased."""
    current_coverage_file = Path("coverage.json")
    baseline_coverage_file = Path(".baseline-coverage.json")

    if not baseline_coverage_file.exists():
        pytest.skip("No baseline coverage file")

    with open(current_coverage_file) as f:
        current = json.load(f)

    with open(baseline_coverage_file) as f:
        baseline = json.load(f)

    current_percent = current["totals"]["percent_covered"]
    baseline_percent = baseline["totals"]["percent_covered"]

    assert current_percent >= baseline_percent, \
        f"Coverage decreased from {baseline_percent}% to {current_percent}%"
```

## Test Quality Checklist

Each unit test MUST satisfy:

- [ ] **Isolated**: No dependencies on other tests
- [ ] **Fast**: Executes in <1 second
- [ ] **Deterministic**: Same input always produces same output
- [ ] **Clear naming**: Test name describes scenario
- [ ] **Single assertion**: Test one thing (or closely related things)
- [ ] **Documented**: Docstring explains what's being tested
- [ ] **Arrange-Act-Assert**: Clear test structure
- [ ] **No hardcoded values**: Use fixtures or constants
- [ ] **Error scenarios**: Test both success and failure
- [ ] **Edge cases**: Test boundary conditions

## Common Patterns

### Testing Exceptions

```python
def test_checkpoint_raises_on_invalid_path():
    """Verify error raised for invalid path."""
    with pytest.raises(CheckpointError, match="invalid path"):
        Checkpoint(run_id="test", base_dir="/invalid/path")
```

### Testing File Operations

```python
def test_save_checkpoint(tmp_path):
    """Verify checkpoint saved correctly."""
    checkpoint = Checkpoint(run_id="test", base_dir=tmp_path)
    state = {"model": "test"}

    checkpoint.save(state)

    assert (tmp_path / "state.json").exists()
    assert json.loads((tmp_path / "state.json").read_text()) == state
```

### Testing Async Code

```python
@pytest.mark.asyncio
async def test_async_scorer():
    """Test async scorer execution."""
    scorer = AsyncCodeScorer()
    result = await scorer.score("def add(a,b): return a+b", "assert add(2,3)==5")
    assert result.passed is True
```

### Parameterized Tests

```python
@pytest.mark.parametrize("input,expected", [
    ("```python\ncode\n```", "code"),
    ("```\ncode\n```", "code"),
    ("code", "code"),
])
def test_code_extraction(input, expected):
    """Test code extraction variants."""
    extractor = CodeExtractor()
    assert extractor.extract(input) == expected
```

## Success Criteria

Unit test plan is successful when:

1. **Coverage Achieved**:
   - [ ] 80% overall line coverage
   - [ ] 100% coverage for critical components
   - [ ] 75% branch coverage

2. **Test Quality**:
   - [ ] All tests are isolated and deterministic
   - [ ] No flaky tests
   - [ ] Fast execution (<5 min for all unit tests)

3. **Automation**:
   - [ ] Tests run on every PR commit
   - [ ] Coverage reported automatically
   - [ ] Coverage regression blocked

4. **Documentation**:
   - [ ] All tests have docstrings
   - [ ] Fixtures documented
   - [ ] Mocking strategy clear

5. **Developer Experience**:
   - [ ] Easy to run locally
   - [ ] Clear failure messages
   - [ ] Fast feedback (<1 min for changed module)

## References

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-cov Plugin](https://pytest-cov.readthedocs.io/)
- [Hypothesis Property Testing](https://hypothesis.readthedocs.io/)
- [Google Testing Blog - Unit Tests](https://testing.googleblog.com/2013/07/testing-on-toilet-know-your-test-doubles.html)

## Appendix: Example Test Module

```python
# tests/unit/test_checkpoint.py

"""
Unit tests for checkpoint state management.

Coverage requirement: 100% (critical component)
"""

import pytest
import json
from pathlib import Path
from matric_eval.state import Checkpoint, CheckpointError

@pytest.fixture
def checkpoint(tmp_path):
    """Create checkpoint instance with temp directory."""
    return Checkpoint(run_id="test-run", base_dir=tmp_path)

class TestCheckpointSave:
    """Test checkpoint save operations."""

    @pytest.mark.critical
    def test_save_creates_file(self, checkpoint, tmp_path):
        """Verify checkpoint file created."""
        state = {"test": "data"}
        checkpoint.save(state)
        assert (tmp_path / "state.json").exists()

    @pytest.mark.critical
    def test_save_atomic(self, checkpoint, tmp_path, mocker):
        """Verify atomic write operation."""
        mock_rename = mocker.spy(Path, "rename")
        checkpoint.save({"test": "data"})
        assert mock_rename.call_count == 1

    # ... more tests

class TestCheckpointLoad:
    """Test checkpoint load operations."""

    @pytest.mark.critical
    def test_load_missing_returns_none(self, checkpoint):
        """Verify None returned for missing checkpoint."""
        assert checkpoint.load() is None

    # ... more tests

# Property-based tests
class TestCheckpointProperties:
    """Property-based tests for checkpoint."""

    @given(st.dictionaries(st.text(), st.text()))
    def test_save_load_roundtrip(self, checkpoint, state):
        """Property: save then load returns same state."""
        checkpoint.save(state)
        loaded = checkpoint.load()
        assert loaded == state
```
