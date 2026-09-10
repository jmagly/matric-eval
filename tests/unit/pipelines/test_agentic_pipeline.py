"""Tests for the registry-derived agent-platform pipeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from matric_eval.pipelines import agentic
from matric_eval.pipelines.agentic import (
    AgenticPipeline,
    PipelineConfig,
    ProviderInventory,
    parse_aiwg_provider_inventory,
)


def _config(
    tmp_path: Path,
    *,
    providers: dict[str, object] | None = None,
    direct_endpoints: list[dict[str, object]] | None = None,
    max_tokens: int = 10_000,
    timeout_seconds: int = 10,
    infrastructure_retries: int = 1,
) -> Path:
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "README.md").write_text("fixture\n", encoding="utf-8")
    path = tmp_path / "pipeline.json"
    path.write_text(
        json.dumps(
            {
                "schema": "matric-eval.agentic-pipeline/1",
                "aiwg": {"version": "1.2.3"},
                "fixture": "fixture",
                "output": "output",
                "scenario": {
                    "id": "smoke",
                    "benchmark_id": "aiwg_smoke",
                    "revision": "fixture-v1",
                    "tier": "smoke",
                    "prompt": "name the fixture",
                },
                "limits": {
                    "max_concurrency": 2,
                    "timeout_seconds": timeout_seconds,
                    "infrastructure_retries": infrastructure_retries,
                    "max_tokens": max_tokens,
                    "max_cost_usd": 2.0,
                },
                "providers": providers or {},
                "direct_endpoints": direct_endpoints or [],
            }
        ),
        encoding="utf-8",
    )
    return path


def _inventory(*providers: str) -> ProviderInventory:
    return ProviderInventory(
        providers=providers,
        command=("aiwg", "help"),
        output_sha256="a" * 64,
        version="1.2.3",
    )


def _enabled_target(**overrides: object) -> dict[str, object]:
    return {
        "status": "enabled",
        "command": [sys.executable, "-c", "pass"],
        "model": "test-model",
        "model_revision": "test-model-r1",
        "dependency_revision": "locked-test-environment",
        "platform_version": "test-platform-1",
        **overrides,
    }


def test_parse_aiwg_provider_inventory_strips_alias_note_and_ansi() -> None:
    output = (
        "\x1b[36m Providers:\x1b[0m 8 — claude, codex, copilot, cursor, factory, "
        "opencode, warp, windsurf (default: claude; aliases: devin → windsurf)\n"
    )

    assert parse_aiwg_provider_inventory(output) == (
        "claude",
        "codex",
        "copilot",
        "cursor",
        "factory",
        "opencode",
        "warp",
        "windsurf",
    )


def test_parse_aiwg_provider_inventory_fails_closed() -> None:
    with pytest.raises(ValueError, match="provider inventory"):
        parse_aiwg_provider_inventory("AIWG help without a registry line")

    with pytest.raises(ValueError, match="declared 2 providers but exposed 1"):
        parse_aiwg_provider_inventory("Providers: 2 — codex\n")


def test_configured_provider_absent_from_registry_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agentic,
        "discover_aiwg_provider_inventory",
        lambda executable="aiwg": _inventory("codex"),
    )
    path = _config(
        tmp_path,
        providers={"retired-provider": {"status": "unsupported", "reason": "legacy"}},
    )

    with pytest.raises(ValueError, match="absent from the current AIWG registry"):
        AgenticPipeline(PipelineConfig.load(path)).run()


def test_config_rejects_secret_values_in_credential_name_list(tmp_path: Path) -> None:
    path = _config(
        tmp_path,
        providers={
            "codex": _enabled_target(command=["codex"], credentials=["sk-not-an-environment-name"])
        },
    )

    with pytest.raises(ValueError, match="environment variable names"):
        PipelineConfig.load(path)


def test_config_rejects_native_result_path_escape(tmp_path: Path) -> None:
    path = _config(
        tmp_path,
        providers={
            "codex": _enabled_target(command=["codex"], result_file="../foreign-result.json")
        },
    )

    with pytest.raises(ValueError, match="isolated workspace"):
        PipelineConfig.load(path)


def test_config_rejects_narrative_disposition_reason(tmp_path: Path) -> None:
    path = _config(
        tmp_path,
        providers={"codex": {"status": "unsupported", "reason": "This is prose, not a code."}},
    )

    with pytest.raises(ValueError, match="machine-readable reason"):
        PipelineConfig.load(path)


def test_config_rejects_fixture_symlinks_and_overlapping_output(tmp_path: Path) -> None:
    symlinked = _config(tmp_path)
    (tmp_path / "fixture" / "foreign").symlink_to(tmp_path / "pipeline.json")
    with pytest.raises(ValueError, match="symbolic links"):
        PipelineConfig.load(symlinked)

    (tmp_path / "fixture" / "foreign").unlink()
    raw = json.loads(symlinked.read_text(encoding="utf-8"))
    raw["output"] = "fixture/output"
    symlinked.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="must not overlap"):
        PipelineConfig.load(symlinked)


def test_config_rejects_duplicate_direct_endpoints_and_reserved_environment(
    tmp_path: Path,
) -> None:
    duplicate = {"id": "ollama", "status": "unavailable", "reason": "not_configured"}
    with pytest.raises(ValueError, match="duplicate id"):
        PipelineConfig.load(_config(tmp_path, direct_endpoints=[duplicate, duplicate.copy()]))

    raw = json.loads((tmp_path / "pipeline.json").read_text(encoding="utf-8"))
    raw["direct_endpoints"] = []
    raw["providers"] = {"codex": _enabled_target(inherit_environment=["HOME"])}
    (tmp_path / "pipeline.json").write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="reserved child variables: HOME"):
        PipelineConfig.load(tmp_path / "pipeline.json")


def test_config_rejects_command_line_secret_flags(tmp_path: Path) -> None:
    path = _config(
        tmp_path,
        providers={"codex": _enabled_target(command=["codex", "--api-key=not-allowed"])},
    )

    with pytest.raises(ValueError, match="named environment variables"):
        PipelineConfig.load(path)


def test_config_rejects_deploy_command_secret_flags(tmp_path: Path) -> None:
    path = _config(
        tmp_path,
        providers={
            "codex": _enabled_target(
                command=["codex"], deploy_command=["aiwg", "--token", "not-allowed"]
            )
        },
    )

    with pytest.raises(ValueError, match="named environment variables"):
        PipelineConfig.load(path)


def test_installed_aiwg_version_must_match_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agentic,
        "discover_aiwg_provider_inventory",
        lambda executable="aiwg": ProviderInventory(
            providers=("codex",),
            command=("aiwg", "help"),
            output_sha256="a" * 64,
            version="different-version",
        ),
    )

    with pytest.raises(RuntimeError, match="does not match installed version"):
        AgenticPipeline(PipelineConfig.load(_config(tmp_path))).run()


def test_matrix_covers_every_aiwg_provider_and_keeps_modes_distinct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agentic,
        "discover_aiwg_provider_inventory",
        lambda executable="aiwg": _inventory("codex", "warp", "new-provider"),
    )
    path = _config(
        tmp_path,
        providers={
            "codex": {"status": "unsupported", "reason": "headless_not_configured"},
            "warp": {"status": "intentionally_skipped", "reason": "manual_ui_required"},
        },
        direct_endpoints=[
            {
                "id": "ollama-local",
                "status": "unavailable",
                "reason": "endpoint_not_provisioned",
            }
        ],
    )

    report = AgenticPipeline(PipelineConfig.load(path)).run()

    assert report["coverage_complete"] is True
    by_target = {(item["execution_mode"], item["target"]): item for item in report["results"]}
    assert by_target[("agentic_platform", "new-provider")]["reason"] == "adapter_not_configured"
    assert by_target[("agentic_platform", "warp")]["status"] == "intentionally_skipped"
    assert by_target[("direct_endpoint", "ollama-local")]["status"] == "unavailable"


def test_configured_direct_endpoint_executes_without_agent_platform_deployment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agentic,
        "discover_aiwg_provider_inventory",
        lambda executable="aiwg": _inventory("codex"),
    )
    path = _config(
        tmp_path,
        direct_endpoints=[
            {
                **_enabled_target(),
                "id": "ollama-local",
                "endpoint_revision": "ollama-0.11.10",
            }
        ],
    )

    report = AgenticPipeline(PipelineConfig.load(path)).run()

    result = next(item for item in report["results"] if item["execution_mode"] == "direct_endpoint")
    assert result["status"] == "passed"
    assert result["runtime"]["endpoint_revision"] == "ollama-0.11.10"
    assert result["attempts"][0]["reason"] == "completed"


def test_enabled_adapter_isolated_execution_redacts_credentials_and_parses_quality(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agentic,
        "discover_aiwg_provider_inventory",
        lambda executable="aiwg": _inventory("codex"),
    )
    monkeypatch.setenv("PIPELINE_TOKEN", "secret-value-123")
    monkeypatch.setenv("PIPELINE_CONTEXT", "sensitive-context-456")
    invoke = (
        "import json, os; "
        "print('token=' + os.environ['PIPELINE_TOKEN'] + os.environ['PIPELINE_CONTEXT']); "
        "open('result.json', 'w').write(json.dumps("
        "{'outcome':'failed','reason':'assertion_missed','usage':{'tokens':12},"
        "'note':os.environ['PIPELINE_TOKEN']}))"
    )
    path = _config(
        tmp_path,
        providers={
            "codex": _enabled_target(
                deploy_command=[sys.executable, "-c", "print('deployed')"],
                command=[sys.executable, "-c", invoke],
                credentials=["PIPELINE_TOKEN"],
                inherit_environment=["PIPELINE_CONTEXT"],
                estimated_tokens=100,
                estimated_cost_usd=0.1,
                result_file="result.json",
            )
        },
    )

    report = AgenticPipeline(PipelineConfig.load(path)).run()

    result = report["results"][0]
    assert result["status"] == "failed"
    assert result["failure_class"] == "agent_model_quality"
    assert result["reason"] == "assertion_missed"
    assert result["usage"] == {"tokens": 12}
    assert report["successful"] is False
    evidence = PipelineConfig.load(path).output / result["evidence"]
    assert "secret-value-123" not in (evidence / "invoke.stdout.log").read_text(encoding="utf-8")
    assert "sensitive-context-456" not in (evidence / "invoke.stdout.log").read_text(
        encoding="utf-8"
    )
    assert "[REDACTED]" in (evidence / "invoke.stdout.log").read_text(encoding="utf-8")
    retained = (evidence / "invoke.native-result.json").read_text(encoding="utf-8")
    assert "secret-value-123" not in retained
    assert "[REDACTED]" in retained


@pytest.mark.parametrize(
    ("output", "expected_status", "expected_reason"),
    [
        ('print(\'{"event":"completed"}\')', "passed", "completed"),
        ("print('not-json')", "failed", "invalid_jsonl_stream"),
    ],
)
def test_jsonl_streaming_contract_is_enforced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output: str,
    expected_status: str,
    expected_reason: str,
) -> None:
    monkeypatch.setattr(
        agentic,
        "discover_aiwg_provider_inventory",
        lambda executable="aiwg": _inventory("codex"),
    )
    path = _config(
        tmp_path,
        infrastructure_retries=0,
        providers={
            "codex": _enabled_target(
                deploy_command=[sys.executable, "-c", "pass"],
                command=[sys.executable, "-c", output],
                streaming="jsonl",
            )
        },
    )

    result = AgenticPipeline(PipelineConfig.load(path)).run()["results"][0]

    assert result["status"] == expected_status
    assert result["reason"] == expected_reason
    if expected_status == "passed":
        assert result["jsonl_event_count"] == 1
        assert result["deployment"]["status"] == "passed"


def test_missing_credentials_and_budget_are_typed_without_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agentic,
        "discover_aiwg_provider_inventory",
        lambda executable="aiwg": _inventory("codex", "claude"),
    )
    monkeypatch.delenv("ABSENT_PIPELINE_TOKEN", raising=False)
    path = _config(
        tmp_path,
        max_tokens=50,
        providers={
            "codex": _enabled_target(
                command=[sys.executable, "-c", "raise SystemExit(99)"],
                credentials=["ABSENT_PIPELINE_TOKEN"],
            ),
            "claude": _enabled_target(
                command=[sys.executable, "-c", "raise SystemExit(99)"],
                estimated_tokens=100,
            ),
        },
    )

    report = AgenticPipeline(PipelineConfig.load(path)).run()

    by_target = {item["target"]: item for item in report["results"]}
    assert by_target["codex"]["reason"] == "missing_credentials"
    assert by_target["claude"]["reason"] == "budget_exhausted"
    assert list((PipelineConfig.load(path).output / "private").iterdir()) == []


def test_infrastructure_failure_retries_but_quality_failure_does_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agentic,
        "discover_aiwg_provider_inventory",
        lambda executable="aiwg": _inventory("codex"),
    )
    marker = tmp_path / "retry-marker"
    invoke = (
        "from pathlib import Path; "
        f"p=Path({str(marker)!r}); "
        "seen=p.exists(); p.write_text('seen'); raise SystemExit(0 if seen else 3)"
    )
    path = _config(
        tmp_path,
        providers={
            "codex": _enabled_target(
                deploy_command=[sys.executable, "-c", "pass"],
                command=[sys.executable, "-c", invoke],
            )
        },
    )

    result = AgenticPipeline(PipelineConfig.load(path)).run()["results"][0]

    assert result["status"] == "passed"
    assert len(result["attempts"]) == 2
    assert result["attempts"][0]["failure_class"] == "infrastructure"


def test_each_retry_reserves_budget_and_exhaustion_remains_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        agentic,
        "discover_aiwg_provider_inventory",
        lambda executable="aiwg": _inventory("codex"),
    )
    path = _config(
        tmp_path,
        max_tokens=150,
        providers={
            "codex": _enabled_target(
                deploy_command=[sys.executable, "-c", "pass"],
                command=[sys.executable, "-c", "raise SystemExit(3)"],
                estimated_tokens=100,
            )
        },
    )

    report = AgenticPipeline(PipelineConfig.load(path)).run()

    result = report["results"][0]
    assert result["status"] == "failed"
    assert result["reason"] == "retry_budget_exhausted"
    assert len(result["attempts"]) == 1
    assert report["successful"] is False


def test_timeout_and_kill_switch_are_typed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agentic,
        "discover_aiwg_provider_inventory",
        lambda executable="aiwg": _inventory("codex"),
    )
    path = _config(
        tmp_path,
        timeout_seconds=1,
        infrastructure_retries=0,
        providers={
            "codex": _enabled_target(
                deploy_command=[sys.executable, "-c", "pass"],
                command=[sys.executable, "-c", "import time; time.sleep(5)"],
            )
        },
    )
    timeout_result = AgenticPipeline(PipelineConfig.load(path)).run()["results"][0]
    assert timeout_result["reason"] == "timeout"
    assert timeout_result["failure_class"] == "infrastructure"

    config = PipelineConfig.load(path)
    (config.output / "KILL").write_text("operator stop\n", encoding="utf-8")
    killed_result = AgenticPipeline(config).run()["results"][0]
    assert killed_result["status"] == "intentionally_skipped"
    assert killed_result["reason"] == "kill_switch_active"
