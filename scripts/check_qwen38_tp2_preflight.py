#!/usr/bin/env python3
"""Content-free preflight checks for the Basilisk two-A100 qualification."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from matric_eval.studies.batch import (
    _model_for_id,
    validate_parallelism_attestation,
    verify_model_artifact,
)
from matric_eval.studies.gpu import (
    A100_TP2_PROFILE,
    NVLINK_P2P_TOPOLOGY_POLICY,
    GpuAllocation,
    GpuExecutionBinding,
)
from matric_eval.studies.protocol import StudyProtocol
from matric_eval.studies.resource_lifecycle import Broker, Docker
from matric_eval.studies.tp2_qualification import write_private_json

DOCKER_HOST = "unix:///run/matric-eval-docker.sock"
BROKER_SOCKET = "/run/ollama-unify/gpu-negotiator.sock"


def _load_object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _git(workspace: Path, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(workspace), *arguments], text=True, timeout=15
    ).strip()


def _check_target(args: argparse.Namespace, study: StudyProtocol) -> dict[str, Any]:
    record = _load_object(args.resource_directory / "record.json", "resource record")
    expected = list(args.gpu)
    if record.get("gpu_uuids") != expected:
        raise RuntimeError("resource record GPU rank order does not match the TP2 allocation")
    docker = Docker(DOCKER_HOST)
    info = docker.inspect(str(record.get("container")))
    if info is None or not info.get("State", {}).get("Running"):
        raise RuntimeError("qualified container is not running")
    if info.get("Config", {}).get("Labels", {}).get("matric.resource") != record.get("resource_id"):
        raise RuntimeError("qualified container label does not match its resource record")
    requests = info.get("HostConfig", {}).get("DeviceRequests")
    device_sets = [
        request.get("DeviceIDs")
        for request in requests or []
        if isinstance(request, dict) and request.get("Driver") == "nvidia"
    ]
    if device_sets != [expected]:
        raise RuntimeError("Docker did not receive the exact ordered two-GPU selector")
    container_id = info.get("Id")
    cuda = {
        gpu
        for gpu, pid in docker.cuda()
        if gpu in expected and isinstance(container_id, str) and container_id in docker.cgroup(pid)
    }
    if cuda != set(expected):
        raise RuntimeError("both qualified GPUs do not have owned container CUDA allocations")

    deadline = time.monotonic() + 30
    while not args.server_receipt.is_file():
        if time.monotonic() >= deadline:
            raise RuntimeError("server receipt was not published after model readiness")
        time.sleep(0.1)
    receipt = _load_object(args.server_receipt, "server receipt")
    parallelism = receipt.get("runtime", {}).get("parallelism")
    if not isinstance(parallelism, dict):
        raise RuntimeError("server receipt lacks parallelism evidence")
    allocation = GpuAllocation(tuple(args.gpu), 75_000, NVLINK_P2P_TOPOLOGY_POLICY)
    binding = validate_parallelism_attestation(
        GpuExecutionBinding(allocation, study.parallelism_profile), parallelism
    )
    if (
        receipt.get("protocol_sha256") != study.canonical_sha256
        or binding["effective"]["tensor_parallel_size"] != 2
        or binding["effective"]["pipeline_parallel_size"] != 1
        or binding["effective"]["visible_gpu_uuids"] != expected
    ):
        raise RuntimeError("server receipt does not attest the exact TP2 execution")
    with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/v1/models", timeout=10) as response:
        models = json.loads(response.read(1024 * 1024))
    served = {
        item.get("id")
        for item in models.get("data", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if args.model_id not in served or str(args.model_path) not in served:
        raise RuntimeError("TP2 server does not advertise both qualified model names")
    return {
        "container_id": container_id,
        "cuda_gpu_uuids": expected,
        "tensor_parallel_size": 2,
        "pipeline_parallel_size": 1,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    if platform.node() != "basilisk":
        raise RuntimeError("TP2 qualification preflight requires host basilisk")
    if len(args.gpu) != 2 or len(set(args.gpu)) != 2:
        raise ValueError("TP2 qualification requires two distinct GPU UUIDs")
    if _git(args.workspace, "status", "--porcelain"):
        raise RuntimeError("qualification checkout is not clean")
    if _git(args.workspace, "rev-parse", "HEAD") != args.revision:
        raise RuntimeError("qualification checkout revision changed")
    study = StudyProtocol.from_yaml(args.protocol, validate_registry=False)
    if study.parallelism_profile is not A100_TP2_PROFILE:
        raise RuntimeError("qualification protocol does not select registered TP2")

    evidence: dict[str, Any] = {}
    if args.stage == "static":
        qualification = _load_object(args.qualification, "model qualification")
        verify_model_artifact(
            _model_for_id(study, args.model_id),
            args.model_path,
            qualification,
            verify_tensor_hashes=True,
        )
        evidence["model_artifact_verified"] = True
    elif args.stage == "cpu":
        subprocess.run(
            [sys.executable, "-m", "matric_eval.studies.server_cli", "--help"],
            check=True,
            capture_output=True,
            timeout=30,
        )
        evidence["server_entrypoint_verified"] = True
    elif args.stage == "auxiliary":
        status = Broker(BROKER_SOCKET).call("status")
        if not isinstance(status.get("gpus"), list) or not isinstance(status.get("leases"), list):
            raise RuntimeError("GPU broker status is malformed")
        known = {item.get("uuid") for item in status["gpus"] if isinstance(item, dict)}
        if not set(args.gpu) <= known:
            raise RuntimeError("GPU broker does not inventory the qualified pair")
        evidence["broker_inventory_verified"] = True
    else:
        evidence.update(_check_target(args, study))
    return {
        "schema": "matric-eval.basilisk-tp2-preflight/1",
        "stage": args.stage,
        "passed": True,
        **evidence,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("static", "cpu", "auxiliary", "target"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--resource-directory", type=Path, required=True)
    parser.add_argument("--gpu", action="append", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--server-receipt", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output = os.environ.get("MATRIC_PREFLIGHT_RECEIPT")
    if not output:
        raise RuntimeError("MATRIC_PREFLIGHT_RECEIPT is required")
    write_private_json(Path(output), run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
