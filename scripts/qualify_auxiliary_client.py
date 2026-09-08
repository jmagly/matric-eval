#!/usr/bin/env python3
"""Bounded auxiliary transport canary using the versioned actual-client path.

Run only after broker-owner authorization and scoped GPU allocation. This does
not run TAU tasks or authorize changes to the frozen simulator protocol.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import uuid
from pathlib import Path

from matric_eval.studies.client_conformance import (
    ClientProfile,
    ConformanceError,
    qualify_completion,
    verify_public_model_metadata,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    allocation = parser.add_mutually_exclusive_group(required=True)
    allocation.add_argument("--lease-receipt", type=Path)
    allocation.add_argument("--public-broker-admission", action="store_true")
    parser.add_argument("--authorized-live-canary", action="store_true", required=True)
    args = parser.parse_args()
    if socket.gethostname().split(".")[0] != "basilisk":
        raise RuntimeError("transport canaries require the authorized A100 host")
    if args.receipt.exists():
        raise ValueError("refusing to overwrite qualification evidence")
    # Retain only the allocation artifact hash; never copy lease tokens.
    import hashlib

    lease_digest = (
        hashlib.sha256(args.lease_receipt.read_bytes()).hexdigest() if args.lease_receipt else None
    )
    profile = ClientProfile(**json.loads(args.profile.read_text()))
    profile.validate()
    if (
        args.public_broker_admission
        and profile.admission_protocol != "ollama-unify-body-free-resume/1"
    ):
        raise ValueError("public broker admission requires the bounded resume profile")
    request_id = "matric-canary-" + uuid.uuid4().hex
    tools = (
        [
            {
                "type": "function",
                "function": {
                    "name": "ping",
                    "description": "Return a fixture ping",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        if profile.tools
        else None
    )
    failure = None
    try:
        before = verify_public_model_metadata(profile, request_id + "-before")
        receipt = qualify_completion(
            profile,
            request_id,
            [{"role": "user", "content": "Call ping." if tools else "Reply exactly OK."}],
            tools=tools,
        )
        if args.public_broker_admission:
            from matric_eval.studies.broker_admission import verify_public_lane

            receipt["allocation"] = verify_public_lane(profile, receipt["broker_admission"])
        after = verify_public_model_metadata(profile, request_id + "-after")
        receipt["public_model_metadata"] = {"before": before, "after": after}
    except ConformanceError as exc:
        failure = str(exc)
        receipt = {
            "schema": profile.schema,
            "profile_sha256": profile.fingerprint(),
            "request_id": request_id,
            "client_response": "failed",
            "reason": failure,
            "broker_admission": exc.broker_evidence,
        }
    if lease_digest is not None:
        receipt["lease_receipt_sha256"] = lease_digest
        receipt["allocation_binding"] = "unverified_external_artifact_hash"
    fd = os.open(args.receipt, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(receipt, output, indent=2)
        output.write("\n")
    if failure:
        raise SystemExit(failure)


if __name__ == "__main__":
    main()
