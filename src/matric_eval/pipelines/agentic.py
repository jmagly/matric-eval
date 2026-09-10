"""Registry-derived agent-platform and direct-endpoint evaluation pipeline.

The runner deliberately accepts argv arrays rather than shell fragments. Provider
credentials are named in configuration and copied into an otherwise minimal child
environment; values never enter the public result contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Sequence

PIPELINE_SCHEMA = "matric-eval.agentic-pipeline/1"
RESULT_SCHEMA = "matric-eval.agentic-pipeline-result/1"
ADAPTER_VERSION = "1"
TERMINAL_STATUSES = {"passed", "failed", "unavailable", "unsupported", "intentionally_skipped"}
CONFIGURED_STATUSES = {"enabled", "unavailable", "unsupported", "intentionally_skipped"}
ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
RESERVED_CHILD_ENV = {
    "BASH_ENV",
    "ENV",
    "HOME",
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
    "MATRIC_EVAL_TIER",
    "NODE_OPTIONS",
    "NODE_PATH",
    "PATH",
    "PYTHONHOME",
    "PYTHONPATH",
}
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)[^\s]+"),
    re.compile(r"\b(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{12,}\b"),
)


@dataclass(frozen=True)
class ProviderInventory:
    """Authoritative provider inventory observed from the installed AIWG CLI."""

    providers: tuple[str, ...]
    command: tuple[str, ...]
    output_sha256: str
    version: str


@dataclass(frozen=True)
class PipelineConfig:
    """Validated pipeline configuration without secret values."""

    source: Path
    fixture: Path
    output: Path
    scenario: dict[str, Any]
    limits: dict[str, Any]
    providers: dict[str, dict[str, Any]]
    direct_endpoints: tuple[dict[str, Any], ...]
    aiwg_executable: str
    aiwg_framework: str
    aiwg_version: str
    configuration_sha256: str

    @classmethod
    def load(cls, path: str | Path) -> PipelineConfig:
        source = Path(path).resolve()
        raw = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema") != PIPELINE_SCHEMA:
            raise ValueError(f"configuration schema must be {PIPELINE_SCHEMA}")
        scenario = _object(raw, "scenario")
        limits = _object(raw, "limits")
        providers = _object(raw, "providers")
        direct = raw.get("direct_endpoints", [])
        if not isinstance(direct, list) or not all(isinstance(item, dict) for item in direct):
            raise ValueError("direct_endpoints must be an array of objects")
        fixture = _relative_to(source.parent, _string(raw, "fixture"))
        output = _relative_to(source.parent, _string(raw, "output"))
        if not fixture.is_dir():
            raise ValueError(f"fixture directory does not exist: {fixture}")
        _validate_fixture(fixture)
        if output == fixture or output.is_relative_to(fixture) or fixture.is_relative_to(output):
            raise ValueError("output and fixture directories must not overlap")
        tier = scenario.get("tier")
        if tier not in {"smoke", "conformance", "full"}:
            raise ValueError("scenario.tier must be smoke, conformance, or full")
        for key in ("id", "benchmark_id", "revision"):
            _metadata_string(scenario, key, prefix="scenario.")
        _string(scenario, "prompt", prefix="scenario.")
        _positive_int(limits, "max_concurrency")
        _positive_int(limits, "timeout_seconds")
        _nonnegative_int(limits, "infrastructure_retries")
        _positive_int(limits, "max_tokens")
        _nonnegative_number(limits, "max_cost_usd")
        for name, adapter in providers.items():
            if not isinstance(name, str) or not isinstance(adapter, dict):
                raise ValueError("providers must map provider ids to objects")
            _validate_target(adapter, f"providers.{name}", mode="agentic_platform")
        endpoint_ids: set[str] = set()
        for index, endpoint in enumerate(direct):
            _metadata_string(endpoint, "id", prefix=f"direct_endpoints[{index}].")
            if endpoint["id"] in endpoint_ids:
                raise ValueError(f"direct_endpoints contains duplicate id: {endpoint['id']}")
            endpoint_ids.add(endpoint["id"])
            _validate_target(endpoint, f"direct_endpoints[{index}]", mode="direct_endpoint")
        aiwg = raw.get("aiwg", {})
        if not isinstance(aiwg, dict):
            raise ValueError("aiwg must be an object")
        return cls(
            source=source,
            fixture=fixture,
            output=output,
            scenario=scenario,
            limits=limits,
            providers=providers,
            direct_endpoints=tuple(direct),
            aiwg_executable=_string(
                {"executable": aiwg.get("executable", "aiwg")},
                "executable",
                prefix="aiwg.",
            ),
            aiwg_framework=_metadata_string(
                {"framework": aiwg.get("framework", "sdlc")}, "framework", prefix="aiwg."
            ),
            aiwg_version=_metadata_string(aiwg, "version", prefix="aiwg."),
            configuration_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        )


def parse_aiwg_provider_inventory(output: str) -> tuple[str, ...]:
    """Parse the provider ids emitted by ``aiwg help`` without a fallback list."""

    clean = ANSI_ESCAPE.sub("", output)
    match = re.search(r"^\s*Providers:\s*(\d+)\s*[—-]\s*(.+)$", clean, re.MULTILINE)
    if not match:
        raise ValueError("AIWG help did not expose a provider inventory")
    expected_count = int(match.group(1))
    inventory = match.group(2).split(" (default:", 1)[0]
    providers: list[str] = []
    for entry in inventory.split(","):
        provider = entry.strip().split()[0]
        if not re.fullmatch(r"[a-z][a-z0-9-]*", provider):
            raise ValueError(f"AIWG emitted an invalid provider id: {provider!r}")
        if provider in providers:
            raise ValueError(f"AIWG emitted a duplicate provider id: {provider}")
        providers.append(provider)
    if not providers:
        raise ValueError("AIWG provider inventory is empty")
    if len(providers) != expected_count:
        raise ValueError(
            f"AIWG provider inventory declared {expected_count} providers but exposed {len(providers)}"
        )
    return tuple(providers)


def discover_aiwg_provider_inventory(executable: str = "aiwg") -> ProviderInventory:
    """Read the current provider registry through AIWG's maintained CLI surface."""

    help_result = subprocess.run(
        [executable, "help"], capture_output=True, text=True, timeout=30, check=False
    )
    if help_result.returncode:
        raise RuntimeError(f"AIWG provider discovery failed with exit {help_result.returncode}")
    version_result = subprocess.run(
        [executable, "version", "--json"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if version_result.returncode:
        raise RuntimeError(f"AIWG version discovery failed with exit {version_result.returncode}")
    try:
        version = str(json.loads(version_result.stdout)["version"])
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise RuntimeError("AIWG version discovery returned invalid JSON") from error
    return ProviderInventory(
        providers=parse_aiwg_provider_inventory(help_result.stdout),
        command=(Path(executable).name, "help"),
        output_sha256=_sha256_text(help_result.stdout),
        version=version,
    )


class AgenticPipeline:
    """Execute a complete, explicit matrix with bounded resource use."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.kill_switch = config.output / "KILL"
        self._budget_lock = threading.Lock()
        self._reserved_tokens = 0
        self._reserved_cost = 0.0

    def run(self) -> dict[str, Any]:
        inventory = discover_aiwg_provider_inventory(self.config.aiwg_executable)
        if inventory.version != self.config.aiwg_version:
            raise RuntimeError(
                f"configured AIWG version {self.config.aiwg_version!r} does not match "
                f"installed version {inventory.version!r}"
            )
        unknown = sorted(set(self.config.providers) - set(inventory.providers))
        if unknown:
            raise ValueError(
                "configured providers are absent from the current AIWG registry: "
                + ", ".join(unknown)
            )
        public = self.config.output / "public"
        private = self.config.output / "private"
        public.mkdir(parents=True, exist_ok=True, mode=0o755)
        private.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(private, 0o700)
        targets = [
            ("agentic_platform", provider, self.config.providers.get(provider))
            for provider in inventory.providers
        ]
        targets.extend(
            ("direct_endpoint", str(endpoint["id"]), endpoint)
            for endpoint in self.config.direct_endpoints
        )
        results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=int(self.config.limits["max_concurrency"])) as pool:
            futures = {
                pool.submit(self._run_target, mode, target, adapter, inventory, private): (
                    mode,
                    target,
                )
                for mode, target, adapter in targets
            }
            for future in as_completed(futures):
                mode, target = futures[future]
                try:
                    results.append(future.result())
                except Exception as error:  # pragma: no cover - defensive containment
                    results.append(
                        {
                            **self._base_result(mode, target, inventory),
                            "status": "failed",
                            "reason": "controller_error",
                            "failure_class": "infrastructure",
                            "error_type": type(error).__name__,
                            "completed_at": time.time(),
                        }
                    )
        results.sort(key=lambda item: (item["execution_mode"], item["target"]))
        report = {
            "schema": RESULT_SCHEMA,
            "scenario": {
                "id": self.config.scenario["id"],
                "benchmark_id": self.config.scenario["benchmark_id"],
                "revision": self.config.scenario["revision"],
                "tier": self.config.scenario["tier"],
            },
            "registry": {
                "providers": list(inventory.providers),
                "command": list(inventory.command),
                "output_sha256": inventory.output_sha256,
                "aiwg_version": inventory.version,
            },
            "configuration_sha256": self.config.configuration_sha256,
            "limits": dict(self.config.limits),
            "results": results,
            "coverage_complete": all(
                any(
                    result["execution_mode"] == "agentic_platform"
                    and result["target"] == provider
                    and result["status"] in TERMINAL_STATUSES
                    for result in results
                )
                for provider in inventory.providers
            ),
            "completed_at": time.time(),
        }
        report["successful"] = report["coverage_complete"] and not any(
            result["status"] == "failed" for result in results
        )
        _write_json(public / "matrix-result.json", report, mode=0o644)
        return report

    def _run_target(
        self,
        mode: str,
        target: str,
        adapter: dict[str, Any] | None,
        inventory: ProviderInventory,
        private: Path,
    ) -> dict[str, Any]:
        base = self._base_result(mode, target, inventory)
        if adapter is None:
            return {**base, "status": "unsupported", "reason": "adapter_not_configured"}
        configured_status = str(adapter.get("status", "unsupported"))
        base["runtime"] = {
            key: adapter[key]
            for key in (
                "model",
                "model_revision",
                "platform_version",
                "endpoint_revision",
                "dependency_revision",
                "streaming",
            )
            if key in adapter
        }
        base["runtime"]["streaming"] = adapter.get("streaming", "stdout-stderr")
        if configured_status != "enabled":
            return {
                **base,
                "status": configured_status,
                "reason": str(adapter.get("reason", "operator_disposition")),
            }
        missing = [name for name in adapter.get("credentials", []) if not os.environ.get(name)]
        if missing:
            return {
                **base,
                "status": "unavailable",
                "reason": "missing_credentials",
                "missing_credential_names": missing,
            }
        command = [str(value) for value in adapter["command"]]
        if "/" not in command[0] and shutil.which(command[0]) is None:
            return {**base, "status": "unavailable", "reason": "executable_not_found"}
        if self._kill_requested():
            return {**base, "status": "intentionally_skipped", "reason": "kill_switch_active"}
        retries = int(self.config.limits["infrastructure_retries"])
        attempts: list[dict[str, Any]] = []
        for attempt in range(1, retries + 2):
            if not self._reserve_budget(adapter):
                if attempts:
                    return {
                        **base,
                        "status": "failed",
                        "reason": "retry_budget_exhausted",
                        "failure_class": "infrastructure",
                        "attempts": attempts,
                    }
                return {
                    **base,
                    "status": "intentionally_skipped",
                    "reason": "budget_exhausted",
                    "attempts": attempts,
                }
            result = self._attempt(mode, target, adapter, attempt, private)
            attempts.append(result)
            if result["failure_class"] != "infrastructure" or attempt > retries:
                return {**base, **result, "attempts": attempts}
        raise AssertionError("retry loop did not produce a terminal result")

    def _attempt(
        self,
        mode: str,
        target: str,
        adapter: dict[str, Any],
        attempt: int,
        private: Path,
    ) -> dict[str, Any]:
        started = time.time()
        safe_target = re.sub(r"[^a-zA-Z0-9_.-]", "_", target)
        evidence = private / f"{mode}-{safe_target}-attempt-{attempt}"
        evidence.mkdir(parents=True, exist_ok=False, mode=0o700)
        os.chmod(evidence, 0o700)
        with tempfile.TemporaryDirectory(prefix=f"matric-eval-{safe_target}-") as temp:
            workspace = Path(temp) / "workspace"
            shutil.copytree(self.config.fixture, workspace, symlinks=False)
            child_env = self._child_environment(adapter, workspace)
            sensitive_names = [
                *adapter.get("credentials", []),
                *adapter.get("inherit_environment", []),
            ]
            secrets = [child_env[name] for name in sensitive_names if name in child_env]
            if mode == "agentic_platform":
                deploy = adapter.get(
                    "deploy_command",
                    [
                        self.config.aiwg_executable,
                        "use",
                        self.config.aiwg_framework,
                        "--provider",
                        target,
                        "--force",
                    ],
                )
                deployment = self._execute(
                    _expand_command(deploy, self._values(target, workspace)),
                    workspace,
                    child_env,
                    secrets,
                    evidence,
                    "deploy",
                )
                if deployment["status"] != "passed":
                    return {
                        **deployment,
                        "reason": "aiwg_deployment_failed",
                        "attempt": attempt,
                        "started_at": started,
                        "completed_at": time.time(),
                    }
            else:
                deployment = None
            execution = self._execute(
                _expand_command(adapter["command"], self._values(target, workspace)),
                workspace,
                child_env,
                secrets,
                evidence,
                "invoke",
            )
            if execution["status"] == "passed" and adapter.get("streaming") == "jsonl":
                execution = _apply_jsonl_contract(execution, evidence / "invoke.stdout.log")
            result_file = adapter.get("result_file")
            if execution["status"] == "passed" and isinstance(result_file, str):
                execution = _apply_native_result(
                    execution, workspace / result_file, evidence, secrets
                )
            result = {
                **execution,
                "attempt": attempt,
                "started_at": started,
                "completed_at": time.time(),
            }
            if deployment is not None:
                result["deployment"] = deployment
            return result

    def _execute(
        self,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        secrets: list[str],
        evidence: Path,
        name: str,
    ) -> dict[str, Any]:
        stdout_path = evidence / f"{name}.stdout.log"
        stderr_path = evidence / f"{name}.stderr.log"
        executable = Path(command[0])
        available = (
            executable.is_absolute()
            and executable.is_file()
            or not executable.is_absolute()
            and (
                (cwd / executable).is_file()
                or shutil.which(command[0], path=env.get("PATH")) is not None
            )
        )
        if not available:
            _write_private_text(stdout_path, "")
            stderr = "executable not found\n"
            _write_private_text(stderr_path, stderr)
            return {
                "status": "failed",
                "reason": "executable_not_found",
                "failure_class": "infrastructure",
                "exit_code": 127,
                "duration_seconds": 0.0,
                "stdout_sha256": _sha256_text(""),
                "stderr_sha256": _sha256_text(stderr),
                "evidence": str(evidence.relative_to(self.config.output)),
            }
        timed_out = False
        cancelled = False
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
        except OSError as error:
            _write_private_text(stdout_path, "")
            stderr = f"process spawn failed: {type(error).__name__}\n"
            _write_private_text(stderr_path, stderr)
            return {
                "status": "failed",
                "reason": "spawn_failed",
                "failure_class": "infrastructure",
                "exit_code": None,
                "duration_seconds": round(time.monotonic() - started, 6),
                "stdout_sha256": _sha256_text(""),
                "stderr_sha256": _sha256_text(stderr),
                "evidence": str(evidence.relative_to(self.config.output)),
            }
        assert process.stdout is not None
        assert process.stderr is not None
        streams = (
            threading.Thread(
                target=_stream_redacted,
                args=(process.stdout, stdout_path, secrets),
                daemon=True,
            ),
            threading.Thread(
                target=_stream_redacted,
                args=(process.stderr, stderr_path, secrets),
                daemon=True,
            ),
        )
        for stream in streams:
            stream.start()
        while process.poll() is None:
            if self._kill_requested():
                cancelled = True
                _stop_process(process)
                break
            if time.monotonic() - started >= int(self.config.limits["timeout_seconds"]):
                timed_out = True
                _stop_process(process)
                break
            time.sleep(0.1)
        exit_code = process.wait(timeout=10)
        for stream in streams:
            stream.join(timeout=10)
        if any(stream.is_alive() for stream in streams):
            raise RuntimeError("output redaction stream did not terminate")
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
        if cancelled:
            status, reason = "failed", "cancelled"
        elif timed_out:
            status, reason = "failed", "timeout"
        elif exit_code:
            status, reason = "failed", "nonzero_exit"
        else:
            status, reason = "passed", "completed"
        return {
            "status": status,
            "reason": reason,
            "failure_class": None if status == "passed" else "infrastructure",
            "exit_code": exit_code,
            "duration_seconds": round(time.monotonic() - started, 6),
            "stdout_sha256": _sha256_text(stdout),
            "stderr_sha256": _sha256_text(stderr),
            "evidence": str(evidence.relative_to(self.config.output)),
        }

    def _reserve_budget(self, adapter: dict[str, Any]) -> bool:
        tokens = int(adapter.get("estimated_tokens", 0))
        cost = float(adapter.get("estimated_cost_usd", 0.0))
        with self._budget_lock:
            if self._reserved_tokens + tokens > int(self.config.limits["max_tokens"]):
                return False
            if self._reserved_cost + cost > float(self.config.limits["max_cost_usd"]):
                return False
            self._reserved_tokens += tokens
            self._reserved_cost += cost
            return True

    def _kill_requested(self) -> bool:
        return self.kill_switch.exists() or os.environ.get("MATRIC_EVAL_KILL_SWITCH") == "1"

    def _child_environment(self, adapter: dict[str, Any], workspace: Path) -> dict[str, str]:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
            "HOME": str(workspace / ".home"),
            "MATRIC_EVAL_TIER": str(self.config.scenario["tier"]),
        }
        Path(env["HOME"]).mkdir(mode=0o700)
        for name in adapter.get("credentials", []):
            env[name] = os.environ[name]
        for name in adapter.get("inherit_environment", []):
            if name in os.environ:
                env[name] = os.environ[name]
        return env

    def _values(self, target: str, workspace: Path) -> dict[str, str]:
        return {
            "target": target,
            "workspace": str(workspace),
            "prompt": str(self.config.scenario["prompt"]),
            "tier": str(self.config.scenario["tier"]),
            "scenario_id": str(self.config.scenario["id"]),
            "benchmark_id": str(self.config.scenario["benchmark_id"]),
        }

    def _base_result(self, mode: str, target: str, inventory: ProviderInventory) -> dict[str, Any]:
        return {
            "adapter_version": ADAPTER_VERSION,
            "execution_mode": mode,
            "target": target,
            "benchmark_id": self.config.scenario["benchmark_id"],
            "scenario_revision": self.config.scenario["revision"],
            "repository_commit": _git_revision(self.config.fixture),
            "aiwg_version": inventory.version,
            "configuration_sha256": self.config.configuration_sha256,
        }


def _apply_native_result(
    execution: dict[str, Any], path: Path, evidence: Path, secrets: Sequence[str]
) -> dict[str, Any]:
    try:
        redacted = _redact(path.read_text(encoding="utf-8"), secrets)
        retained = evidence / "invoke.native-result.json"
        _write_private_text(retained, redacted)
        native = json.loads(redacted)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {
            **execution,
            "status": "failed",
            "reason": "invalid_native_result",
            "failure_class": "infrastructure",
        }
    outcome = native.get("outcome") if isinstance(native, dict) else None
    reason = native.get("reason") if isinstance(native, dict) else None
    if (
        outcome not in {"passed", "failed"}
        or not isinstance(reason, str)
        or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,127}", reason)
    ):
        return {
            **execution,
            "status": "failed",
            "reason": "invalid_native_result",
            "failure_class": "infrastructure",
        }
    return {
        **execution,
        "status": outcome,
        "reason": reason,
        "failure_class": None if outcome == "passed" else "agent_model_quality",
        "usage": _normalize_usage(native.get("usage")),
        "native_result_sha256": _sha256_text(redacted),
    }


def _apply_jsonl_contract(execution: dict[str, Any], path: Path) -> dict[str, Any]:
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            raise ValueError("empty JSONL stream")
        for line in lines:
            if not isinstance(json.loads(line), dict):
                raise ValueError("JSONL event must be an object")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return {
            **execution,
            "status": "failed",
            "reason": "invalid_jsonl_stream",
            "failure_class": "infrastructure",
        }
    return {**execution, "jsonl_event_count": len(lines)}


def _validate_target(target: dict[str, Any], where: str, *, mode: str) -> None:
    status = target.get("status", "unsupported")
    if status not in CONFIGURED_STATUSES:
        raise ValueError(f"{where}.status is invalid")
    for key in (
        "model",
        "model_revision",
        "platform_version",
        "endpoint_revision",
        "dependency_revision",
    ):
        if key in target:
            _metadata_string(target, key, prefix=f"{where}.")
    if status == "enabled":
        required_revisions = ["model", "model_revision", "dependency_revision"]
        required_revisions.append(
            "platform_version" if mode == "agentic_platform" else "endpoint_revision"
        )
        for key in required_revisions:
            _metadata_string(target, key, prefix=f"{where}.")
        command = target.get("command")
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(value, str) and value for value in command)
        ):
            raise ValueError(f"{where}.command must be a non-empty argv array")
        _validate_command_secrets(command, f"{where}.command")
        deploy_command = target.get("deploy_command")
        if deploy_command is not None:
            if (
                not isinstance(deploy_command, list)
                or not deploy_command
                or not all(isinstance(value, str) and value for value in deploy_command)
            ):
                raise ValueError(f"{where}.deploy_command must be a non-empty argv array")
            _validate_command_secrets(deploy_command, f"{where}.deploy_command")
    else:
        _machine_reason(target, "reason", prefix=f"{where}.")
    for key in ("credentials", "inherit_environment"):
        names = target.get(key, [])
        if not isinstance(names, list) or not all(
            isinstance(name, str) and ENV_NAME.fullmatch(name) for name in names
        ):
            raise ValueError(f"{where}.{key} must contain environment variable names")
        reserved = sorted(set(names) & RESERVED_CHILD_ENV)
        if reserved:
            raise ValueError(
                f"{where}.{key} contains reserved child variables: {', '.join(reserved)}"
            )
    _nonnegative_int(target, "estimated_tokens", default=0)
    _nonnegative_number(target, "estimated_cost_usd", default=0.0)
    streaming = target.get("streaming", "stdout-stderr")
    if streaming not in {"stdout-stderr", "jsonl"}:
        raise ValueError(f"{where}.streaming must be stdout-stderr or jsonl")
    result_file = target.get("result_file")
    if result_file is not None:
        if not isinstance(result_file, str) or not result_file:
            raise ValueError(f"{where}.result_file must be a relative path")
        result_path = Path(result_file)
        if result_path.is_absolute() or ".." in result_path.parts:
            raise ValueError(f"{where}.result_file must remain inside the isolated workspace")


def _expand_command(command: Sequence[Any], values: dict[str, str]) -> list[str]:
    if not isinstance(command, (list, tuple)):
        raise ValueError("command must be an argv array")
    expanded: list[str] = []
    for raw_value in command:
        value = str(raw_value)
        for name, replacement in values.items():
            value = value.replace(f"{{{name}}}", replacement)
        expanded.append(value)
    return expanded


def _redact(text: str, secrets: Sequence[str]) -> str:
    redacted = text
    for secret in sorted((value for value in secrets if value), key=len, reverse=True):
        redacted = redacted.replace(secret, "[REDACTED]")
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(
            lambda match: f"{match.group(1)}[REDACTED]" if match.lastindex else "[REDACTED]",
            redacted,
        )
    return redacted


def _stream_redacted(stream: IO[str], path: Path, secrets: Sequence[str]) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle, stream:
        for line in stream:
            handle.write(_redact(line, secrets))
            handle.flush()


def _validate_command_secrets(command: Sequence[str], where: str) -> None:
    if any(
        re.search(
            r"(?i)^--?(?:api[-_]?key|access[-_]?token|auth(?:orization)?|credential|token|password|secret)(?:=|$)",
            value,
        )
        or re.search(r"\b(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{12,}\b", value)
        for value in command
    ):
        raise ValueError(f"{where} must receive credentials through named environment variables")


def _normalize_usage(value: Any) -> dict[str, int | float]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, int | float] = {}
    tokens = value.get("tokens")
    if type(tokens) is int and tokens >= 0:
        normalized["tokens"] = tokens
    cost = value.get("cost_usd")
    if not isinstance(cost, bool) and isinstance(cost, (int, float)) and float(cost) >= 0:
        normalized["cost_usd"] = float(cost)
    return normalized


def _stop_process(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _git_revision(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unversioned"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_json(path: Path, value: dict[str, Any], *, mode: int) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, mode)
    temporary.replace(path)


def _write_private_text(path: Path, value: str) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(value)


def _validate_fixture(fixture: Path) -> None:
    for candidate in fixture.rglob("*"):
        if candidate.is_symlink():
            raise ValueError(f"fixture must not contain symbolic links: {candidate}")
        if not candidate.is_dir() and not candidate.is_file():
            raise ValueError(
                f"fixture must contain only regular files and directories: {candidate}"
            )


def _object(value: dict[str, Any], key: str) -> dict[str, Any]:
    result = value.get(key)
    if not isinstance(result, dict):
        raise ValueError(f"{key} must be an object")
    return result


def _string(value: dict[str, Any], key: str, *, prefix: str = "") -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"{prefix}{key} must be a non-empty string")
    return result


def _metadata_string(value: dict[str, Any], key: str, *, prefix: str = "") -> str:
    result = _string(value, key, prefix=prefix)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@+=-]{0,255}", result):
        raise ValueError(f"{prefix}{key} must be a bounded metadata identifier")
    return result


def _machine_reason(value: dict[str, Any], key: str, *, prefix: str = "") -> str:
    result = _string(value, key, prefix=prefix)
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{0,127}", result):
        raise ValueError(f"{prefix}{key} must be a machine-readable reason")
    return result


def _positive_int(value: dict[str, Any], key: str) -> int:
    result = value.get(key)
    if type(result) is not int or result <= 0:
        raise ValueError(f"{key} must be a positive integer")
    return result


def _nonnegative_int(value: dict[str, Any], key: str, *, default: int | None = None) -> int:
    result = value.get(key, default)
    if type(result) is not int or result < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return result


def _nonnegative_number(value: dict[str, Any], key: str, *, default: float | None = None) -> float:
    result = value.get(key, default)
    if (
        result is None
        or isinstance(result, bool)
        or not isinstance(result, (int, float))
        or float(result) < 0
    ):
        raise ValueError(f"{key} must be a non-negative number")
    return float(result)


def _relative_to(base: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    options = parser.parse_args(argv)
    report = AgenticPipeline(PipelineConfig.load(options.config)).run()
    print(json.dumps(report, sort_keys=True))
    return 0 if report["successful"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
