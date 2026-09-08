"""Real subprocess qualification of pre-target admission and receipt serialization."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from matric_eval.studies.preflight import SCHEMA, execute_plan, validate_admission


@pytest.fixture
def plan(tmp_path: Path) -> dict:
    script = tmp_path / "check.py"
    script.write_text(
        'import json,os\nfrom pathlib import Path\nPath(os.environ["MATRIC_PREFLIGHT_RECEIPT"]).write_text(json.dumps({"schema":"fixture/1","passed":True,"uid":os.getuid()}))\n'
    )
    marker = tmp_path / "loaded"
    return {
        "schema": SCHEMA,
        "checks": [
            {
                "id": stage,
                "stage": stage,
                "command": [sys.executable, str(script)],
                "inputs": [str(script)],
                "timeout_seconds": 5,
                "freshness_seconds": 60,
                "deterministic": True,
                "receipt_contract": {"schema": "fixture/1", "passed": True, "uid": os.getuid()},
            }
            for stage in ("static", "cpu", "auxiliary", "target")
        ],
        "target_launch": [
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(marker)!r}).touch()",
        ],
        "adapter": [sys.executable, str(script)],
        "adapter_receipt_contract": {"schema": "fixture/1", "passed": True},
        "target_cleanup": [sys.executable, "-c", "pass"],
    }


def test_admission_repetition_and_invalidation(plan: dict, tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    plan["checks"][0]["repetitions"] = 3
    first = execute_plan(plan, receipt)
    assert first["completed"] and first["target_launches"] == 0
    assert first["checks_reexecuted"] == 5
    assert len({row["evidence_id"] for row in first["checks"]}) == 5
    validate_admission(first, plan, 60)
    second = execute_plan(plan, receipt)
    assert second["checks_reused"] == 3
    assert second["checks_reexecuted"] == 2
    source = Path(plan["checks"][0]["inputs"][0])
    source.write_text(source.read_text() + "# dependency changed\n")
    with pytest.raises(ValueError, match="changed"):
        validate_admission(second, plan, 60)
    third = execute_plan(plan, receipt)
    assert third["checks_reused"] == 0
    assert third["checks_reexecuted"] == 5


@pytest.mark.parametrize("failure", ["exit", "schema", "missing", "timeout"])
def test_independent_failures_prevent_acquisition(plan: dict, tmp_path: Path, failure: str) -> None:
    bad = plan["checks"][0]
    if failure == "exit":
        bad["command"] = [
            sys.executable,
            "-c",
            "import sys; print('token=hide'); sys.stderr.write('sandbox failed'); sys.exit(9)",
        ]
    elif failure == "schema":
        bad["receipt_contract"]["schema"] = "obsolete/0"
    elif failure == "missing":
        bad["inputs"].append(str(tmp_path / "missing-dependency"))
    else:
        bad["command"] = [sys.executable, "-c", "import time; time.sleep(5)"]
        bad["timeout_seconds"] = 0.05
    plan["checks"][1]["receipt_contract"]["schema"] = "obsolete/0"
    result = execute_plan(plan, tmp_path / "receipt.json", launch=True)
    assert not result["admitted"]
    assert result["target_launches"] == 0 and result["target_loads_avoided"] == 1
    assert not (tmp_path / "loaded").exists()
    assert len(result["checks"]) == 3
    assert [row["status"] for row in result["checks"]] == ["failed", "failed", "completed"]
    if failure == "exit":
        diagnostic = result["checks"][0]["diagnostic"]
        assert diagnostic["exit_code"] == 9
        assert "hide" not in diagnostic["stdout"]
        assert diagnostic["stderr"] == "sandbox failed"


def test_real_launcher_adapter_receipt_path(plan: dict, tmp_path: Path) -> None:
    result = execute_plan(plan, tmp_path / "receipt.json", launch=True)
    assert result["completed"] and result["target_launches"] == 1
    assert (tmp_path / "loaded").exists()
    assert result["adapter"]["receipt_sha256"]
    saved = json.loads((tmp_path / "receipt.json").read_text())
    assert saved["context"]["uid"] == os.getuid()
    assert saved["context"]["cwd"] == os.getcwd()
    assert saved["context"]["mounts_sha256"]
    assert (tmp_path / "receipt.json").stat().st_mode & 0o777 == 0o600


def test_failed_run_is_never_cached(plan: dict, tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    plan["checks"][1]["receipt_contract"]["passed"] = False
    execute_plan(plan, path)
    assert execute_plan(plan, path)["checks_reused"] == 0


def test_duplicate_repetitions_rejected(plan: dict, tmp_path: Path) -> None:
    plan["checks"][0]["repetitions"] = 3
    result = execute_plan(plan, tmp_path / "receipt.json")
    result["checks"][1]["evidence_id"] = result["checks"][0]["evidence_id"]
    with pytest.raises(ValueError, match="duplicated"):
        validate_admission(result, plan, 60)


def test_service_cli_controlled_endpoint_and_obsolete_adapter_receipt(
    plan: dict, tmp_path: Path
) -> None:
    """Actual CLI -> adapter -> HTTP socket -> receipt, in inherited service context."""
    import subprocess

    adapter = tmp_path / "adapter.py"
    adapter.write_text("""import json,os,threading,urllib.request
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
class Handler(BaseHTTPRequestHandler):
 def do_POST(self):
  data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  assert data['messages']==[{'role':'user','content':'receipt canary'}]
  body=json.dumps({'id':'fixture','choices':[{'message':{'role':'assistant','content':'ok'}}]}).encode()
  self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
 def log_message(self,*args): pass
server=HTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.handle_request);thread.start()
request=urllib.request.Request('http://127.0.0.1:%s/v1/chat/completions'%server.server_port,
 data=json.dumps({'model':'controlled','messages':[{'role':'user','content':'receipt canary'}]}).encode(),headers={'Content-Type':'application/json'})
with urllib.request.urlopen(request,timeout=5) as response:
 assert json.load(response)['choices'][0]['message']['content']=='ok'
thread.join();server.server_close()
Path(os.environ['MATRIC_PREFLIGHT_RECEIPT']).write_text(json.dumps({'schema':'adapter/1','passed':True}))
""")
    plan["adapter"] = [sys.executable, str(adapter)]
    plan["adapter_receipt_contract"] = {"schema": "adapter/1", "passed": True}
    source = tmp_path / "plan.json"
    source.write_text(json.dumps(plan))
    output = tmp_path / "cli-receipt.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "from matric_eval.cli import main; main()",
            "study-run",
            "preflight",
            str(source),
            str(output),
            "--launch",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(output.read_text())
    assert result["completed"] and result["adapter"]["receipt_sha256"]
    plan["adapter_receipt_contract"]["schema"] = "obsolete/0"
    rejected = execute_plan(plan, output, launch=True)
    assert not rejected["completed"]
    assert rejected["cleanup"]["exit_code"] == 0


def test_adapter_schema_smoke_blocks_target(plan: dict, tmp_path: Path) -> None:
    # Same adapter receipt contract belongs in a controlled-endpoint CPU smoke.
    plan["checks"][1]["receipt_contract"] = {"schema": "obsolete-adapter/0"}
    result = execute_plan(plan, tmp_path / "receipt.json", launch=True)
    assert not result["completed"] and result["target_launches"] == 0


def test_expired_live_and_runtime_context_require_new_checks(
    plan: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = execute_plan(plan, tmp_path / "receipt.json")
    result["checks"][2]["completed_at"] -= 61
    with pytest.raises(ValueError, match="stale"):
        validate_admission(result, plan, 60)
    result = execute_plan(plan, tmp_path / "receipt.json")
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    with pytest.raises(ValueError, match="changed"):
        validate_admission(result, plan, 60)


def test_resident_target_checks_never_reacquire(plan: dict, tmp_path: Path) -> None:
    from matric_eval.studies.preflight import execute_target_checks

    admission = execute_plan(plan, tmp_path / "admission.json")
    target = execute_target_checks(plan, tmp_path / "target.json", admission)
    assert target["completed"] and target["target_launches"] == 0
    assert [row["stage"] for row in target["checks"]] == ["target"]
    assert not (tmp_path / "loaded").exists()
    admission["admitted"] = False
    rejected = execute_target_checks(plan, tmp_path / "target.json", admission)
    assert not rejected["completed"] and not rejected["checks"]


def test_supported_tau_inputs_use_canonical_protocol_hash(tmp_path: Path) -> None:
    import hashlib
    import subprocess

    from matric_eval.studies.preflight import digest
    from matric_eval.studies.protocol import StudyProtocol

    checkout = Path(__file__).resolve().parents[3]
    protocol_path = checkout / "studies/qwen38-obliteration-2026-09/protocol.yaml"
    protocol = StudyProtocol.from_yaml(protocol_path, validate_registry=False)
    selected = ["retail:43", "airline:3", "retail:47"]
    manifest = {
        "study_id": protocol.id,
        "cohort": "pilot",
        "allocations": [{"allocation_id": "tau3-bench", "selected_ids": selected}],
    }
    manifest["manifest_sha256"] = digest(manifest)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    scored = tmp_path / "scored.json"
    scored.write_text(json.dumps({"airline": ["3"], "retail": ["43", "47"]}))
    summary = tmp_path / "summary.json"
    summary.write_text(
        json.dumps(
            {
                "manifest_sha256": manifest["manifest_sha256"],
                "cohort": "pilot",
                "protocol_sha256": protocol.canonical_sha256,
                "scored_samples": {"tau3-bench": 3},
                "artifacts": {
                    "tau3-scored-ids.json": hashlib.sha256(scored.read_bytes()).hexdigest()
                },
            }
        )
    )
    receipt = tmp_path / "receipt.json"
    command = [
        sys.executable,
        str(checkout / "scripts/preflight_qwen38_tau.py"),
        "inputs",
        "--protocol",
        str(protocol_path),
        "--model-id",
        "qwen38-27b-source-bf16",
        "--manifest",
        str(manifest_path),
        "--inputs-summary",
        str(summary),
        "--scored-ids",
        str(scored),
        "--tau-checkout",
        str(tmp_path),
    ]
    completed = subprocess.run(
        command,
        env={**os.environ, "MATRIC_PREFLIGHT_RECEIPT": str(receipt)},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(receipt.read_text())["ordered_ids"] == selected
    assert json.loads(scored.read_text()) == {"airline": ["3"], "retail": ["43", "47"]}


def test_failed_check_retains_own_request_receipt(plan: dict, tmp_path: Path) -> None:
    script = Path(plan["checks"][2]["inputs"][0])
    # Make only auxiliary command fail after writing its own correlated evidence.
    failed = tmp_path / "failed.py"
    failed.write_text(
        'import json,os,sys\nfrom pathlib import Path\nPath(os.environ["MATRIC_PREFLIGHT_RECEIPT"]).write_text(json.dumps({"broker_request_id":"own-123","reason":"queue_expired"}))\nsys.exit(7)\n'
    )
    plan["checks"][2]["command"] = [sys.executable, str(failed)]
    plan["checks"][2]["inputs"] = [str(script), str(failed)]
    result = execute_plan(plan, tmp_path / "receipt.json", launch=True)
    row = result["checks"][2]
    assert row["diagnostic"]["exit_code"] == 7
    assert json.loads(row["receipt_excerpt"])["broker_request_id"] == "own-123"
    assert result["target_launches"] == 0
