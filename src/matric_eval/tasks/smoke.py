"""
Smoke test suite for quick model validation.

Uses 5 samples per benchmark for rapid feedback (~2 min per model).
Based on matric-cli's smoke tier approach.
"""

from inspect_ai import Task, task
from inspect_ai.dataset import Sample, MemoryDataset
from inspect_ai.scorer import match, includes, model_graded_fact
from inspect_ai.solver import generate, system_message


# =============================================================================
# HumanEval Smoke Samples (5 representative problems)
# =============================================================================

HUMANEVAL_SAMPLES = [
    Sample(
        input="""Write a Python function `has_close_elements(numbers: List[float], threshold: float) -> bool` that checks if any two numbers in the list are closer than the given threshold.

Example:
>>> has_close_elements([1.0, 2.0, 3.0], 0.5)
False
>>> has_close_elements([1.0, 2.8, 3.0, 4.0, 5.0, 2.0], 0.3)
True

Return only the function code, no explanations.""",
        target="""def has_close_elements(numbers: List[float], threshold: float) -> bool:
    for i, n1 in enumerate(numbers):
        for j, n2 in enumerate(numbers):
            if i != j and abs(n1 - n2) < threshold:
                return True
    return False""",
        id="humaneval_0",
        metadata={"difficulty": "easy", "category": "code"}
    ),
    Sample(
        input="""Write a Python function `truncate_number(number: float) -> float` that returns the decimal part of a positive floating point number.

Example:
>>> truncate_number(3.5)
0.5

Return only the function code.""",
        target="""def truncate_number(number: float) -> float:
    return number % 1.0""",
        id="humaneval_2",
        metadata={"difficulty": "easy", "category": "code"}
    ),
    Sample(
        input="""Write a Python function `below_zero(operations: List[int]) -> bool` that detects if a bank account balance goes below zero after a sequence of deposits (positive) and withdrawals (negative).

Example:
>>> below_zero([1, 2, 3])
False
>>> below_zero([1, 2, -4, 5])
True

Return only the function code.""",
        target="""def below_zero(operations: List[int]) -> bool:
    balance = 0
    for op in operations:
        balance += op
        if balance < 0:
            return True
    return False""",
        id="humaneval_3",
        metadata={"difficulty": "easy", "category": "code"}
    ),
    Sample(
        input="""Write a Python function `intersperse(numbers: List[int], delimiter: int) -> List[int]` that inserts a delimiter between every two consecutive elements of the input list.

Example:
>>> intersperse([], 4)
[]
>>> intersperse([1, 2, 3], 4)
[1, 4, 2, 4, 3]

Return only the function code.""",
        target="""def intersperse(numbers: List[int], delimiter: int) -> List[int]:
    if not numbers:
        return []
    result = []
    for i, n in enumerate(numbers):
        result.append(n)
        if i < len(numbers) - 1:
            result.append(delimiter)
    return result""",
        id="humaneval_5",
        metadata={"difficulty": "medium", "category": "code"}
    ),
    Sample(
        input="""Write a Python function `parse_nested_parens(paren_string: str) -> List[int]` that takes a string of groups of nested parentheses separated by spaces. Return a list of the maximum depth of nesting for each group.

Example:
>>> parse_nested_parens('(()()) ((())) () ((())())')
[2, 3, 1, 3]

Return only the function code.""",
        target="""def parse_nested_parens(paren_string: str) -> List[int]:
    result = []
    for group in paren_string.split():
        depth = 0
        max_depth = 0
        for c in group:
            if c == '(':
                depth += 1
                max_depth = max(max_depth, depth)
            elif c == ')':
                depth -= 1
        result.append(max_depth)
    return result""",
        id="humaneval_6",
        metadata={"difficulty": "medium", "category": "code"}
    ),
]


# =============================================================================
# MBPP Smoke Samples (5 representative problems)
# =============================================================================

MBPP_SAMPLES = [
    Sample(
        input="""Write a Python function `is_even(n)` that returns True if n is even, False otherwise.

Test cases:
assert is_even(2) == True
assert is_even(3) == False

Return only the function code.""",
        target="""def is_even(n):
    return n % 2 == 0""",
        id="mbpp_1",
        metadata={"difficulty": "easy", "category": "code", "function_name": "is_even"}
    ),
    Sample(
        input="""Write a Python function `find_max(lst)` that returns the maximum element in a list.

Test cases:
assert find_max([1, 2, 3, 4, 5]) == 5
assert find_max([-1, -2, -3]) == -1

Return only the function code.""",
        target="""def find_max(lst):
    return max(lst)""",
        id="mbpp_2",
        metadata={"difficulty": "easy", "category": "code", "function_name": "find_max"}
    ),
    Sample(
        input="""Write a Python function `reverse_string(s)` that returns the reversed string.

Test cases:
assert reverse_string("hello") == "olleh"
assert reverse_string("") == ""

Return only the function code.""",
        target="""def reverse_string(s):
    return s[::-1]""",
        id="mbpp_3",
        metadata={"difficulty": "easy", "category": "code", "function_name": "reverse_string"}
    ),
    Sample(
        input="""Write a Python function `count_vowels(s)` that counts the number of vowels (a, e, i, o, u) in a string.

Test cases:
assert count_vowels("hello") == 2
assert count_vowels("xyz") == 0

Return only the function code.""",
        target="""def count_vowels(s):
    return sum(1 for c in s.lower() if c in 'aeiou')""",
        id="mbpp_4",
        metadata={"difficulty": "easy", "category": "code", "function_name": "count_vowels"}
    ),
    Sample(
        input="""Write a Python function `fibonacci(n)` that returns the nth Fibonacci number where fibonacci(0) = 0, fibonacci(1) = 1.

Test cases:
assert fibonacci(0) == 0
assert fibonacci(1) == 1
assert fibonacci(10) == 55

Return only the function code.""",
        target="""def fibonacci(n):
    if n <= 0:
        return 0
    if n == 1:
        return 1
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b""",
        id="mbpp_5",
        metadata={"difficulty": "medium", "category": "code", "function_name": "fibonacci"}
    ),
]


# =============================================================================
# GSM8K Smoke Samples (5 representative math problems)
# =============================================================================

GSM8K_SAMPLES = [
    Sample(
        input="""Janet's ducks lay 16 eggs per day. She eats three for breakfast every morning and bakes muffins for her friends every day with four. She sells the remainder at the farmers' market daily for $2 per fresh duck egg. How much in dollars does she make every day at the farmers' market?

Think step by step, then provide the final numeric answer.""",
        target="18",
        id="gsm8k_1",
        metadata={"difficulty": "easy", "category": "math"}
    ),
    Sample(
        input="""A robe takes 2 bolts of blue fiber and half that much white fiber. How many bolts in total does it take?

Think step by step, then provide the final numeric answer.""",
        target="3",
        id="gsm8k_2",
        metadata={"difficulty": "easy", "category": "math"}
    ),
    Sample(
        input="""Josh decides to try flipping a house. He buys a house for $80,000 and then puts in $50,000 in repairs. This increased the value of the house by 150%. How much profit did he make?

Think step by step, then provide the final numeric answer.""",
        target="70000",
        id="gsm8k_3",
        metadata={"difficulty": "medium", "category": "math"}
    ),
    Sample(
        input="""James decides to run 3 sprints 3 times a week. He runs 60 meters each sprint. How many total meters does he run a week?

Think step by step, then provide the final numeric answer.""",
        target="540",
        id="gsm8k_4",
        metadata={"difficulty": "easy", "category": "math"}
    ),
    Sample(
        input="""Every day, Wendi feeds each of her chickens three cups of mixed chicken feed, containing seeds, mealworms and vegetables to help keep them healthy. She gives the chickens their feed in three separate meals. In the morning, she gives her flock of chickens 15 cups of feed. In the afternoon, she gives her chickens another 25 cups of feed. If Wendi's flock has 20 chickens, how many cups of feed does she need to give her chickens in the final meal of the day?

Think step by step, then provide the final numeric answer.""",
        target="20",
        id="gsm8k_5",
        metadata={"difficulty": "medium", "category": "math"}
    ),
]


# =============================================================================
# Task Definitions
# =============================================================================

@task
def smoke_humaneval() -> Task:
    """HumanEval smoke test (5 samples)."""
    return Task(
        dataset=MemoryDataset(HUMANEVAL_SAMPLES),
        solver=[
            system_message("You are a Python coding assistant. Write clean, correct code. Return only the function, no explanations."),
            generate(),
        ],
        scorer=includes(),  # Check if target concepts are in response
        name="humaneval_smoke",
    )


@task
def smoke_mbpp() -> Task:
    """MBPP smoke test (5 samples)."""
    return Task(
        dataset=MemoryDataset(MBPP_SAMPLES),
        solver=[
            system_message("You are a Python coding assistant. Write the function exactly as specified. Return only the function code."),
            generate(),
        ],
        scorer=includes(),
        name="mbpp_smoke",
    )


@task
def smoke_gsm8k() -> Task:
    """GSM8K smoke test (5 samples)."""
    return Task(
        dataset=MemoryDataset(GSM8K_SAMPLES),
        solver=[
            system_message("You are a math problem solver. Show your work step by step, then provide the final numeric answer."),
            generate(),
        ],
        scorer=match(numeric=True),  # Match numeric answer
        name="gsm8k_smoke",
    )


@task
def smoke_suite() -> Task:
    """Combined smoke suite - all benchmarks (15 samples total)."""
    all_samples = HUMANEVAL_SAMPLES + MBPP_SAMPLES + GSM8K_SAMPLES
    return Task(
        dataset=MemoryDataset(all_samples),
        solver=[
            system_message("You are a helpful coding and math assistant. For code problems, return only the function. For math problems, show your work and provide the numeric answer."),
            generate(),
        ],
        scorer=includes(),
        name="smoke_suite",
    )
