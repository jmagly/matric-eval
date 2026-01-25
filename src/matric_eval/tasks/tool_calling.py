"""
Tool calling evaluation task for matric-eval.

Evaluates model ability to correctly invoke functions/tools with proper
parameter formatting, error handling, and multi-step reasoning.

Based on Berkeley Function Calling Leaderboard (BFCL) patterns.
"""

import json
import random
from pathlib import Path
from typing import Any, Literal

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Scorer, Score, Target, scorer
from inspect_ai.solver import generate, system_message

from matric_eval.config import get_sample_count, get_seed

# Path to tool calling dataset (BFCL-style format)
TOOL_CALLING_PATH = Path("/home/roctinam/data/evals/bfcl/tool_calling.jsonl")

# Scenario types
ScenarioType = Literal[
    "simple",
    "parallel",
    "nested",
    "error_handling",
    "complex_types",
    "multi_turn",
]

# Scenarios with their characteristics
SCENARIOS: dict[ScenarioType, str] = {
    "simple": "Single function call with clear parameters",
    "parallel": "Multiple independent function calls",
    "nested": "Chained function calls (output feeds input)",
    "error_handling": "Invalid parameters or missing functions",
    "complex_types": "Arrays, objects, optional parameters",
    "multi_turn": "Conversational tool use with results",
}

# Sample function definitions for synthetic test generation
SAMPLE_FUNCTIONS = {
    "simple": [
        {
            "name": "get_weather",
            "description": "Get current weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"},
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "Temperature unit",
                    },
                },
                "required": ["location"],
            },
        },
        {
            "name": "get_stock_price",
            "description": "Get current stock price",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Stock ticker symbol"},
                },
                "required": ["symbol"],
            },
        },
        {
            "name": "send_email",
            "description": "Send an email to a recipient",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    ],
    "parallel": [
        {
            "name": "search_hotels",
            "description": "Search for hotels in a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "checkin": {"type": "string", "description": "Check-in date YYYY-MM-DD"},
                    "checkout": {"type": "string", "description": "Check-out date YYYY-MM-DD"},
                },
                "required": ["location", "checkin", "checkout"],
            },
        },
        {
            "name": "search_flights",
            "description": "Search for flights",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string"},
                    "destination": {"type": "string"},
                    "date": {"type": "string", "description": "Flight date YYYY-MM-DD"},
                },
                "required": ["origin", "destination", "date"],
            },
        },
        {
            "name": "search_car_rentals",
            "description": "Search for car rentals",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "pickup_date": {"type": "string"},
                    "return_date": {"type": "string"},
                },
                "required": ["location", "pickup_date", "return_date"],
            },
        },
    ],
    "complex_types": [
        {
            "name": "create_event",
            "description": "Create a calendar event",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "start_time": {"type": "string"},
                    "end_time": {"type": "string"},
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of attendee emails",
                    },
                    "location": {"type": "string"},
                    "reminder": {
                        "type": "object",
                        "properties": {
                            "minutes_before": {"type": "integer"},
                            "method": {"type": "string", "enum": ["email", "popup"]},
                        },
                    },
                },
                "required": ["title", "start_time", "end_time"],
            },
        },
        {
            "name": "bulk_update_records",
            "description": "Update multiple database records",
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                    "updates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer"},
                                "fields": {"type": "object"},
                            },
                        },
                    },
                    "dry_run": {"type": "boolean", "default": False},
                },
                "required": ["table", "updates"],
            },
        },
    ],
}

# Sample queries for synthetic generation
SAMPLE_QUERIES = {
    "simple": [
        ("What's the weather in New York?", "get_weather", {"location": "New York"}),
        ("Get me the current price of AAPL stock", "get_stock_price", {"symbol": "AAPL"}),
        (
            "Send an email to john@example.com with subject 'Meeting' and body 'Hi John, let's meet tomorrow.'",
            "send_email",
            {"to": "john@example.com", "subject": "Meeting", "body": "Hi John, let's meet tomorrow."},
        ),
        ("What's the temperature in London in celsius?", "get_weather", {"location": "London", "unit": "celsius"}),
        ("Check the stock price for GOOGL", "get_stock_price", {"symbol": "GOOGL"}),
    ],
    "parallel": [
        (
            "I need to book a trip to Paris from NYC on 2024-03-15, find me flights and hotels.",
            ["search_flights", "search_hotels"],
            [
                {"origin": "NYC", "destination": "Paris", "date": "2024-03-15"},
                {"location": "Paris", "checkin": "2024-03-15", "checkout": "2024-03-20"},
            ],
        ),
        (
            "Search for hotels and car rentals in Miami from March 1-5, 2024",
            ["search_hotels", "search_car_rentals"],
            [
                {"location": "Miami", "checkin": "2024-03-01", "checkout": "2024-03-05"},
                {"location": "Miami", "pickup_date": "2024-03-01", "return_date": "2024-03-05"},
            ],
        ),
    ],
    "complex_types": [
        (
            "Create a meeting called 'Team Sync' from 2pm to 3pm tomorrow with alice@co.com and bob@co.com",
            "create_event",
            {
                "title": "Team Sync",
                "start_time": "2024-01-21T14:00:00",
                "end_time": "2024-01-21T15:00:00",
                "attendees": ["alice@co.com", "bob@co.com"],
            },
        ),
    ],
}


def record_to_sample(record: dict[str, Any]) -> Sample:
    """
    Convert a tool calling record to an Inspect AI Sample.

    Args:
        record: Dictionary with keys: functions, query, expected_call, scenario

    Returns:
        Sample with input=formatted_prompt, target=expected_function_call
    """
    functions = record.get("functions", [])
    user_query = record.get("query", record.get("user_query", ""))

    # Format function definitions
    functions_json = json.dumps(functions, indent=2)

    prompt = f"""You have access to the following functions:

{functions_json}

User request: {user_query}

Respond with the function call(s) in JSON format. Use this structure:
{{"name": "function_name", "parameters": {{"param1": "value1"}}}}

If multiple functions are needed, provide them as a JSON array.
"""

    # Target is the expected function call(s)
    expected = record.get("expected_call", record.get("ground_truth", {}))
    target = json.dumps(expected) if isinstance(expected, (dict, list)) else str(expected)

    return Sample(
        input=prompt,
        target=target,
        id=f"tool_call_{record.get('id', hash(user_query) % 100000)}",
        metadata={
            "scenario": record.get("scenario", "simple"),
            "functions": functions,
            "difficulty": record.get("difficulty", "medium"),
        },
    )


def _generate_synthetic_samples(
    count: int,
    scenario: ScenarioType | None = None,
    seed: int | None = None,
) -> list[Sample]:
    """
    Generate synthetic tool calling test cases.

    Args:
        count: Number of samples to generate
        scenario: Specific scenario to generate, or None for all
        seed: Random seed for reproducibility

    Returns:
        List of Sample objects
    """
    rng = random.Random(seed if seed is not None else get_seed())
    samples = []

    scenarios_to_use: list[ScenarioType] = (
        [scenario] if scenario else list(SCENARIOS.keys())
    )

    for i in range(count):
        s = rng.choice(scenarios_to_use)

        if s == "simple":
            # Pick a random simple query
            query, func_name, params = rng.choice(SAMPLE_QUERIES["simple"])
            functions = SAMPLE_FUNCTIONS["simple"]
            expected = {"name": func_name, "parameters": params}

        elif s == "parallel":
            # Pick a parallel query
            query, func_names, params_list = rng.choice(SAMPLE_QUERIES["parallel"])
            functions = SAMPLE_FUNCTIONS["parallel"]
            expected = [
                {"name": name, "parameters": params}
                for name, params in zip(func_names, params_list)
            ]

        elif s == "nested":
            # Nested: use weather result in another call
            query = "Get the weather in Tokyo, and if it's cold (below 10C), search for hotels there."
            functions = SAMPLE_FUNCTIONS["simple"] + SAMPLE_FUNCTIONS["parallel"][:1]
            expected = [
                {"name": "get_weather", "parameters": {"location": "Tokyo", "unit": "celsius"}},
                {"name": "search_hotels", "parameters": {"location": "Tokyo", "checkin": "today", "checkout": "tomorrow"}},
            ]

        elif s == "error_handling":
            # Query that requires non-existent function
            query = "Order me a pizza with pepperoni."
            functions = SAMPLE_FUNCTIONS["simple"]
            expected = {"error": "No suitable function available for ordering pizza"}

        elif s == "complex_types":
            # Complex parameter types
            query, func_name, params = rng.choice(SAMPLE_QUERIES["complex_types"])
            functions = SAMPLE_FUNCTIONS["complex_types"]
            expected = {"name": func_name, "parameters": params}

        elif s == "multi_turn":
            # Multi-turn conversation (simplified as single turn for now)
            query = "First get the weather in Boston, then based on that, send an email to team@example.com about today's conditions."
            functions = SAMPLE_FUNCTIONS["simple"]
            expected = [
                {"name": "get_weather", "parameters": {"location": "Boston"}},
                {"name": "send_email", "parameters": {
                    "to": "team@example.com",
                    "subject": "Weather Update",
                    "body": "Today's weather in Boston: [weather_result]",
                }},
            ]

        else:
            # Default to simple
            query, func_name, params = rng.choice(SAMPLE_QUERIES["simple"])
            functions = SAMPLE_FUNCTIONS["simple"]
            expected = {"name": func_name, "parameters": params}

        record = {
            "id": f"{s}_{i}",
            "functions": functions,
            "query": query,
            "expected_call": expected,
            "scenario": s,
            "difficulty": "easy" if s == "simple" else "medium" if s in ["parallel", "complex_types"] else "hard",
        }

        samples.append(record_to_sample(record))

    return samples


def load_tool_calling(
    tier: str = "smoke",
    scenario: ScenarioType | None = None,
) -> list[Sample]:
    """
    Load tool calling samples for the given tier.

    Args:
        tier: Evaluation tier ("smoke", "quick", "full")
        scenario: Optional specific scenario to filter by

    Returns:
        List of Sample objects

    Raises:
        FileNotFoundError: If dataset file not found (falls back to synthetic)
    """
    # Get sample count from config
    sample_count = get_sample_count("tool_calling", tier)

    if sample_count == 0:
        return []

    # Try to load from file first
    if TOOL_CALLING_PATH.exists():
        records = []
        with open(TOOL_CALLING_PATH, "r") as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    # Filter by scenario if specified
                    if scenario is None or record.get("scenario") == scenario:
                        records.append(record)

        if records:
            all_samples = [record_to_sample(r) for r in records]

            if sample_count >= len(all_samples):
                return all_samples

            # Reproducible sampling
            seed = get_seed()
            rng = random.Random(seed)
            sampled = rng.sample(all_samples, sample_count)
            sampled.sort(key=lambda s: s.id)
            return sampled

    # Fall back to synthetic generation
    return _generate_synthetic_samples(sample_count, scenario)


def extract_function_call(response: str) -> dict | list | None:
    """
    Extract function call JSON from model response.

    Handles various formats:
    - Raw JSON
    - JSON in markdown code blocks
    - JSON with surrounding text

    Args:
        response: Model's response text

    Returns:
        Parsed function call dict/list, or None if not parseable
    """
    import re

    # Try direct JSON parse first
    try:
        return json.loads(response.strip())
    except json.JSONDecodeError:
        pass

    # Try to find JSON in code blocks
    code_block_patterns = [
        r"```json\s*([\s\S]*?)```",
        r"```\s*([\s\S]*?)```",
        r"`([^`]+)`",
    ]

    for pattern in code_block_patterns:
        matches = re.findall(pattern, response, re.IGNORECASE)
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

    # Try to find JSON object/array in text
    json_patterns = [
        r"(\{[^{}]*\})",  # Simple object
        r"(\[[^\[\]]*\])",  # Simple array
        r"(\{[\s\S]*\})",  # Complex object (greedy)
        r"(\[[\s\S]*\])",  # Complex array (greedy)
    ]

    for pattern in json_patterns:
        matches = re.findall(pattern, response)
        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

    return None


def calculate_param_match(actual: dict, expected: dict) -> float:
    """
    Calculate parameter matching score.

    Args:
        actual: Actual parameters from model
        expected: Expected parameters

    Returns:
        Score from 0.0 to 1.0
    """
    if not expected:
        return 1.0 if not actual else 0.5

    matches = 0.0
    total = len(expected)

    for key, value in expected.items():
        if key in actual:
            if actual[key] == value:
                matches += 1.0
            elif isinstance(value, str) and isinstance(actual[key], str):
                # Partial string match
                if value.lower() in actual[key].lower() or actual[key].lower() in value.lower():
                    matches += 0.7
                else:
                    matches += 0.3  # Key present but wrong value
            elif isinstance(value, (list, dict)) and isinstance(actual[key], (list, dict)):
                # Partial structural match
                matches += 0.5
            else:
                matches += 0.2  # Key present, type mismatch

    return matches / total if total > 0 else 1.0


def calculate_function_call_score(actual: dict | list | None, expected: dict | list) -> tuple[float, str]:
    """
    Calculate overall function call score.

    Args:
        actual: Parsed function call from model
        expected: Expected function call

    Returns:
        Tuple of (score, explanation)
    """
    if actual is None:
        return 0.0, "Could not parse function call from response"

    # Handle list of function calls
    if isinstance(expected, list):
        if not isinstance(actual, list):
            actual = [actual]

        if len(actual) != len(expected):
            return 0.3, f"Expected {len(expected)} function calls, got {len(actual)}"

        total_score = 0.0
        for exp in expected:
            best_match = 0.0
            for act in actual:
                if act.get("name") == exp.get("name"):
                    param_score = calculate_param_match(
                        act.get("parameters", {}),
                        exp.get("parameters", {}),
                    )
                    best_match = max(best_match, 0.5 + 0.5 * param_score)
                elif "error" in exp and "error" in str(act):
                    best_match = max(best_match, 0.8)
            total_score += best_match

        final_score = total_score / len(expected)
        return final_score, f"Multi-call score: {final_score:.2%}"

    # Single function call
    if isinstance(actual, list):
        actual = actual[0] if actual else {}

    # Check for error handling scenario
    if "error" in expected:
        if "error" in str(actual).lower() or "cannot" in str(actual).lower():
            return 1.0, "Correctly identified unavailable function"
        return 0.3, "Should have indicated no suitable function"

    # Check function name
    if actual.get("name") != expected.get("name"):
        return 0.0, f"Wrong function: expected {expected.get('name')}, got {actual.get('name')}"

    # Check parameters
    param_score = calculate_param_match(
        actual.get("parameters", {}),
        expected.get("parameters", {}),
    )

    if param_score == 1.0:
        return 1.0, "Perfect match"
    elif param_score >= 0.7:
        return param_score, f"Partial parameter match: {param_score:.2%}"
    else:
        return param_score, f"Poor parameter match: {param_score:.2%}"


@scorer(metrics=["accuracy"])
def tool_call_scorer() -> Scorer:
    """
    Scorer for tool calling evaluation.

    Evaluates:
    - Correct function name selection
    - Correct parameter values
    - Proper handling of multiple function calls
    - Error handling scenarios
    """

    async def score(state, target: Target) -> Score:
        response = state.output.completion if state.output else ""

        try:
            expected = json.loads(target.text) if target.text else {}
        except json.JSONDecodeError:
            expected = {}

        # Parse model's function call
        actual = extract_function_call(response)

        # Calculate score
        value, explanation = calculate_function_call_score(actual, expected)

        return Score(
            value=value,
            explanation=explanation,
            metadata={
                "expected": expected,
                "actual": actual,
                "scenario": state.metadata.get("scenario") if hasattr(state, "metadata") else None,
            },
        )

    return score


@task
def tool_calling(
    tier: str = "smoke",
    scenario: ScenarioType | None = None,
) -> Task:
    """
    Tool calling evaluation task.

    Evaluates model's ability to correctly invoke functions/tools with proper
    parameter formatting and multi-step reasoning.

    Args:
        tier: Evaluation tier
            - "smoke": 5 samples (~1 minute)
            - "quick": 30 samples (~5 minutes)
            - "full": all samples
        scenario: Optional specific scenario to evaluate:
            - "simple": Single function call
            - "parallel": Multiple independent calls
            - "nested": Chained function calls
            - "error_handling": Invalid requests
            - "complex_types": Complex parameter types
            - "multi_turn": Conversational tool use

    Returns:
        Task configured for tool calling evaluation

    Example:
        >>> task = tool_calling(tier="smoke", scenario="simple")
        >>> # Run with: inspect eval tool_calling.py --model ollama/llama3.2:3b
    """
    samples = load_tool_calling(tier, scenario)

    return Task(
        dataset=samples,
        solver=[
            system_message(
                "You are a helpful assistant with access to functions. "
                "When the user makes a request, respond with the appropriate "
                "function call(s) in valid JSON format. "
                "Use this structure: {\"name\": \"function_name\", \"parameters\": {...}}"
            ),
            generate(),
        ],
        scorer=tool_call_scorer(),
        name=f"tool_calling{'_' + scenario if scenario else ''}",
    )
