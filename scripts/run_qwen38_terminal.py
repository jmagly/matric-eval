#!/usr/bin/env python3
"""Run and officially score a manifest-locked Terminal-Bench 2.1 cohort."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import yaml

HARBOR_PACKAGE_VERSION = "0.22.0"
TERMINAL_SOURCE_REVISION = "5c8eadf1f393183288fa08b8f73ca9a469cc5e00"
CONTEXT_SAFETY_MARGIN_TOKENS = 32
PRIVATE_ROOT = Path("/srv/matric-eval/results/qwen38-obliteration-2026-09")
DOCKER_HOST = "unix:///run/matric-eval-docker.sock"
DOCKER_DATA_ROOT = "/srv/obliteratus/matric-eval/docker/data"
DEFAULT_DOCKER_CONFIG_ASSET = (
    Path(__file__).resolve().parents[1]
    / "studies/qwen38-obliteration-2026-09/host/matric-eval-docker-daemon.json"
)
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


def _require_clean_checkout(checkout: Path) -> None:
    status = subprocess.run(
        ["git", "-C", str(checkout), "status", "--porcelain=v1"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout
    if status:
        raise RuntimeError("Terminal-Bench source checkout must be clean")


def _validate_docker_config(payload: JsonObject) -> None:
    required = {
        "data-root": DOCKER_DATA_ROOT,
        "bridge": "none",
        "iptables": True,
        "ip-forward": True,
        "ip-masq": True,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise RuntimeError(f"isolated Docker configuration must set {key}={expected!r}")
    pools = payload.get("default-address-pools")
    if pools != [{"base": "10.241.0.0/16", "size": 24}]:
        raise RuntimeError("isolated Docker address pool does not match the study contract")


def _docker_evidence(config_path: Path, expected_path: Path) -> JsonObject:
    actual = subprocess.run(
        ["sudo", "-n", "cat", str(config_path)],
        check=True,
        capture_output=True,
        timeout=10,
    ).stdout
    try:
        payload = json.loads(actual)
    except json.JSONDecodeError as error:
        raise ValueError("isolated Docker daemon configuration is not JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("isolated Docker daemon configuration must be an object")
    expected_sha256 = _sha256_file(expected_path)
    actual_sha256 = hashlib.sha256(actual).hexdigest()
    if actual_sha256 != expected_sha256:
        raise RuntimeError("isolated Docker configuration differs from the retained asset")
    _validate_docker_config(payload)
    result = subprocess.run(
        ["docker", "--host", DOCKER_HOST, "info", "--format", "{{.DockerRootDir}}"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.stdout.strip() != DOCKER_DATA_ROOT:
        raise RuntimeError("Harbor Docker daemon does not use the model filesystem")
    return {
        "host": DOCKER_HOST,
        "data_root": DOCKER_DATA_ROOT,
        "configuration_sha256": actual_sha256,
        "network_pool": "10.241.0.0/16",
    }


def _generation_seed(root_seed: int, sample_id: str) -> int:
    payload = f"{root_seed}\0terminal-bench-2.1\0{sample_id}".encode()
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
        raise ValueError("Terminal-Bench target must use the primary runtime contract")
    sampler = runtime.get("sampler")
    if not isinstance(sampler, dict) or sampler.get("seed") != study.get("seed"):
        raise ValueError("model sampler must use the shared study seed")
    benchmarks = study.get("benchmarks")
    terminal = (
        next(
            (
                candidate
                for candidate in benchmarks
                if isinstance(candidate, dict) and candidate.get("id") == "terminal-bench-2.1"
            ),
            None,
        )
        if isinstance(benchmarks, list)
        else None
    )
    if terminal is None or terminal.get("dataset_revision") != TERMINAL_SOURCE_REVISION:
        raise ValueError("protocol does not contain the pinned Terminal-Bench allocation")
    if terminal.get("scoring_protocol") != "terminal-bench-2.1-official-container-grader":
        raise ValueError("protocol does not require the official container grader")
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
        raise ValueError("Terminal-Bench runner requires the declared pilot or full manifest")
    allocations = manifest.get("allocations")
    selected = (
        next(
            (
                allocation.get("selected_ids")
                for allocation in allocations
                if isinstance(allocation, dict)
                and allocation.get("allocation_id") == "terminal-bench-2.1"
            ),
            None,
        )
        if isinstance(allocations, list)
        else None
    )
    if selected != scored_ids:
        raise ValueError("Terminal-Bench scored IDs do not exactly match the study manifest")
    return actual_hash


def _validate_endpoint(endpoint: str, model_id: str, model_path: Path) -> None:
    if not endpoint.startswith("http://127.0.0.1:") or not endpoint.endswith("/v1"):
        raise ValueError("Terminal-Bench endpoint must be a localhost HTTP /v1 endpoint")
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
        raise RuntimeError(
            "study server does not advertise both required Terminal-Bench model names"
        )


def _validate_context_allocation(
    input_tokens: int,
    output_tokens: int,
    context_limit: int,
    safety_margin: int = CONTEXT_SAFETY_MARGIN_TOKENS,
) -> None:
    """Reject a declared request budget that overbooks the model context."""
    values = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "context_limit": context_limit,
        "safety_margin": safety_margin,
    }
    for label, value in values.items():
        if type(value) is not int or value < 1:
            raise ValueError(f"{label} must be a positive integer")
    if safety_margin < 32:
        raise ValueError("context safety margin must be at least 32 tokens")
    combined = input_tokens + output_tokens + safety_margin
    if combined > context_limit:
        raise ValueError(
            f"combined context budget {combined} exceeds context limit {context_limit}"
        )


def _context_budget(context_limit: int, output_tokens: int) -> JsonObject:
    """Reserve output and safety tokens before advertising the input limit."""
    if type(context_limit) is not int or context_limit < 1:
        raise ValueError("context_limit must be a positive integer")
    if type(output_tokens) is not int or output_tokens < 1:
        raise ValueError("output_tokens must be a positive integer")
    input_tokens = context_limit - output_tokens - CONTEXT_SAFETY_MARGIN_TOKENS
    _validate_context_allocation(input_tokens, output_tokens, context_limit)
    return {
        "max_context_tokens": context_limit,
        "max_input_tokens": input_tokens,
        "max_output_tokens": output_tokens,
        "safety_margin_tokens": CONTEXT_SAFETY_MARGIN_TOKENS,
    }


def _agent_kwargs(endpoint: str, sampler: JsonObject, seed: int, context_limit: int) -> JsonObject:
    context_budget = _context_budget(context_limit, sampler["max_tokens"])
    return {
        "api_base": endpoint,
        "temperature": float(sampler["temperature"]),
        "model_info": {
            "max_input_tokens": context_budget["max_input_tokens"],
            "max_output_tokens": context_budget["max_output_tokens"],
            "input_cost_per_token": 0.0,
            "output_cost_per_token": 0.0,
            "cache_creation_input_token_cost": 0.0,
            "cache_read_input_token_cost": 0.0,
        },
        "llm_kwargs": {"api_key": "EMPTY"},
        "llm_call_kwargs": {
            "top_p": float(sampler["top_p"]),
            "presence_penalty": float(sampler["presence_penalty"]),
            "max_tokens": context_budget["max_output_tokens"],
            "seed": seed,
            "extra_body": {
                "top_k": int(sampler["top_k"]),
                "min_p": float(sampler["min_p"]),
                "repetition_penalty": float(sampler["repetition_penalty"]),
                "chat_template_kwargs": {"enable_thinking": False},
            },
        },
    }


def _job_config(
    *,
    jobs_dir: Path,
    job_name: str,
    tasks_dir: Path,
    task_id: str,
    model_id: str,
    agent_kwargs: JsonObject,
) -> JsonObject:
    return {
        "job_name": job_name,
        "jobs_dir": str(jobs_dir),
        "n_attempts": 1,
        "n_concurrent_trials": 1,
        "quiet": True,
        "retry": {"max_retries": 0},
        "environment": {"type": "docker", "delete": True},
        "agents": [
            {
                "name": "terminus-2",
                "model_name": f"hosted_vllm/{model_id}",
                "n_concurrent": 1,
                "kwargs": agent_kwargs,
            }
        ],
        "datasets": [{"path": str(tasks_dir), "task_names": [task_id]}],
    }


def _private_path(path: Path, label: str, *, allow_existing: bool = False) -> None:
    if not path.is_absolute() or not path.is_relative_to(PRIVATE_ROOT):
        raise ValueError(f"{label} is outside {PRIVATE_ROOT}: {path}")
    if path.exists() and not allow_existing:
        raise ValueError(f"refusing to overwrite Terminal-Bench evidence: {path}")


def _result_name(sample_id: str) -> str:
    return "terminal-" + hashlib.sha256(sample_id.encode()).hexdigest()[:20]


def _write_private_json(path: Path, payload: Any) -> str:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)
    return _sha256_file(path)


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


def _parse_job_result(path: Path) -> tuple[JsonObject, JsonObject | None, str | None]:
    result = _load_object(path, "Harbor job result")
    trials = result.get("trial_results")
    if isinstance(trials, list):
        if len(trials) != 1 or not isinstance(trials[0], dict):
            raise RuntimeError("Harbor job result must contain exactly one official trial")
        trial: JsonObject = trials[0]
    else:
        # Harbor 0.22 writes a summary at <job>/result.json and the official
        # TrialResult at <job>/<trial>/result.json instead of embedding a
        # trial_results array in the summary. Keep support for the embedded
        # layout so retained evidence from either supported shape is readable.
        if result.get("n_total_trials") != 1:
            raise RuntimeError("Harbor job result must declare exactly one official trial")
        nested_results = sorted(
            candidate / "result.json"
            for candidate in path.parent.iterdir()
            if candidate.is_dir()
            and not candidate.is_symlink()
            and (candidate / "result.json").is_file()
            and not (candidate / "result.json").is_symlink()
        )
        if len(nested_results) != 1:
            raise RuntimeError("Harbor job result must contain exactly one nested trial result")
        trial = _load_object(nested_results[0], "Harbor trial result")
    verifier = trial.get("verifier_result")
    rewards = verifier.get("rewards") if isinstance(verifier, dict) else None
    if rewards is not None and not isinstance(rewards, dict):
        raise RuntimeError("Harbor verifier rewards must be an object")
    exception = trial.get("exception_info")
    exception_type = exception.get("exception_type") if isinstance(exception, dict) else None
    return result, rewards, exception_type if isinstance(exception_type, str) else None


def _result_duration_seconds(result: JsonObject) -> float:
    """Recover elapsed time from a retained Harbor 0.22 job summary."""
    started = result.get("started_at")
    finished = result.get("finished_at")
    if not isinstance(started, str) or not isinstance(finished, str):
        raise RuntimeError("retained Harbor job result omits execution timestamps")
    try:
        duration = (
            datetime.fromisoformat(finished.replace("Z", "+00:00"))
            - datetime.fromisoformat(started.replace("Z", "+00:00"))
        ).total_seconds()
    except ValueError as error:
        raise RuntimeError("retained Harbor job result timestamps are invalid") from error
    if duration < 0:
        raise RuntimeError("retained Harbor job result has negative execution time")
    return duration


def _job_configs_match(actual: JsonObject, expected: JsonObject) -> bool:
    """Compare configs while normalizing Harbor's set-backed retry exclusion list."""
    normalized: list[JsonObject] = []
    for payload in (actual, expected):
        candidate = json.loads(json.dumps(payload))
        retry = candidate.get("retry")
        exclusions = retry.get("exclude_exceptions") if isinstance(retry, dict) else None
        if isinstance(exclusions, list) and all(isinstance(value, str) for value in exclusions):
            retry["exclude_exceptions"] = sorted(exclusions)
        normalized.append(candidate)
    return normalized[0] == normalized[1]


def run_terminal(args: argparse.Namespace) -> JsonObject:
    if platform.node() != "basilisk":
        raise RuntimeError("Terminal-Bench study execution requires host basilisk")
    _private_path(
        args.result_dir,
        "Terminal-Bench result directory",
        allow_existing=args.resume_existing,
    )
    _private_path(args.receipt, "Terminal-Bench receipt")
    if importlib.metadata.version("harbor") != HARBOR_PACKAGE_VERSION:
        raise RuntimeError("installed Harbor version does not match the study contract")
    if Path(sys.executable).resolve() != args.harbor_python.resolve():
        raise RuntimeError("runner must execute inside the declared Harbor environment")
    if _git_revision(args.terminal_checkout) != TERMINAL_SOURCE_REVISION:
        raise RuntimeError("Terminal-Bench checkout revision does not match the contract")
    _require_clean_checkout(args.terminal_checkout)
    docker_evidence = _docker_evidence(
        args.docker_daemon_config, args.expected_docker_daemon_config
    )

    study, model, sampler = _load_protocol(args.protocol, args.model_id)
    runtime = model["runtime"]
    context_budget = _context_budget(runtime["context_limit"], sampler["max_tokens"])
    summary = _load_object(args.inputs_summary, "agentic input summary")
    scored_payload = json.loads(args.scored_ids.read_text(encoding="utf-8"))
    if not isinstance(scored_payload, list) or not all(
        isinstance(value, str) and value for value in scored_payload
    ):
        raise ValueError("Terminal-Bench scored IDs must be a JSON list of strings")
    scored_ids = [str(value) for value in scored_payload]
    if len(scored_ids) != len(set(scored_ids)):
        raise ValueError("Terminal-Bench scored IDs must be unique")
    artifacts = summary.get("artifacts")
    expected_ids_hash = (
        artifacts.get("terminal-bench-scored-ids.json") if isinstance(artifacts, dict) else None
    )
    if _sha256_file(args.scored_ids) != expected_ids_hash:
        raise ValueError("Terminal-Bench ID hash does not match the agentic input summary")
    scored_samples = summary.get("scored_samples")
    if not isinstance(scored_samples, dict) or len(scored_ids) != scored_samples.get(
        "terminal-bench-2.1"
    ):
        raise ValueError("Terminal-Bench count does not match the agentic input summary")
    manifest_sha256 = _verify_manifest(args.manifest, summary, scored_ids, str(study["id"]))
    server_receipt = _load_object(args.server_receipt, "model server receipt")
    if (
        server_receipt.get("study_id") != study["id"]
        or server_receipt.get("model_id") != args.model_id
        or server_receipt.get("protocol_sha256") != summary.get("protocol_sha256")
    ):
        raise ValueError("model server receipt does not match the Terminal-Bench run")
    _validate_endpoint(args.endpoint, args.model_id, args.model_path)

    tasks_dir = args.terminal_checkout / "tasks"
    missing = [
        task_id for task_id in scored_ids if not (tasks_dir / task_id / "task.toml").is_file()
    ]
    if missing:
        raise RuntimeError(f"Terminal-Bench checkout omits {len(missing)} selected tasks")

    from harbor.models.job.config import JobConfig

    control_dir = args.result_dir / "control"
    if args.result_dir.exists():
        if (
            not args.resume_existing
            or not args.result_dir.is_dir()
            or args.result_dir.is_symlink()
            or not control_dir.is_dir()
            or control_dir.is_symlink()
        ):
            raise RuntimeError("resume requires an existing private result and control directory")
        for retained in args.result_dir.rglob("*"):
            if retained.is_symlink():
                raise RuntimeError("private evidence tree contains a symbolic link")
    else:
        args.result_dir.mkdir(parents=True, exist_ok=False)
        args.result_dir.chmod(0o750)
        control_dir.mkdir(mode=0o750)
    records: list[JsonObject] = []
    exceptions: Counter[str] = Counter()
    recovered_tasks = 0
    recovered_execution_seconds = 0.0
    started = time.time()
    for sample_id in scored_ids:
        seed = _generation_seed(int(study["seed"]), sample_id)
        job_name = _result_name(sample_id)
        config = _job_config(
            jobs_dir=args.result_dir,
            job_name=job_name,
            tasks_dir=tasks_dir,
            task_id=sample_id,
            model_id=args.model_id,
            agent_kwargs=_agent_kwargs(args.endpoint, sampler, seed, runtime["context_limit"]),
        )
        validated = JobConfig.model_validate(config)
        config_payload = validated.model_dump(
            mode="json",
            exclude_none=True,
            context={"redact_sensitive_env": True},
        )
        config_path = control_dir / f"{job_name}.json"
        stdout_path = control_dir / f"{job_name}.stdout.log"
        stderr_path = control_dir / f"{job_name}.stderr.log"
        job_dir = args.result_dir / job_name
        job_result_path = job_dir / "result.json"
        recovered = job_dir.exists()
        if recovered:
            if not args.resume_existing:
                raise RuntimeError("existing Harbor job requires --resume-existing")
            if not config_path.is_file() or not _job_configs_match(
                _load_object(config_path, "retained Harbor job configuration"),
                config_payload,
            ):
                raise RuntimeError("retained Harbor job configuration differs from the study")
            if not stdout_path.is_file() or not stderr_path.is_file():
                raise RuntimeError("retained Harbor job omits its control logs")
            result, rewards, exception_type = _parse_job_result(job_result_path)
            duration_seconds = _result_duration_seconds(result)
            harbor_exit_code: int | None = None
            recovered_tasks += 1
            recovered_execution_seconds += duration_seconds
        else:
            if config_path.exists() or stdout_path.exists() or stderr_path.exists():
                raise RuntimeError("orphaned Harbor control evidence prevents a clean trial")
            _write_private_json(config_path, config_payload)
            task_started = time.time()
            env = dict(os.environ)
            env["OPENAI_API_KEY"] = "EMPTY"
            env["DOCKER_HOST"] = DOCKER_HOST
            with (
                stdout_path.open("x", encoding="utf-8") as stdout,
                stderr_path.open("x", encoding="utf-8") as stderr,
            ):
                stdout_path.chmod(0o600)
                stderr_path.chmod(0o600)
                completed = subprocess.run(
                    [
                        str(args.harbor_executable),
                        "run",
                        "--config",
                        str(config_path),
                        "--yes",
                    ],
                    cwd=args.terminal_checkout,
                    env=env,
                    stdout=stdout,
                    stderr=stderr,
                    text=True,
                    timeout=None,
                )
            if not job_result_path.is_file():
                raise RuntimeError(f"Harbor omitted the job result for {sample_id}")
            _, rewards, exception_type = _parse_job_result(job_result_path)
            duration_seconds = time.time() - task_started
            harbor_exit_code = completed.returncode
        if exception_type:
            exceptions[exception_type] += 1
        records.append(
            {
                "canonical_id": sample_id,
                "generation_seed": seed,
                "harbor_exit_code": harbor_exit_code,
                "recovered_existing_trial": recovered,
                "rewards": rewards,
                "exception_type": exception_type,
                "duration_seconds": duration_seconds,
                "job_name": job_name,
                "job_result_sha256": _sha256_file(job_result_path),
            }
        )

    _seal_private_tree(args.result_dir)
    primary_rewards = [
        float(record["rewards"]["reward"])
        for record in records
        if isinstance(record.get("rewards"), dict)
        and isinstance(record["rewards"].get("reward"), (int, float))
    ]
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
            "package": "harbor",
            "version": HARBOR_PACKAGE_VERSION,
            "terminal_bench_source_revision": TERMINAL_SOURCE_REVISION,
            "python": platform.python_version(),
            "matric_eval_revision": _git_revision(Path(__file__).resolve().parents[1]),
            "agent": "terminus-2",
            "environment": "docker",
            "official_container_verifier": True,
            "docker": docker_evidence,
        },
        "execution": {
            "attempts_per_task": 1,
            "concurrency": 1,
            "retries": 0,
            "timeout_multiplier": 1.0,
            "resume_existing": args.resume_existing,
            "recovered_tasks": recovered_tasks,
            "recovered_execution_seconds": recovered_execution_seconds,
            "context_budget": context_budget,
            "context_budget_enforcement": "harbor-model-info-input-limit-requested-unverified",
            "target_thinking_mode_requested": "disabled",
        },
        "sampler": sampler,
        "scored_samples": len(records),
        "scored_results": records,
        "primary_reward_count": len(primary_rewards),
        "primary_reward_mean": (
            sum(primary_rewards) / len(primary_rewards) if primary_rewards else None
        ),
        "exception_counts": dict(sorted(exceptions.items())),
        "execution_seconds": recovered_execution_seconds + time.time() - started,
        "private_files": _file_manifest(args.result_dir),
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    _write_private_json(args.receipt, receipt)
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--server-receipt", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:18083/v1")
    parser.add_argument("--terminal-checkout", type=Path, required=True)
    parser.add_argument("--harbor-python", type=Path, required=True)
    parser.add_argument("--harbor-executable", type=Path, required=True)
    parser.add_argument(
        "--docker-daemon-config",
        type=Path,
        default=Path("/srv/obliteratus/matric-eval/docker/daemon.json"),
    )
    parser.add_argument(
        "--expected-docker-daemon-config",
        type=Path,
        default=DEFAULT_DOCKER_CONFIG_ASSET,
    )
    parser.add_argument("--inputs-summary", type=Path, required=True)
    parser.add_argument("--scored-ids", type=Path, required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument(
        "--resume-existing",
        action="store_true",
        help="verify and retain completed official trials in an existing result directory",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    receipt = run_terminal(build_parser().parse_args(argv))
    print(
        json.dumps(
            {
                "study_id": receipt["study_id"],
                "model_id": receipt["model_id"],
                "scored_samples": receipt["scored_samples"],
                "primary_reward_mean": receipt["primary_reward_mean"],
                "exception_counts": receipt["exception_counts"],
                "execution_seconds": receipt["execution_seconds"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
