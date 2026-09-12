#!/usr/bin/env python3
"""Direct-endpoint adapter for an OpenAI-compatible chat endpoint.

Runs inside the pipeline's isolated workspace with a scrubbed environment, so it
uses only the standard library. Reads the fixture from the working directory,
sends it with the scenario prompt, and writes a result document.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

FIXTURE_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".toml"}
MAX_FIXTURE_BYTES = 16384
PROJECT_NAME = re.compile(r"^project name:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def read_fixture(root: pathlib.Path) -> str:
    parts: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in FIXTURE_SUFFIXES:
            continue
        if any(segment.startswith(".") for segment in path.relative_to(root).parts):
            continue
        try:
            body = path.read_text(encoding="utf-8")[:MAX_FIXTURE_BYTES]
        except (OSError, UnicodeDecodeError):
            continue
        parts.append("--- {} ---\n{}".format(path.relative_to(root), body))
    return "\n".join(parts)


def score(answer: str, fixture: str) -> tuple[str, str]:
    """Grade an answer against an expectation carried by the fixture.

    The adapter is the scorer for its target, so the expectation is derived from
    the fixture rather than hardcoded; the assertion then travels with the
    fixture instead of being pinned to one scenario's wording.
    """
    expectation = PROJECT_NAME.search(fixture)
    if expectation is None:
        return "passed", "answer_returned"
    expected = expectation.group(1).rstrip(".")
    if expected.lower() in answer.lower():
        return "passed", "project_name_reported"
    return "failed", "project_name_absent"


def expected_project_name(fixture: str) -> str | None:
    match = PROJECT_NAME.search(fixture)
    return match.group(1).rstrip(".") if match else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=240.0)
    arguments = parser.parse_args()

    workspace = pathlib.Path.cwd()
    fixture = read_fixture(workspace)
    content = "{}\n\nWorkspace contents:\n{}".format(arguments.prompt, fixture)

    payload = json.dumps(
        {
            "model": arguments.model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": arguments.max_tokens,
            "temperature": 0,
            "stream": False,
        }
    ).encode()

    request = urllib.request.Request(
        arguments.endpoint.rstrip("/") + "/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=arguments.timeout) as response:
            body = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        print("endpoint request failed: {}".format(error), file=sys.stderr)
        return 1

    choice = body["choices"][0]
    message = choice.get("message", {})
    answer = (message.get("content") or "").strip()
    usage = body.get("usage", {})

    if not answer:
        # Reasoning models can exhaust the token budget before emitting content.
        print(
            "empty content; finish_reason={} completion_tokens={}".format(
                choice.get("finish_reason"), usage.get("completion_tokens")
            ),
            file=sys.stderr,
        )
        return 1

    outcome, reason = score(answer, fixture)

    result = {
        "outcome": outcome,
        "reason": reason,
        "usage": {
            "tokens": usage.get("total_tokens"),
            "cost_usd": 0.0,
        },
        "answer": answer,
        "expected": expected_project_name(fixture),
        "model": body.get("model", arguments.model),
        "finish_reason": choice.get("finish_reason"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
    }
    pathlib.Path(arguments.result).write_text(json.dumps(result, indent=2) + "\n")
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
