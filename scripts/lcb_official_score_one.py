#!/usr/bin/env python3
"""Run one LiveCodeBench generation through the pinned official checker.

This file is executed only inside a locked-down container. It deliberately does
not import matric-eval because the inference image is a lean scoring sandbox.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

OFFICIAL_CHECKER = Path("/opt/livecodebench/lcb_runner/evaluation/testing_util.py")


def _official_extract_code(model_output: str) -> str:
    """Match LiveCodeBench's OpenAIChat extraction at the pinned revision."""
    lines = model_output.split("\n")
    fences = [index for index, line in enumerate(lines) if "```" in line]
    if len(fences) < 2:
        return ""
    return "\n".join(lines[fences[-2] + 1 : fences[-1]])


def _load_run_test() -> Any:
    spec = importlib.util.spec_from_file_location("lcb_testing_util", OFFICIAL_CHECKER)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load the pinned LiveCodeBench checker")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_test


def main() -> int:
    payload = json.load(sys.stdin)
    completion = payload["completion"]
    tests = payload["tests"]
    sample = {
        "input_output": json.dumps(
            {
                "inputs": [test["input"] for test in tests],
                "outputs": [test["output"] for test in tests],
                "fn_name": payload.get("func_name"),
            }
        )
    }
    code = _official_extract_code(completion)
    if not code:
        print(
            json.dumps(
                {
                    "passed": False,
                    "tests_executed": 0,
                    "result_codes": {},
                    "code_parse_failure": True,
                }
            )
        )
        return 0
    results, _metadata = _load_run_test()(sample, test=code, debug=False, timeout=payload["timeout"])
    normalized = [value.item() if hasattr(value, "item") else value for value in results]
    print(
        json.dumps(
            {
                "passed": bool(normalized) and all(value is True for value in normalized),
                "tests_executed": len(normalized),
                "result_codes": dict(Counter(str(value) for value in normalized)),
                "code_parse_failure": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
