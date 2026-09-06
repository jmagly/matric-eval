"""CLI for contract-checked deterministic scoring of one study output batch."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import subprocess
from pathlib import Path
from typing import Sequence

from matric_eval.studies.protocol import StudyProtocol
from matric_eval.studies.scoring import (
    IFEVAL_EVALUATOR_REVISION,
    LCB_EVALUATOR_REVISION,
    docker_livecodebench_executor,
    load_jsonl,
    score_offline_outputs,
    sha256_file,
    verify_lcb_evaluator_checkout,
    write_private_jsonl,
)


def _code_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    revision = result.stdout.strip()
    if len(revision) != 40:
        raise RuntimeError("scoring checkout did not report a full Git revision")
    return revision


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol", type=Path)
    parser.add_argument("results", type=Path)
    parser.add_argument("scoring_records", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--code-timeout", type=int, default=6)
    parser.add_argument(
        "--docker-code-sandbox",
        action="store_true",
        help="run generated Python in the isolated networkless A100 Docker daemon",
    )
    args = parser.parse_args(argv)
    if args.code_timeout < 1:
        parser.error("--code-timeout must be positive")

    study = StudyProtocol.from_yaml(args.protocol, validate_registry=False)
    if args.docker_code_sandbox:
        verify_lcb_evaluator_checkout()
    rows, summary = score_offline_outputs(
        study=study,
        results=load_jsonl(args.results),
        scoring_records=load_jsonl(args.scoring_records),
        executor=docker_livecodebench_executor if args.docker_code_sandbox else None,
        code_timeout=args.code_timeout,
    )
    code_revision = _code_revision()
    for row in rows:
        row["scoring_code_revision"] = code_revision
    summary.update(
        {
            "scoring_code_revision": code_revision,
            "evaluators": {
                "ifeval": {
                    "language_detector_seed": study.seed,
                    "implementation": "instruction-following-eval",
                    "revision": IFEVAL_EVALUATOR_REVISION,
                    "version": importlib.metadata.version("instruction-following-eval"),
                },
                "livecodebench": {
                    "implementation": "LiveCodeBench/LiveCodeBench",
                    "revision": LCB_EVALUATOR_REVISION,
                },
                "mmlu-pro": {
                    "implementation": "matric-eval",
                    "revision": code_revision,
                },
            },
            "results_sha256": sha256_file(args.results),
            "scoring_records_sha256": sha256_file(args.scoring_records),
            "scores_sha256": write_private_jsonl(args.output, rows),
        }
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
