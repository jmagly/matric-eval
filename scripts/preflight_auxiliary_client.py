#!/usr/bin/env python3
"""Adapt actual public-broker client canaries into correlated preflight receipts."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from matric_eval.studies.preflight import file_digest, write_receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--canary-script", type=Path, required=True)
    parser.add_argument("--operation", choices=("completion", "embedding"), default="completion")
    args = parser.parse_args()
    from matric_eval.studies.client_conformance import ClientProfile

    document = json.loads(args.profile.read_text())
    dimensions = document.pop("embedding_dimensions", None)
    if (args.operation == "embedding") != (dimensions is not None):
        raise ValueError("embedding dimensions and operation must agree")
    profile = ClientProfile(**document)
    profile.validate()
    if profile.admission_protocol != "ollama-unify-body-free-resume/1":
        raise ValueError("preflight requires actual correlated public broker admission")
    with tempfile.TemporaryDirectory(prefix="matric-auxiliary-preflight-") as temporary:
        receipt_path = Path(temporary) / "client.json"
        command = [
            sys.executable,
            str(args.canary_script),
            "--profile",
            str(args.profile),
            "--receipt",
            str(receipt_path),
            "--authorized-live-canary",
        ]
        if args.operation == "completion":
            command.append("--public-broker-admission")
        completed = subprocess.run(
            command, check=False, timeout=profile.timeout + profile.admission_total_seconds + 60
        )
        if receipt_path.stat().st_size > 1024 * 1024:
            raise ValueError("auxiliary client receipt exceeds 1 MiB")
        receipt = json.loads(receipt_path.read_text())
        admission = receipt.get("broker_admission", {})
        allocation = receipt.get("allocation", {})
        profile_field = (
            "client_profile_sha256" if args.operation == "embedding" else "profile_sha256"
        )
        passed = (
            completed.returncode == 0
            and receipt.get("client_response") == "passed"
            and receipt.get(profile_field) == profile.fingerprint()
            and admission.get("logical_request_id") == receipt.get("request_id")
            and bool(admission.get("broker_request_id"))
            and bool(admission.get("lane"))
            and allocation.get("broker_request_id") == admission.get("broker_request_id")
            and allocation.get("logical_request_id") == admission.get("logical_request_id")
            and allocation.get("lane") == admission.get("lane")
            and (dimensions is None or receipt.get("measured", {}).get("dimensions") == dimensions)
        )
        write_receipt(
            Path(os.environ["MATRIC_PREFLIGHT_RECEIPT"]),
            {
                "schema": "matric-eval.auxiliary-preflight/1",
                "transport_passed": passed,
                "operation": args.operation,
                "profile_sha256": profile.fingerprint(),
                "profile_file_sha256": file_digest(args.profile),
                "broker_admission": admission,
                "allocation": allocation,
                "measured": receipt.get("measured"),
                "execution_digest_binding": "unverified",
                "client_exit_code": completed.returncode,
                "reason": receipt.get("reason") if not passed else None,
                "qualification_scope": "actual_client_transport_and_own_request_correlation",
                "semantic_calibration": "not_performed",
                "phase_timing": "warmup_included_in_queue",
            },
        )
    if not passed:
        print("auxiliary client transport/profile/own-request correlation failed", file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
