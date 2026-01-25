# ADR-003: JSONL as Universal Test Format

**Status**: Accepted
**Date**: 2026-01-24
**Decision Makers**: matric-eval development team
**Supersedes**: N/A

## Context

matric-eval needs a format for storing test datasets, both:
1. **Public benchmarks**: HumanEval, MBPP, GSM8K, etc.
2. **Custom tests**: App-specific tests for matric-cli and matric-memory

Requirements for the format:
- Compatible with evaluation frameworks (Inspect AI, lm-eval-harness)
- Human-readable and editable
- Version control friendly (git diff, merge)
- Streaming-friendly for large datasets
- Extensible for different test types (code, math, tool-use, etc.)
- Cross-language compatibility (Python, TypeScript, Rust)

## Decision

**Adopt JSON Lines (JSONL) as the universal test format for all datasets.**

### Format Specification

Each line in a JSONL file is a complete JSON object representing one test case:

```jsonl
{"id": "HE001", "prompt": "def factorial(n):\n    \"\"\"...", "tests": "assert factorial(5) == 120", "capability": "code_generation"}
{"id": "HE002", "prompt": "def fib(n):\n    \"\"\"...", "tests": "assert fib(10) == 55", "capability": "code_generation"}
```

### Standard Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["id", "prompt"],
  "properties": {
    "id": {
      "type": "string",
      "description": "Unique identifier for this test case"
    },
    "prompt": {
      "type": "string",
      "description": "Input prompt to send to the model"
    },
    "target": {
      "type": "string",
      "description": "Expected output (for exact match)"
    },
    "tests": {
      "type": "string",
      "description": "Test code to validate generated code"
    },
    "expected_tools": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Expected tool calls (for agent tests)"
    },
    "capability": {
      "type": "string",
      "enum": ["code_generation", "reasoning", "math", "instruction_following", "tool_calling", "agent"],
      "description": "Capability being tested"
    },
    "difficulty": {
      "type": "string",
      "enum": ["easy", "medium", "hard"],
      "description": "Problem difficulty level"
    },
    "metadata": {
      "type": "object",
      "description": "Additional test-specific metadata"
    }
  }
}
```

### Example Datasets

**Code Generation (HumanEval-style)**:
```jsonl
{"id": "HE001", "prompt": "def factorial(n: int) -> int:\n    \"\"\"Return the factorial of n.\n    >>> factorial(5)\n    120\n    \"\"\"", "tests": "assert factorial(5) == 120\nassert factorial(0) == 1", "capability": "code_generation", "difficulty": "easy"}
{"id": "HE002", "prompt": "def is_palindrome(s: str) -> bool:\n    \"\"\"Check if string is palindrome.\"\"\"", "tests": "assert is_palindrome('radar') == True\nassert is_palindrome('hello') == False", "capability": "code_generation", "difficulty": "easy"}
```

**Math Reasoning (GSM8K-style)**:
```jsonl
{"id": "GSM001", "prompt": "Janet has 3 apples. She buys 5 more. How many apples does she have?", "target": "8", "capability": "math", "difficulty": "easy"}
{"id": "GSM002", "prompt": "A train travels 60 miles in 1 hour. How far does it travel in 2.5 hours?", "target": "150", "capability": "math", "difficulty": "medium"}
```

**Tool Calling (matric-cli custom)**:
```jsonl
{"id": "TC001", "prompt": "Read the contents of config.json and tell me the version number.", "expected_tools": ["read_file"], "target": "1.0.0", "capability": "tool_calling"}
{"id": "TC002", "prompt": "Create a new file called hello.txt with the content 'Hello, World!'", "expected_tools": ["write_file"], "capability": "tool_calling"}
```

**Agent Scenarios (matric-cli custom)**:
```jsonl
{"id": "AG001", "prompt": "Find all TypeScript files in the src directory and count the total lines of code.", "expected_tools": ["bash", "read_file"], "capability": "agent", "metadata": {"max_steps": 5}}
{"id": "AG002", "prompt": "Fix the syntax error in main.ts and run the tests.", "expected_tools": ["read_file", "write_file", "bash"], "capability": "agent", "metadata": {"max_steps": 10}}
```

## Consequences

### Positive

1. **Framework compatibility**: Both Inspect AI and lm-eval-harness natively support JSONL datasets:
   ```python
   # Inspect AI
   from inspect_ai.dataset import json_dataset
   dataset = json_dataset("tests/tool_calling.jsonl")

   # lm-eval-harness
   # Uses JSONL by default for custom tasks
   ```

2. **Human-readable**: Easy to read, write, and debug without special tools:
   ```bash
   # View first 5 tests
   head -5 humaneval.jsonl

   # Count tests
   wc -l humaneval.jsonl

   # Filter by capability
   grep '"capability": "code_generation"' tests.jsonl
   ```

3. **Version control friendly**: Each line is independent, making git diffs clean:
   ```diff
   - {"id": "HE001", "prompt": "def factorial(n):", "tests": "assert factorial(5) == 120"}
   + {"id": "HE001", "prompt": "def factorial(n: int) -> int:", "tests": "assert factorial(5) == 120"}
   ```

4. **Streaming-friendly**: Process line-by-line without loading entire dataset into memory:
   ```python
   def stream_dataset(path: str):
       with open(path) as f:
           for line in f:
               yield json.loads(line)
   ```

5. **Cross-language compatibility**: Easy to parse in any language:
   ```typescript
   // TypeScript
   import * as readline from 'readline';
   for await (const line of readline.createInterface({ input: fs.createReadStream('tests.jsonl') })) {
     const test = JSON.parse(line);
   }
   ```
   ```rust
   // Rust
   use serde_json::from_str;
   for line in BufReader::new(File::open("tests.jsonl")?).lines() {
       let test: Test = from_str(&line?)?;
   }
   ```

6. **Extensible**: Add new fields without breaking existing consumers:
   ```jsonl
   {"id": "TC001", "prompt": "...", "expected_tools": ["read_file"], "new_field": "ignored by old code"}
   ```

### Negative

1. **No schema enforcement**: JSON doesn't enforce schema at parse time. Requires validation:
   ```python
   from jsonschema import validate
   validate(test, SCHEMA)
   ```

2. **Single-line limitation**: Very long prompts become hard to read in JSONL. Mitigation: Use external files for long content:
   ```jsonl
   {"id": "AG001", "prompt_file": "prompts/ag001.txt", ...}
   ```

3. **No native comments**: JSON doesn't support comments. Mitigation: Use metadata field or separate documentation.

4. **Duplicate data**: No referential integrity; each line must contain all needed data. Mitigation: Use preprocessing to expand templates.

### Mitigation Strategies

| Issue | Mitigation |
|-------|------------|
| Schema enforcement | JSON Schema validation in loader |
| Long prompts | External file references or heredoc-style field |
| Comments | Metadata field or companion README |
| Duplication | Template expansion preprocessing |

## Alternatives Considered

### Alternative A: JSON (Single File)

**Description**: Store all tests in a single JSON array.

```json
{
  "tests": [
    {"id": "HE001", "prompt": "..."},
    {"id": "HE002", "prompt": "..."}
  ]
}
```

**Pros**:
- Standard JSON
- Can include top-level metadata
- Schema validation tools widely available

**Cons**:
- Must load entire file into memory
- Git diffs are noisy (entire file changed)
- Merge conflicts on simultaneous edits
- No streaming support

**Decision**: Rejected. Scalability issues for large datasets (5000+ tests).

### Alternative B: YAML

**Description**: YAML format for test definitions.

```yaml
tests:
  - id: HE001
    prompt: |
      def factorial(n: int) -> int:
          """Return the factorial of n."""
    tests: |
      assert factorial(5) == 120
```

**Pros**:
- Excellent multi-line string support
- Human-friendly syntax
- Comments supported
- References/anchors for DRY

**Cons**:
- Framework compatibility issues (Inspect AI expects JSONL)
- Parsing inconsistencies across languages
- Whitespace sensitivity
- Slower parsing than JSON

**Decision**: Rejected. Framework compatibility more important than human ergonomics.

### Alternative C: CSV

**Description**: Comma-separated values format.

```csv
id,prompt,target,capability
HE001,"def factorial(n):...",120,code_generation
```

**Pros**:
- Simple format
- Spreadsheet editable
- Streamable

**Cons**:
- Limited to simple data types
- No nested structures (expected_tools array)
- Escaping complexity for multi-line content
- No metadata support

**Decision**: Rejected. Too limited for complex test definitions.

### Alternative D: Parquet

**Description**: Columnar binary format.

**Pros**:
- Excellent compression
- Fast columnar queries
- Schema enforcement
- Standard in ML pipelines

**Cons**:
- Binary format (not human-readable)
- Requires special tools to edit
- Version control unfriendly
- Overkill for our dataset sizes

**Decision**: Rejected. Human-readability more important than performance for our scale.

### Alternative E: SQLite

**Description**: Relational database for test storage.

**Pros**:
- Schema enforcement
- Query support
- Referential integrity
- Transactional updates

**Cons**:
- Binary format
- Requires database tooling
- Version control unfriendly
- Framework compatibility issues

**Decision**: Rejected. Over-engineered for our needs; framework compatibility issues.

## Implementation Notes

### Dataset Directory Structure

```
datasets/
├── public/                     # Public benchmarks (symlinks)
│   ├── humaneval.jsonl        -> /home/roctinam/data/evals/humaneval/humaneval.jsonl
│   ├── mbpp.jsonl             -> /home/roctinam/data/evals/mbpp/mbpp.jsonl
│   ├── gsm8k.jsonl            -> /home/roctinam/data/evals/gsm8k/gsm8k.jsonl
│   └── arc.jsonl              -> /home/roctinam/data/evals/arc/arc.jsonl
│
└── custom/                     # App-specific tests
    ├── cli/
    │   ├── tool_calling.jsonl
    │   └── agent_scenarios.jsonl
    └── memory/
        ├── title_generation.jsonl
        └── semantic_similarity.jsonl
```

### Loader Implementation

```python
import json
from pathlib import Path
from typing import Iterator
from dataclasses import dataclass

@dataclass
class TestCase:
    id: str
    prompt: str
    target: str | None = None
    tests: str | None = None
    expected_tools: list[str] | None = None
    capability: str | None = None
    difficulty: str | None = None
    metadata: dict | None = None

def load_dataset(path: Path) -> Iterator[TestCase]:
    """Load JSONL dataset with streaming."""
    with open(path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                yield TestCase(**data)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON at line {line_num}: {e}")
            except TypeError as e:
                raise ValueError(f"Invalid schema at line {line_num}: {e}")
```

### Validation Script

```python
#!/usr/bin/env python3
"""Validate JSONL dataset against schema."""

import json
import sys
from pathlib import Path
from jsonschema import validate, ValidationError

SCHEMA = {
    "type": "object",
    "required": ["id", "prompt"],
    "properties": {
        "id": {"type": "string"},
        "prompt": {"type": "string"},
        "target": {"type": "string"},
        "tests": {"type": "string"},
        "expected_tools": {"type": "array", "items": {"type": "string"}},
        "capability": {"type": "string"},
        "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
        "metadata": {"type": "object"},
    }
}

def validate_dataset(path: Path) -> list[str]:
    errors = []
    with open(path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                validate(data, SCHEMA)
            except json.JSONDecodeError as e:
                errors.append(f"Line {line_num}: Invalid JSON - {e}")
            except ValidationError as e:
                errors.append(f"Line {line_num}: Schema error - {e.message}")
    return errors

if __name__ == "__main__":
    for path in sys.argv[1:]:
        errors = validate_dataset(Path(path))
        if errors:
            print(f"\n{path}:")
            for error in errors:
                print(f"  {error}")
            sys.exit(1)
    print("All datasets valid")
```

## References

- [JSON Lines Specification](https://jsonlines.org/)
- [Inspect AI Dataset Documentation](https://inspect.aisi.org.uk/datasets.html)
- [lm-eval-harness Custom Tasks](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/docs/task_guide.md)
- [HumanEval Dataset](https://github.com/openai/human-eval)
- [MBPP Dataset](https://github.com/google-research/google-research/tree/master/mbpp)
