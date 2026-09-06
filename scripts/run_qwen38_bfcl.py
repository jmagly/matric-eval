#!/usr/bin/env python3
"""Run and officially score a manifest-locked BFCL agentic cohort."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Sequence

import yaml

BFCL_PACKAGE_VERSION = "2026.3.23"
BFCL_SOURCE_REVISION = "6ea57973c7a6097fd7c5915698c54c17c5b1b6c8"
PRIVATE_ROOT = Path("/srv/matric-eval/results/qwen38-obliteration-2026-09")
JsonObject = dict[str, Any]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path, label: str) -> JsonObject:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return payload


def _git_revision(checkout: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    revision = result.stdout.strip()
    if len(revision) != 40:
        raise RuntimeError(f"{checkout} did not report a full Git revision")
    return revision


def _generation_seed(root_seed: int, sample_id: str) -> int:
    payload = f"{root_seed}\0bfcl-v4-agentic\0{sample_id}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")


def _load_protocol(path: Path, model_id: str) -> tuple[JsonObject, JsonObject, JsonObject]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("study"), dict):
        raise ValueError("protocol must contain a study object")
    study: JsonObject = payload["study"]
    models = study.get("models")
    if not isinstance(models, list):
        raise ValueError("protocol models must be a list")
    model = next(
        (
            candidate
            for candidate in models
            if isinstance(candidate, dict) and candidate.get("id") == model_id
        ),
        None,
    )
    if model is None:
        raise ValueError(f"unknown study model id: {model_id}")
    runtime = model.get("runtime")
    if not isinstance(runtime, dict) or runtime.get("execution_mode") != "offline-batch":
        raise ValueError("BFCL target must use the primary offline-batch runtime contract")
    sampler = runtime.get("sampler")
    if not isinstance(sampler, dict) or sampler.get("seed") != study.get("seed"):
        raise ValueError("model sampler must use the shared study seed")
    benchmarks = study.get("benchmarks")
    bfcl = (
        next(
            (
                candidate
                for candidate in benchmarks
                if isinstance(candidate, dict) and candidate.get("id") == "bfcl-v4-agentic"
            ),
            None,
        )
        if isinstance(benchmarks, list)
        else None
    )
    if bfcl is None or bfcl.get("dataset_revision") != BFCL_SOURCE_REVISION:
        raise ValueError("protocol does not contain the pinned BFCL V4 allocation")
    return study, model, sampler


def _verify_manifest(
    manifest_path: Path,
    summary: JsonObject,
    scored_ids: list[str],
    study_id: str,
) -> str:
    manifest = _load_object(manifest_path, "study manifest")
    canonical = dict(manifest)
    declared_hash = canonical.pop("manifest_sha256", None)
    actual_hash = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if declared_hash != actual_hash or summary.get("manifest_sha256") != actual_hash:
        raise ValueError("study manifest hash does not match the agentic input summary")
    cohort = manifest.get("cohort")
    if (
        manifest.get("study_id") != study_id
        or cohort not in {"pilot", "full"}
        or summary.get("cohort") != cohort
    ):
        raise ValueError("BFCL runner requires the declared pilot or full manifest")
    allocations = manifest.get("allocations")
    selected = (
        next(
            (
                allocation.get("selected_ids")
                for allocation in allocations
                if isinstance(allocation, dict)
                and allocation.get("allocation_id") == "bfcl-v4-agentic"
            ),
            None,
        )
        if isinstance(allocations, list)
        else None
    )
    if selected != scored_ids:
        raise ValueError("BFCL scored IDs do not exactly match the study manifest")
    return actual_hash


def _validate_endpoint(endpoint: str, model_id: str, model_path: Path) -> None:
    if not endpoint.startswith("http://127.0.0.1:") or not endpoint.endswith("/v1"):
        raise ValueError("BFCL endpoint must be a localhost HTTP /v1 endpoint")
    with urllib.request.urlopen(f"{endpoint}/models", timeout=10) as response:
        payload = json.loads(response.read(1024 * 1024))
    data = payload.get("data") if isinstance(payload, dict) else None
    served = (
        {
            item.get("id")
            for item in data
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        if isinstance(data, list)
        else set()
    )
    if model_id not in served or str(model_path) not in served:
        raise RuntimeError("study server does not advertise both required BFCL model names")


def _register_study_model(
    registry_name: str,
    model_id: str,
    sampler: JsonObject,
    root_seed: int,
    context_limit: int,
) -> None:
    from bfcl_eval.constants.model_config import MODEL_CONFIG_MAPPING, ModelConfig
    from bfcl_eval.model_handler.local_inference.qwen_fc import QwenFCHandler

    def nested_override(method: Any) -> Any:
        """Mark nested overrides for BFCL's metaclass without frame introspection."""
        method.__override__ = True
        return method

    class StudyQwenFCHandler(QwenFCHandler):
        """Qwen handler that supplies every preregistered sampling control."""

        @nested_override
        def inference(
            self,
            test_entry: dict[str, Any],
            include_input_log: bool,
            exclude_state_log: bool,
        ) -> Any:
            sample_id = test_entry.get("id")
            if not isinstance(sample_id, str) or not sample_id:
                raise ValueError("BFCL test entry is missing its canonical ID")
            self._study_sample_id = sample_id
            return super().inference(test_entry, include_input_log, exclude_state_log)

        @nested_override
        def _query_prompting(self, inference_data: dict[str, Any]) -> tuple[Any, float]:
            sample_id = getattr(self, "_study_sample_id", None)
            if not isinstance(sample_id, str):
                raise RuntimeError("BFCL query is missing its study sample ID")
            formatted_prompt = self._format_prompt(
                inference_data["message"], inference_data["function"]
            )
            inference_data["inference_input_log"] = {"formatted_prompt": formatted_prompt}
            input_tokens = len(self.tokenizer.tokenize(formatted_prompt))
            effective_context_limit = min(int(self.max_context_length), context_limit)
            remaining = max(1, effective_context_limit - input_tokens - 2)
            max_tokens = min(int(sampler["max_tokens"]), remaining)
            extra_body = {
                "top_k": int(sampler["top_k"]),
                "min_p": float(sampler["min_p"]),
                "repetition_penalty": float(sampler["repetition_penalty"]),
            }
            if hasattr(self, "stop_token_ids"):
                extra_body["stop_token_ids"] = self.stop_token_ids
            if hasattr(self, "skip_special_tokens"):
                extra_body["skip_special_tokens"] = self.skip_special_tokens
            started = time.time()
            response = self.client.completions.create(
                model=self.model_path_or_id,
                prompt=formatted_prompt,
                temperature=float(sampler["temperature"]),
                top_p=float(sampler["top_p"]),
                presence_penalty=float(sampler["presence_penalty"]),
                max_tokens=max_tokens,
                seed=_generation_seed(root_seed, sample_id),
                extra_body=extra_body,
                timeout=72000,
            )
            return response, time.time() - started

    MODEL_CONFIG_MAPPING[registry_name] = ModelConfig(
        model_name=model_id,
        display_name=registry_name,
        url="local-qualified-checkpoint",
        org="matric-eval-study",
        license="see-model-card",
        model_handler=StudyQwenFCHandler,
        input_price=None,
        output_price=None,
        is_fc_model=True,
        underscore_to_dot=False,
    )


def _file_manifest(root: Path) -> list[JsonObject]:
    return [
        {
            "path": str(path.relative_to(root)),
            "size": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def _seal_private_tree(root: Path) -> None:
    """Make runner-created evidence private without following links."""
    for path in [root, *sorted(root.rglob("*"))]:
        if path.is_symlink():
            raise RuntimeError(f"private evidence tree contains a symbolic link: {path}")
        path.chmod(0o750 if path.is_dir() else 0o600)


def _collect_top_level_ids(root: Path) -> set[str]:
    found: set[str] = set()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in {".json", ".jsonl"}:
            continue
        text = path.read_text(encoding="utf-8")
        try:
            payloads: list[Any] = [json.loads(text)]
        except json.JSONDecodeError:
            payloads = [json.loads(line) for line in text.splitlines() if line.strip()]
        for payload in payloads:
            records = payload if isinstance(payload, list) else [payload]
            for record in records:
                if isinstance(record, dict) and isinstance(record.get("id"), str):
                    found.add(record["id"])
    return found


def run_bfcl(args: argparse.Namespace) -> JsonObject:
    if platform.node() != "basilisk":
        raise RuntimeError("BFCL study execution requires host basilisk")
    for path in (args.result_dir, args.score_dir, args.receipt):
        if not path.is_absolute() or not path.is_relative_to(PRIVATE_ROOT):
            raise ValueError(f"BFCL private artifact path is outside {PRIVATE_ROOT}: {path}")
        if path.exists():
            raise ValueError(f"refusing to overwrite BFCL evidence: {path}")
    if importlib.metadata.version("bfcl-eval") != BFCL_PACKAGE_VERSION:
        raise RuntimeError("installed BFCL runner version does not match the study contract")
    if _git_revision(args.bfcl_checkout) != BFCL_SOURCE_REVISION:
        raise RuntimeError("BFCL source checkout revision does not match the study contract")

    study, model, sampler = _load_protocol(args.protocol, args.model_id)
    summary = _load_object(args.inputs_summary, "agentic input summary")
    runner_ids = _load_object(args.runner_ids, "BFCL runner IDs")
    scored_payload = json.loads(args.scored_ids.read_text(encoding="utf-8"))
    if not isinstance(scored_payload, list) or not all(
        isinstance(value, str) for value in scored_payload
    ):
        raise ValueError("BFCL scored IDs must be a JSON list of strings")
    scored_ids = [str(value) for value in scored_payload]
    artifacts = summary.get("artifacts")
    expected_runner_hash = (
        artifacts.get("bfcl-runner-ids.json") if isinstance(artifacts, dict) else None
    )
    expected_scored_hash = (
        artifacts.get("bfcl-scored-ids.json") if isinstance(artifacts, dict) else None
    )
    if _sha256_file(args.runner_ids) != expected_runner_hash:
        raise ValueError("BFCL runner ID hash does not match the agentic input summary")
    if _sha256_file(args.scored_ids) != expected_scored_hash:
        raise ValueError("BFCL scored ID hash does not match the agentic input summary")
    manifest_sha256 = _verify_manifest(args.manifest, summary, scored_ids, str(study["id"]))
    server_receipt = _load_object(args.server_receipt, "model server receipt")
    if (
        server_receipt.get("study_id") != study["id"]
        or server_receipt.get("model_id") != args.model_id
        or server_receipt.get("protocol_sha256") != summary.get("protocol_sha256")
    ):
        raise ValueError("model server receipt does not match the BFCL study run")
    _validate_endpoint(args.endpoint, args.model_id, args.model_path)

    categories = list(runner_ids)
    if not categories or not all(isinstance(value, list) for value in runner_ids.values()):
        raise ValueError("BFCL runner IDs must map categories to ID lists")
    runner_case_count = sum(len(value) for value in runner_ids.values())
    if runner_case_count != summary.get("bfcl_runner_cases_including_dependencies"):
        raise ValueError("BFCL runner dependency count does not match the agentic input summary")

    registry_name = args.model_id
    runtime = model["runtime"]
    _register_study_model(
        registry_name,
        args.model_id,
        sampler,
        int(study["seed"]),
        int(runtime["context_limit"]),
    )
    from bfcl_eval import _llm_response_generation as generation
    from bfcl_eval.eval_checker import eval_runner

    generation.TEST_IDS_TO_GENERATE_PATH = args.runner_ids
    os.environ["REMOTE_OPENAI_BASE_URL"] = args.endpoint
    os.environ["REMOTE_OPENAI_API_KEY"] = "EMPTY"
    os.environ["REMOTE_OPENAI_TOKENIZER_PATH"] = str(args.model_path)
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"

    generation_started = time.time()
    generation.main(
        SimpleNamespace(
            model=[registry_name],
            test_category=["agentic"],
            temperature=float(sampler["temperature"]),
            include_input_log=False,
            exclude_state_log=False,
            num_threads=1,
            num_gpus=1,
            backend="vllm",
            gpu_memory_utilization=0.9,
            result_dir=args.result_dir,
            run_ids=True,
            allow_overwrite=False,
            skip_server_setup=True,
            local_model_path=str(args.model_path),
            lora_modules=None,
            enable_lora=False,
            max_lora_rank=None,
        )
    )
    generation_seconds = time.time() - generation_started
    evaluation_started = time.time()
    eval_runner.main(
        [registry_name],
        categories,
        args.result_dir,
        args.score_dir,
        partial_eval=True,
    )
    evaluation_seconds = time.time() - evaluation_started
    _seal_private_tree(args.result_dir)
    _seal_private_tree(args.score_dir)

    found_ids = _collect_top_level_ids(args.result_dir)
    missing = sorted(set(scored_ids) - found_ids)
    if missing:
        raise RuntimeError(f"BFCL result artifacts omit {len(missing)} scored IDs")
    receipt: JsonObject = {
        "schema_version": "1",
        "study_id": study["id"],
        "protocol_sha256": summary["protocol_sha256"],
        "manifest_sha256": manifest_sha256,
        "model_id": args.model_id,
        "model_source": model["source"],
        "model_revision": model["checkpoint_revision"],
        "server_receipt_sha256": _sha256_file(args.server_receipt),
        "runner": {
            "package": "bfcl-eval",
            "version": BFCL_PACKAGE_VERSION,
            "source_revision": BFCL_SOURCE_REVISION,
            "python": platform.python_version(),
            "matric_eval_revision": _git_revision(Path(__file__).resolve().parents[1]),
        },
        "sampler": sampler,
        "runner_cases_including_dependencies": runner_case_count,
        "scored_ids": scored_ids,
        "scored_generation_seeds": {
            sample_id: _generation_seed(int(study["seed"]), sample_id) for sample_id in scored_ids
        },
        "generation_seconds": generation_seconds,
        "evaluation_seconds": evaluation_seconds,
        "result_files": _file_manifest(args.result_dir),
        "score_files": _file_manifest(args.score_dir),
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    args.receipt.chmod(0o600)
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--server-receipt", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:18083/v1")
    parser.add_argument("--bfcl-checkout", type=Path, required=True)
    parser.add_argument("--inputs-summary", type=Path, required=True)
    parser.add_argument("--runner-ids", type=Path, required=True)
    parser.add_argument("--scored-ids", type=Path, required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--score-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    receipt = run_bfcl(build_parser().parse_args(argv))
    print(
        json.dumps(
            {
                "study_id": receipt["study_id"],
                "model_id": receipt["model_id"],
                "runner_cases_including_dependencies": receipt[
                    "runner_cases_including_dependencies"
                ],
                "scored_samples": len(receipt["scored_ids"]),
                "generation_seconds": receipt["generation_seconds"],
                "evaluation_seconds": receipt["evaluation_seconds"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
