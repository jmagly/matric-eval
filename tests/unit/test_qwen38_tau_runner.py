"""Tests for the official tau3-bench study bridge."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from matric_eval.studies import StudyProtocol

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"
SCRIPT = ROOT / "scripts/run_qwen38_tau.py"
SPEC = importlib.util.spec_from_file_location("qwen38_tau_runner", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
tau_runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tau_runner
SPEC.loader.exec_module(tau_runner)


def test_protocol_and_generation_seed_match_study_contract() -> None:
    protocol = StudyProtocol.from_yaml(PROTOCOL)
    model = protocol.models[0]
    study_data, model_data, sampler = tau_runner._load_protocol(PROTOCOL, model.id)

    assert study_data["id"] == protocol.id
    assert model_data["checkpoint_revision"] == model.checkpoint_revision
    assert sampler["temperature"] == 1.0
    assert tau_runner._generation_seed(protocol.seed, "retail:43") == protocol.generation_seed(
        "tau3-bench", "retail:43"
    )

    with pytest.raises(ValueError, match="unknown study model"):
        tau_runner._load_protocol(PROTOCOL, "unknown")


@pytest.mark.parametrize("cohort", ["pilot", "full"])
def test_manifest_and_scored_ids_restore_exact_order(tmp_path: Path, cohort: str) -> None:
    scored = {"airline": ["3"], "retail": ["43", "47"]}
    flattened = tau_runner._flatten_scored_ids(scored)
    assert flattened == ["airline:3", "retail:43", "retail:47"]

    selected = ["retail:43", "airline:3", "retail:47"]
    manifest = {
        "study_id": "study",
        "cohort": cohort,
        "allocations": [{"allocation_id": "tau3-bench", "selected_ids": selected}],
    }
    manifest_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest["manifest_sha256"] = manifest_hash
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    assert (
        tau_runner._verify_manifest(
            path,
            {"manifest_sha256": manifest_hash, "cohort": cohort},
            flattened,
            "study",
        )
        == manifest_hash
    )
    grouped = list(reversed(flattened))
    tau_runner._verify_manifest(
        path, {"manifest_sha256": manifest_hash, "cohort": cohort}, grouped, "study"
    )
    assert grouped == selected
    assert json.loads(path.read_text())["allocations"][0]["selected_ids"] == selected
    for invalid in (flattened[:-1], flattened + [flattened[0]], ["substituted:1", *flattened[1:]]):
        with pytest.raises(ValueError, match="exactly match"):
            tau_runner._verify_manifest(
                path, {"manifest_sha256": manifest_hash, "cohort": cohort}, invalid, "study"
            )
    manifest["study_id"] = "tampered"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="hash"):
        tau_runner._verify_manifest(
            path, {"manifest_sha256": manifest_hash, "cohort": cohort}, flattened, "study"
        )


def test_sampler_and_external_args_are_sealed(tmp_path: Path) -> None:
    sampler = {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 0.0,
        "repetition_penalty": 1.0,
        "max_tokens": 8192,
    }
    agent_args = tau_runner._agent_args("http://127.0.0.1:18080/v1", sampler, 32768)
    assert agent_args == {
        "api_base": "http://127.0.0.1:18080/v1",
        "api_key": "EMPTY",
        "temperature": 1.0,
        "top_p": 0.95,
        "presence_penalty": 0.0,
        "max_tokens": 8192,
        "num_retries": 0,
        "extra_body": {
            "top_k": 20,
            "min_p": 0.0,
            "repetition_penalty": 1.0,
            "chat_template_kwargs": {"enable_thinking": False},
        },
    }
    budget = tau_runner._context_budget(32768, agent_args["max_tokens"])
    assert (
        budget["max_input_tokens"] + budget["max_output_tokens"] + budget["safety_margin_tokens"]
        == budget["max_context_tokens"]
    )
    assert tau_runner._load_external_args(None) == {"temperature": 0.0}

    secret_args = tmp_path / "secret.json"
    secret_args.write_text('{"api_key": "must-not-be-recorded"}', encoding="utf-8")
    with pytest.raises(ValueError, match="file descriptor"):
        tau_runner._load_external_args(secret_args)

    nested_secret_args = tmp_path / "nested-secret.json"
    nested_secret_args.write_text(
        '{"extra_headers": {"authorization_token": "must-not-be-recorded"}}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="file descriptor"):
        tau_runner._load_external_args(nested_secret_args)

    seeded_args = tmp_path / "seeded.json"
    seeded_args.write_text('{"seed": 7}', encoding="utf-8")
    with pytest.raises(ValueError, match="derives"):
        tau_runner._load_external_args(seeded_args)


def test_context_budget_accepts_32768_and_rejects_32769() -> None:
    assert tau_runner.CONTEXT_SAFETY_MARGIN_TOKENS >= 32
    budget = tau_runner._context_budget(32768, 8192)
    assert budget == {
        "max_context_tokens": 32768,
        "max_input_tokens": 24544,
        "max_output_tokens": 8192,
        "safety_margin_tokens": 32,
    }
    tau_runner._validate_context_allocation(24544, 8192, 32768)
    with pytest.raises(ValueError, match="32769 exceeds context limit 32768"):
        tau_runner._validate_context_allocation(24545, 8192, 32768)
    with pytest.raises(ValueError, match="positive integer"):
        tau_runner._context_budget(8224, 8192)
    with pytest.raises(ValueError, match="positive integer"):
        tau_runner._agent_args("http://127.0.0.1:18080/v1", {"max_tokens": 8192}, 8224)
    with pytest.raises(ValueError, match="positive integer"):
        tau_runner._context_budget(32768, True)
    with pytest.raises(ValueError, match="at least 32 tokens"):
        tau_runner._validate_context_allocation(24545, 8192, 32768, 31)


def test_context_overflow_has_typed_nonretryable_attribution() -> None:
    exc = tau_runner.TargetContextRuntimeInvalid(
        {
            "input_tokens": 24545,
            "output_tokens": 8192,
            "safety_margin_tokens": 32,
            "combined_tokens": 32769,
            "context_limit": 32768,
        }
    )
    failure = tau_runner._context_invalid_failure(exc)
    assert failure["owner"] == "context-runtime"
    assert failure["actor"] == "runner"
    assert failure["stage"] == "context-budget"
    assert failure["http_attempted"] is False
    assert failure["side_effect_retry_attempted"] is False
    assert failure["exception_chain"][0]["type"] == "TargetContextRuntimeInvalid"


@pytest.mark.parametrize(
    ("actor", "stage", "reason", "owner"),
    [
        ("target-model", "target-sampling", "sampling_failure", "target-model"),
        ("user-simulator", "simulator-sampling", "html_response_body", "simulator"),
        ("evaluator", "nl-evaluation", "truncated_json_response", "evaluator"),
        (
            "harness-interface",
            "llm-sampling",
            "empty_response_body",
            "harness-interface",
        ),
    ],
)
def test_typed_tau_runtime_failures_are_analytic_invalid_attributions(
    actor: str, stage: str, reason: str, owner: str
) -> None:
    class RuntimeInvalid(RuntimeError):
        def __init__(self) -> None:
            self.evidence = {
                "actor": actor,
                "stage": stage,
                "reason": reason,
                "http_attempted": True,
                "retryable": True,
                "side_effect_retry_attempted": False,
                "recovery_attempted": True,
            }
            super().__init__("content-free typed failure")

    failure = tau_runner._runtime_invalid_failure(RuntimeInvalid())
    assert failure["owner"] == owner
    assert failure["actor"] == actor
    assert failure["stage"] == stage
    assert failure["reason"] == reason
    assert failure["retryable"] is False
    assert failure["side_effect_retry_attempted"] is False
    assert failure["recovery_attempted"] is True
    assert len(failure["exception_chain"]) == 1


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
        tau_runner._validate_context_allocation(**allocation)


@pytest.mark.parametrize("field", ["context_limit", "output_tokens"])
@pytest.mark.parametrize("invalid", [0, -1, True, 32768.0, "32768", None])
def test_context_budget_rejects_types_before_arithmetic(field: str, invalid: Any) -> None:
    allocation = {"context_limit": 32768, "output_tokens": 8192}
    allocation[field] = invalid
    with pytest.raises(ValueError, match="positive integer"):
        tau_runner._context_budget(**allocation)


@pytest.mark.parametrize(
    ("context_limit", "output_tokens", "expected_input"),
    [(8225, 8192, 1), (32768, 4096, 28640), (34, 1, 1), (65536, 8192, 57312)],
)
def test_context_budget_reserves_output_and_margin_at_all_sizes(
    context_limit: int, output_tokens: int, expected_input: int
) -> None:
    budget = tau_runner._context_budget(context_limit, output_tokens)
    assert budget["max_input_tokens"] == expected_input
    assert budget["max_output_tokens"] == output_tokens
    assert budget["max_context_tokens"] == context_limit
    assert budget["safety_margin_tokens"] == 32
    assert json.loads(json.dumps(budget)) == budget


def test_larger_context_margin_is_honored() -> None:
    tau_runner._validate_context_allocation(24512, 8192, 32768, 64)
    with pytest.raises(ValueError, match="32769 exceeds"):
        tau_runner._validate_context_allocation(24513, 8192, 32768, 64)


def test_help_does_not_run_preflight_or_access_services(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("help must not execute the runner or access services")

    monkeypatch.setattr(tau_runner, "run_tau", forbidden)
    monkeypatch.setattr(tau_runner.subprocess, "run", forbidden)
    monkeypatch.setattr(tau_runner.urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(tau_runner.importlib.metadata, "version", forbidden)
    with pytest.raises(SystemExit) as result:
        tau_runner.main(["--help"])
    assert result.value.code == 0
    assert "--model-id" in capsys.readouterr().out


def test_external_key_uses_one_shot_descriptor_and_is_redacted() -> None:
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"test-external-secret\n")
    os.close(write_fd)

    secret = tau_runner._read_secret_fd(read_fd)
    assert secret == "test-external-secret"
    with pytest.raises(OSError):
        os.read(read_fd, 1)
    with pytest.raises(ValueError, match="3 or greater"):
        tau_runner._read_secret_fd(0)

    payload = {
        "info": {
            "llm_args": {
                "api_key": secret,
                "nested": [{"authorization_token": secret}],
                "temperature": 0.0,
            }
        }
    }
    redacted = tau_runner._redact_sensitive(payload)
    assert secret not in json.dumps(redacted)
    assert redacted["info"]["llm_args"]["api_key"] == "<redacted>"
    assert redacted["info"]["llm_args"]["temperature"] == 0.0


def test_tau_external_model_is_an_immutable_snapshot() -> None:
    parser = tau_runner.build_parser()
    model_actions = {
        action.dest: action
        for action in parser._actions
        if action.dest in {"user_model", "nl_evaluator_model"}
    }
    assert set(model_actions) == {"user_model", "nl_evaluator_model"}
    assert tau_runner.TAU_EXTERNAL_MODEL == "gpt-4.1-2025-04-14"


def test_endpoint_and_private_result_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int) -> bytes:
            return json.dumps({"data": [{"id": "model"}, {"id": "/qualified/model"}]}).encode()[
                :size
            ]

    monkeypatch.setattr(tau_runner.urllib.request, "urlopen", lambda *args, **kwargs: Response())
    tau_runner._validate_endpoint("http://127.0.0.1:18080/v1", "model", Path("/qualified/model"))
    with pytest.raises(ValueError, match="localhost"):
        tau_runner._validate_endpoint("http://example.com/v1", "model", Path("/qualified/model"))

    first = tau_runner._result_filename("telecom:one")
    second = tau_runner._result_filename("telecom:two")
    assert first.startswith("task-") and first.endswith(".json")
    assert first != second


def test_target_counter_requires_exact_server_template_context_and_parsers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_path = Path("/qualified/model")
    template = Path("/private/chat-template.jinja")
    receipt = {
        "chat_template_sha256": "a" * 64,
        "runtime": {
            "versions": {"transformers": "5.14.1"},
            "arguments": [
                str(model_path),
                "--host",
                "127.0.0.1",
                "--chat-template",
                str(template),
                "--max-model-len",
                "32768",
                "--language-model-only",
                "--enable-auto-tool-choice",
                "--reasoning-parser",
                "qwen3",
                "--tool-call-parser",
                "qwen3_coder",
            ],
        },
    }
    captured: dict[str, Any] = {}

    def loader(**kwargs: Any) -> tuple[str, dict[str, str]]:
        captured.update(kwargs)
        return "counter", {"status": "attested"}

    monkeypatch.setattr(tau_runner, "load_attested_tokenizer", loader)
    counter, evidence = tau_runner._load_target_counter(
        server_receipt=receipt,
        model_path=model_path,
        chat_template=template,
        runtime={"context_limit": 32768, "chat_template_sha256": "a" * 64},
        transformers_version="5.14.1",
    )
    assert counter == "counter"
    assert evidence == {"status": "attested"}
    assert captured["expected_template_sha256"] == "a" * 64

    receipt["runtime"]["arguments"][-1] = "wrong"
    with pytest.raises(ValueError, match="wrong tool/reasoning parser"):
        tau_runner._load_target_counter(
            server_receipt=receipt,
            model_path=model_path,
            chat_template=template,
            runtime={"context_limit": 32768, "chat_template_sha256": "a" * 64},
            transformers_version="5.14.1",
        )


def test_tau_worktree_requires_content_addressed_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = SimpleNamespace(upstream_revision=tau_runner.TAU_SOURCE_REVISION)
    simulator_contract = SimpleNamespace(context_contract=contract)
    monkeypatch.setattr(tau_runner, "load_patch_contract", lambda _: contract)
    monkeypatch.setattr(
        tau_runner,
        "load_simulator_patch_contract",
        lambda _: simulator_contract,
    )
    monkeypatch.setattr(
        tau_runner,
        "verify_tau_simulator_checkout",
        lambda checkout, loaded: {
            "checkout": str(checkout),
            "verified": loaded is simulator_contract,
        },
    )
    evidence = tau_runner._tau_worktree_evidence(
        Path("/tau"), Path("/context.json"), Path("/simulator.json")
    )
    assert evidence == {"checkout": "/tau", "verified": True}

    contract.upstream_revision = "0" * 40
    with pytest.raises(RuntimeError, match="protocol-pinned revision"):
        tau_runner._tau_worktree_evidence(
            Path("/tau"), Path("/context.json"), Path("/simulator.json")
        )


@pytest.mark.parametrize("overflow", [False, True])
def test_receipt_distinguishes_requested_context_and_thinking_from_effective_behavior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, overflow: bool
) -> None:
    model_id = "qwen38-27b-source-bf16"
    digest = "a" * 64
    args = SimpleNamespace(
        protocol=PROTOCOL,
        manifest=tmp_path / "manifest",
        model_id=model_id,
        model_path=Path("/fixture/model"),
        tau_checkout=Path("/fixture/tau"),
        tau_patch_manifest=Path("/fixture/patch.json"),
        tau_simulator_patch_manifest=Path("/fixture/simulator-patch.json"),
        chat_template=Path("/fixture/chat-template.jinja"),
        inputs_summary=tmp_path / "summary",
        scored_ids=tmp_path / "ids",
        server_receipt=tmp_path / "server",
        endpoint="http://127.0.0.1:18083/v1",
        user_model=tau_runner.TAU_EXTERNAL_MODEL,
        nl_evaluator_model=tau_runner.TAU_EXTERNAL_MODEL,
        external_llm_args=None,
        external_api_key_fd=3,
        result_dir=tmp_path / "results",
        receipt=tmp_path / "receipt.json",
    )
    objects = {
        args.manifest: {
            "allocations": [{"allocation_id": "tau3-bench", "selected_ids": ["airline:3"]}]
        },
        args.inputs_summary: {
            "protocol_sha256": digest,
            "scored_samples": {"tau3-bench": 1},
            "artifacts": {"tau3-scored-ids.json": digest},
        },
        args.scored_ids: {"airline": ["3"]},
        args.server_receipt: {
            "study_id": "qwen38-obliteration-2026-09",
            "model_id": model_id,
            "protocol_sha256": digest,
            "chat_template_sha256": digest,
            "runtime": {"versions": {"transformers": "5.14.1"}, "arguments": []},
        },
    }
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    for key in ("TOKENIZERS_PARALLELISM", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.setenv(key, "fixture")
    monkeypatch.setattr(tau_runner.platform, "node", lambda: "basilisk")
    monkeypatch.setattr(
        tau_runner.importlib.metadata, "version", lambda _: tau_runner.TAU_PACKAGE_VERSION
    )
    monkeypatch.setattr(tau_runner, "_private_path", lambda *args: None)
    monkeypatch.setattr(tau_runner, "_git_revision", lambda _: tau_runner.TAU_SOURCE_REVISION)
    monkeypatch.setattr(
        tau_runner,
        "load_patch_contract",
        lambda _: SimpleNamespace(transformers_version="5.14.1"),
    )
    monkeypatch.setattr(
        tau_runner,
        "load_simulator_patch_contract",
        lambda _: SimpleNamespace(patch_sha256=digest),
    )
    monkeypatch.setattr(tau_runner, "_tau_worktree_evidence", lambda *args: {})
    monkeypatch.setattr(tau_runner, "_load_object", lambda path, _: objects[path])
    original_sha256_file = tau_runner._sha256_file
    monkeypatch.setattr(
        tau_runner,
        "_sha256_file",
        lambda path: (
            original_sha256_file(path)
            if args.result_dir in path.parents or path == args.receipt
            else digest
        ),
    )
    monkeypatch.setattr(tau_runner, "_verify_manifest", lambda *args: digest)
    monkeypatch.setattr(tau_runner, "_validate_endpoint", lambda *args: None)
    monkeypatch.setattr(
        tau_runner,
        "_load_target_counter",
        lambda **kwargs: (
            lambda messages, tools: 24545 if overflow else 1,
            {"transformers_version": "5.14.1"},
        ),
    )
    monkeypatch.setattr(tau_runner, "_read_secret_fd", lambda _: "fixture-external-secret")
    captured = []
    active_guard = []

    def simulated_task(config: Any, task: Any, **kwargs: Any) -> SimpleNamespace:
        captured.append(config)
        active_guard[-1](
            config.llm_agent,
            [{"role": "user", "content": "fixture"}],
            None,
            None,
            "agent_response",
            {"max_tokens": 8192},
        )
        return SimpleNamespace(
            seed=config.seed,
            termination_reason="user_stop",
            reward_info=SimpleNamespace(reward=1),
            model_dump=lambda **kwargs: {"seed": config.seed},
        )

    modules = {
        name: ModuleType(name)
        for name in (
            "tau2",
            "tau2.evaluator",
            "tau2.evaluator.evaluator_nl_assertions",
            "tau2.evaluator.evaluator",
            "tau2.data_model",
            "tau2.data_model.simulation",
            "tau2.run",
            "tau2.utils",
            "tau2.utils.llm_utils",
        )
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
        if "." in name:
            parent, child = name.rsplit(".", 1)
            setattr(modules[parent], child, module)
    modules["tau2.data_model.simulation"].TextRunConfig = lambda **kwargs: SimpleNamespace(**kwargs)
    modules["tau2.evaluator.evaluator"].EvaluationType = SimpleNamespace(ALL="all")
    modules["tau2.run"].get_tasks = lambda *args, **kwargs: [SimpleNamespace(id="3")]
    modules["tau2.run"].run_single_task = simulated_task

    @contextmanager
    def scoped_guard(guard: Any) -> Any:
        active_guard.append(guard)
        try:
            yield
        finally:
            active_guard.pop()

    modules["tau2.utils.llm_utils"].scoped_llm_request_guard = scoped_guard

    class TauRuntimeInvalid(RuntimeError):
        pass

    @contextmanager
    def scoped_runtime() -> Any:
        yield SimpleNamespace(
            as_dict=lambda: {
                "environment_call_count": 0,
                "simulator_sampling_attempts": 0,
                "simulator_recovery_attempts": 0,
                "side_effect_retry_attempted": False,
            }
        )

    modules["tau2.utils.llm_utils"].TauRuntimeInvalid = TauRuntimeInvalid
    modules["tau2.utils.llm_utils"].scoped_simulation_runtime_evidence = scoped_runtime

    receipt = tau_runner.run_tau(args)

    assert len(captured) == 1
    assert "metadata" not in captured[0].llm_args_agent
    assert captured[0].llm_args_agent["num_retries"] == 0
    assert captured[0].llm_args_agent["extra_body"]["chat_template_kwargs"] == {
        "enable_thinking": False
    }
    execution = receipt["execution"]
    assert execution["context_budget"] == tau_runner._context_budget(32768, 8192)
    assert execution["context_budget_enforcement"] == "exact-serialized-target-pre-http"
    assert execution["target_transport_retries"] == 0
    assert execution["target_thinking_mode_requested"] == "disabled"
    assert "target_thinking_mode" not in execution
    assert json.loads(args.receipt.read_text())["execution"] == execution
    record = receipt["scored_results"][0]
    raw_path = args.result_dir / record["raw_result_file"]
    assert record["raw_result_sha256"] == hashlib.sha256(raw_path.read_bytes()).hexdigest()
    assert record["fresh_attempt_count"] == record["total_attempt_count"] == 1
    assert record["recovered_attempt_count"] == 0
    if overflow:
        assert record["analytic_status"] == "invalid"
        assert record["reward"] is None and record["termination_reason"] is None
        assert receipt["reward_count"] == 0 and receipt["reward_mean"] is None
        assert receipt["analytic_status_counts"] == {"invalid": 1}
        assert receipt["termination_counts"] == {}
        assert record["failure_attribution"]["owner"] == "context-runtime"
        assert record["failure_attribution"]["retryable"] is False
        raw = json.loads((args.result_dir / record["raw_result_file"]).read_text())
        assert raw["official_reward"] is None
        assert raw["official_termination_reason"] is None
        assert raw["analytic_status"] == "invalid"
        assert raw["partial_trace"]["target_request"]["messages"] == [
            {"role": "user", "content": "fixture"}
        ]
    else:
        assert record["analytic_status"] == "valid"
        assert record["reward"] == 1 and record["termination_reason"] == "user_stop"
        assert receipt["analytic_status_counts"] == {"valid": 1}
    preserved = {path: path.read_bytes() for path in (raw_path, args.receipt)}
    with pytest.raises(FileExistsError):
        tau_runner.run_tau(args)
    assert len(captured) == 1
    assert all(path.read_bytes() == payload for path, payload in preserved.items())


def test_grouped_ids_restore_interleaved_manifest_order(tmp_path):
    selected = ["retail:43", "airline:3", "retail:47"]
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps({"allocations": [{"allocation_id": "tau3-bench", "selected_ids": selected}]})
    )
    grouped = tau_runner._flatten_scored_ids({"airline": ["3"], "retail": ["43", "47"]})
    assert tau_runner._manifest_ordered_scored_ids(path, grouped) == selected
    for invalid in (
        grouped[:-1],
        grouped + ["airline:4"],
        grouped + [grouped[0]],
        ["airline:4", "retail:43", "retail:47"],
    ):
        with pytest.raises(ValueError, match="membership"):
            tau_runner._manifest_ordered_scored_ids(path, invalid)
    path.write_text(
        json.dumps(
            {
                "allocations": [
                    {
                        "allocation_id": "tau3-bench",
                        "selected_ids": ["retail:43", "retail:43", "airline:3"],
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="membership"):
        tau_runner._manifest_ordered_scored_ids(path, grouped)
