#!/usr/bin/env python3
"""Materialize manifest-locked agentic IDs and BFCL dependency closure."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from matric_eval.studies import StudyProtocol

BFCL_CATEGORIES = (
    "memory_kv",
    "memory_vector",
    "memory_rec_sum",
    "web_search_base",
    "web_search_no_snippet",
)


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest must contain an object")
    return payload


def _selected_ids(manifest: dict[str, Any], allocation_id: str) -> list[str]:
    allocations = manifest.get("allocations")
    if not isinstance(allocations, list):
        raise ValueError("manifest allocations must be a list")
    for allocation in allocations:
        if isinstance(allocation, dict) and allocation.get("allocation_id") == allocation_id:
            ids = allocation.get("selected_ids")
            if isinstance(ids, list) and all(isinstance(value, str) for value in ids):
                return ids
    raise ValueError(f"manifest is missing allocation {allocation_id}")


def _canonical_manifest_sha256(manifest: dict[str, Any]) -> str:
    canonical = dict(manifest)
    declared = canonical.pop("manifest_sha256", None)
    actual = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if declared != actual:
        raise ValueError("manifest SHA-256 does not match canonical content")
    return actual


def _bfcl_dependency_closure(python: Path, selected: list[str]) -> dict[str, list[str]]:
    code = """
import json, sys
from bfcl_eval.utils import load_dataset_entry
categories = (
    "memory_kv", "memory_vector", "memory_rec_sum",
    "web_search_base", "web_search_no_snippet",
)
selected = set(json.load(sys.stdin))
result = {}
found = set()
for category in categories:
    entries = load_dataset_entry(category, include_prereq=True)
    by_id = {entry["id"]: entry for entry in entries}
    needed = {sample_id for sample_id in selected if sample_id in by_id}
    found.update(needed)
    while True:
        dependencies = {
            dependency
            for sample_id in needed
            for dependency in by_id[sample_id].get("depends_on", [])
            if dependency in by_id
        }
        expanded = needed | dependencies
        if expanded == needed:
            break
        needed = expanded
    result[category] = [entry["id"] for entry in entries if entry["id"] in needed]
missing = sorted(selected - found)
if missing:
    raise RuntimeError(f"selected BFCL IDs were not found: {missing}")
print(json.dumps(result, sort_keys=True))
"""
    result = subprocess.run(
        [str(python), "-c", code],
        input=json.dumps(selected),
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise ValueError("BFCL dependency helper returned an invalid object")
    return {
        category: [str(value) for value in payload.get(category, [])]
        for category in BFCL_CATEGORIES
    }


def _write_json(path: Path, payload: Any) -> str:
    if path.exists():
        raise ValueError(f"refusing to overwrite agentic input: {path}")
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8") as handle:
        handle.write(serialized)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)
    return hashlib.sha256(serialized.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--bfcl-python", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    study = StudyProtocol.from_yaml(args.protocol)
    manifest = _load_manifest(args.manifest)
    if manifest.get("study_id") != study.id:
        raise ValueError("manifest study ID does not match protocol")
    if manifest.get("protocol_sha256") != study.canonical_sha256:
        raise ValueError("manifest protocol hash does not match protocol")
    manifest_sha256 = _canonical_manifest_sha256(manifest)
    cohort = manifest.get("cohort")
    if cohort not in {"pilot", "full"}:
        raise ValueError("manifest cohort must be pilot or full")

    bfcl_scored = _selected_ids(manifest, "bfcl-v4-agentic")
    tau_scored = _selected_ids(manifest, "tau3-bench")
    terminal_scored = _selected_ids(manifest, "terminal-bench-2.1")
    bfcl_runner = _bfcl_dependency_closure(args.bfcl_python, bfcl_scored)
    runner_ids = {value for values in bfcl_runner.values() for value in values}
    if not set(bfcl_scored).issubset(runner_ids):
        raise ValueError("BFCL runner closure omits scored IDs")

    tau_by_domain: dict[str, list[str]] = {}
    for sample_id in tau_scored:
        domain, separator, task_id = sample_id.partition(":")
        if not separator or not domain or not task_id:
            raise ValueError(f"invalid tau3 canonical ID: {sample_id}")
        tau_by_domain.setdefault(domain, []).append(task_id)

    args.output_dir.mkdir(parents=True, exist_ok=False)
    args.output_dir.chmod(0o750)
    artifacts = {
        "bfcl-runner-ids.json": bfcl_runner,
        "bfcl-scored-ids.json": bfcl_scored,
        "tau3-scored-ids.json": tau_by_domain,
        "terminal-bench-scored-ids.json": terminal_scored,
    }
    hashes = {
        name: _write_json(args.output_dir / name, payload) for name, payload in artifacts.items()
    }
    summary = {
        "schema_version": "1",
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "manifest_sha256": manifest_sha256,
        "cohort": cohort,
        "scored_samples": {
            "bfcl-v4-agentic": len(bfcl_scored),
            "tau3-bench": len(tau_scored),
            "terminal-bench-2.1": len(terminal_scored),
        },
        "bfcl_runner_cases_including_dependencies": len(runner_ids),
        "artifacts": hashes,
    }
    summary_hash = _write_json(args.output_dir / "agentic-inputs-summary.json", summary)
    print(json.dumps({**summary, "summary_sha256": summary_hash}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
