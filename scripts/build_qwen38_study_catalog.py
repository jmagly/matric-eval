#!/usr/bin/env python3
"""Build the canonical ID catalog for the Qwen3.8 intervention study."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from datasets import load_dataset

from matric_eval.studies import StudyProtocol
from matric_eval.tasks.refusal import (
    load_or_bench_hard,
    load_strongreject,
    load_xstest,
)

STUDY_ROOT = Path("studies/qwen38-obliteration-2026-09")
BFCL_CATEGORIES = (
    "memory_kv",
    "memory_vector",
    "memory_rec_sum",
    "web_search_base",
    "web_search_no_snippet",
)


def _git_revision(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number} must contain an object")
        rows.append(row)
    return rows


def _bfcl_entries(python: Path) -> list[dict[str, str]]:
    code = """
import json
from bfcl_eval.utils import load_dataset_entry
categories = [
    "memory_kv", "memory_vector", "memory_rec_sum",
    "web_search_base", "web_search_no_snippet",
]
print(json.dumps([
    {"id": entry["id"], "stratum": category}
    for category in categories
    for entry in load_dataset_entry(category, include_prereq=False)
], sort_keys=True))
"""
    result = subprocess.run(
        [str(python), "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )
    entries = json.loads(result.stdout)
    if not isinstance(entries, list):
        raise ValueError("BFCL catalog subprocess did not return a list")
    return entries


def _tau_ids(checkout: Path) -> list[str]:
    root = checkout / "data/tau2/domains"
    ids = []
    for domain in ("airline", "retail", "telecom", "banking_knowledge"):
        tasks = json.loads((root / domain / "tasks.json").read_text(encoding="utf-8"))
        task_ids = [str(task.get("id", task.get("task_id"))) for task in tasks]
        split_path = root / domain / "split_tasks.json"
        if split_path.exists():
            split = json.loads(split_path.read_text(encoding="utf-8"))
            task_ids = [str(task_id) for task_id in split["base"]]
        ids.extend(f"{domain}:{task_id}" for task_id in task_ids)
    return ids


def _lcb_ids(snapshot: Path) -> list[str]:
    names = ["test.jsonl", "test2.jsonl", "test3.jsonl", "test4.jsonl", "test5.jsonl", "test6.jsonl"]
    rows = [row for name in names for row in _jsonl(snapshot / name)]
    return [f"{row['platform']}/{row['question_id']}" for row in rows]


def build_catalog(args: argparse.Namespace) -> dict[str, list[Any]]:
    study = StudyProtocol.from_yaml(args.protocol)
    revisions = {allocation.id: allocation.dataset_revision for allocation in study.benchmarks}
    if _git_revision(args.bfcl_checkout) != revisions["bfcl-v4-agentic"]:
        raise ValueError("BFCL checkout revision does not match the protocol")
    if _git_revision(args.tau_checkout) != revisions["tau3-bench"]:
        raise ValueError("tau3 checkout revision does not match the protocol")
    if _git_revision(args.terminal_checkout) != revisions["terminal-bench-2.1"]:
        raise ValueError("Terminal-Bench checkout revision does not match the protocol")
    if _git_revision(args.fastchat_checkout) != revisions["mtbench"]:
        raise ValueError("FastChat checkout revision does not match the protocol")

    os.environ["XDG_CACHE_HOME"] = str(args.cache_root)
    ifeval = load_dataset(
        "google/IFEval",
        split="train",
        revision=revisions["ifeval"],
        cache_dir=str(args.cache_root / "huggingface/datasets"),
    )
    mmlu = load_dataset(
        "TIGER-Lab/MMLU-Pro",
        split="test",
        revision=revisions["mmlu-pro"],
        cache_dir=str(args.cache_root / "huggingface/datasets"),
    )
    mtbench_path = (
        args.fastchat_checkout / "fastchat/llm_judge/data/mt_bench/question.jsonl"
    )
    terminal_root = args.terminal_checkout / "tasks"
    terminal_ids = sorted(
        path.name
        for path in terminal_root.iterdir()
        if path.is_dir() and (path / "task.toml").is_file()
    )

    catalog: dict[str, list[Any]] = {
        "xstest-safe": [str(sample.id) for sample in load_xstest("full", subset="safe")],
        "xstest-unsafe": [str(sample.id) for sample in load_xstest("full", subset="unsafe")],
        "or-bench-hard-benign": [str(sample.id) for sample in load_or_bench_hard("full")],
        "strongreject-harmful": [str(sample.id) for sample in load_strongreject("full")],
        "ifeval": [str(row["key"]) for row in ifeval],
        "mmlu-pro": [str(row["question_id"]) for row in mmlu],
        "livecodebench": _lcb_ids(args.livecodebench_snapshot),
        "mtbench": [str(row["question_id"]) for row in _jsonl(mtbench_path)],
        "bfcl-v4-agentic": _bfcl_entries(args.bfcl_python),
        "tau3-bench": _tau_ids(args.tau_checkout),
        "terminal-bench-2.1": terminal_ids,
    }
    expected = {allocation.id: allocation.available_samples for allocation in study.benchmarks}
    if set(catalog) != set(expected):
        raise ValueError("catalog allocations do not match the protocol")
    for allocation_id, entries in catalog.items():
        ids = [str(entry["id"]) if isinstance(entry, dict) else str(entry) for entry in entries]
        if len(ids) != expected[allocation_id]:
            raise ValueError(
                f"{allocation_id} exposes {len(ids)} IDs; expected {expected[allocation_id]}"
            )
        if len(ids) != len(set(ids)):
            raise ValueError(f"{allocation_id} contains duplicate canonical IDs")
    return catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=STUDY_ROOT / "protocol.yaml")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--livecodebench-snapshot", type=Path, required=True)
    parser.add_argument("--fastchat-checkout", type=Path, required=True)
    parser.add_argument("--bfcl-checkout", type=Path, required=True)
    parser.add_argument("--bfcl-python", type=Path, required=True)
    parser.add_argument("--tau-checkout", type=Path, required=True)
    parser.add_argument("--terminal-checkout", type=Path, required=True)
    args = parser.parse_args()

    catalog = build_catalog(args)
    serialized = json.dumps(catalog, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialized, encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "sha256": hashlib.sha256(serialized.encode()).hexdigest(),
                "allocations": {key: len(value) for key, value in sorted(catalog.items())},
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
