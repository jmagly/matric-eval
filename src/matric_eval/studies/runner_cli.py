"""Lean command-line entry point for the pinned offline study container."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from matric_eval.studies.batch import run_offline_batch


def build_parser() -> argparse.ArgumentParser:
    """Build the container runner argument parser without importing benchmark tasks."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("requests", type=Path)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-qualification", type=Path, required=True)
    parser.add_argument("--chat-template", type=Path, required=True)
    parser.add_argument("--gpu-lease-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one manifest-locked allocation batch and print its evidence summary."""
    args = build_parser().parse_args(argv)
    summary = run_offline_batch(
        protocol_path=args.protocol,
        manifest_path=args.manifest,
        requests_path=args.requests,
        model_id=args.model_id,
        model_path=args.model_path,
        model_qualification_path=args.model_qualification,
        chat_template_path=args.chat_template,
        lease_receipt_path=args.gpu_lease_receipt,
        output_path=args.output,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
