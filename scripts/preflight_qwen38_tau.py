#!/usr/bin/env python3
"""Target-independent official Tau checks for study-run preflight command profiles.

Run each mode as an independent check in the actual Tau environment. This script
never imports a target model or acquires a GPU. Auxiliary broker qualification is
a separate command check using qualify_auxiliary_client.py in its pinned profile.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path

import run_qwen38_tau as tau

from matric_eval.studies.preflight import write_receipt
from matric_eval.studies.protocol import StudyProtocol


def launcher_smoke(args: argparse.Namespace) -> dict[str, object]:
    """Official task/config/generate serialization with a real controlled socket.

    Load one immutable selected task but do not execute or score its simulation.
    The canary is a separate non-scored request through Tau's actual generate.
    """
    import tempfile
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from tau2.data_model.message import UserMessage
    from tau2.data_model.simulation import TextRunConfig
    from tau2.run import get_tasks
    from tau2.utils.llm_utils import generate

    grouped = tau._load_object(args.scored_ids, "scored IDs")
    ids = tau._flatten_scored_ids(grouped)
    study, _, _ = tau._load_protocol(args.protocol, args.model_id)
    summary = tau._load_object(args.inputs_summary, "input summary")
    tau._verify_manifest(args.manifest, summary, ids, study["id"])
    domain, task_id = ids[0].split(":", 1)
    loaded = get_tasks(domain, task_split_name="base", task_ids=[task_id])
    if len(loaded) != 1 or loaded[0].id != task_id:
        raise ValueError("controlled launcher official task membership mismatch")
    # Use production config fields through the official resolved schema.
    config = TextRunConfig(
        domain=domain,
        task_set_name=domain,
        task_split_name="base",
        task_ids=[task_id],
        num_trials=1,
        agent="llm_agent",
        user="user_simulator",
        llm_agent="hosted_vllm/preflight-control",
        llm_user=tau.TAU_EXTERNAL_MODEL,
        max_steps=200,
        max_errors=10,
        max_concurrency=1,
        workers=0,
        seed=int(study["seed"]),
        max_retries=0,
        auto_resume=False,
        auto_review=False,
        hallucination_retries=0,
    )
    TextRunConfig.model_validate_json(config.model_dump_json())
    requests: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            requests.append(data)
            body = json.dumps(
                {
                    "id": "preflight-control",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "preflight-control",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "OK"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        response = generate(
            model="hosted_vllm/preflight-control",
            messages=[UserMessage(role="user", content="Reply exactly OK.")],
            api_base=f"http://127.0.0.1:{server.server_port}/v1",
            api_key="EMPTY",
            max_tokens=8,
            timeout=10,
            num_retries=0,
            call_name="preflight_controlled_adapter",
        )
        if response.content != "OK" or len(requests) != 1:
            raise ValueError("official adapter controlled endpoint failed")
        if requests[0].get("messages") != [{"role": "user", "content": "Reply exactly OK."}]:
            raise ValueError("official adapter changed controlled request shape")
        with tempfile.TemporaryDirectory(prefix="tau-receipt-smoke-") as temporary:
            path = Path(temporary) / "native-receipt.json"
            # Same private fsync JSON serializer used by the production Tau adapter.
            sha = tau._write_private_json(
                path,
                {
                    "schema_version": "1",
                    "qualification_only": True,
                    "scored_samples": 0,
                    "configuration": config.model_dump(mode="json"),
                    "task": loaded[0].model_dump(mode="json"),
                    "response": response.model_dump(mode="json"),
                },
            )
            saved = json.loads(path.read_text())
            if saved["schema_version"] != "1" or saved["scored_samples"] != 0:
                raise ValueError("official adapter receipt contract mismatch")
        return {
            "official_task_id": ids[0],
            "http_requests": len(requests),
            "native_receipt_sha256": sha,
            "scored_tasks_executed": 0,
            "client_path": "tau2.utils.llm_utils.generate",
            "qualification": "controlled_endpoint_only",
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("inputs", "patch", "dependencies", "tasks", "sandbox", "launcher")
    )
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--inputs-summary", type=Path, required=True)
    parser.add_argument("--scored-ids", type=Path, required=True)
    parser.add_argument("--tau-checkout", type=Path, required=True)
    parser.add_argument("--tau-patch-manifest", type=Path, default=tau.DEFAULT_TAU_PATCH_MANIFEST)
    args = parser.parse_args()
    result: dict[str, object] = {
        "schema": "matric-eval.tau-preflight/1",
        "mode": args.mode,
        "passed": True,
    }
    if args.mode == "inputs":
        study, _, _ = tau._load_protocol(args.protocol, args.model_id)
        summary = tau._load_object(args.inputs_summary, "agentic input summary")
        grouped = tau._load_object(args.scored_ids, "scored IDs")
        ids = tau._flatten_scored_ids(grouped)
        if tau._sha256_file(args.scored_ids) != summary["artifacts"]["tau3-scored-ids.json"]:
            raise ValueError("scored input hash differs from frozen summary")
        if (
            StudyProtocol.from_yaml(args.protocol, validate_registry=False).canonical_sha256
            != summary["protocol_sha256"]
        ):
            raise ValueError("protocol hash differs from frozen summary")
        if len(ids) != summary["scored_samples"]["tau3-bench"]:
            raise ValueError("scored count differs from summary")
        result["manifest_sha256"] = tau._verify_manifest(args.manifest, summary, ids, study["id"])
        result["ordered_ids"] = ids
    elif args.mode == "patch":
        result["patch"] = tau._tau_worktree_evidence(args.tau_checkout, args.tau_patch_manifest)
    elif args.mode == "dependencies":
        versions = {}
        missing = []
        for package in ("tau2", "litellm", "openai", "httpx", "pydantic", "pydantic-settings"):
            try:
                versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                missing.append(package)
        if missing:
            raise RuntimeError("missing resolved Tau dependencies: " + ", ".join(missing))
        result["resolved_dependencies"] = versions
        import tau2

        resolved_package = Path(tau2.__file__).resolve()
        if not resolved_package.is_relative_to((args.tau_checkout / "src/tau2").resolve()):
            raise RuntimeError("resolved Tau package differs from declared benchmark checkout")
        result["resolved_tau_module"] = str(resolved_package)
        if importlib.metadata.version("tau2") != tau.TAU_PACKAGE_VERSION:
            raise ValueError("installed tau2 version differs from pinned contract")
        if tau._git_revision(args.tau_checkout) != tau.TAU_SOURCE_REVISION:
            raise ValueError("tau checkout revision differs from pinned contract")
        # Import actual resolved runner/model types before target allocation.
        from tau2.data_model.simulation import TextRunConfig
        from tau2.run import get_tasks

        result["configuration_fields"] = sorted(TextRunConfig.model_fields)
        result["task_loader"] = get_tasks.__module__
    elif args.mode == "tasks":
        from tau2.run import get_tasks

        grouped = tau._load_object(args.scored_ids, "scored IDs")
        for domain, ids in grouped.items():
            loaded = [task.id for task in get_tasks(domain, task_split_name="base", task_ids=ids)]
            if len(loaded) != len(set(loaded)) or set(loaded) != set(ids):
                raise ValueError(f"official task loader membership mismatch: {domain}")
        result["domains"] = sorted(grouped)
    elif args.mode == "launcher":
        result["launcher"] = launcher_smoke(args)
    else:
        result["sandbox"] = tau._knowledge_dependency_evidence()
    write_receipt(Path(os.environ["MATRIC_PREFLIGHT_RECEIPT"]), result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
