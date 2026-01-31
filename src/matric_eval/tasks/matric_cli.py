"""
Matric-CLI application-specific evaluation tasks.

Tests code generation and tool calling capabilities specific to the
matric-cli TypeScript CLI application.
"""

import json
import re
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score, Target, accuracy, scorer
from inspect_ai.solver import generate

from matric_eval.config import get_sample_count

# Path to test data
DATA_DIR = Path(__file__).parent.parent.parent.parent / "tests" / "integration" / "matric_cli" / "data"


def load_code_generation_scenarios() -> list[dict[str, Any]]:
    """Load code generation scenarios from JSON."""
    path = DATA_DIR / "code_generation_scenarios.json"
    if not path.exists():
        raise FileNotFoundError(f"Code generation scenarios not found: {path}")
    with open(path) as f:
        return json.load(f)


def load_tool_calling_scenarios() -> list[dict[str, Any]]:
    """Load tool calling scenarios from JSON."""
    path = DATA_DIR / "tool_calling_scenarios.json"
    if not path.exists():
        raise FileNotFoundError(f"Tool calling scenarios not found: {path}")
    with open(path) as f:
        return json.load(f)


def scenario_to_sample(scenario: dict[str, Any], category: str) -> Sample:
    """Convert a scenario dict to an Inspect AI Sample."""
    return Sample(
        id=scenario["id"],
        input=scenario["prompt"],
        target=scenario.get("expected_behavior", ""),
        metadata={
            "category": category,
            "difficulty": scenario.get("difficulty", "medium"),
            "required_checks": scenario.get("required_checks", []),
            "tags": scenario.get("tags", []),
        },
    )


def load_matric_cli(tier: str = "smoke") -> list[Sample]:
    """
    Load matric-cli evaluation samples.

    Args:
        tier: Evaluation tier (smoke, quick, full)

    Returns:
        List of Sample objects for evaluation
    """
    samples = []

    # Load code generation scenarios
    try:
        code_gen = load_code_generation_scenarios()
        for scenario in code_gen:
            samples.append(scenario_to_sample(scenario, "code_generation"))
    except FileNotFoundError:
        pass

    # Load tool calling scenarios
    try:
        tool_call = load_tool_calling_scenarios()
        for scenario in tool_call:
            samples.append(scenario_to_sample(scenario, "tool_calling"))
    except FileNotFoundError:
        pass

    # Apply tier-based sampling
    sample_count = get_sample_count("matric_cli", tier)
    if sample_count and len(samples) > sample_count:
        # Reproducible sampling
        import random
        rng = random.Random(42)
        samples = rng.sample(samples, sample_count)

    return samples


@scorer(metrics=[accuracy()])
def matric_cli_scorer():
    """
    Score matric-cli responses using pattern matching.

    Checks for required code patterns based on scenario metadata.
    """
    async def score(state, target: Target) -> Score:
        response = state.output.completion if state.output else ""
        metadata = state.metadata or {}
        required_checks = metadata.get("required_checks", [])

        if not required_checks:
            # No specific checks - use basic heuristics
            has_code = bool(re.search(r'```|function|const |let |def |class ', response))
            return Score(value=1.0 if has_code else 0.0, answer=response[:200])

        # Pattern definitions for each check type
        patterns = {
            # Code generation checks
            "hasFunctionDeclaration": r'function\s+\w+|const\s+\w+\s*=\s*(?:async\s*)?\(',
            "hasParameter": r'\([^)]*\w+[^)]*\)',
            "hasRecursion": r'fibonacci\s*\(.*fibonacci\s*\(|function\s+\w+.*\w+\s*\(',
            "hasMemoization": r'memo|cache|Map|Record|WeakMap',
            "hasTypeAnnotation": r':\s*(?:number|string|boolean|any|\w+\[\])',
            "hasLoop": r'for\s*\(|while\s*\(|\.forEach|\.map\s*\(',
            "hasReturn": r'return\s+',
            "hasReturnBoolean": r'return\s+(?:true|false)',
            "hasEdgeCaseHandling": r'[<>]=?\s*[012]|[012]\s*[<>]=?|if\s*\(',
            "hasSplit": r'\.split\s*\(',
            "hasLengthComparison": r'\.length\s*[<>=]|[<>=]\s*\w+\.length',
            "removedTodos": r'^(?!.*//\s*TODO)',
            "identifiedBug": r'off-by-one|<=\s*arr\.length|index|bound',
            "hasCorrectLoop": r'i\s*<\s*arr\.length(?!\s*=)',
            "hasMethodName": r'findUserByEmail|findByEmail',
            "hasReturnType": r':\s*\w+\s*\|\s*undefined|:\s*\w+\s*\?',
            "hasArraySearch": r'\.find\s*\(|\.filter\s*\(|for\s*\(',
            "hasEmailComparison": r'\.email\s*===|===\s*\w*email',
            "hasMiddleCalculation": r'Math\.floor|>>>\s*1|\/\s*2',
            "hasBinaryLogic": r'left|right|mid|low|high',
            "hasTypes": r':\s*number\[\].*:\s*number|:\s*number.*:\s*number\[\]',
            "hasParameters": r'\([^)]*,\s*[^)]*\)',
            # Tool calling checks
            "hasToolCall": r'tool_call|function_call|<tool>|```json',
            "hasCorrectFunction": r'"name"\s*:\s*"',
            "hasParameters": r'"parameters"|"arguments"|"params"',
            "hasValidJSON": r'\{[^}]*"[^"]+"\s*:',
        }

        passed = 0
        for check in required_checks:
            pattern = patterns.get(check, r'.*')
            if re.search(pattern, response, re.IGNORECASE | re.DOTALL):
                passed += 1

        score_value = passed / len(required_checks) if required_checks else 0.0
        return Score(
            value=score_value,
            answer=response[:200],
            explanation=f"Passed {passed}/{len(required_checks)} checks",
        )

    return score


@task
def matric_cli(tier: str = "smoke") -> Task:
    """
    Matric-CLI evaluation task.

    Evaluates code generation and tool calling for the matric-cli application.

    Args:
        tier: Evaluation tier (smoke, quick, full)

    Returns:
        Configured Task for evaluation
    """
    samples = load_matric_cli(tier)

    return Task(
        name="matric_cli",
        dataset=samples,
        solver=generate(),
        scorer=matric_cli_scorer(),
    )
