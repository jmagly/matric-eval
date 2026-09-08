#!/usr/bin/env python3
"""Apply or verify the content-addressed Qwen3.8 Tau runtime patch."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Sequence

from qwen38_tau_context import (
    load_patch_contract,
)
from qwen38_tau_simulator import (
    load_simulator_patch_contract,
    prepare_tau_simulator_checkout,
    verify_tau_simulator_checkout,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT / "studies/qwen38-obliteration-2026-09/patches/tau2-1.0.1-context-guard.json"
)
DEFAULT_SIMULATOR_MANIFEST = (
    ROOT / "studies/qwen38-obliteration-2026-09/patches/tau2-1.0.1-simulator-interface-guard.json"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tau-checkout", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--simulator-manifest", type=Path, default=DEFAULT_SIMULATOR_MANIFEST)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--sync", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    context_contract = load_patch_contract(args.manifest)
    simulator_contract = load_simulator_patch_contract(args.simulator_manifest)
    if simulator_contract.context_contract != context_contract:
        raise RuntimeError("explicit context manifest differs from the simulator prerequisite")
    evidence = (
        verify_tau_simulator_checkout(args.tau_checkout, simulator_contract)
        if args.verify_only
        else prepare_tau_simulator_checkout(args.tau_checkout, simulator_contract)
    )
    if args.sync:
        subprocess.run(
            ["uv", "sync", "--locked", "--extra", "knowledge"],
            cwd=args.tau_checkout,
            check=True,
        )
        evidence["environment_sync"] = "uv-sync-locked-knowledge"
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
