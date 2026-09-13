"""The local-judge lane must reuse the locked protocol and only swap transport.

A stub caller stands in for ollama so the test proves: the amendment plan passes
the locked validator, items are built from a pilot observation set, blinding and
role ordering come from the locked helpers, disagreements are adjudicated, and the
bundle records the amendment lane.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
PROTOCOL = REPO / "studies" / "qwen38-obliteration-2026-09" / "protocol.yaml"
PLAN = REPO / "studies" / "qwen38-obliteration-2026-09" / "judge-plan-local-amendment.yaml"


def _load(name: str):
    path = REPO / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_amendment_plan_passes_the_locked_validator() -> None:
    locked = _load("run_qwen38_judges.py")
    study = locked.StudyProtocol.from_yaml(PROTOCOL, validate_registry=False)
    plan = yaml.safe_load(PLAN.read_text())
    locked.validate_plan(plan, study, "pilot")
    assert plan["amendment"]["comparability"] == "separate-amendment-lane"
    assert (
        plan["amendment"]["owner_authorized_exception"]["control"] == "target_models_may_not_judge"
    )
    assert plan["judges"]["primary"]["model"] != plan["judges"]["secondary"]["model"]


def test_pilot_items_and_bundle_with_stub_judges(tmp_path: Path) -> None:
    locked = _load("run_qwen38_judges.py")
    local = _load("run_qwen38_local_judges.py")
    study = locked.StudyProtocol.from_yaml(PROTOCOL, validate_registry=False)
    plan = yaml.safe_load(PLAN.read_text())
    # Build the manifest the real way so identity, ordering and count checks are genuine.
    catalog = {}
    for allocation in study.benchmarks:
        count = allocation.pilot_samples + 3
        if allocation.selection_strategy == "sha256-ranked-v1":
            catalog[allocation.id] = [f"{allocation.id}-{i}" for i in range(count)]
        else:
            catalog[allocation.id] = [
                {"id": f"{allocation.id}-{i}", "stratum": f"stratum-{i % 3}"} for i in range(count)
            ]
    manifest = study.selection_manifest(catalog, "pilot")
    selected = {a["allocation_id"]: a["selected_ids"] for a in manifest["allocations"]}
    model = study.models[0]
    run_dir = tmp_path / "run-control" / "pilot-x"
    run_dir.mkdir(parents=True)
    requests = tmp_path / "requests.jsonl"
    reqs, obs = [], []
    for alloc in ("xstest-safe", "xstest-unsafe", "ifeval"):
        for sid in selected[alloc][:2]:
            rid = f"{alloc}:{sid}:turn-1"
            reqs.append(
                {
                    "request_id": rid,
                    "allocation_id": alloc,
                    "sample_id": sid,
                    "messages": [{"role": "user", "content": f"prompt {alloc} {sid}"}],
                }
            )
            obs.append(
                {
                    "request_id": rid,
                    "allocation_id": alloc,
                    "sample_id": sid,
                    "model_id": model.id,
                    "protocol_sha256": study.canonical_sha256,
                    "completion": f"answer {sid}",
                }
            )
    requests.write_text("".join(json.dumps(r) + "\n" for r in reqs))
    (run_dir / "observations.jsonl").write_text("".join(json.dumps(o) + "\n" for o in obs))
    second_ids = {selected["xstest-safe"][1], selected["xstest-unsafe"][1]}

    model_id, items = local.items_for_run(locked, study, run_dir, requests)
    assert model_id == model.id
    assert sorted({i.allocation_id for i in items}) == [
        "xstest-safe",
        "xstest-unsafe",
    ]  # ifeval is not judged
    assert len(items) == 4

    calls: list[tuple[str, str]] = []

    def stub(judge_model: str, instructions: str, input_text: str, schema: dict):
        calls.append((judge_model, input_text[:40]))
        # Ornith says compliance, E03 says refusal on sample s2 only -> forces one adjudication per allocation
        behavior = "full_compliance"
        if any(sid in input_text for sid in second_ids) and judge_model.startswith("manitcor/"):
            behavior = "full_refusal"
        return locked.CallResult(
            value={"behavior": behavior, "rationale": "stub"},
            response_id="r",
            response_model=judge_model,
            usage={},
            seconds=0.01,
            attempts=1,
        )

    bundle = locked.build_bundle(
        study=study,
        manifest=manifest,
        cohort="pilot",
        plan=plan,
        plan_sha256="p" * 64,
        items=items,
        artifacts={"stub": True},
        journal_path=tmp_path / "journal.jsonl",
        call=stub,
        code_revision="0" * 40,
    )
    outcomes = bundle["outcomes"]
    assert len(outcomes) == 4
    disagreed = [o for o in outcomes if o["judges_disagreed"]]
    assert len(disagreed) == 2 and all(o["adjudicated"] for o in disagreed)
    # adjudicator (Ornith) resolves to compliance: xstest-safe compliance -> 0.0, xstest-unsafe compliance -> 1.0
    by = {(o["allocation_id"], o["sample_id"]): o["value"] for o in outcomes}
    assert by[("xstest-safe", selected["xstest-safe"][1])] == 0.0
    assert by[("xstest-unsafe", selected["xstest-unsafe"][1])] == 1.0
    assert all(o["blind_id"].startswith("B") for o in outcomes)
    primary = plan["judges"]["primary"]["model"]
    secondary = plan["judges"]["secondary"]["model"]
    assert {c[0] for c in calls} == {primary, secondary}
    journal = [json.loads(line) for line in (tmp_path / "journal.jsonl").read_text().splitlines()]
    assert sum(1 for r in journal if r["role"] == "adjudicator") == 2


def test_local_caller_parses_openai_compatible_payload() -> None:
    locked = _load("run_qwen38_judges.py")
    local = _load("run_qwen38_local_judges.py")
    plan = yaml.safe_load(PLAN.read_text())
    primary = plan["judges"]["primary"]["model"]

    class _Response:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload
            self.content = b"{}"

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    good = {
        "id": "chatcmpl-1",
        "model": primary,
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"behavior": "partial_refusal", "rationale": "x"}),
                },
            }
        ],
        "usage": {"completion_tokens": 12},
    }
    caller = local.LocalOllamaCaller(plan, locked)
    caller._client.post = lambda url, json=None: _Response(good)  # type: ignore[method-assign]
    result = caller(primary, "instr", "input", {"type": "object"})
    caller.close()
    assert result.value["behavior"] == "partial_refusal"
    assert result.usage["finish_reason"] == "stop"
    assert result.response_id == "chatcmpl-1"

    # Budget exhausted by reasoning at "low" must fall through to "none", recorded per judgment.
    exhausted = dict(
        good,
        choices=[{"finish_reason": "length", "message": {"role": "assistant", "content": ""}}],
    )
    seen: list[str] = []

    def _post(url, json=None):
        seen.append(json["reasoning_effort"])
        return _Response(exhausted if json["reasoning_effort"] == "low" else good)

    fallback = local.LocalOllamaCaller(
        dict(plan, api=dict(plan["api"], retry_backoff_seconds=[0])), locked
    )
    fallback._client.post = _post  # type: ignore[method-assign]
    result = fallback(primary, "instr", "input", {"type": "object"})
    fallback.close()
    assert seen == ["low", "none"]
    assert result.usage["reasoning_mode"] == "none"
    assert result.attempts == 2

    # A response from the wrong model must never be accepted as a judgment.
    plan["api"]["max_attempts"] = 1
    plan["api"]["retry_backoff_seconds"] = [0]
    wrong = dict(good, model="someone-else")
    strict = local.LocalOllamaCaller(plan, locked)
    strict._client.post = lambda url, json=None: _Response(wrong)  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        strict(primary, "instr", "input", {"type": "object"})
    strict.close()
