#!/usr/bin/env python3
"""Bounded public-broker embedding qualification through actual LiteLLM."""

from __future__ import annotations

import argparse
import json
import os
import platform
import uuid
from pathlib import Path
from typing import Any

from matric_eval.studies.broker_admission import verify_public_lane
from matric_eval.studies.client_conformance import (
    ClientProfile,
    ConformanceError,
    qualify_embedding,
    verify_public_model_metadata,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--authorized-live-canary", action="store_true", required=True)
    args = parser.parse_args()
    if platform.node().split(".")[0] != "basilisk":
        raise RuntimeError("embedding qualification requires A100")
    document = json.loads(args.profile.read_text())
    dimensions = document.pop("embedding_dimensions")
    profile = ClientProfile(**document)
    profile.validate()
    if (
        profile.api_base.rstrip("/") != "http://127.0.0.1:11434"
        or profile.admission_protocol != "ollama-unify-body-free-resume/1"
    ):
        raise ValueError("embedding qualification requires the public broker resume profile")
    if args.receipt.exists():
        raise ValueError("refusing to overwrite qualification evidence")
    request_id = "matric-embedding-" + uuid.uuid4().hex
    receipt: dict[str, Any] = {
        "request_id": request_id,
        "client_profile_sha256": profile.fingerprint(),
    }
    failed = False
    try:
        before = verify_public_model_metadata(profile, request_id + "-before")
        receipt.update(
            qualify_embedding(
                model=profile.model.replace("ollama_chat/", "ollama/", 1),
                api_base=profile.api_base,
                expected_digest=profile.model_digest,
                observed_digest=before["model_digest"],
                dimensions=dimensions,
                request_id=request_id,
                client_version=profile.client_version,
                timeout=profile.timeout,
                broker_identity=profile.broker_identity,
                broker_revision=profile.broker_revision,
                admission_protocol=profile.admission_protocol,
                profile=profile,
            )
        )
        receipt["allocation"] = verify_public_lane(profile, receipt["broker_admission"])
        receipt["public_model_metadata"] = {
            "before": before,
            "after": verify_public_model_metadata(profile, request_id + "-after"),
        }
        receipt["client_response"] = "passed"
    except ConformanceError as exc:
        failed = True
        receipt.update({"client_response": "failed", "reason": str(exc)})
        if exc.broker_evidence:
            receipt["broker_admission"] = exc.broker_evidence
    fd = os.open(args.receipt, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(receipt, output, indent=2)
        output.flush()
        os.fsync(output.fileno())
    return 75 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
