"""Tests for the official Terminal-Bench study bridge."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from matric_eval.studies import StudyProtocol

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"
SCRIPT = ROOT / "scripts/run_qwen38_terminal.py"
SPEC = importlib.util.spec_from_file_location("qwen38_terminal_runner", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
terminal_runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = terminal_runner
SPEC.loader.exec_module(terminal_runner)


def test_protocol_and_generation_seed_match_study_contract() -> None:
    protocol = StudyProtocol.from_yaml(PROTOCOL)
    model = protocol.models[0]
    study_data, model_data, sampler = terminal_runner._load_protocol(PROTOCOL, model.id)

    assert study_data["id"] == protocol.id
    assert model_data["checkpoint_revision"] == model.checkpoint_revision
    assert sampler["temperature"] == 1.0
    assert terminal_runner._generation_seed(
        protocol.seed, "largest-eigenval"
    ) == protocol.generation_seed("terminal-bench-2.1", "largest-eigenval")


@pytest.mark.parametrize("cohort", ["pilot", "full"])
def test_manifest_requires_exact_scored_ids(tmp_path: Path, cohort: str) -> None:
    selected = ["largest-eigenval", "extract-elf"]
    manifest = {
        "study_id": "study",
        "cohort": cohort,
        "allocations": [{"allocation_id": "terminal-bench-2.1", "selected_ids": selected}],
    }
    manifest_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest["manifest_sha256"] = manifest_hash
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    assert (
        terminal_runner._verify_manifest(
            path,
            {"manifest_sha256": manifest_hash, "cohort": cohort},
            selected,
            "study",
        )
        == manifest_hash
    )
    with pytest.raises(ValueError, match="exactly match"):
        terminal_runner._verify_manifest(
            path,
            {"manifest_sha256": manifest_hash, "cohort": cohort},
            list(reversed(selected)),
            "study",
        )


def test_agent_and_job_config_carry_full_sampler() -> None:
    sampler = {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repetition_penalty": 1.0,
        "max_tokens": 8192,
    }
    kwargs = terminal_runner._agent_kwargs("http://127.0.0.1:18080/v1", sampler, 123, 32768)
    calls = kwargs["llm_call_kwargs"]
    assert kwargs["temperature"] == 1.0
    assert kwargs["model_info"]["max_input_tokens"] == 24544
    assert kwargs["model_info"]["max_output_tokens"] == 8192
    assert (
        kwargs["model_info"]["max_input_tokens"]
        + kwargs["model_info"]["max_output_tokens"]
        + terminal_runner.CONTEXT_SAFETY_MARGIN_TOKENS
        == 32768
    )
    assert calls == {
        "top_p": 0.95,
        "presence_penalty": 0.0,
        "max_tokens": 8192,
        "seed": 123,
        "extra_body": {
            "top_k": 20,
            "min_p": 0.0,
            "repetition_penalty": 1.0,
            "chat_template_kwargs": {"enable_thinking": False},
        },
    }
    config = terminal_runner._job_config(
        jobs_dir=Path("/private/jobs"),
        job_name="one",
        tasks_dir=Path("/terminal/tasks"),
        task_id="largest-eigenval",
        model_id="model",
        agent_kwargs=kwargs,
    )
    assert config["n_concurrent_trials"] == 1
    assert config["retry"]["max_retries"] == 0
    assert config["agents"][0]["model_name"] == "hosted_vllm/model"
    assert config["agents"][0]["kwargs"]["model_info"]["max_input_tokens"] == 24544
    assert config["agents"][0]["kwargs"]["llm_call_kwargs"]["extra_body"] == calls["extra_body"]
    assert config["datasets"][0]["task_names"] == ["largest-eigenval"]


def test_context_budget_accepts_32768_and_rejects_32769() -> None:
    assert terminal_runner.CONTEXT_SAFETY_MARGIN_TOKENS >= 32
    budget = terminal_runner._context_budget(32768, 8192)
    assert budget == {
        "max_context_tokens": 32768,
        "max_input_tokens": 24544,
        "max_output_tokens": 8192,
        "safety_margin_tokens": 32,
    }
    terminal_runner._validate_context_allocation(24544, 8192, 32768)
    with pytest.raises(ValueError, match="32769 exceeds context limit 32768"):
        terminal_runner._validate_context_allocation(24545, 8192, 32768)
    with pytest.raises(ValueError, match="positive integer"):
        terminal_runner._context_budget(8224, 8192)
    with pytest.raises(ValueError, match="positive integer"):
        terminal_runner._agent_kwargs("http://127.0.0.1:18080/v1", {"max_tokens": 8192}, 123, 8224)
    with pytest.raises(ValueError, match="positive integer"):
        terminal_runner._context_budget(32768, True)
    with pytest.raises(ValueError, match="at least 32 tokens"):
        terminal_runner._validate_context_allocation(24545, 8192, 32768, 31)


def test_receipt_records_requested_budget_and_thinking_without_effective_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_id = "qwen38-27b-source-bf16"
    digest = "a" * 64
    checkout = tmp_path / "terminal"
    task_dir = checkout / "tasks" / "fixture-task"
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text("# fixture", encoding="utf-8")
    scored_ids = tmp_path / "ids.json"
    scored_ids.write_text('["fixture-task"]', encoding="utf-8")
    args = SimpleNamespace(
        protocol=PROTOCOL,
        manifest=tmp_path / "manifest",
        model_id=model_id,
        model_path=Path("/fixture/model"),
        terminal_checkout=checkout,
        harbor_python=Path(sys.executable),
        harbor_executable=Path("/fixture/harbor"),
        docker_daemon_config=tmp_path / "docker",
        expected_docker_daemon_config=tmp_path / "expected",
        inputs_summary=tmp_path / "summary",
        scored_ids=scored_ids,
        server_receipt=tmp_path / "server",
        endpoint="http://127.0.0.1:18083/v1",
        result_dir=tmp_path / "results",
        receipt=tmp_path / "receipt.json",
        resume_existing=False,
    )
    objects = {
        args.inputs_summary: {
            "protocol_sha256": digest,
            "scored_samples": {"terminal-bench-2.1": 1},
            "artifacts": {"terminal-bench-scored-ids.json": digest},
        },
        args.server_receipt: {
            "study_id": "qwen38-obliteration-2026-09",
            "model_id": model_id,
            "protocol_sha256": digest,
        },
    }
    monkeypatch.setattr(terminal_runner.platform, "node", lambda: "basilisk")
    monkeypatch.setattr(
        terminal_runner.importlib.metadata,
        "version",
        lambda _: terminal_runner.HARBOR_PACKAGE_VERSION,
    )
    monkeypatch.setattr(terminal_runner, "_private_path", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        terminal_runner, "_git_revision", lambda _: terminal_runner.TERMINAL_SOURCE_REVISION
    )
    monkeypatch.setattr(terminal_runner, "_require_clean_checkout", lambda _: None)
    monkeypatch.setattr(terminal_runner, "_docker_evidence", lambda *args: {})
    monkeypatch.setattr(terminal_runner, "_load_object", lambda path, _: objects[path])
    monkeypatch.setattr(terminal_runner, "_sha256_file", lambda _: digest)
    monkeypatch.setattr(terminal_runner, "_verify_manifest", lambda *args: digest)
    monkeypatch.setattr(terminal_runner, "_validate_endpoint", lambda *args: None)
    monkeypatch.setattr(terminal_runner, "_parse_job_result", lambda _: ({}, {"reward": 1}, None))
    captured = []

    def job_config(config: Any) -> SimpleNamespace:
        captured.append(config)
        return SimpleNamespace(model_dump=lambda **kwargs: config)

    def fake_harbor(*command: Any, **kwargs: Any) -> SimpleNamespace:
        job_dir = args.result_dir / terminal_runner._result_name("fixture-task")
        job_dir.mkdir()
        (job_dir / "result.json").write_text("{}", encoding="utf-8")
        return SimpleNamespace(returncode=0)

    modules = {
        name: ModuleType(name)
        for name in (
            "harbor",
            "harbor.models",
            "harbor.models.job",
            "harbor.models.job.config",
        )
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
        if "." in name:
            parent, child = name.rsplit(".", 1)
            setattr(modules[parent], child, module)
    modules["harbor.models.job.config"].JobConfig = SimpleNamespace(model_validate=job_config)
    monkeypatch.setattr(terminal_runner.subprocess, "run", fake_harbor)

    receipt = terminal_runner.run_terminal(args)

    assert len(captured) == 1
    kwargs = captured[0]["agents"][0]["kwargs"]
    assert kwargs["model_info"]["max_input_tokens"] == 24544
    assert kwargs["llm_call_kwargs"]["extra_body"]["chat_template_kwargs"] == {
        "enable_thinking": False
    }
    execution = receipt["execution"]
    assert execution["context_budget"] == terminal_runner._context_budget(32768, 8192)
    assert (
        execution["context_budget_enforcement"]
        == "harbor-model-info-input-limit-requested-unverified"
    )
    assert execution["target_thinking_mode_requested"] == "disabled"
    assert "target_thinking_mode" not in execution
    assert json.loads(args.receipt.read_text())["execution"] == execution


@pytest.mark.parametrize(
    "field", ["input_tokens", "output_tokens", "context_limit", "safety_margin"]
)
@pytest.mark.parametrize(
    "invalid", [0, -1, True, False, 1.0, "1", None, float("nan"), float("inf")]
)
def test_context_allocation_rejects_nonpositive_or_noninteger_values(
    field: str, invalid: Any
) -> None:
    allocation = {
        "input_tokens": 24544,
        "output_tokens": 8192,
        "context_limit": 32768,
        "safety_margin": 32,
    }
    allocation[field] = invalid
    with pytest.raises(ValueError, match="positive integer"):
        terminal_runner._validate_context_allocation(**allocation)


@pytest.mark.parametrize("field", ["context_limit", "output_tokens"])
@pytest.mark.parametrize("invalid", [0, -1, True, 32768.0, "32768", None])
def test_context_budget_rejects_types_before_arithmetic(field: str, invalid: Any) -> None:
    allocation = {"context_limit": 32768, "output_tokens": 8192}
    allocation[field] = invalid
    with pytest.raises(ValueError, match="positive integer"):
        terminal_runner._context_budget(**allocation)


@pytest.mark.parametrize(
    ("context_limit", "output_tokens", "expected_input"),
    [(8225, 8192, 1), (32768, 4096, 28640), (34, 1, 1), (65536, 8192, 57312)],
)
def test_context_budget_reserves_output_and_margin_at_all_sizes(
    context_limit: int, output_tokens: int, expected_input: int
) -> None:
    budget = terminal_runner._context_budget(context_limit, output_tokens)
    assert budget["max_input_tokens"] == expected_input
    assert budget["max_output_tokens"] == output_tokens
    assert budget["max_context_tokens"] == context_limit
    assert budget["safety_margin_tokens"] == 32
    assert json.loads(json.dumps(budget)) == budget


def test_larger_context_margin_is_honored() -> None:
    terminal_runner._validate_context_allocation(24512, 8192, 32768, 64)
    with pytest.raises(ValueError, match="32769 exceeds"):
        terminal_runner._validate_context_allocation(24513, 8192, 32768, 64)


def test_help_does_not_run_preflight_or_access_services(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("help must not execute the runner or access services")

    monkeypatch.setattr(terminal_runner, "run_terminal", forbidden)
    monkeypatch.setattr(terminal_runner.subprocess, "run", forbidden)
    monkeypatch.setattr(terminal_runner.urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(terminal_runner.importlib.metadata, "version", forbidden)
    with pytest.raises(SystemExit) as result:
        terminal_runner.main(["--help"])
    assert result.value.code == 0
    assert "--model-id" in capsys.readouterr().out


def test_endpoint_and_job_result_parsing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int) -> bytes:
            return json.dumps({"data": [{"id": "model"}, {"id": "/qualified/model"}]}).encode()[
                :size
            ]

    monkeypatch.setattr(
        terminal_runner.urllib.request, "urlopen", lambda *args, **kwargs: Response()
    )
    terminal_runner._validate_endpoint(
        "http://127.0.0.1:18080/v1", "model", Path("/qualified/model")
    )

    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "trial_results": [
                    {
                        "verifier_result": {"rewards": {"reward": 1}},
                        "exception_info": None,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    _, rewards, exception = terminal_runner._parse_job_result(result_path)
    assert rewards == {"reward": 1}
    assert exception is None


def test_harbor_022_nested_trial_result_parsing(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    result_path = job_dir / "result.json"
    result_path.write_text(json.dumps({"n_total_trials": 1}), encoding="utf-8")
    trial_dir = job_dir / "task__trial"
    trial_dir.mkdir()
    (trial_dir / "result.json").write_text(
        json.dumps(
            {
                "verifier_result": {"rewards": {"reward": 0}},
                "exception_info": {"exception_type": "AgentTimeoutError"},
            }
        ),
        encoding="utf-8",
    )

    _, rewards, exception = terminal_runner._parse_job_result(result_path)

    assert rewards == {"reward": 0}
    assert exception == "AgentTimeoutError"


def test_retained_job_duration_uses_harbor_timestamps() -> None:
    assert (
        terminal_runner._result_duration_seconds(
            {
                "started_at": "2026-09-06T13:57:00+00:00",
                "finished_at": "2026-09-06T14:13:10+00:00",
            }
        )
        == 970.0
    )
    with pytest.raises(RuntimeError, match="negative execution time"):
        terminal_runner._result_duration_seconds(
            {
                "started_at": "2026-09-06T14:13:10Z",
                "finished_at": "2026-09-06T13:57:00Z",
            }
        )


def test_retained_job_config_normalizes_only_set_backed_exclusions() -> None:
    actual = {
        "retry": {"max_retries": 0, "exclude_exceptions": ["Timeout", "Parse"]},
        "job_name": "job",
    }
    expected = {
        "retry": {"max_retries": 0, "exclude_exceptions": ["Parse", "Timeout"]},
        "job_name": "job",
    }

    assert terminal_runner._job_configs_match(actual, expected)
    expected["job_name"] = "different"
    assert not terminal_runner._job_configs_match(actual, expected)


def test_harbor_022_nested_trial_result_must_be_unique(tmp_path: Path) -> None:
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps({"n_total_trials": 1}), encoding="utf-8")
    for name in ("trial-one", "trial-two"):
        trial_dir = tmp_path / name
        trial_dir.mkdir()
        (trial_dir / "result.json").write_text("{}", encoding="utf-8")

    with pytest.raises(RuntimeError, match="exactly one nested trial result"):
        terminal_runner._parse_job_result(result_path)


def test_resume_existing_is_explicit() -> None:
    args = terminal_runner.build_parser().parse_args(
        [
            "protocol.yaml",
            "manifest.json",
            "--model-id",
            "model",
            "--model-path",
            "/model",
            "--server-receipt",
            "/receipt.json",
            "--terminal-checkout",
            "/terminal",
            "--harbor-python",
            "/venv/python",
            "--harbor-executable",
            "/venv/harbor",
            "--inputs-summary",
            "/inputs.json",
            "--scored-ids",
            "/ids.json",
            "--result-dir",
            "/results",
            "--receipt",
            "/terminal-receipt.json",
            "--resume-existing",
        ]
    )

    assert args.resume_existing is True


def test_result_names_are_content_free_and_stable() -> None:
    one = terminal_runner._result_name("largest-eigenval")
    two = terminal_runner._result_name("extract-elf")
    assert one.startswith("terminal-")
    assert one != two
    assert "eigenval" not in one


def test_isolated_docker_network_contract() -> None:
    terminal_runner._validate_docker_config(
        {
            "data-root": "/srv/obliteratus/matric-eval/docker/data",
            "bridge": "none",
            "iptables": True,
            "ip-forward": True,
            "ip-masq": True,
            "default-address-pools": [{"base": "10.241.0.0/16", "size": 24}],
        }
    )
    with pytest.raises(RuntimeError, match="iptables"):
        terminal_runner._validate_docker_config(
            {
                "data-root": "/srv/obliteratus/matric-eval/docker/data",
                "bridge": "none",
                "iptables": False,
                "ip-forward": True,
                "ip-masq": True,
                "default-address-pools": [{"base": "10.241.0.0/16", "size": 24}],
            }
        )


def test_private_tree_is_sealed_and_rejects_links(tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    nested = root / "nested"
    nested.mkdir(parents=True)
    artifact = nested / "result.json"
    artifact.write_text("private", encoding="utf-8")

    terminal_runner._seal_private_tree(root)

    assert root.stat().st_mode & 0o777 == 0o750
    assert nested.stat().st_mode & 0o777 == 0o750
    assert artifact.stat().st_mode & 0o777 == 0o600

    (root / "link").symlink_to(artifact)
    with pytest.raises(RuntimeError, match="symbolic link"):
        terminal_runner._seal_private_tree(root)
