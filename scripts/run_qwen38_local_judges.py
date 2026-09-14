#!/usr/bin/env python3
"""Run the locked Qwen3.8 dual-judge protocol with local uncensored judges.

Reuses the locked runner (blinding, order randomization, rubric schemas, result
validation, disagreement, journal, adjudication, bundle) and swaps only the
transport: native ollama /api/chat through the ollama-unify negotiator proxy,
thinking disabled, temperature 0, JSON-schema constrained output via the
OpenAI-compatible /v1/chat/completions route (the native /api/chat route is not
proxied by the negotiator and hangs). Runs one bundle
per pilot observation set, since build_bundle sorts outcomes by study model id and
the pilot has two instances of the same model.

Recorded as an auxiliary amendment lane (separate-amendment-lane); never mixed
with API-judged results.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import httpx
import yaml

PRIVATE_ROOT = Path("/srv/matric-eval/results/qwen38-obliteration-2026-09")
REPO = Path(__file__).resolve().parents[1]
JUDGED_IN_PILOT = ("xstest-safe", "xstest-unsafe")


def _locked():
    path = Path(__file__).with_name("run_qwen38_judges.py")
    spec = importlib.util.spec_from_file_location("qwen38_locked_judges", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


class LocalOllamaCaller:
    """Same call signature as OpenAIResponsesCaller: (model, instructions, input_text, schema) -> CallResult."""

    def __init__(self, plan: dict, locked):
        api = plan["api"]
        self._api = api
        self._CallResult = locked.CallResult
        self._client = httpx.Client(timeout=float(api["timeout_seconds"]))
        self._receipts: list[dict] = []

    def close(self):
        self._client.close()

    def _bounded(self, schema):
        # The locked validator checks labels, not rationale length; a T=0 judge can ramble a
        # rationale past any token budget. Cap it in the grammar the server enforces.
        limit = int(self._api.get("rationale_max_chars", 0) or 0)
        if not limit:
            return schema
        out = json.loads(json.dumps(schema))
        for key, prop in out.get("properties", {}).items():
            if key.endswith("rationale") and prop.get("type") == "string":
                prop["maxLength"] = limit
        return out

    def _post(self, model, instructions, input_text, schema, effort):
        api = self._api
        schema = self._bounded(schema)
        return self._client.post(
            api["endpoint"],
            json={
                "model": model,
                "temperature": float(api["temperature"]),
                "max_tokens": int(api["num_predict"]),
                "seed": int(api["seed"]),
                "reasoning_effort": effort,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "matric_eval_judgment",
                        "strict": True,
                        "schema": schema,
                    },
                },
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": input_text},
                ],
            },
        )

    def __call__(self, model: str, instructions: str, input_text: str, schema: dict):
        api = self._api
        started = time.monotonic()
        last = "request failed"
        efforts = [str(api["reasoning_effort"])] + (
            [str(api["reasoning_fallback"])] if api.get("reasoning_fallback") else []
        )
        attempt = 0
        for effort in efforts:
            for _ in range(int(api["max_attempts"])):
                attempt += 1
                try:
                    r = self._post(model, instructions, input_text, schema, effort)
                    if r.status_code >= 500 or r.status_code == 429:
                        last = f"transient HTTP {r.status_code}"
                    else:
                        r.raise_for_status()
                        try:
                            payload = r.json()
                        except json.JSONDecodeError:
                            # Negotiator admission answers with a non-JSON body while a lane loads/swaps.
                            last = f"non-JSON body ({len(r.content)} bytes) during lane admission"
                            self._receipts.append(
                                {
                                    "model": model,
                                    "attempt": attempt,
                                    "effort": effort,
                                    "transient": last,
                                }
                            )
                            payload = None
                        if payload is not None:
                            if payload.get("model") != model:
                                raise ValueError("response model does not match requested judge")
                            choice = payload["choices"][0]
                            content = choice["message"].get("content") or ""
                            finish = choice.get("finish_reason")
                            if finish == "length":
                                # Budget exhausted -- by reasoning (empty content) or by a rambling rationale
                                # (truncated JSON). Deterministic at T=0, so fall through to the next
                                # reasoning mode instead of retrying identically.
                                last = f"budget exhausted (effort={effort}, {len(content)} content chars)"
                                self._receipts.append(
                                    {
                                        "model": model,
                                        "attempt": attempt,
                                        "effort": effort,
                                        "exhausted": True,
                                        "content_chars": len(content),
                                    }
                                )
                                break
                            try:
                                value = json.loads(content)
                            except json.JSONDecodeError:
                                last = f"content not JSON (finish={finish}, {len(content)} chars)"
                                self._receipts.append(
                                    {
                                        "model": model,
                                        "attempt": attempt,
                                        "effort": effort,
                                        "transient": last,
                                    }
                                )
                                continue
                            if not isinstance(value, dict):
                                raise ValueError("structured output is not an object")
                            usage = dict(payload.get("usage") or {})
                            usage["finish_reason"] = finish
                            usage["reasoning_mode"] = effort
                            usage["reasoning_chars"] = len(choice["message"].get("reasoning") or "")
                            rid = str(
                                payload.get("id")
                                or "local-"
                                + hashlib.sha256((model + content).encode()).hexdigest()[:24]
                            )
                            self._receipts.append(
                                {
                                    "request_id": rid,
                                    "model": model,
                                    "attempt": attempt,
                                    "effort": effort,
                                    "finish_reason": finish,
                                    "completion_tokens": usage.get("completion_tokens"),
                                    "reasoning_chars": usage["reasoning_chars"],
                                    "seconds": round(time.monotonic() - started, 3),
                                }
                            )
                            return self._CallResult(
                                value=value,
                                response_id=rid,
                                response_model=str(payload.get("model")),
                                usage=usage,
                                seconds=time.monotonic() - started,
                                attempts=attempt,
                            )
                except (httpx.HTTPError, ValueError, KeyError) as exc:
                    last = type(exc).__name__
                time.sleep(
                    float(
                        api["retry_backoff_seconds"][
                            min(attempt - 1, len(api["retry_backoff_seconds"]) - 1)
                        ]
                    )
                )
        raise RuntimeError(f"local judge failed after {attempt} attempts: {last}")


def items_for_run(locked, study, run_dir: Path, requests_path: Path):
    reqs = {r["request_id"]: r for r in _jsonl(requests_path)}
    rows = _jsonl(run_dir / "observations.jsonl")
    model_ids = {r["model_id"] for r in rows}
    if len(model_ids) != 1:
        raise ValueError(f"{run_dir}: expected one model id, got {model_ids}")
    (model_id,) = model_ids
    items = []
    for r in rows:
        if r["allocation_id"] not in JUDGED_IN_PILOT:
            continue
        if r["protocol_sha256"] != study.canonical_sha256:
            raise ValueError(f"{run_dir}: protocol digest mismatch")
        req = reqs[r["request_id"]]
        items.append(
            locked.JudgeItem(
                model_id=model_id,
                allocation_id=r["allocation_id"],
                sample_id=r["sample_id"],
                prompt=locked._messages_prompt(req["messages"], r["request_id"]),
                response=r["completion"],
            )
        )
    return model_id, items


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--plan", type=Path, required=True)
    ap.add_argument("--runs", required=True, help="comma-separated run-control directory names")
    ap.add_argument("--result-root", type=Path, default=PRIVATE_ROOT)
    ap.add_argument("--requests", type=Path, default=None)
    ap.add_argument("--out-root", type=Path, default=None)
    ap.add_argument(
        "--protocol", type=Path, default=REPO / "studies/qwen38-obliteration-2026-09/protocol.yaml"
    )
    a = ap.parse_args()
    Q = a.result_root
    a.requests = a.requests or Q / "pilot-cleared-offline-requests.jsonl"
    a.out_root = a.out_root or Q / "pilot-judges-local"
    locked = _locked()
    study = locked.StudyProtocol.from_yaml(a.protocol)
    plan = yaml.safe_load(a.plan.read_text())
    plan_sha = _sha(a.plan)
    manifest = json.loads((Q / "pilot-manifest.json").read_text())
    if manifest["protocol_sha256"] != study.canonical_sha256:
        raise ValueError("pilot manifest is not bound to the live protocol")
    locked.validate_plan(plan, study, "pilot")
    code_rev = locked._code_revision(REPO)
    a.out_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    summary = []
    for run in [r.strip() for r in a.runs.split(",") if r.strip()]:
        run_dir = Q / "run-control" / run
        out_dir = a.out_root / run
        out_dir.mkdir(exist_ok=True, mode=0o700)
        bundle_path = out_dir / "judge-bundle.json"
        if bundle_path.exists():
            print(json.dumps({"run": run, "status": "exists", "bundle": str(bundle_path)}))
            continue
        model_id, items = items_for_run(locked, study, run_dir, a.requests)
        artifacts = {
            "manifest_sha256": _sha(Q / "pilot-manifest.json"),
            "offline_requests_sha256": _sha(a.requests),
            "observations_sha256": _sha(run_dir / "observations.jsonl"),
            "run_control": str(run_dir),
            "judged_allocations": list(JUDGED_IN_PILOT),
            "amendment": plan.get("amendment"),
        }
        caller = LocalOllamaCaller(plan, locked)
        try:
            bundle = locked.build_bundle(
                study=study,
                manifest=manifest,
                cohort="pilot",
                plan=plan,
                plan_sha256=plan_sha,
                items=items,
                artifacts=artifacts,
                journal_path=out_dir / "judge-journal.jsonl",
                call=caller,
                code_revision=code_rev,
            )
        finally:
            caller.close()
        bundle["lane"] = "separate-amendment-lane"
        bundle["run_control"] = run
        bundle["call_receipts"] = caller._receipts
        bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
        bundle_path.chmod(0o600)
        by = {}
        for o in bundle["outcomes"]:
            by.setdefault(o["allocation_id"], []).append(o["value"])
        means = {k: round(sum(v) / len(v), 3) for k, v in by.items()}
        dis = sum(1 for o in bundle["outcomes"] if o["judges_disagreed"])
        summary.append(
            {
                "run": run,
                "model_id": model_id,
                "items": len(items),
                "means": means,
                "disagreements": dis,
                "bundle_sha256": _sha(bundle_path),
            }
        )
        print(json.dumps(summary[-1], sort_keys=True), flush=True)
    (a.out_root / "summary.json").write_text(
        json.dumps({"plan_sha256": plan_sha, "runs": summary}, indent=2, sort_keys=True) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
