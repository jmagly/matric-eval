"""Language-specific test runners for agentic benchmarks.

Each runner knows how to construct the appropriate test command
for its language ecosystem. The actual execution happens in the
agentic-sandbox via the SandboxClient.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class TestResult:
    """Result of running a test suite in the sandbox."""

    passed: bool
    exit_code: int
    output: str
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0


@runtime_checkable
class TestRunner(Protocol):
    """Protocol for language-specific test runners."""

    @property
    def language(self) -> str:
        """Language identifier."""
        ...

    def build_test_command(self, test_path: str) -> str:
        """Build the shell command to run tests.

        Args:
            test_path: Path to test file or directory

        Returns:
            Shell command string
        """
        ...


class PythonTestRunner:
    """Test runner for Python projects (pytest)."""

    @property
    def language(self) -> str:
        return "python"

    def build_test_command(self, test_path: str) -> str:
        return f"python -m pytest {test_path} -v --tb=short 2>&1"


class NodeTestRunner:
    """Test runner for Node.js projects (npm test / jest)."""

    @property
    def language(self) -> str:
        return "javascript"

    def build_test_command(self, test_path: str) -> str:
        return f"npx jest {test_path} --verbose 2>&1"


class GoTestRunner:
    """Test runner for Go projects."""

    @property
    def language(self) -> str:
        return "go"

    def build_test_command(self, test_path: str) -> str:
        return f"go test {test_path} -v 2>&1"


class JavaTestRunner:
    """Test runner for Java projects (Maven)."""

    @property
    def language(self) -> str:
        return "java"

    def build_test_command(self, test_path: str) -> str:
        return f"mvn test -pl {test_path} 2>&1"


# Registry of available test runners
RUNNERS: dict[str, type[TestRunner]] = {
    "python": PythonTestRunner,
    "javascript": NodeTestRunner,
    "go": GoTestRunner,
    "java": JavaTestRunner,
}


def get_runner(language: str) -> TestRunner:
    """Get a test runner for the specified language.

    Args:
        language: Language identifier

    Returns:
        TestRunner instance

    Raises:
        KeyError: If no runner exists for the language
    """
    runner_cls = RUNNERS.get(language)
    if runner_cls is None:
        raise KeyError(
            f"No test runner for language '{language}'. "
            f"Available: {', '.join(sorted(RUNNERS))}"
        )
    return runner_cls()
