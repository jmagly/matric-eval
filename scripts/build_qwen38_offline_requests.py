#!/usr/bin/env python3
"""Materialize manifest-ordered offline requests and private scoring records."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
from typing import Any

from datasets import load_dataset

from matric_eval.prompts import get_prompt
from matric_eval.studies import StudyBatchRequest, StudyProtocol, validate_batch_contract
from matric_eval.tasks.ifeval import record_to_sample as ifeval_sample
from matric_eval.tasks.livecodebench import record_to_sample as livecodebench_sample
from matric_eval.tasks.mtbench import record_to_sample as mtbench_sample
from matric_eval.tasks.mmlu_pro import record_to_sample as mmlu_sample
from matric_eval.tasks.refusal import load_or_bench_hard, load_strongreject, load_xstest

LCB_FILES = (
    "test.jsonl",
    "test2.jsonl",
    "test3.jsonl",
    "test4.jsonl",
    "test5.jsonl",
    "test6.jsonl",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain an object")
    return payload


def _selected_ids(manifest: dict[str, Any], allocation_id: str) -> list[str]:
    allocations = manifest.get("allocations")
    if not isinstance(allocations, list):
        raise ValueError("manifest allocations must be a list")
    for allocation in allocations:
        if isinstance(allocation, dict) and allocation.get("allocation_id") == allocation_id:
            ids = allocation.get("selected_ids")
            if isinstance(ids, list) and all(isinstance(sample_id, str) for sample_id in ids):
                return ids
    raise ValueError(f"manifest is missing allocation {allocation_id}")


def _sample_record(sample: Any) -> dict[str, Any]:
    target = getattr(sample, "target", None)
    if hasattr(target, "text"):
        target = target.text
    return {
        "target": target,
        "metadata": getattr(sample, "metadata", None),
    }


def _mmlu_prompt(row: dict[str, Any]) -> str:
    module = importlib.import_module("inspect_evals.mmlu_pro.mmlu_pro")
    template = str(module.USER_PROMPT_TEMPLATE)
    options = [str(option) for option in row["options"] if option != "N/A"]
    choices = "\n".join(
        f"{chr(ord('A') + index)}) {option}" for index, option in enumerate(options)
    )
    letters = ",".join(chr(ord("A") + index) for index in range(len(options)))
    return template.format(question=row["question"], choices=choices, letters=letters)


def _lcb_selected(snapshot: Path, selected: set[str]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for filename in LCB_FILES:
        with (snapshot / filename).open(encoding="utf-8") as source:
            for line in source:
                if not line.strip():
                    continue
                row = json.loads(line)
                sample_id = f"{row['platform']}/{row['question_id']}"
                if sample_id in selected:
                    records[sample_id] = row
    return records


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    if path.exists():
        raise ValueError(f"refusing to overwrite existing study input: {path}")
    with path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)
    return _sha256_file(path)


def build_inputs(args: argparse.Namespace) -> dict[str, Any]:
    study = StudyProtocol.from_yaml(args.protocol)
    manifest = _load_json(args.manifest)
    os.environ["XDG_CACHE_HOME"] = str(args.cache_root)
    revisions = {allocation.id: allocation.dataset_revision for allocation in study.benchmarks}

    sample_maps: dict[str, dict[str, tuple[list[dict[str, str]], dict[str, Any]]]] = {}
    refusal_sets = {
        "xstest-safe": load_xstest("full", subset="safe"),
        "xstest-unsafe": load_xstest("full", subset="unsafe"),
        "or-bench-hard-benign": load_or_bench_hard("full"),
        "strongreject-harmful": load_strongreject("full"),
    }
    for allocation_id, samples in refusal_sets.items():
        sample_maps[allocation_id] = {
            str(sample.id): (
                [{"role": "user", "content": str(sample.input)}],
                _sample_record(sample),
            )
            for sample in samples
        }

    ifeval = load_dataset(
        "google/IFEval",
        split="train",
        revision=revisions["ifeval"],
        cache_dir=str(args.cache_root / "huggingface/datasets"),
    )
    sample_maps["ifeval"] = {}
    for row in ifeval:
        sample = ifeval_sample(dict(row))
        sample_maps["ifeval"][str(sample.id)] = (
            [{"role": "user", "content": str(sample.input)}],
            _sample_record(sample),
        )

    mmlu = load_dataset(
        "TIGER-Lab/MMLU-Pro",
        split="test",
        revision=revisions["mmlu-pro"],
        cache_dir=str(args.cache_root / "huggingface/datasets"),
    )
    sample_maps["mmlu-pro"] = {}
    for raw_row in mmlu:
        row = dict(raw_row)
        sample = mmlu_sample(row)
        sample_maps["mmlu-pro"][str(sample.id)] = (
            [{"role": "user", "content": _mmlu_prompt(row)}],
            _sample_record(sample),
        )

    lcb_ids = _selected_ids(manifest, "livecodebench")
    lcb_rows = _lcb_selected(args.livecodebench_snapshot, set(lcb_ids))
    sample_maps["livecodebench"] = {}
    for sample_id, row in lcb_rows.items():
        sample = livecodebench_sample(row)
        sample_maps["livecodebench"][sample_id] = (
            [
                {"role": "system", "content": get_prompt("livecodebench", thinking=True)},
                {"role": "user", "content": str(sample.input)},
            ],
            _sample_record(sample),
        )

    mtbench_path = args.fastchat_checkout / "fastchat/llm_judge/data/mt_bench/question.jsonl"
    sample_maps["mtbench"] = {}
    for line in mtbench_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        sample = mtbench_sample(json.loads(line))
        sample_maps["mtbench"][str(sample.id)] = (
            [{"role": "user", "content": str(sample.input)}],
            _sample_record(sample),
        )

    offline_allocations = [
        allocation
        for allocation in study.benchmarks
        if allocation.execution_mode == "offline-batch"
    ]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.chmod(0o750)
    artifacts: dict[str, Any] = {}
    for allocation in offline_allocations:
        selected = _selected_ids(manifest, allocation.id)
        available = sample_maps[allocation.id]
        missing = [sample_id for sample_id in selected if sample_id not in available]
        if missing:
            raise ValueError(f"{allocation.id} is missing selected IDs: {missing[:5]}")
        request_rows = []
        scoring_rows = []
        parsed_requests = []
        for sample_id in selected:
            messages, scoring = available[sample_id]
            request_id = f"{allocation.id}:{sample_id}:turn-1"
            request = {
                "request_id": request_id,
                "allocation_id": allocation.id,
                "sample_id": sample_id,
                "messages": messages,
            }
            request_rows.append(request)
            parsed_requests.append(StudyBatchRequest.from_dict(request, len(request_rows)))
            scoring_rows.append(
                {
                    "request_id": request_id,
                    "allocation_id": allocation.id,
                    "sample_id": sample_id,
                    **scoring,
                }
            )
        validate_batch_contract(study, manifest, parsed_requests)
        request_path = args.output_dir / f"{allocation.id}-requests.jsonl"
        scoring_path = args.output_dir / f"{allocation.id}-scoring.jsonl"
        artifacts[allocation.id] = {
            "samples": len(selected),
            "requests": str(request_path),
            "requests_sha256": _write_jsonl(request_path, request_rows),
            "scoring": str(scoring_path),
            "scoring_sha256": _write_jsonl(scoring_path, scoring_rows),
        }
    return {
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "manifest_sha256": manifest.get("manifest_sha256"),
        "cohort": manifest.get("cohort"),
        "artifacts": artifacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--livecodebench-snapshot", type=Path, required=True)
    parser.add_argument("--fastchat-checkout", type=Path, required=True)
    args = parser.parse_args()
    summary = build_inputs(args)
    summary_path = args.output_dir / "inputs-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_path.chmod(0o600)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
