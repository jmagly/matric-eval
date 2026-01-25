"""
Shared pytest fixtures for matric-eval test suite.

Provides common test data, mocks, and utilities across all tests.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock, Mock

import pytest
from inspect_ai.dataset import Sample
from inspect_ai.log import EvalLog, EvalResults, EvalScore


# =============================================================================
# Directory Fixtures
# =============================================================================


@pytest.fixture
def tmp_results_dir() -> Generator[Path, None, None]:
    """
    Create a temporary directory for test results.

    Yields:
        Path to temporary directory, cleaned up after test
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="matric_eval_test_"))
    try:
        yield tmp_dir
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)


@pytest.fixture
def tmp_logs_dir(tmp_results_dir: Path) -> Path:
    """Create logs subdirectory in temp results."""
    logs_dir = tmp_results_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


# =============================================================================
# Mock Ollama Fixtures
# =============================================================================


@pytest.fixture
def mock_ollama_list_output() -> str:
    """Mock output from 'ollama list' command."""
    return """NAME                    ID              SIZE      MODIFIED
llama3.2:3b            a80c4f17acd5    2.0 GB    2 weeks ago
qwen2.5:7b             e9c23b5a5d51    4.7 GB    3 days ago
mistral:7b             f974a74358d6    4.1 GB    1 week ago
deepseek-coder:6.7b    8e9f8e5d1234    3.9 GB    5 days ago
nomic-embed-text       5c3f3d2e1f23    274 MB    1 month ago
llama3.2:70b           9f8e7d6c5b4a    40 GB     1 week ago
snowflake-arctic-embed a1b2c3d4e5f6    669 MB    2 weeks ago"""


@pytest.fixture
def mock_ollama_models() -> list[dict[str, Any]]:
    """Expected parsed model list from mock_ollama_list_output."""
    return [
        {"name": "llama3.2:3b", "size_gb": 2.0, "size_str": "2.0 GB"},
        {"name": "qwen2.5:7b", "size_gb": 4.7, "size_str": "4.7 GB"},
        {"name": "mistral:7b", "size_gb": 4.1, "size_str": "4.1 GB"},
        {"name": "deepseek-coder:6.7b", "size_gb": 3.9, "size_str": "3.9 GB"},
    ]


@pytest.fixture
def mock_ollama_response() -> dict[str, Any]:
    """Mock Ollama API response for model generation."""
    return {
        "model": "llama3.2:3b",
        "created_at": "2024-01-20T12:00:00Z",
        "response": "def has_close_elements(numbers, threshold):\n    return False",
        "done": True,
    }


# =============================================================================
# Sample Test Data Fixtures
# =============================================================================


@pytest.fixture
def sample_humaneval_problem() -> Sample:
    """Sample HumanEval problem for testing."""
    return Sample(
        input="""Write a Python function `add(a: int, b: int) -> int` that adds two numbers.

Example:
>>> add(2, 3)
5

Return only the function code.""",
        target="""def add(a: int, b: int) -> int:
    return a + b""",
        id="humaneval_test_0",
        metadata={"difficulty": "easy", "category": "code"},
    )


@pytest.fixture
def sample_mbpp_problem() -> Sample:
    """Sample MBPP problem for testing."""
    return Sample(
        input="""Write a Python function `multiply(a, b)` that multiplies two numbers.

Test cases:
assert multiply(2, 3) == 6
assert multiply(0, 5) == 0

Return only the function code.""",
        target="""def multiply(a, b):
    return a * b""",
        id="mbpp_test_0",
        metadata={"difficulty": "easy", "category": "code", "function_name": "multiply"},
    )


@pytest.fixture
def sample_gsm8k_problem() -> Sample:
    """Sample GSM8K math problem for testing."""
    return Sample(
        input="""If John has 5 apples and gives 2 to Mary, how many apples does John have left?

Think step by step, then provide the final numeric answer.""",
        target="3",
        id="gsm8k_test_0",
        metadata={"difficulty": "easy", "category": "math"},
    )


@pytest.fixture
def sample_problems_list(
    sample_humaneval_problem: Sample,
    sample_mbpp_problem: Sample,
    sample_gsm8k_problem: Sample,
) -> list[Sample]:
    """List of all sample problems for combined testing."""
    return [sample_humaneval_problem, sample_mbpp_problem, sample_gsm8k_problem]


# =============================================================================
# Mock EvalLog Fixtures
# =============================================================================


@pytest.fixture
def mock_eval_log() -> EvalLog:
    """
    Mock EvalLog object with realistic structure.

    Note: This is a simplified mock. For real Inspect AI logs,
    use actual eval() calls in integration tests.
    """
    mock_log = MagicMock(spec=EvalLog)

    # Mock results
    mock_results = MagicMock(spec=EvalResults)
    mock_score = MagicMock(spec=EvalScore)
    mock_score.metrics = {"accuracy": {"value": 0.8}}
    mock_results.scores = [mock_score]

    mock_log.results = mock_results
    mock_log.samples = [MagicMock() for _ in range(5)]
    mock_log.status = "success"

    return mock_log


@pytest.fixture
def mock_eval_log_with_error() -> EvalLog:
    """Mock EvalLog representing a failed evaluation."""
    mock_log = MagicMock(spec=EvalLog)
    mock_log.results = None
    mock_log.samples = []
    mock_log.status = "error"
    mock_log.error = "Model timeout"
    return mock_log


# =============================================================================
# Mock Subprocess Fixtures
# =============================================================================


@pytest.fixture
def mock_subprocess_success(mock_ollama_list_output: str) -> Mock:
    """Mock subprocess.run for successful Ollama commands."""
    mock = Mock()
    mock.return_value.stdout = mock_ollama_list_output
    mock.return_value.stderr = ""
    mock.return_value.returncode = 0
    return mock


@pytest.fixture
def mock_subprocess_ollama_not_found() -> Mock:
    """Mock subprocess.run raising FileNotFoundError (Ollama not installed)."""
    mock = Mock()
    mock.side_effect = FileNotFoundError("ollama: command not found")
    return mock


@pytest.fixture
def mock_subprocess_ollama_error() -> Mock:
    """Mock subprocess.run with Ollama returning error."""
    from subprocess import CalledProcessError

    mock = Mock()
    mock.side_effect = CalledProcessError(1, "ollama list", stderr="Connection refused")
    return mock


# =============================================================================
# Configuration Fixtures
# =============================================================================


@pytest.fixture(autouse=False)
def env_no_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear all EVAL_* environment variables and reset settings singleton."""
    env_vars = [
        "EVAL_SEED",
        "EVAL_HUMANEVAL_SAMPLES",
        "EVAL_MBPP_SAMPLES",
        "EVAL_GSM8K_SAMPLES",
        "MAX_MODEL_SIZE_GB",
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)

    # Reset the settings singleton so it re-reads from environment
    import matric_eval.config.settings as settings_module
    settings_module._settings = None


@pytest.fixture(autouse=False)
def env_custom_seed(monkeypatch: pytest.MonkeyPatch) -> int:
    """Set custom seed via environment."""
    # First clear any existing value
    monkeypatch.delenv("EVAL_SEED", raising=False)
    # Then set new value
    seed = 12345
    monkeypatch.setenv("EVAL_SEED", str(seed))

    # Reset the settings singleton so it re-reads from environment
    import matric_eval.config.settings as settings_module
    settings_module._settings = None

    return seed


@pytest.fixture(autouse=False)
def env_custom_samples(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Set custom sample counts via environment."""
    # Clear any existing values first
    monkeypatch.delenv("EVAL_HUMANEVAL_SAMPLES", raising=False)
    monkeypatch.delenv("EVAL_MBPP_SAMPLES", raising=False)
    monkeypatch.delenv("EVAL_GSM8K_SAMPLES", raising=False)

    # Set new values
    samples = {"humaneval": 10, "mbpp": 20, "gsm8k": 15}
    monkeypatch.setenv("EVAL_HUMANEVAL_SAMPLES", str(samples["humaneval"]))
    monkeypatch.setenv("EVAL_MBPP_SAMPLES", str(samples["mbpp"]))
    monkeypatch.setenv("EVAL_GSM8K_SAMPLES", str(samples["gsm8k"]))

    # Reset the settings singleton so it re-reads from environment
    import matric_eval.config.settings as settings_module
    settings_module._settings = None

    return samples


# =============================================================================
# Test Data Files
# =============================================================================


@pytest.fixture
def sample_result_json(tmp_results_dir: Path) -> Path:
    """Create a sample result JSON file."""
    result_data = {
        "model": "llama3.2:3b",
        "timestamp": "2024-01-20T12:00:00",
        "benchmarks": {
            "humaneval": {"score": 0.6, "samples": 5, "status": "success"},
            "mbpp": {"score": 0.8, "samples": 5, "status": "success"},
            "gsm8k": {"score": 0.4, "samples": 5, "status": "success"},
        },
        "overall_score": 0.6,
        "status": "success",
    }

    result_file = tmp_results_dir / "llama3.2_3b.json"
    result_file.write_text(json.dumps(result_data, indent=2))
    return result_file


@pytest.fixture
def sample_summary_json(tmp_results_dir: Path) -> Path:
    """Create a sample summary JSON file."""
    summary_data = {
        "timestamp": "2024-01-20T12:00:00",
        "tier": "smoke",
        "models_evaluated": 2,
        "results": [
            {
                "model": "llama3.2:3b",
                "overall_score": 0.6,
                "status": "success",
            },
            {
                "model": "qwen2.5:7b",
                "overall_score": 0.75,
                "status": "success",
            },
        ],
    }

    summary_file = tmp_results_dir / "summary.json"
    summary_file.write_text(json.dumps(summary_data, indent=2))
    return summary_file


# =============================================================================
# Utility Functions
# =============================================================================


@pytest.fixture
def create_mock_dataset():
    """Factory fixture for creating mock datasets."""
    def _create(samples: list[Sample], name: str = "test_dataset"):
        from inspect_ai.dataset import MemoryDataset
        return MemoryDataset(samples=samples, name=name)
    return _create


# =============================================================================
# External Data File Helpers
# =============================================================================

# Paths to external benchmark datasets (only available on dev machines)
DATA_PATHS = {
    "arc": "/home/roctinam/data/evals/arc/ARC-Challenge/ARC-Challenge-Test.jsonl",
    "gsm8k": "/home/roctinam/data/evals/gsm8k/test.jsonl",
    "humaneval": "/home/roctinam/data/evals/humaneval/HumanEval.jsonl",
    "mbpp": "/home/roctinam/data/evals/mbpp/mbpp.jsonl",
    "ifeval": "/home/roctinam/data/evals/ifeval/data.jsonl",
    "livecodebench": "/home/roctinam/data/evals/livecodebench/release_v1.jsonl",
    "ds1000": "/home/roctinam/data/evals/ds1000/ds1000.jsonl",
    "mtbench": "/home/roctinam/data/evals/mtbench/question.jsonl",
}


def has_data_file(benchmark: str) -> bool:
    """Check if the benchmark's external data file exists."""
    path = DATA_PATHS.get(benchmark)
    if path is None:
        return False
    return Path(path).exists()


# Pre-compute availability flags for use in skipif conditions
ARC_DATA_AVAILABLE = has_data_file("arc")
GSM8K_DATA_AVAILABLE = has_data_file("gsm8k")
HUMANEVAL_DATA_AVAILABLE = has_data_file("humaneval")
MBPP_DATA_AVAILABLE = has_data_file("mbpp")
IFEVAL_DATA_AVAILABLE = has_data_file("ifeval")
LIVECODEBENCH_DATA_AVAILABLE = has_data_file("livecodebench")
DS1000_DATA_AVAILABLE = has_data_file("ds1000")
MTBENCH_DATA_AVAILABLE = has_data_file("mtbench")


# Reusable skip decorators for tests requiring external data
requires_arc_data = pytest.mark.skipif(
    not ARC_DATA_AVAILABLE, reason="ARC dataset not available in CI"
)
requires_gsm8k_data = pytest.mark.skipif(
    not GSM8K_DATA_AVAILABLE, reason="GSM8K dataset not available in CI"
)
requires_humaneval_data = pytest.mark.skipif(
    not HUMANEVAL_DATA_AVAILABLE, reason="HumanEval dataset not available in CI"
)
requires_mbpp_data = pytest.mark.skipif(
    not MBPP_DATA_AVAILABLE, reason="MBPP dataset not available in CI"
)
requires_ifeval_data = pytest.mark.skipif(
    not IFEVAL_DATA_AVAILABLE, reason="IFEval dataset not available in CI"
)
requires_livecodebench_data = pytest.mark.skipif(
    not LIVECODEBENCH_DATA_AVAILABLE, reason="LiveCodeBench dataset not available in CI"
)
requires_ds1000_data = pytest.mark.skipif(
    not DS1000_DATA_AVAILABLE, reason="DS-1000 dataset not available in CI"
)
requires_mtbench_data = pytest.mark.skipif(
    not MTBENCH_DATA_AVAILABLE, reason="MT-Bench dataset not available in CI"
)
