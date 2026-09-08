"""Explicit external-runner amendment using the same adapter as transport canaries."""

from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterator

from matric_eval.studies.client_conformance import (
    ClientProfile,
    ConformanceError,
    invoke_completion,
    normalize_model,
)


def load_amendment(
    profile_path: Path, amendment_path: Path, *, study_id: str, protocol_sha256: str
) -> tuple[ClientProfile, dict[str, Any]]:
    profile = ClientProfile(**json.loads(profile_path.read_text()))
    profile.validate()
    if (
        profile.api_base.rstrip("/") != "http://127.0.0.1:11434"
        or profile.admission_protocol != "ollama-unify-body-free-resume/1"
    ):
        raise ConformanceError("auxiliary_amendment_requires_public_broker")
    amendment = json.loads(amendment_path.read_text())
    if (
        amendment.get("schema") != "matric-eval.auxiliary-amendment/1"
        or amendment.get("study_id") != study_id
        or amendment.get("protocol_sha256") != protocol_sha256
        or amendment.get("profile_sha256") != profile.fingerprint()
        or amendment.get("comparability") != "separate-amendment-lane"
        or amendment.get("roles") != ["user_simulator", "nl_evaluator"]
    ):
        raise ConformanceError("auxiliary_amendment_identity_mismatch")
    return profile, amendment


def external_arguments(profile: ClientProfile) -> dict[str, Any]:
    """Explicit arguments passed through the official external harness."""
    arguments = profile.arguments("profile-contract")
    # Correlation is unique per call, supplied at the common dispatch boundary.
    arguments.pop("headers")
    arguments.pop("seed", None)
    return arguments


def _receipt(directory: Path, request_id: str, receipt: dict[str, Any]) -> None:
    fd = os.open(directory / f"{request_id}.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(receipt, output, sort_keys=True)
        output.flush()
        os.fsync(output.fileno())


@contextmanager
def scoped_auxiliary_client(
    module: Any, profile: ClientProfile, directory: Path, *, seed: int
) -> Iterator[None]:
    """Intercept only the selected auxiliary model in a single-worker Tau run.

    Calls for the target retain their original implementation. The shared adapter
    validates every effective option before dispatch and retains content-free
    per-call evidence. No prior qualification is implicitly reused for a new seed.
    """
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    original = module.completion
    effective = replace(profile, seed=seed)

    def completion(*, model: str, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        if normalize_model(model) != normalize_model(profile.model):
            return original(model=model, messages=messages, **kwargs)
        tools = kwargs.pop("tools", None)
        tool_choice = kwargs.pop("tool_choice", None)
        expected = external_arguments(effective)
        expected["seed"] = seed
        # The official harness may supply the seed through its RNG/config only;
        # make the declared per-task generation seed explicit at this boundary.
        kwargs.setdefault("seed", seed)
        if kwargs != expected or tool_choice is not None:
            raise ConformanceError("external_client_arguments_mismatch")
        request_id = "matric-runtime-" + uuid.uuid4().hex
        try:
            response, receipt = invoke_completion(effective, request_id, messages, tools=tools)
        except ConformanceError as exc:
            _receipt(
                directory,
                request_id,
                {
                    "request_id": request_id,
                    "profile_sha256": effective.fingerprint(),
                    "client_response": "failed",
                    "reason": str(exc),
                    "broker_admission": exc.broker_evidence,
                },
            )
            raise
        _receipt(directory, request_id, receipt)
        return response

    module.completion = completion
    try:
        yield
    finally:
        module.completion = original
