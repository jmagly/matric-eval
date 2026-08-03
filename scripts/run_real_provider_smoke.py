#!/usr/bin/env python3
"""Run an artifact-producing smoke evaluation against a real provider."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from matric_eval.tasks.registry import get_registry


def utc_now() -> str:
    """Return an RFC 3339 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def public_url(value: str) -> str:
    """Remove credentials and query data before persisting a provider URL."""
    parsed = urlsplit(value)
    hostname = parsed.hostname or ""
    if parsed.port:
        hostname = f"{hostname}:{parsed.port}"
    return urlunsplit((parsed.scheme, hostname, parsed.path, "", ""))


def request_json(
    base_url: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 30,
) -> dict[str, Any]:
    """Call an Ollama JSON endpoint using only the standard library."""
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    with urlopen(request, timeout=timeout) as response:
        decoded = json.loads(response.read())
    if not isinstance(decoded, dict):
        raise ValueError(f"Expected object response from {path}")
    return decoded


def wait_for_provider(base_url: str, timeout: float) -> dict[str, Any]:
    """Wait for Ollama to become reachable, returning its version response."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return request_json(base_url, "/api/version", timeout=5)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            last_error = exc
            time.sleep(2)
    raise TimeoutError(f"Provider unavailable after {timeout:.0f}s: {last_error}")


def model_snapshot(base_url: str, model: str, pull_timeout: float) -> dict[str, Any]:
    """Pull the fixture and return its immutable digest and runtime details."""
    request_json(
        base_url,
        "/api/pull",
        {"name": model, "stream": False},
        timeout=pull_timeout,
    )
    tags = request_json(base_url, "/api/tags", timeout=30).get("models", [])
    selected = next((item for item in tags if item.get("name") == model), None)
    if selected is None:
        raise RuntimeError(f"Pulled model is absent from provider inventory: {model}")
    details = request_json(base_url, "/api/show", {"model": model}, timeout=30)
    return {
        "name": model,
        "digest": selected.get("digest"),
        "size": selected.get("size"),
        "modified_at": selected.get("modified_at"),
        "details": details.get("details", selected.get("details", {})),
    }


def benchmark_snapshot(name: str, git_sha: str | None) -> dict[str, Any]:
    """Return the benchmark protocol and effective dataset revision."""
    metadata = get_registry().get_or_raise(name)
    revision = metadata.dataset_revision or git_sha
    return {
        "name": metadata.name,
        "protocol_version": metadata.protocol_version,
        "dataset_source": metadata.dataset_source,
        "dataset_revision": revision,
        "dataset_revision_source": "registry" if metadata.dataset_revision else "git_commit",
        "evaluator_source": metadata.evaluator_source,
        "evaluator_revision": metadata.evaluator_revision,
        "tier_samples": metadata.tier_samples.get("smoke", 0),
    }


def git_revision() -> str | None:
    """Resolve the tested source revision in hosted and local runs."""
    configured = os.getenv("GITHUB_SHA") or os.getenv("CI_COMMIT_SHA")
    if configured:
        return configured
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write deterministic, human-readable JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def latest_summary(results_dir: Path) -> tuple[Path, dict[str, Any]]:
    """Load the single summary produced by this smoke invocation."""
    summaries = sorted(results_dir.glob("run-*/summary.json"))
    if len(summaries) != 1:
        raise RuntimeError(f"Expected one run summary, found {len(summaries)}")
    payload = json.loads(summaries[0].read_text())
    if not isinstance(payload, dict):
        raise ValueError("Run summary must contain a JSON object")
    return summaries[0], payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-url", required=True)
    parser.add_argument("--model", default="smollm2:135m")
    parser.add_argument("--benchmark", default="matric_cli")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provider-wait", type=float, default=90)
    parser.add_argument("--pull-timeout", type=float, default=300)
    parser.add_argument("--evaluation-timeout", type=float, default=600)
    parser.add_argument(
        "--required-credential-env",
        help="environment variable required by credentialed provider fixtures",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    started_at = utc_now()
    output: Path = args.output
    results_dir = output / "results"
    log_path = output / "evaluation.log"
    report_path = output / "smoke-report.json"
    output.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "running",
        "started_at": started_at,
        "completed_at": None,
        "duration_seconds": None,
        "trigger": os.getenv("GITHUB_EVENT_NAME", "local"),
        "git_sha": git_revision(),
        "runner": {
            "accelerator": os.getenv("MATRIC_SMOKE_ACCELERATOR", "cpu"),
            "credential_mode": "required" if args.required_credential_env else "none",
        },
        "provider": {"name": "ollama", "url": public_url(args.provider_url)},
        "model": {"name": args.model},
        "benchmark": {"name": args.benchmark},
    }

    try:
        if args.required_credential_env and not os.getenv(args.required_credential_env):
            report["status"] = "gated"
            report["gate_reason"] = f"Missing required credential: {args.required_credential_env}"
            return 2

        version = wait_for_provider(args.provider_url, args.provider_wait)
        report["provider"]["version"] = version.get("version")
        report["model"] = model_snapshot(args.provider_url, args.model, args.pull_timeout)
        report["benchmark"] = benchmark_snapshot(args.benchmark, report["git_sha"])

        command = [
            sys.executable,
            "-m",
            "matric_eval.cli",
            "run",
            "--provider",
            "ollama",
            "--provider-url",
            args.provider_url,
            "--model",
            args.model,
            "--benchmark",
            args.benchmark,
            "--tier",
            "smoke",
            "--thinking",
            "off",
            "--output",
            str(results_dir),
            "--output-format",
            "json",
        ]
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=args.evaluation_timeout,
            check=False,
        )
        log_path.write_text(
            f"$ {' '.join(command)}\n\n[stdout]\n{process.stdout}\n[stderr]\n{process.stderr}"
        )
        report["command"] = command
        report["command_exit_code"] = process.returncode
        summary_path, summary = latest_summary(results_dir)
        report["summary_path"] = str(summary_path.relative_to(output))
        report["summary"] = summary
        failed = summary.get("failed", 0)
        successful = summary.get("successful", 0)
        if process.returncode != 0 or failed or successful != 1:
            raise RuntimeError(
                f"Evaluation did not produce one successful result "
                f"(exit={process.returncode}, successful={successful}, failed={failed})"
            )
        report["status"] = "success"
        return 0
    except TimeoutError as exc:
        report["status"] = "gated" if "Provider unavailable" in str(exc) else "failed"
        report["error"] = str(exc)
        return 2 if report["status"] == "gated" else 1
    except (
        HTTPError,
        URLError,
        OSError,
        RuntimeError,
        ValueError,
        subprocess.SubprocessError,
    ) as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        return 1
    finally:
        report["completed_at"] = utc_now()
        report["duration_seconds"] = round(time.monotonic() - started, 3)
        write_json(report_path, report)


if __name__ == "__main__":
    raise SystemExit(main())
