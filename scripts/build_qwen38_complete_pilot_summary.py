#!/usr/bin/env python3
"""Seal complete direct, agentic, scorer, and judge pilot runtime evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from matric_eval.studies import StudyProtocol, validated_parallelism_binding

JsonObject = dict[str, Any]
PRIVATE_ROOT = Path("/srv/matric-eval/results/qwen38-obliteration-2026-09")
PUBLIC_ROOT = PRIVATE_ROOT / "public"
MODEL_FILES = {
    "qwen38-27b-source-bf16": "source",
    "qwen38-27b-e03-bf16": "e03",
    "qwen38-27b-pliny-v3-bf16": "pliny",
}
AGENTIC_ALLOCATIONS = {
    "bfcl": "bfcl-v4-agentic",
    "tau": "tau3-bench",
    "terminal": "terminal-bench-2.1",
}
JUDGED_ALLOCATIONS = frozenset(
    {
        "xstest-safe",
        "xstest-unsafe",
        "or-bench-hard-benign",
        "strongreject-harmful",
        "mtbench",
    }
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path, label: str) -> JsonObject:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return payload


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if result < 0 or result == float("inf") or result != result:
        raise ValueError(f"{label} must be finite and non-negative")
    return result


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _manifest(study: StudyProtocol, payload: JsonObject) -> tuple[str, dict[str, list[str]]]:
    canonical = dict(payload)
    declared = canonical.pop("manifest_sha256", None)
    actual = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if declared != actual:
        raise ValueError("manifest_sha256 does not match canonical pilot manifest content")
    expected = {
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "cohort": "pilot",
        "seed": study.seed,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError("pilot manifest identity does not match the protocol")
    raw_allocations = payload.get("allocations")
    if not isinstance(raw_allocations, list):
        raise ValueError("pilot manifest allocations must be a list")
    selected: dict[str, list[str]] = {}
    for raw, allocation in zip(raw_allocations, study.benchmarks, strict=True):
        if not isinstance(raw, dict) or raw.get("allocation_id") != allocation.id:
            raise ValueError("pilot manifest allocation order does not match the protocol")
        ids = raw.get("selected_ids")
        if (
            not isinstance(ids, list)
            or len(ids) != allocation.pilot_samples
            or not all(isinstance(sample_id, str) and sample_id for sample_id in ids)
            or len(ids) != len(set(ids))
        ):
            raise ValueError(f"pilot manifest allocation {allocation.id} has invalid IDs")
        selected[allocation.id] = ids
    if len(raw_allocations) != len(study.benchmarks):
        raise ValueError("pilot manifest allocation count does not match the protocol")
    return actual, selected


def _receipt_identity(
    receipt: JsonObject,
    *,
    study: StudyProtocol,
    manifest_sha256: str,
    model: Any,
    label: str,
) -> None:
    expected = {
        "schema_version": "1",
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "manifest_sha256": manifest_sha256,
        "model_id": model.id,
        "model_source": model.source,
        "model_revision": model.checkpoint_revision,
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ValueError(f"{label} receipt identity does not match the pilot")


def _record_ids(receipt: JsonObject, label: str) -> list[str]:
    records = receipt.get("scored_results")
    if not isinstance(records, list) or not all(isinstance(record, dict) for record in records):
        raise ValueError(f"{label}.scored_results must be a list of objects")
    ids = [record.get("canonical_id") for record in records]
    if not all(isinstance(sample_id, str) and sample_id for sample_id in ids):
        raise ValueError(f"{label} contains an invalid canonical ID")
    return [str(sample_id) for sample_id in ids]


def _agentic_evidence(
    *,
    study: StudyProtocol,
    manifest_sha256: str,
    selected: Mapping[str, list[str]],
    result_root: Path,
    tau_receipt_variant: str,
    incomplete_tau_runtime_models: frozenset[str],
) -> tuple[dict[str, JsonObject], JsonObject, JsonObject, JsonObject]:
    models: dict[str, JsonObject] = {}
    artifact_hashes: JsonObject = {}
    tau_amendment: JsonObject | None = None
    tau_runner_exceptions = 0
    terminal_timeouts = 0
    for model in study.models:
        prefix = MODEL_FILES[model.id]
        paths = {
            lane: result_root
            / f"{prefix}-pilot-{'tau-local' if lane == 'tau' and tau_receipt_variant == 'local-amended' else lane}-receipt.json"
            for lane in AGENTIC_ALLOCATIONS
        }
        receipts = {lane: _json(path, f"{model.id} {lane}") for lane, path in paths.items()}
        for lane, receipt in receipts.items():
            _receipt_identity(
                receipt,
                study=study,
                manifest_sha256=manifest_sha256,
                model=model,
                label=f"{model.id} {lane}",
            )
        amendment = receipts["tau"].get("protocol_amendment")
        if tau_receipt_variant == "local-amended":
            if not isinstance(amendment, dict) or not amendment:
                raise ValueError(f"{model.id} amended Tau receipt lacks protocol_amendment")
            if tau_amendment is None:
                tau_amendment = amendment
            elif amendment != tau_amendment:
                raise ValueError("amended Tau receipts do not share one protocol amendment")
        elif amendment is not None:
            raise ValueError(f"{model.id} default Tau receipt unexpectedly declares an amendment")
        bfcl_ids = receipts["bfcl"].get("scored_ids")
        if bfcl_ids != selected[AGENTIC_ALLOCATIONS["bfcl"]]:
            raise ValueError(f"{model.id} BFCL receipt does not match selected pilot IDs")
        for lane in ("tau", "terminal"):
            if (
                _record_ids(receipts[lane], f"{model.id} {lane}")
                != selected[AGENTIC_ALLOCATIONS[lane]]
            ):
                raise ValueError(f"{model.id} {lane} receipt does not match selected pilot IDs")
            if receipts[lane].get("scored_samples") != len(selected[AGENTIC_ALLOCATIONS[lane]]):
                raise ValueError(f"{model.id} {lane} scored sample count does not match the pilot")
        bfcl_seconds = _number(
            receipts["bfcl"].get("generation_seconds"),
            f"{model.id}.bfcl.generation_seconds",
        ) + _number(
            receipts["bfcl"].get("evaluation_seconds"),
            f"{model.id}.bfcl.evaluation_seconds",
        )
        tau_seconds = _number(
            receipts["tau"].get("execution_seconds"),
            f"{model.id}.tau.execution_seconds",
        )
        terminal_seconds = _number(
            receipts["terminal"].get("execution_seconds"),
            f"{model.id}.terminal.execution_seconds",
        )
        lane_seconds = {
            "bfcl-v4-agentic": bfcl_seconds,
            "tau3-bench": tau_seconds,
            "terminal-bench-2.1": terminal_seconds,
        }
        tau_terminations = receipts["tau"].get("termination_counts")
        terminal_exceptions = receipts["terminal"].get("exception_counts")
        if not isinstance(tau_terminations, dict):
            raise ValueError(f"{model.id}.tau.termination_counts must be an object")
        if not isinstance(terminal_exceptions, dict):
            raise ValueError(f"{model.id}.terminal.exception_counts must be an object")
        tau_runner_exceptions += _integer(
            tau_terminations.get("runner_error", 0), f"{model.id}.tau.runner_error"
        )
        terminal_timeouts += _integer(
            terminal_exceptions.get("AgentTimeoutError", 0),
            f"{model.id}.terminal.AgentTimeoutError",
        )
        estimated_full = sum(
            seconds
            * next(item.full_samples for item in study.benchmarks if item.id == allocation_id)
            / next(item.pilot_samples for item in study.benchmarks if item.id == allocation_id)
            for allocation_id, seconds in lane_seconds.items()
        )
        runtime_accounting_complete = model.id not in incomplete_tau_runtime_models
        models[model.id] = {
            "pilot_seconds": sum(lane_seconds.values()),
            "pilot_gpu_hours": sum(lane_seconds.values()) / 3600.0,
            "estimated_full_seconds": estimated_full if runtime_accounting_complete else None,
            "estimated_full_gpu_hours": (
                estimated_full / 3600.0 if runtime_accounting_complete else None
            ),
            "estimated_full_seconds_recorded_lower_bound": (
                estimated_full if not runtime_accounting_complete else None
            ),
            "lanes": {
                "bfcl-v4-agentic": {
                    "selected_samples": len(bfcl_ids),
                    "runner_cases_including_dependencies": receipts["bfcl"].get(
                        "runner_cases_including_dependencies"
                    ),
                    "generation_seconds": receipts["bfcl"]["generation_seconds"],
                    "official_evaluation_seconds": receipts["bfcl"]["evaluation_seconds"],
                },
                "tau3-bench": {
                    "selected_samples": len(selected["tau3-bench"]),
                    "execution_seconds": tau_seconds,
                    "runtime_accounting_complete": runtime_accounting_complete,
                    "reward_count": receipts["tau"].get("reward_count"),
                    "termination_counts": tau_terminations,
                },
                "terminal-bench-2.1": {
                    "selected_samples": len(selected["terminal-bench-2.1"]),
                    "execution_seconds": terminal_seconds,
                    "primary_reward_count": receipts["terminal"].get("primary_reward_count"),
                    "exception_counts": terminal_exceptions,
                },
            },
        }
        artifact_hashes[model.id] = {
            f"{lane}_receipt_sha256": _sha256(path) for lane, path in paths.items()
        }
    gate = {
        "decision": (
            "no-go"
            if tau_runner_exceptions or terminal_timeouts or incomplete_tau_runtime_models
            else "go"
        ),
        "tau_runner_exceptions": tau_runner_exceptions,
        "terminal_agent_timeouts": terminal_timeouts,
        "incomplete_tau_runtime_models": sorted(incomplete_tau_runtime_models),
        "blockers": [
            message
            for count, message in (
                (
                    tau_runner_exceptions,
                    "Repair and replay Tau runner exceptions for every model in affected paired blocks.",
                ),
                (
                    terminal_timeouts,
                    "Repair Terminal-Bench execution and replay the complete paired pilot lane.",
                ),
                (
                    len(incomplete_tau_runtime_models),
                    "Reconstruct complete Tau runtime accounting before forecasting expansion cost.",
                ),
            )
            if count
        ],
    }
    amendments = {"tau3-bench": tau_amendment} if tau_amendment is not None else {}
    return models, artifact_hashes, amendments, gate


def _judge_evidence(
    *,
    study: StudyProtocol,
    manifest_sha256: str,
    selected: Mapping[str, list[str]],
    bundle: JsonObject,
) -> JsonObject:
    expected_identity = {
        "schema_version": "2",
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "manifest_sha256": manifest_sha256,
        "cohort": "pilot",
    }
    if any(bundle.get(key) != value for key, value in expected_identity.items()):
        raise ValueError("judge bundle identity does not match the pilot")
    judge_plan_sha256 = bundle.get("judge_plan_sha256")
    if (
        not isinstance(judge_plan_sha256, str)
        or len(judge_plan_sha256) != 64
        or any(character not in "0123456789abcdef" for character in judge_plan_sha256)
    ):
        raise ValueError("judge bundle must identify its locked judge plan")
    judges = bundle.get("judges")
    if not isinstance(judges, dict):
        raise ValueError("judge bundle must declare primary, secondary, and adjudicator snapshots")
    identities: list[tuple[str, str, str]] = []
    public_judges: JsonObject = {}
    for role in ("primary", "secondary", "adjudicator"):
        judge = judges.get(role)
        if not isinstance(judge, dict):
            raise ValueError(f"judge {role} identity must be an object")
        identity = tuple(judge.get(key) for key in ("provider", "model", "snapshot"))
        if not all(isinstance(value, str) and value for value in identity):
            raise ValueError(f"judge {role} identity must be an immutable snapshot")
        identities.append(identity)  # type: ignore[arg-type]
        public_judges[role] = dict(zip(("provider", "model", "snapshot"), identity, strict=True))
    if identities[0] == identities[1]:
        raise ValueError("primary and secondary judges must be distinct")
    if identities[0] == identities[2]:
        raise ValueError("primary judge and adjudicator must be distinct")
    target_names = {model.id for model in study.models} | {model.source for model in study.models}
    if any(value in target_names for identity in identities for value in identity):
        raise ValueError("target study models may not judge their own outputs")
    expected_controls = {
        "blinded_model_labels": True,
        "order_randomized": True,
        "target_models_may_not_judge": True,
        "first_pass_judges_per_outcome": 2,
        "first_pass_independent": True,
        "disagreement_policy": "adjudicate-all",
    }
    controls = bundle.get("controls")
    if not isinstance(controls, dict) or any(
        controls.get(key) != value for key, value in expected_controls.items()
    ):
        raise ValueError("judge controls do not match the preregistration")
    outcomes = bundle.get("outcomes")
    if not isinstance(outcomes, list) or not all(isinstance(item, dict) for item in outcomes):
        raise ValueError("judge outcomes must be a list of objects")
    expected = {
        (model.id, allocation.id, sample_id)
        for model in study.models
        for allocation in study.benchmarks
        if allocation.id in JUDGED_ALLOCATIONS
        for sample_id in selected[allocation.id]
    }
    found: set[tuple[str, str, str]] = set()
    disagreements = 0
    unresolved = 0
    for outcome in outcomes:
        identity = (
            outcome.get("model_id"),
            outcome.get("allocation_id"),
            outcome.get("sample_id"),
        )
        if identity not in expected or identity in found:
            raise ValueError("judge outcomes contain an unexpected or duplicate identity")
        found.add(identity)  # type: ignore[arg-type]
        disagreed = outcome.get("judges_disagreed") is True
        if disagreed:
            disagreements += 1
            if outcome.get("adjudicated") is not True:
                raise ValueError("every judge disagreement must be adjudicated")
        status = outcome.get("status")
        value = outcome.get("value")
        if status == "observed":
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 <= float(value) <= 1
            ):
                raise ValueError("observed judge outcomes require a value within [0, 1]")
        elif status == "model-timeout":
            if value != 0:
                raise ValueError("model-timeout judge outcomes must have value zero")
        elif status in {"infrastructure-error", "judge-parse-failure"}:
            if value is not None:
                raise ValueError("excluded or unresolved judge outcomes must have null values")
        else:
            raise ValueError("judge outcome has an unsupported status")
        if status == "judge-parse-failure":
            unresolved += 1
    if found != expected:
        raise ValueError("judge outcomes do not exactly cover the pilot judged matrix")
    runtime = bundle.get("runtime")
    if not isinstance(runtime, dict):
        raise ValueError("judge bundle must include content-free runtime accounting")
    primary_calls = _integer(runtime.get("primary_calls"), "judge.runtime.primary_calls")
    secondary_calls = _integer(runtime.get("secondary_calls"), "judge.runtime.secondary_calls")
    adjudicator_calls = _integer(
        runtime.get("adjudicator_calls"), "judge.runtime.adjudicator_calls"
    )
    retries = _integer(runtime.get("retries"), "judge.runtime.retries")
    primary_seconds = _number(runtime.get("primary_seconds"), "judge.runtime.primary_seconds")
    secondary_seconds = _number(runtime.get("secondary_seconds"), "judge.runtime.secondary_seconds")
    adjudication_seconds = _number(
        runtime.get("adjudication_seconds"), "judge.runtime.adjudication_seconds"
    )
    if (
        primary_calls < len(outcomes)
        or secondary_calls < len(outcomes)
        or adjudicator_calls < disagreements
    ):
        raise ValueError("judge call accounting is smaller than the outcome/disagreement matrix")
    if primary_calls + secondary_calls + adjudicator_calls != (
        2 * len(outcomes) + disagreements + retries
    ):
        raise ValueError("judge calls do not reconcile with outcomes, adjudications, and retries")
    pilot_judged = sum(
        allocation.pilot_samples
        for allocation in study.benchmarks
        if allocation.id in JUDGED_ALLOCATIONS
    )
    full_judged = sum(
        allocation.full_samples
        for allocation in study.benchmarks
        if allocation.id in JUDGED_ALLOCATIONS
    )
    total_seconds = primary_seconds + secondary_seconds + adjudication_seconds
    return {
        "judge_plan_sha256": judge_plan_sha256,
        "judges": public_judges,
        "outcomes": len(outcomes),
        "disagreements": disagreements,
        "unresolved_parse_failures": unresolved,
        "primary_calls": primary_calls,
        "secondary_calls": secondary_calls,
        "adjudicator_calls": adjudicator_calls,
        "retries": retries,
        "primary_seconds": primary_seconds,
        "secondary_seconds": secondary_seconds,
        "adjudication_seconds": adjudication_seconds,
        "pilot_seconds": total_seconds,
        "estimated_full_seconds": total_seconds * full_judged / pilot_judged,
        "forecast_method": "total judge wall time scaled by full/pilot judged outcome ratio",
    }


def _code_revision() -> str:
    root = Path(__file__).resolve().parents[1]
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if status.stdout:
        raise RuntimeError("pilot summary checkout must be clean")
    revision = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    if len(revision) != 40:
        raise RuntimeError("pilot summary checkout did not report a full Git revision")
    return revision


def build_summary(
    *,
    study: StudyProtocol,
    manifest: JsonObject,
    direct: JsonObject,
    result_root: Path,
    judge_bundle: JsonObject,
    judge_bundle_sha256: str,
    code_revision: str,
    tau_receipt_variant: str = "default",
    incomplete_tau_runtime_models: frozenset[str] = frozenset(),
) -> JsonObject:
    manifest_sha256, selected = _manifest(study, manifest)
    model_ids = [model.id for model in study.models]
    expected_direct = {
        "schema_version": "2",
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "manifest_sha256": manifest_sha256,
        "study_seed": study.seed,
        "status": "direct-pilot-pipeline-validated-agentic-and-judged-lanes-pending",
    }
    if any(direct.get(key) != value for key, value in expected_direct.items()):
        raise ValueError("direct pilot summary identity or status does not match")
    direct_models = direct.get("models")
    if not isinstance(direct_models, dict) or set(direct_models) != set(model_ids):
        raise ValueError("direct pilot summary model set does not match the protocol")
    unknown_incomplete = incomplete_tau_runtime_models - set(model_ids)
    if unknown_incomplete:
        raise ValueError(f"unknown incomplete Tau runtime models: {sorted(unknown_incomplete)}")
    for model_id, model in direct_models.items():
        if not isinstance(model, dict):
            raise ValueError(f"direct pilot model {model_id} must be an object")
        parallelism = model.get("parallelism")
        if not isinstance(parallelism, dict):
            raise ValueError(f"direct pilot model {model_id} lacks parallelism evidence")
        binding, _ = validated_parallelism_binding(parallelism)
        if binding.profile.id != study.parallelism_profile.id:
            raise ValueError(f"direct pilot model {model_id} profile does not match protocol")
        _number(model.get("total_generation_seconds"), f"{model_id}.total_generation_seconds")
        _number(
            model.get("total_initialization_seconds"),
            f"{model_id}.total_initialization_seconds",
        )
        _number(
            model.get("total_deterministic_scoring_seconds"),
            f"{model_id}.total_deterministic_scoring_seconds",
        )
        _number(
            model.get("estimated_full_direct_seconds_from_scratch"),
            f"{model_id}.estimated_full_direct_seconds_from_scratch",
        )
    agentic, agentic_hashes, amendments, scale_gate = _agentic_evidence(
        study=study,
        manifest_sha256=manifest_sha256,
        selected=selected,
        result_root=result_root,
        tau_receipt_variant=tau_receipt_variant,
        incomplete_tau_runtime_models=incomplete_tau_runtime_models,
    )
    judge = _judge_evidence(
        study=study,
        manifest_sha256=manifest_sha256,
        selected=selected,
        bundle=judge_bundle,
    )
    models: JsonObject = {}
    for model_id in model_ids:
        models[model_id] = {
            **direct_models[model_id],
            "agentic": agentic[model_id],
            "pilot_gpu_hours": (
                float(direct_models[model_id]["total_initialization_seconds"])
                + float(direct_models[model_id]["total_generation_seconds"])
                + float(agentic[model_id]["pilot_seconds"])
            )
            / 3600.0,
            "estimated_full_gpu_hours": (
                (
                    float(direct_models[model_id]["estimated_full_direct_seconds_from_scratch"])
                    + float(agentic[model_id]["estimated_full_seconds"])
                )
                / 3600.0
                if agentic[model_id]["estimated_full_seconds"] is not None
                else None
            ),
        }
    totals = {
        "direct_initialization_seconds": sum(
            float(model["total_initialization_seconds"]) for model in direct_models.values()
        ),
        "direct_generation_seconds": sum(
            float(model["total_generation_seconds"]) for model in direct_models.values()
        ),
        "deterministic_scoring_seconds_including_repeat": sum(
            float(model["total_deterministic_scoring_seconds"]) for model in direct_models.values()
        ),
        "agentic_seconds": sum(float(model["pilot_seconds"]) for model in agentic.values()),
        "judge_seconds": float(judge["pilot_seconds"]),
    }
    return {
        "schema_version": "1",
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "manifest_sha256": manifest_sha256,
        "study_seed": study.seed,
        "status": (
            "complete" if scale_gate["decision"] == "go" else "evidence-complete-scale-no-go"
        ),
        "interpretation": "Pilot metrics are calibration evidence, not confirmatory results. Expansion remains governed by scale_gate.",
        "summary_code_revision": code_revision,
        "pilot_samples_per_model": study.pilot_samples_per_model,
        "full_samples_per_model": study.full_samples_per_model,
        "models": models,
        "judge": judge,
        "protocol_amendments": amendments,
        "scale_gate": scale_gate,
        "runtime_totals": totals,
        "artifact_sha256": {
            "judge_bundle": judge_bundle_sha256,
            "agentic_receipts": agentic_hashes,
        },
        "forecast_limits": [
            "direct first-turn and MT-Bench turn-two times are scaled separately",
            "agentic lanes are scaled by each allocation full/pilot sample ratio",
            "execution_seconds are receipt-accounted time; models marked runtime_accounting_complete=false are lower bounds after resume",
            "judge time is scaled by the aggregate judged-outcome ratio",
            "forecasts exclude queue delay and are not throughput guarantees",
        ],
    }


def _write(path: Path, payload: JsonObject) -> str:
    if path.exists():
        raise ValueError(f"refusing to overwrite complete pilot summary: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o644)
    return _sha256(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--direct-summary", type=Path, required=True)
    parser.add_argument("--result-root", type=Path, required=True)
    parser.add_argument("--judge-outcomes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--tau-receipt-variant",
        choices=("default", "local-amended"),
        default="default",
        help="Select immutable default or explicitly amended local-simulator Tau receipts.",
    )
    parser.add_argument(
        "--incomplete-tau-runtime-model",
        action="append",
        default=[],
        help="Model ID whose Tau receipt time covers only a resumed segment (repeatable).",
    )
    args = parser.parse_args(argv)
    if platform.node() != "basilisk":
        raise RuntimeError("complete Qwen3.8 pilot accounting requires host basilisk")
    for path in (
        args.manifest,
        args.direct_summary,
        args.result_root,
        args.judge_outcomes,
        args.output,
    ):
        if not path.is_absolute() or not path.is_relative_to(PRIVATE_ROOT):
            raise ValueError(f"pilot artifact path is outside {PRIVATE_ROOT}: {path}")
    if not args.output.is_relative_to(PUBLIC_ROOT):
        raise ValueError(f"complete pilot summary output must be below {PUBLIC_ROOT}")
    study = StudyProtocol.from_yaml(args.protocol, validate_registry=False)
    summary = build_summary(
        study=study,
        manifest=_json(args.manifest, "pilot manifest"),
        direct=_json(args.direct_summary, "direct pilot summary"),
        result_root=args.result_root,
        judge_bundle=_json(args.judge_outcomes, "pilot judge bundle"),
        judge_bundle_sha256=_sha256(args.judge_outcomes),
        code_revision=_code_revision(),
        tau_receipt_variant=args.tau_receipt_variant,
        incomplete_tau_runtime_models=frozenset(args.incomplete_tau_runtime_model),
    )
    output_sha256 = _write(args.output, summary)
    print(
        json.dumps(
            {
                "study_id": study.id,
                "status": summary["status"],
                "output": str(args.output),
                "output_sha256": output_sha256,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
