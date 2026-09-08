#!/usr/bin/env python3
"""Target-independent official Tau checks for study-run preflight command profiles.

Run each mode as an independent check in the actual Tau environment. This script
never imports a target model or acquires a GPU. Auxiliary broker qualification is
a separate command check using qualify_auxiliary_client.py in its pinned profile.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import os
from pathlib import Path

import run_qwen38_tau as tau

from matric_eval.studies.preflight import write_receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inputs", "patch", "dependencies", "tasks", "sandbox"))
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--inputs-summary", type=Path, required=True)
    parser.add_argument("--scored-ids", type=Path, required=True)
    parser.add_argument("--tau-checkout", type=Path, required=True)
    parser.add_argument("--tau-patch-manifest", type=Path, default=tau.DEFAULT_TAU_PATCH_MANIFEST)
    args = parser.parse_args()
    result: dict[str, object] = {
        "schema": "matric-eval.tau-preflight/1",
        "mode": args.mode,
        "passed": True,
    }
    if args.mode == "inputs":
        study, _, _ = tau._load_protocol(args.protocol, args.model_id)
        summary = tau._load_object(args.inputs_summary, "agentic input summary")
        grouped = tau._load_object(args.scored_ids, "scored IDs")
        ids = tau._flatten_scored_ids(grouped)
        if tau._sha256_file(args.scored_ids) != summary["artifacts"]["tau3-scored-ids.json"]:
            raise ValueError("scored input hash differs from frozen summary")
        if tau._sha256_file(args.protocol) != summary["protocol_sha256"]:
            raise ValueError("protocol hash differs from frozen summary")
        if len(ids) != summary["scored_samples"]["tau3-bench"]:
            raise ValueError("scored count differs from summary")
        result["manifest_sha256"] = tau._verify_manifest(args.manifest, summary, ids, study["id"])
        result["ordered_ids"] = ids
    elif args.mode == "patch":
        result["patch"] = tau._tau_worktree_evidence(args.tau_checkout, args.tau_patch_manifest)
    elif args.mode == "dependencies":
        if importlib.metadata.version("tau2") != tau.TAU_PACKAGE_VERSION:
            raise ValueError("installed tau2 version differs from pinned contract")
        if tau._git_revision(args.tau_checkout) != tau.TAU_SOURCE_REVISION:
            raise ValueError("tau checkout revision differs from pinned contract")
        # Import actual resolved runner/model types before target allocation.
        from tau2.data_model.simulation import TextRunConfig
        from tau2.run import get_tasks

        result["configuration_fields"] = sorted(TextRunConfig.model_fields)
        result["task_loader"] = get_tasks.__module__
    elif args.mode == "tasks":
        from tau2.run import get_tasks

        grouped = tau._load_object(args.scored_ids, "scored IDs")
        for domain, ids in grouped.items():
            loaded = [task.id for task in get_tasks(domain, task_split_name="base", task_ids=ids)]
            if len(loaded) != len(set(loaded)) or set(loaded) != set(ids):
                raise ValueError(f"official task loader membership mismatch: {domain}")
        result["domains"] = sorted(grouped)
    else:
        result["sandbox"] = tau._knowledge_dependency_evidence()
    write_receipt(Path(os.environ["MATRIC_PREFLIGHT_RECEIPT"]), result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
