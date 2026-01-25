# matric-eval Test Suite

Comprehensive test suite for the matric-eval model evaluation framework.

## Structure

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── factories.py             # Test data factories
├── README.md               # This file
├── test_cli.py             # CLI tests
├── test_config.py          # Configuration tests
├── unit/                   # Unit tests
│   ├── test_datasets.py    # Dataset loading tests
│   └── test_tasks.py       # Task definition tests
└── integration/            # Integration tests
    └── test_ollama.py      # Ollama integration tests
```

## Running Tests

### All Tests

```bash
# Run all tests with coverage
pytest --cov=matric_eval --cov-report=html

# Run all tests verbosely
pytest -v
```

### By Category

```bash
# Unit tests only (fast)
pytest -m unit

# Integration tests (require external services)
pytest -m integration

# Smoke tests
pytest -m smoke

# Exclude slow tests
pytest -m "not slow"
```

### By Module

```bash
# Test specific module
pytest tests/test_cli.py
pytest tests/unit/test_datasets.py

# Test specific class
pytest tests/test_cli.py::TestGetOllamaModels

# Test specific function
pytest tests/test_config.py::TestGetSeed::test_default_seed
```

### Coverage Reports

```bash
# Generate HTML coverage report
pytest --cov=matric_eval --cov-report=html
open htmlcov/index.html

# Show missing lines in terminal
pytest --cov=matric_eval --cov-report=term-missing

# Fail if coverage below 80%
pytest --cov=matric_eval --cov-fail-under=80
```

## Test Markers

Tests are marked for organization and selective execution:

- `@pytest.mark.unit` - Fast, isolated unit tests
- `@pytest.mark.integration` - Tests requiring external services (Ollama)
- `@pytest.mark.slow` - Tests taking >1 second
- `@pytest.mark.smoke` - Smoke test validation

## Fixtures

### Directory Fixtures

- `tmp_results_dir` - Temporary directory for test results
- `tmp_logs_dir` - Temporary logs directory

### Mock Ollama Fixtures

- `mock_ollama_list_output` - Mock 'ollama list' output
- `mock_ollama_models` - Expected parsed model list
- `mock_ollama_response` - Mock API response

### Sample Data Fixtures

- `sample_humaneval_problem` - Single HumanEval sample
- `sample_mbpp_problem` - Single MBPP sample
- `sample_gsm8k_problem` - Single GSM8K sample
- `sample_problems_list` - Combined list of samples

### Configuration Fixtures

- `env_no_overrides` - Clear environment variables
- `env_custom_seed` - Set custom seed
- `env_custom_samples` - Set custom sample counts

## Test Data Factories

Use factories to create dynamic test data:

```python
from tests.factories import SampleFactory, ResultFactory, OllamaFactory

# Create samples
humaneval = SampleFactory.create_humaneval_sample(problem_id=1)
batch = SampleFactory.create_batch(10, factory_type="mbpp")

# Create results
result = ResultFactory.create_model_result("llama3.2:3b")
summary = ResultFactory.create_summary()

# Create Ollama data
models = OllamaFactory.create_model_list(count=5)
output = OllamaFactory.create_ollama_list_output(models)
```

## Writing New Tests

### Unit Test Template

```python
import pytest
from matric_eval.module import function_to_test

@pytest.mark.unit
class TestFeature:
    """Tests for specific feature."""

    def test_normal_case(self) -> None:
        """Should handle normal input correctly."""
        result = function_to_test("input")
        assert result == "expected"

    def test_edge_case_empty(self) -> None:
        """Should handle empty input."""
        result = function_to_test("")
        assert result == ""

    def test_error_case(self) -> None:
        """Should raise error for invalid input."""
        with pytest.raises(ValueError):
            function_to_test(None)
```

### Integration Test Template

```python
import pytest

@pytest.mark.integration
class TestIntegration:
    """Integration tests requiring external services."""

    def test_with_real_service(self, skip_if_no_ollama: None) -> None:
        """Should interact with real Ollama."""
        # Test implementation
        pass
```

## Coverage Goals

| Metric | Minimum | Critical Paths |
|--------|---------|----------------|
| Line Coverage | 80% | 100% |
| Branch Coverage | 75% | 100% |
| Function Coverage | 90% | 100% |

Critical paths requiring 100% coverage:
- Model discovery and filtering
- Evaluation execution
- Result generation
- Configuration loading

## Continuous Integration

Tests run automatically on:
- Every commit (unit tests)
- Pull requests (unit + integration)
- Main branch merges (full suite + coverage)

## Troubleshooting

### Import Errors

```bash
# Ensure package is installed in editable mode
pip install -e .

# Or with uv
uv pip install -e .
```

### Ollama Tests Failing

Integration tests require Ollama to be running:

```bash
# Check Ollama status
ollama list

# Start Ollama if needed
ollama serve
```

### Coverage Not Working

```bash
# Install coverage dependencies
pip install pytest-cov

# Or with uv
uv pip install pytest-cov
```

### Slow Tests

Skip slow tests during development:

```bash
pytest -m "not slow"
```

## Best Practices

1. **One assertion per test** - Each test should verify one specific behavior
2. **Descriptive names** - Test names should describe what is being tested
3. **Arrange-Act-Assert** - Structure tests clearly
4. **Use fixtures** - Don't repeat setup code
5. **Mock externals** - Unit tests should not hit real services
6. **Test edge cases** - Empty inputs, boundaries, errors
7. **Keep tests fast** - Unit tests should run in milliseconds

## References

- [pytest documentation](https://docs.pytest.org/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)
- [Test-Driven Development by Example](https://www.oreilly.com/library/view/test-driven-development/0321146530/)
- [xUnit Test Patterns](http://xunitpatterns.com/)
