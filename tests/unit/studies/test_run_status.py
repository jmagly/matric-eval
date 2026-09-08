"""Real subprocess and status projection regression tests (no model calls)."""

import json
import signal
import subprocess
import sys
import time

import pytest
from click.testing import CliRunner

from matric_eval.studies.run_status import AdapterStatus, RunStatus, diagnostic, supervise
from matric_eval.studies.status_cli import study_run


def create(tmp_path, count=10):
    return RunStatus.create(
        tmp_path / "run",
        run_id="study",
        attempt_id="attempt-1",
        tasks=[{"model_id": "source", "suite_id": "tau", "task_id": str(n)} for n in range(count)],
    )


def test_ready_is_not_progress_and_stale_is_not_alive(tmp_path):
    status = create(tmp_path)
    status.phase("ready")
    with status.update() as data:
        data["heartbeat_at"] = time.time() - 60
    data = status.read()
    assert data["counts"]["attempted"] == data["counts"]["valid"] == 0
    assert not data["liveness"]["heartbeat_fresh"]
    result = CliRunner().invoke(study_run, ["status", str(status.directory)])
    assert result.exit_code == 0
    assert "Attempted 0/10; scored-valid 0/10" in result.output


def test_failed_admission_preserves_all_planned_denominators(tmp_path):
    tasks = [
        {"model_id": m, "suite_id": suite, "task_id": str(n)}
        for m in ("source", "E03", "Pliny")
        for suite in ("tau", "terminal")
        for n in range(10)
    ]
    status = RunStatus.create(tmp_path / "run", run_id="study", attempt_id="1", tasks=tasks)
    code = supervise(
        status,
        [
            sys.executable,
            "-c",
            "import sys; print('banking sandbox refused', file=sys.stderr); sys.exit(23)",
        ],
        timeout=5,
    )
    data = status.read()
    assert code == 23
    assert data["counts"]["planned"] == data["counts"]["not_started"] == 60
    assert data["counts"]["attempted"] == data["counts"]["valid"] == 0
    assert data["diagnostics"][-1]["exit_code"] == 23
    assert "banking sandbox refused" in data["diagnostics"][-1]["stderr"]
    assert all(t["reason"] == "worker_exit" for t in data["tasks"])


def test_empty_success_is_missing_receipts(tmp_path):
    status = create(tmp_path)
    assert supervise(status, [sys.executable, "-c", "pass"], timeout=5) == 1
    assert status.read()["terminal_event"]["reason"] == "missing_task_receipts"


def test_real_child_receipt_counts_zero_reward_as_valid(tmp_path):
    status = create(tmp_path, 1)
    script = """
from matric_eval.studies.run_status import AdapterStatus
s = AdapterStatus('source', 'tau')
s.start('0')
s.result('0', reward=0.0, valid=True, reason=None, evidence_uri='fixture.json', evidence_sha256='a'*64)
"""
    assert supervise(status, [sys.executable, "-c", script], timeout=5) == 0
    data = status.read()
    assert data["counts"]["attempted"] == data["counts"]["valid"] == 1
    assert data["tasks"][0]["reward"] == 0
    assert data["terminal_event"]["phase"] == "completed"


def test_timeout_captures_bounded_redacted_output(tmp_path):
    status = create(tmp_path)
    script = "import sys,time; print('token=abc123',flush=True); print('x'*50000,file=sys.stderr,flush=True); time.sleep(30)"
    assert supervise(status, [sys.executable, "-c", script], timeout=0.5, grace=0.1) == 124
    error = status.read()["diagnostics"][-1]
    assert error["reason"] == "worker_timeout"
    assert "abc123" not in json.dumps(error)
    assert len(error["stderr"]) <= 8192 and error["truncated"]


def test_signal_kill_is_not_success(tmp_path):
    status = create(tmp_path)
    supervise(
        status,
        [sys.executable, "-c", "import os,signal; os.kill(os.getpid(), signal.SIGKILL)"],
        timeout=5,
    )
    assert status.read()["diagnostics"][-1]["signal"] == signal.SIGKILL


def test_supervisor_loss_reconciles_once(tmp_path):
    script = """
import sys,time
from pathlib import Path
from matric_eval.studies.run_status import RunStatus
s=RunStatus.create(Path(sys.argv[1]),run_id='r',attempt_id='a',tasks=[dict(model_id='m',suite_id='s',task_id='t')])
s.task('m','s','t',state='executing')
print('ready',flush=True)
time.sleep(30)
"""
    worker = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path / "run")], stdout=subprocess.PIPE, text=True
    )
    try:
        assert worker.stdout.readline().strip() == "ready"
        worker.kill()
        worker.wait(timeout=5)
        status = RunStatus(tmp_path / "run")
        data = status.read()
        assert data["phase"] == "cleanup-pending"
        assert data["tasks"][0]["state"] == "unknown"
        assert data["terminal_event"] == status.read()["terminal_event"]
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait()


def test_no_uncorrelated_or_duplicate_progress(tmp_path, monkeypatch):
    status = create(tmp_path, 1)
    monkeypatch.setenv("MATRIC_RUN_STATUS_DIR", str(status.directory))
    adapter = AdapterStatus("source", "tau")
    with pytest.raises(ValueError, match="outside"):
        adapter.start("unrelated")
    with pytest.raises(ValueError, match="accepted measured"):
        status.task("source", "tau", "0", state="scored-valid")
    adapter.start("0")
    adapter.result(
        "0",
        reward=None,
        valid=False,
        reason="harness_invalid",
        evidence_uri="missing.json",
        evidence_sha256=None,
    )
    with pytest.raises(ValueError, match="terminal disposition"):
        adapter.start("0")
    assert status.read()["counts"]["invalid"] == 1


def test_sandbox_diagnostic_preserves_original_condition():
    error = subprocess.CalledProcessError(
        17, "sandbox", output="canary failed", stderr="bwrap: permission denied"
    )
    result = diagnostic(error, actor="banking", stage="sandbox", reason="sandbox_failed")
    assert result["exit_code"] == 17
    assert result["stdout"] == "canary failed"
    assert result["stderr"] == "bwrap: permission denied"


def test_orphan_child_is_stopped_even_after_leader_exit(tmp_path):
    from matric_eval.studies.run_status import process_identity

    status = create(tmp_path)
    pidfile = tmp_path / "child.pid"
    script = f"""
import os,signal,time
pid=os.fork()
if pid == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    os.close(1)
    os.close(2)
    time.sleep(30)
else:
    open({str(pidfile)!r}, 'w').write(str(pid))
"""
    supervise(status, [sys.executable, "-c", script], timeout=5, grace=0.1)
    assert process_identity(int(pidfile.read_text())) is None
    assert status.read()["cleanup"] == "process-group-stopped-gpu-unverified"


def test_supervisor_sigterm_has_terminal_receipt(tmp_path):
    script = """
import sys
from pathlib import Path
from matric_eval.studies.run_status import RunStatus,supervise
s=RunStatus.create(Path(sys.argv[1]),run_id='r',attempt_id='a',tasks=[dict(model_id='m',suite_id='s',task_id='t')])
supervise(s,[sys.executable,'-c','import time;time.sleep(30)'],timeout=30,grace=.1)
"""
    worker = subprocess.Popen([sys.executable, "-c", script, str(tmp_path / "run")])
    try:
        status = RunStatus(tmp_path / "run")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if status.path.exists() and status.read(reconcile=False)["worker"]:
                break
            time.sleep(0.01)
        else:
            pytest.fail("supervisor did not start")
        worker.terminate()
        worker.wait(timeout=5)
        assert status.read()["terminal_event"]["phase"] == "cancelled"
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait()


def test_missing_receipts_retain_exit_output(tmp_path):
    status = create(tmp_path)
    supervise(status, [sys.executable, "-c", "print('partial native result written')"], timeout=5)
    data = status.read()
    assert data["diagnostics"][-2]["exit_code"] == 0
    assert "partial native result written" in data["diagnostics"][-2]["stdout"]
    assert data["diagnostics"][-1]["reason"] == "missing_task_receipts"


def test_native_grader_failure_preserves_attribution_and_human_detail(tmp_path, monkeypatch):
    status = create(tmp_path, 1)
    monkeypatch.setenv("MATRIC_RUN_STATUS_DIR", str(status.directory))
    adapter = AdapterStatus("source", "tau")
    adapter.start("0")
    adapter.result(
        "0",
        reward=None,
        valid=False,
        reason="missing_reward",
        evidence_uri="native.json",
        evidence_sha256=None,
        native_failure={
            "owner": "evaluator",
            "actor": "evaluator",
            "stage": "verification",
            "detail": "verifier emitted malformed JSON",
        },
        exit_code=3,
    )
    data = status.read()
    assert data["tasks"][0]["observation"]["outcome"] == "grader_failed"
    assert data["diagnostics"][-1]["exit_code"] == 3
    result = CliRunner().invoke(study_run, ["status", str(status.directory)])
    assert "evaluator/verification" in result.output
    assert "verifier emitted malformed JSON" in result.output


def test_exception_message_truncation_is_declared():
    assert diagnostic(RuntimeError("x" * 9000), actor="a", stage="s", reason="r")["truncated"]


def test_adapter_admission_failure_is_terminal_preflight_blocker(tmp_path):
    status = create(tmp_path)
    script = """
from matric_eval.studies.run_status import adapter_main
def fail():
    raise RuntimeError('banking dependency unavailable')
raise SystemExit(adapter_main(fail))
"""
    supervise(status, [sys.executable, "-c", script], timeout=5)
    data = status.read()
    assert data["terminal_event"]["phase"] == "preflight-blocked"
    assert data["counts"]["attempted"] == 0
    result = CliRunner().invoke(study_run, ["status", str(status.directory)])
    assert "banking dependency unavailable" in result.output


def test_worker_exit_retains_resource_cleanup_obligation(tmp_path):
    status = create(tmp_path)
    script = """
import os,sys
from pathlib import Path
from matric_eval.studies.run_status import RunStatus
with RunStatus(Path(os.environ['MATRIC_RUN_STATUS_DIR'])).update() as data:
    data['resources'] = {'resource_id':'owned', 'state':'cleanup-pending', 'cleanup':'pending', 'record':'/private/attempt/record.json'}
sys.exit(17)
"""
    assert supervise(status, [sys.executable, "-c", script], timeout=5) == 17
    assert status.read()["cleanup"] == "pending"
    result = CliRunner().invoke(study_run, ["status", str(status.directory)])
    assert result.exit_code == 0
    assert (
        "Resources: cleanup-pending; cleanup: pending; record: /private/attempt/record.json"
        in result.output
    )
