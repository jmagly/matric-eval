#!/usr/bin/env python3
"""Apply or verify the Qwen3.8 study's content-addressed Harbor patch."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Sequence

from qwen38_terminal_runtime import (
    apply_harbor_patch,
    load_patch_contract,
    verify_harbor_checkout,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT / "studies/qwen38-obliteration-2026-09/patches/harbor-0.22.0-terminal-runtime-guard.json"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harbor-checkout", type=Path, required=True)
    parser.add_argument("--patch-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--sync-locked",
        action="store_true",
        help="run uv sync --locked only after the patched checkout verifies",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    contract = load_patch_contract(args.patch_manifest)
    evidence = (
        apply_harbor_patch(args.harbor_checkout, contract)
        if args.apply
        else verify_harbor_checkout(args.harbor_checkout, contract)
    )
    if args.sync_locked:
        subprocess.run(
            ["uv", "sync", "--locked"],
            cwd=args.harbor_checkout,
            check=True,
            timeout=1800,
        )
        evidence["environment_sync"] = "uv-sync-locked"
    else:
        evidence["environment_sync"] = "not-requested"
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
