#!/usr/bin/env python3
"""Qualify the official Tau generation boundary without executing a benchmark task."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path

from matric_eval.studies.auxiliary_runtime import external_arguments, scoped_auxiliary_client
from matric_eval.studies.broker_admission import verify_public_lane
from matric_eval.studies.client_conformance import ClientProfile, verify_public_model_metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--authorized-live-canary", action="store_true", required=True)
    args = parser.parse_args()
    if platform.node().split(".")[0] != "basilisk":
        raise RuntimeError("official client qualification requires A100")
    profile = ClientProfile(**json.loads(args.profile.read_text()))
    profile.validate()
    if (
        profile.api_base.rstrip("/") != "http://127.0.0.1:11434"
        or profile.admission_protocol != "ollama-unify-body-free-resume/1"
        or profile.seed is None
        or profile.tools
    ):
        raise ValueError("qualification requires a public native broker profile and explicit seed")
    args.directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    from tau2.data_model.message import UserMessage
    from tau2.utils import llm_utils

    before = verify_public_model_metadata(profile, "official-before")
    calls = args.directory / "calls"
    with scoped_auxiliary_client(llm_utils, profile, calls, seed=profile.seed):
        response = llm_utils.generate(
            model=profile.model,
            messages=[UserMessage(role="user", content="Reply exactly OK.")],
            **external_arguments(profile),
        )
    receipts = list(calls.glob("*.json"))
    if len(receipts) != 1:
        raise RuntimeError("expected exactly one correlated external generation")
    receipt = json.loads(receipts[0].read_text())
    receipt["allocation"] = verify_public_lane(profile, receipt["broker_admission"])
    receipt["public_model_metadata"] = {
        "before": before,
        "after": verify_public_model_metadata(profile, "official-after"),
    }
    receipt["official_harness"] = {
        "entrypoint": "tau2.utils.llm_utils.generate",
        "module_sha256": hashlib.sha256(Path(llm_utils.__file__).read_bytes()).hexdigest(),
        "python": platform.python_version(),
        "versions": {
            name: importlib.metadata.version(name)
            for name in (
                "litellm",
                "openai",
                "httpx",
                "pydantic",
                "pydantic-settings",
                "jsonschema",
            )
        },
        "response_role": response.role,
        "visible_output_present": bool(response.content and response.content.strip()),
        "tasks_executed": 0,
    }
    path = args.directory / "qualification.json"
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(receipt, output, indent=2)
        output.flush()
        os.fsync(output.fileno())
    print(json.dumps({"receipt": str(path), "request_id": receipt["request_id"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
