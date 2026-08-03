#!/usr/bin/env python3
"""Enforce the strict mypy baseline without allowing new type debt."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "mypy-baseline.json"
ErrorKey = tuple[str, str, str]


def parse_mypy_output(output: str) -> Counter[ErrorKey]:
    """Parse mypy's JSON-lines output into stable, line-independent counts."""
    errors: Counter[ErrorKey] = Counter()
    for line in output.splitlines():
        if not line.strip():
            continue
        record: dict[str, Any] = json.loads(line)
        if record.get("severity") != "error":
            continue
        key = (
            str(record["file"]),
            str(record.get("code") or "unknown"),
            str(record["message"]),
        )
        errors[key] += 1
    return errors


def load_baseline(path: Path = BASELINE_PATH) -> Counter[ErrorKey]:
    """Load the committed baseline."""
    data = json.loads(path.read_text())
    return Counter(
        {(item["file"], item["code"], item["message"]): item["count"] for item in data["errors"]}
    )


def find_regressions(current: Counter[ErrorKey], baseline: Counter[ErrorKey]) -> Counter[ErrorKey]:
    """Return errors whose current count exceeds the committed allowance."""
    return current - baseline


def write_baseline(errors: Counter[ErrorKey], path: Path = BASELINE_PATH) -> None:
    """Write a deterministic baseline after intentional debt reduction."""
    records = [
        {"file": file, "code": code, "message": message, "count": count}
        for (file, code, message), count in sorted(errors.items())
    ]
    payload = {
        "schema_version": 1,
        "command": "mypy src/ --output=json",
        "policy": "Existing findings may decrease; new or increased findings fail.",
        "errors": records,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")


def run_mypy() -> Counter[ErrorKey]:
    """Run strict mypy using the repository's pinned environment."""
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "src/", "--output=json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        sys.stderr.write(result.stderr)
        raise RuntimeError(f"mypy failed to execute (exit {result.returncode})")
    try:
        return parse_mypy_output(result.stdout)
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise RuntimeError("Could not parse mypy JSON output") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update",
        action="store_true",
        help="replace the baseline with the current findings after reviewed debt reduction",
    )
    args = parser.parse_args()

    current = run_mypy()
    if args.update:
        write_baseline(current)
        print(f"Updated {BASELINE_PATH.relative_to(ROOT)} with {sum(current.values())} errors.")
        return 0

    if not BASELINE_PATH.exists():
        print(f"Missing mypy baseline: {BASELINE_PATH}", file=sys.stderr)
        return 2

    baseline = load_baseline()
    regressions = find_regressions(current, baseline)
    if regressions:
        print("Mypy baseline regression detected:", file=sys.stderr)
        for (file, code, message), count in sorted(regressions.items())[:25]:
            print(f"  {file} [{code}] x{count}: {message}", file=sys.stderr)
        print(
            f"Current: {sum(current.values())}; baseline: {sum(baseline.values())}.",
            file=sys.stderr,
        )
        return 1

    reduction = sum(baseline.values()) - sum(current.values())
    print(
        f"Mypy ratchet passed: {sum(current.values())} current errors, "
        f"{sum(baseline.values())} baseline ({reduction} removed)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
