"""CLI for contract-checked deterministic scoring of one study output batch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from matric_eval.studies.protocol import StudyProtocol
from matric_eval.studies.scoring import load_jsonl, score_offline_outputs, sha256_file
from matric_eval.studies.scoring import write_private_jsonl


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol", type=Path)
    parser.add_argument("results", type=Path)
    parser.add_argument("scoring_records", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--code-timeout", type=int, default=30)
    args = parser.parse_args(argv)
    if args.code_timeout < 1:
        parser.error("--code-timeout must be positive")

    study = StudyProtocol.from_yaml(args.protocol, validate_registry=False)
    rows, summary = score_offline_outputs(
        study=study,
        results=load_jsonl(args.results),
        scoring_records=load_jsonl(args.scoring_records),
        code_timeout=args.code_timeout,
    )
    summary.update(
        {
            "results_sha256": sha256_file(args.results),
            "scoring_records_sha256": sha256_file(args.scoring_records),
            "scores_sha256": write_private_jsonl(args.output, rows),
        }
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
