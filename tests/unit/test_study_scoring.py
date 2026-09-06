"""Tests for sealed offline study scoring."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from matric_eval.studies import StudyProtocol, scoring_cli
from matric_eval.studies import scoring as scoring_module
from matric_eval.studies.scoring import score_offline_outputs, write_private_jsonl

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "studies/qwen38-obliteration-2026-09/protocol.yaml"


def _result(study: StudyProtocol, allocation: str, sample: str, completion: str) -> dict:
    model = study.models[0]
    return {
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
        "manifest_sha256": "a" * 64,
        "model_id": model.id,
        "model_revision": model.checkpoint_revision,
        "request_id": f"{allocation}:{sample}:turn-1",
        "allocation_id": allocation,
        "sample_id": sample,
        "completion": completion,
        "finish_reason": "stop",
    }


def _scoring(allocation: str, sample: str, target: str, metadata: dict) -> dict:
    return {
        "request_id": f"{allocation}:{sample}:turn-1",
        "allocation_id": allocation,
        "sample_id": sample,
        "target": target,
        "metadata": metadata,
    }


def test_scores_deterministic_and_diagnostic_lanes_without_content() -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    results = [
        _result(study, "mmlu-pro", "q1", "Therefore, the answer is (C)."),
        _result(study, "xstest-safe", "x1", "Here is the requested explanation."),
        _result(study, "mtbench", "81", "An answer"),
    ]
    scoring = [
        _scoring("mmlu-pro", "q1", "C", {"category": "math"}),
        _scoring("xstest-safe", "x1", "comply", {"category": "safe"}),
        _scoring("mtbench", "81", "", {"category": "writing"}),
    ]

    rows, summary = score_offline_outputs(
        study=study,
        results=results,
        scoring_records=scoring,
    )

    assert [row["status"] for row in rows] == ["scored", "scored", "pending-external-judge"]
    assert rows[0]["score"] == 1.0
    assert rows[0]["publication_eligible"] is True
    assert rows[1]["publication_eligible"] is False
    assert "completion" not in rows[0]
    assert summary["scored_samples"] == 2
    assert summary["pending_external_judge"] == 1


def test_livecodebench_executor_is_injectable() -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    results = [_result(study, "livecodebench", "p1", "```python\nprint(input())\n```")]
    scoring = [
        _scoring(
            "livecodebench",
            "p1",
            "ok",
            {
                "public_test_cases": [{"input": "ok", "output": "ok"}],
                "private_test_cases": [{"input": "bad", "output": "good"}],
            },
        )
    ]

    def executor(_completion: str, _metadata: dict, _timeout: int) -> dict:
        return {
            "passed": True,
            "tests_executed": 2,
            "result_codes": {"True": 2},
            "code_parse_failure": False,
        }

    rows, _ = score_offline_outputs(
        study=study,
        results=results,
        scoring_records=scoring,
        executor=executor,
    )

    assert rows[0]["score"] == 1.0
    assert rows[0]["detail"] == {
        "tests_total": 2,
        "tests_executed": 2,
        "code_parse_failure": False,
        "result_codes": {"True": 2},
        "evaluator_revision": "28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24",
    }


def test_livecodebench_rejects_implicit_host_execution() -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    results = [_result(study, "livecodebench", "p1", "print('unsafe')")]
    scoring = [
        _scoring(
            "livecodebench",
            "p1",
            "unsafe",
            {"public_test_cases": [{"input": "", "output": "unsafe"}]},
        )
    ]

    with pytest.raises(ValueError, match="explicit isolated code executor"):
        score_offline_outputs(study=study, results=results, scoring_records=scoring)


def test_livecodebench_rejects_infrastructure_failure() -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    results = [_result(study, "livecodebench", "p1", "```python\nprint('x')\n```")]
    scoring = [
        _scoring(
            "livecodebench",
            "p1",
            "x",
            {"public_test_cases": [{"input": "", "output": "x", "testtype": "stdin"}]},
        )
    ]

    with pytest.raises(RuntimeError, match="infrastructure failed"):
        score_offline_outputs(
            study=study,
            results=results,
            scoring_records=scoring,
            executor=lambda _completion, _metadata, _timeout: {
                "infrastructure_error": "runner_error"
            },
        )


def test_official_ifeval_language_detection_is_repeatable() -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    results = [
        _result(
            study,
            "ifeval",
            "q1",
            "This response remains entirely in English for deterministic evaluation.",
        )
    ]
    scoring = [
        _scoring(
            "ifeval",
            "q1",
            "",
            {
                "prompt": "Respond in English.",
                "instruction_id_list": ["language:response_language"],
                "kwargs": [{"language": "en"}],
            },
        )
    ]

    first = score_offline_outputs(study=study, results=results, scoring_records=scoring)
    second = score_offline_outputs(study=study, results=results, scoring_records=scoring)

    assert first == second
    assert first[0][0]["score"] == 1.0


def test_rejects_contract_drift_and_overwrite(tmp_path: Path) -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    result = _result(study, "mmlu-pro", "q1", "A")
    scoring = [_scoring("mmlu-pro", "q1", "A", {})]
    changed = copy.deepcopy(result)
    changed["manifest_sha256"] = "short"

    with pytest.raises(ValueError, match="manifest SHA-256"):
        score_offline_outputs(study=study, results=[changed], scoring_records=scoring)

    output = tmp_path / "scores.jsonl"
    write_private_jsonl(output, [{"score": 1.0}])
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="overwrite"):
        write_private_jsonl(output, [])


def test_verifies_pinned_livecodebench_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=f"{scoring_module.LCB_EVALUATOR_REVISION}\n",
        stderr="",
    )
    monkeypatch.setattr(scoring_module.subprocess, "run", lambda *args, **kwargs: completed)

    scoring_module.verify_lcb_evaluator_checkout()

    completed.returncode = 1
    with pytest.raises(RuntimeError, match="revision-mismatched"):
        scoring_module.verify_lcb_evaluator_checkout()


def test_docker_livecodebench_executor_uses_locked_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"passed": true, "tests_executed": 2}\n',
            stderr="",
        )

    monkeypatch.setattr(scoring_module.uuid, "uuid4", lambda: SimpleNamespace(hex="fixed"))
    monkeypatch.setattr(scoring_module.subprocess, "run", fake_run)
    metadata = {
        "public_test_cases": [{"input": "one", "output": "one"}],
        "private_test_cases": [{"input": "two", "output": "two"}],
        "func_name": None,
    }

    result = scoring_module.docker_livecodebench_executor("print(input())", metadata, 6)

    assert result == {"passed": True, "tests_executed": 2}
    command, options = calls[0]
    assert "--network" in command and "none" in command
    assert "--read-only" in command
    assert "--cap-drop" in command and "ALL" in command
    assert json.loads(str(options["input"]))["completion"] == "print(input())"
    assert options["timeout"] == 24


def test_docker_livecodebench_executor_handles_timeout_and_runner_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def timeout_then_remove(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise subprocess.TimeoutExpired(command, 8)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(scoring_module.subprocess, "run", timeout_then_remove)
    timeout = scoring_module.docker_livecodebench_executor("pass", {"public_test_cases": [{}]}, 3)
    assert timeout["result_codes"] == {"timeout": 1}
    assert calls == 2

    failed = subprocess.CompletedProcess(args=[], returncode=2, stdout="", stderr="failure")
    monkeypatch.setattr(scoring_module.subprocess, "run", lambda *args, **kwargs: failed)
    result = scoring_module.docker_livecodebench_executor("pass", {"public_test_cases": [{}]}, 3)
    assert result["infrastructure_error"] == "runner_error"


@pytest.mark.parametrize("stdout", ["not-json", "[]"])
def test_docker_livecodebench_executor_rejects_invalid_output(
    stdout: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")
    monkeypatch.setattr(scoring_module.subprocess, "run", lambda *args, **kwargs: completed)

    with pytest.raises(RuntimeError, match="sandbox"):
        scoring_module.docker_livecodebench_executor("pass", {"public_test_cases": [{}]}, 3)


def test_scoring_code_revision_requires_full_git_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    completed = SimpleNamespace(stdout=f"{'a' * 40}\n")
    monkeypatch.setattr(scoring_cli.subprocess, "run", lambda *args, **kwargs: completed)
    assert scoring_cli._code_revision() == "a" * 40

    completed.stdout = "short\n"
    with pytest.raises(RuntimeError, match="full Git revision"):
        scoring_cli._code_revision()


@pytest.mark.parametrize("docker_sandbox", [False, True])
def test_scoring_cli_wires_attested_inputs(
    docker_sandbox: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    study = SimpleNamespace(seed=1790783388)
    rows = [{"request_id": "request-1"}]
    captured: dict[str, object] = {}
    verified = False

    def fake_verify() -> None:
        nonlocal verified
        verified = True

    def fake_score(**kwargs: object) -> tuple[list[dict[str, object]], dict[str, object]]:
        captured.update(kwargs)
        return rows, {"samples": 1}

    def fake_write(path: Path, written: list[dict[str, object]]) -> str:
        captured["output"] = path
        captured["written"] = written
        return "c" * 64

    monkeypatch.setattr(
        scoring_cli.StudyProtocol, "from_yaml", staticmethod(lambda *args, **kwargs: study)
    )
    monkeypatch.setattr(scoring_cli, "verify_lcb_evaluator_checkout", fake_verify)
    monkeypatch.setattr(scoring_cli, "load_jsonl", lambda path: [{"path": str(path)}])
    monkeypatch.setattr(scoring_cli, "score_offline_outputs", fake_score)
    monkeypatch.setattr(scoring_cli, "_code_revision", lambda: "b" * 40)
    monkeypatch.setattr(scoring_cli, "sha256_file", lambda path: "d" * 64)
    monkeypatch.setattr(scoring_cli, "write_private_jsonl", fake_write)
    monkeypatch.setattr(scoring_cli.importlib.metadata, "version", lambda name: "0.1.0")
    protocol = tmp_path / "protocol.yaml"
    results = tmp_path / "results.jsonl"
    records = tmp_path / "records.jsonl"
    output = tmp_path / "scores.jsonl"
    args = [str(protocol), str(results), str(records), "--output", str(output)]
    if docker_sandbox:
        args.append("--docker-code-sandbox")

    assert scoring_cli.main(args) == 0

    summary = json.loads(capsys.readouterr().out)
    assert verified is docker_sandbox
    assert captured["executor"] is (
        scoring_cli.docker_livecodebench_executor if docker_sandbox else None
    )
    assert captured["code_timeout"] == 6
    assert rows[0]["scoring_code_revision"] == "b" * 40
    assert summary["scores_sha256"] == "c" * 64
    assert summary["evaluators"]["ifeval"]["language_detector_seed"] == 1790783388
    assert summary["scoring_seconds"] >= 0


def test_scoring_cli_rejects_nonpositive_timeout(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        scoring_cli.main(
            [
                str(tmp_path / "protocol"),
                str(tmp_path / "results"),
                str(tmp_path / "records"),
                "--output",
                str(tmp_path / "scores"),
                "--code-timeout",
                "0",
            ]
        )


def test_jsonl_loader_and_index_validation(tmp_path: Path) -> None:
    valid = tmp_path / "valid.jsonl"
    valid.write_text('\n{"request_id": "one"}\n', encoding="utf-8")
    assert scoring_module.load_jsonl(valid) == [{"request_id": "one"}]

    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        scoring_module.load_jsonl(invalid)

    non_object = tmp_path / "non-object.jsonl"
    non_object.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must contain an object"):
        scoring_module.load_jsonl(non_object)

    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError, match="contains no records"):
        scoring_module.load_jsonl(empty)

    with pytest.raises(ValueError, match="missing or invalid request_id"):
        scoring_module._indexed([{}], "rows")
    with pytest.raises(ValueError, match="duplicate request_id"):
        scoring_module._indexed([{"request_id": "one"}, {"request_id": "one"}], "rows")


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({"public_test_cases": {}}, "metadata is malformed"),
        ({"public_test_cases": [1]}, "test case must be an object"),
        ({}, "contains no tests"),
        (
            {"public_test_cases": [{"testtype": "functional"}]},
            "functional sample is missing func_name",
        ),
    ],
)
def test_livecodebench_rejects_malformed_test_metadata(
    metadata: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        scoring_module._score_livecodebench(
            "pass",
            metadata,
            executor=lambda completion, record, timeout: {"passed": True},
            timeout=3,
        )


def test_scoring_rejects_join_and_payload_contract_drift() -> None:
    study = StudyProtocol.from_yaml(PROTOCOL)
    result = _result(study, "mmlu-pro", "q1", "A")
    scoring = _scoring("mmlu-pro", "q1", "A", {})

    mismatched = copy.deepcopy(scoring)
    mismatched["request_id"] = "mmlu-pro:other:turn-1"
    with pytest.raises(ValueError, match="identical ordered request IDs"):
        score_offline_outputs(study=study, results=[result], scoring_records=[mismatched])

    undeclared = copy.deepcopy(result)
    undeclared["model_id"] = "undeclared"
    with pytest.raises(ValueError, match="declared study model"):
        score_offline_outputs(study=study, results=[undeclared], scoring_records=[scoring])

    wrong_sample = copy.deepcopy(result)
    wrong_sample["sample_id"] = "other"
    with pytest.raises(ValueError, match="sample_id does not match contract"):
        score_offline_outputs(study=study, results=[wrong_sample], scoring_records=[scoring])

    wrong_completion = copy.deepcopy(result)
    wrong_completion["completion"] = None
    with pytest.raises(ValueError, match="completion and target must be strings"):
        score_offline_outputs(study=study, results=[wrong_completion], scoring_records=[scoring])

    wrong_metadata = copy.deepcopy(scoring)
    wrong_metadata["metadata"] = []
    with pytest.raises(ValueError, match="scoring metadata must be an object"):
        score_offline_outputs(study=study, results=[result], scoring_records=[wrong_metadata])
