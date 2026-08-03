#!/usr/bin/env python3
"""Validate built release packages from clean consumer environments."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> str:
    process = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if process.returncode:
        raise RuntimeError(
            f"Command failed ({process.returncode}): {' '.join(command)}\n"
            f"stdout:\n{process.stdout}\nstderr:\n{process.stderr}"
        )
    return process.stdout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _output_digest(output: str) -> str:
    return hashlib.sha256(output.encode()).hexdigest()


def _one(paths: list[Path], description: str) -> Path:
    if len(paths) != 1:
        raise ValueError(f"Expected one {description}, found {[str(path) for path in paths]}")
    return paths[0].resolve()


def _clean_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("VIRTUAL_ENV", None)
    environment["UV_LINK_MODE"] = "copy"
    return environment


def _validate_python_install(
    *,
    uv: str,
    requested_version: str,
    artifact: Path,
    artifact_kind: str,
    expected_version: str,
    workspace: Path,
) -> tuple[dict[str, Any], Path]:
    environment = _clean_environment()
    install_root = workspace / f"python-{requested_version}-{artifact_kind}"
    environment_root = install_root / "environment"
    consumer_root = install_root / "consumer"
    consumer_root.mkdir(parents=True)

    _run(
        [uv, "venv", "--python", requested_version, str(environment_root)],
        cwd=consumer_root,
        env=environment,
    )
    python = environment_root / "bin/python"
    executable = environment_root / "bin/matric-eval"
    _run(
        [uv, "pip", "install", "--python", str(python), str(artifact)],
        cwd=consumer_root,
        env=environment,
    )

    runtime = json.loads(
        _run(
            [
                str(python),
                "-c",
                (
                    "import json, platform; "
                    "from importlib.metadata import version; "
                    "print(json.dumps({'python': platform.python_version(), "
                    "'implementation': platform.python_implementation(), "
                    "'matric_eval': version('matric-eval')}))"
                ),
            ],
            cwd=consumer_root,
            env=environment,
        )
    )
    if runtime["matric_eval"] != expected_version:
        raise ValueError(f"Installed {runtime['matric_eval']}, expected {expected_version}")

    version_output = _run([str(executable), "--version"], cwd=consumer_root, env=environment)
    if not version_output.strip().endswith(expected_version):
        raise ValueError(f"Unexpected CLI version output: {version_output!r}")
    help_output = _run([str(executable), "--help"], cwd=consumer_root, env=environment)
    benchmark_output = _run(
        [str(executable), "list-benchmarks", "--output-format", "json"],
        cwd=consumer_root,
        env=environment,
    )
    benchmarks = json.loads(benchmark_output)
    if "injecagent" not in benchmarks:
        raise ValueError("Clean benchmark inventory does not contain injecagent")

    audit_path = consumer_root / "benchmark-audit.json"
    _run(
        [
            str(executable),
            "audit-benchmarks",
            "--output-format",
            "json",
            "--output",
            str(audit_path),
        ],
        cwd=consumer_root,
        env=environment,
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit["summary"]["error"]:
        raise ValueError(f"Clean benchmark audit has errors: {audit['summary']}")

    provider_output = _run(
        [str(executable), "list-providers", "--output-format", "json"],
        cwd=consumer_root,
        env=environment,
    )
    providers = json.loads(provider_output)
    provider_names = sorted(item["name"] for item in providers)
    if not {"ollama", "openrouter"}.issubset(provider_names):
        raise ValueError(f"Provider registry smoke failed: {provider_names}")

    return (
        {
            "artifact": artifact.name,
            "artifact_kind": artifact_kind,
            "requested_python": requested_version,
            "runtime": runtime,
            "commands": {
                "benchmark_count": len(benchmarks),
                "benchmark_inventory_sha256": _output_digest(benchmark_output),
                "benchmark_audit_summary": audit["summary"],
                "cli_help_sha256": _output_digest(help_output),
                "cli_version": version_output.strip(),
                "provider_registry": provider_names,
            },
        },
        executable,
    )


def _validate_typescript_install(
    *,
    npm: str,
    node: str,
    artifact: Path,
    expected_version: str,
    executable: Path,
    workspace: Path,
) -> dict[str, Any]:
    consumer_root = workspace / "typescript-consumer"
    consumer_root.mkdir()
    environment = _clean_environment()
    environment["MATRIC_EVAL_BIN"] = str(executable)

    _run([npm, "init", "--yes"], cwd=consumer_root, env=environment)
    _run(
        [npm, "install", "--ignore-scripts", str(artifact)],
        cwd=consumer_root,
        env=environment,
    )
    validation_script = consumer_root / "validate.mjs"
    validation_script.write_text(
        """import { createClient } from '@matric/eval-client';
const client = createClient(process.env.MATRIC_EVAL_BIN);
const version = await client.getVersion();
const benchmarks = await client.listBenchmarks();
if (!benchmarks.includes('injecagent')) {
  throw new Error('TypeScript client benchmark inventory omitted injecagent');
}
console.log(JSON.stringify({ version, benchmarkCount: benchmarks.length }));
""",
        encoding="utf-8",
    )
    result = json.loads(_run([node, str(validation_script)], cwd=consumer_root, env=environment))
    if not result["version"].endswith(expected_version):
        raise ValueError(f"TypeScript client returned unexpected version: {result['version']}")
    package = json.loads(
        (consumer_root / "node_modules/@matric/eval-client/package.json").read_text(
            encoding="utf-8"
        )
    )
    if package["version"] != expected_version:
        raise ValueError(f"Installed npm package {package['version']}, expected {expected_version}")
    return {
        "artifact": artifact.name,
        "node": _run([node, "--version"], cwd=consumer_root).strip(),
        "npm": _run([npm, "--version"], cwd=consumer_root).strip(),
        "package_name": package["name"],
        "package_version": package["version"],
        "client_result": result,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected", required=True)
    parser.add_argument("--python-version", action="append", required=True)
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--npm", default="npm")
    parser.add_argument("--node", default="node")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    artifact_root = args.artifact_root.resolve()
    wheel = _one(list((artifact_root / "packages/python").glob("*.whl")), "wheel")
    sdist = _one(list((artifact_root / "packages/python").glob("*.tar.gz")), "sdist")
    npm_package = _one(list((artifact_root / "packages/typescript").glob("*.tgz")), "npm package")
    artifacts = [wheel, sdist, npm_package]

    _run(
        [args.uv, "python", "install", *args.python_version],
        cwd=artifact_root,
        env=_clean_environment(),
    )
    python_results: list[dict[str, Any]] = []
    typescript_executable: Path | None = None
    with tempfile.TemporaryDirectory(prefix="matric-eval-release-validation-") as temporary:
        workspace = Path(temporary)
        for version in args.python_version:
            for artifact_kind, artifact in (("wheel", wheel), ("sdist", sdist)):
                print(f"Validating {artifact_kind} on Python {version}", flush=True)
                result, executable = _validate_python_install(
                    uv=args.uv,
                    requested_version=version,
                    artifact=artifact,
                    artifact_kind=artifact_kind,
                    expected_version=args.expected,
                    workspace=workspace,
                )
                python_results.append(result)
                if artifact_kind == "wheel" and typescript_executable is None:
                    typescript_executable = executable
        if typescript_executable is None:
            raise AssertionError("No Python executable was retained for TypeScript validation")
        print("Validating npm consumer contract", flush=True)
        typescript_result = _validate_typescript_install(
            npm=args.npm,
            node=args.node,
            artifact=npm_package,
            expected_version=args.expected,
            executable=typescript_executable,
            workspace=workspace,
        )

    report = {
        "schema_version": 1,
        "status": "passed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "expected_version": args.expected,
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "artifacts": [
            {
                "path": str(path.relative_to(artifact_root)),
                "sha256": _sha256(path),
                "size": path.stat().st_size,
            }
            for path in artifacts
        ],
        "python": python_results,
        "typescript": typescript_result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
