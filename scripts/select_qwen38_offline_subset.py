#!/usr/bin/env python3
"""Materialize an allocation subset of the offline study inputs.

`build_qwen38_offline_requests.py` writes one `<allocation>-requests.jsonl` and
`<allocation>-scoring.jsonl` pair per offline-batch allocation. When only some
allocations are acquirable (see #234), the runner needs a requests file limited to
those allocations and the scorer needs a scoring-records file with *identical
ordered request IDs*. Building either by hand risks a silent mismatch; this
produces both from one list, in protocol order, and refuses to overwrite.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from matric_eval.studies.protocol import StudyProtocol


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"{path}:{number} must contain an object")
        rows.append(payload)
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    if path.exists():
        raise ValueError(f"refusing to overwrite existing study input: {path}")
    digest = hashlib.sha256()
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            line = json.dumps(row, sort_keys=True) + "\n"
            handle.write(line)
            digest.update(line.encode())
    return digest.hexdigest()


def select_subset(
    *,
    protocol_path: Path,
    input_dir: Path,
    allocation_ids: list[str],
    output_prefix: Path,
) -> dict[str, Any]:
    """Concatenate the chosen allocations' request/scoring pairs in protocol order."""
    study = StudyProtocol.from_yaml(protocol_path, validate_registry=False)
    offline_order = [a.id for a in study.benchmarks if a.execution_mode == "offline-batch"]
    declared = {a.id: a.execution_mode for a in study.benchmarks}

    requested = list(dict.fromkeys(allocation_ids))
    if len(requested) != len(allocation_ids):
        raise ValueError("allocation list contains duplicates")
    for allocation_id in requested:
        if allocation_id not in declared:
            raise ValueError(f"unknown allocation: {allocation_id}")
        if declared[allocation_id] != "offline-batch":
            raise ValueError(
                f"{allocation_id} is {declared[allocation_id]}, not offline-batch; "
                "it cannot be run through the offline runner"
            )
    # The batch runner requires request blocks to follow protocol order.
    ordered = [a for a in offline_order if a in requested]

    request_rows: list[dict[str, Any]] = []
    scoring_rows: list[dict[str, Any]] = []
    per_allocation: dict[str, int] = {}
    for allocation_id in ordered:
        requests = _read_jsonl(input_dir / f"{allocation_id}-requests.jsonl")
        scoring = _read_jsonl(input_dir / f"{allocation_id}-scoring.jsonl")
        request_ids = [r.get("request_id") for r in requests]
        if request_ids != [r.get("request_id") for r in scoring]:
            raise ValueError(
                f"{allocation_id}: requests and scoring records disagree on request IDs"
            )
        if any(r.get("allocation_id") != allocation_id for r in requests):
            raise ValueError(f"{allocation_id}: a request row names a different allocation")
        request_rows.extend(requests)
        scoring_rows.extend(scoring)
        per_allocation[allocation_id] = len(requests)

    all_ids = [r["request_id"] for r in request_rows]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("subset contains duplicate request IDs")

    requests_path = Path(f"{output_prefix}-requests.jsonl")
    scoring_path = Path(f"{output_prefix}-scoring.jsonl")
    return {
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "allocations": ordered,
        "requests_per_allocation": per_allocation,
        "request_count": len(request_rows),
        "requests_path": str(requests_path),
        "requests_sha256": _write_jsonl(requests_path, request_rows),
        "scoring_path": str(scoring_path),
        "scoring_sha256": _write_jsonl(scoring_path, scoring_rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="directory holding <allocation>-requests.jsonl / -scoring.jsonl pairs",
    )
    parser.add_argument(
        "--allocations", required=True, help="comma-separated allocation IDs to include"
    )
    parser.add_argument(
        "--output-prefix",
        type=Path,
        required=True,
        help="writes <prefix>-requests.jsonl and <prefix>-scoring.jsonl",
    )
    args = parser.parse_args()
    receipt = select_subset(
        protocol_path=args.protocol,
        input_dir=args.input_dir,
        allocation_ids=[a.strip() for a in args.allocations.split(",") if a.strip()],
        output_prefix=args.output_prefix,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
