"""Real journal scheduling qualification, with process restart and admission failure."""

import json
import multiprocessing
from pathlib import Path

import pytest

from matric_eval.results.contract import Observation, ObservationIdentity
from matric_eval.state.journal import (
    AttemptIntent,
    ObservationJournal,
    TerminalAttempt,
    storage_profile,
)
from matric_eval.state.observation_identity import (
    COMPONENTS,
    ExecutionFingerprint,
    ReplayCapability,
)
from matric_eval.studies.suite_schedule import Schedule, SuiteFailure, Work, execute, plan


def _semantics_only_profile(path):
    return {
        **storage_profile(path),
        "supported": True,
        "profile": "TEST-ONLY-sqlite-transaction-semantics",
    }


def _child_storage_seam(path):
    import matric_eval.state.journal as module

    if not storage_profile(Path(path))["supported"]:
        module.storage_profile = _semantics_only_profile


@pytest.fixture(autouse=True)
def journal_storage_context(tmp_path, monkeypatch, record_property):
    actual = storage_profile(tmp_path)
    record_property("actual_storage_profile", json.dumps(actual, sort_keys=True))
    record_property(
        "filesystem_qualification",
        "actual_ext4" if actual["supported"] else "sqlite_transaction_semantics_only",
    )
    if not actual["supported"]:
        monkeypatch.setattr("matric_eval.state.journal.storage_profile", _semantics_only_profile)


def work(key, model="model", suite="terminal", **updates):
    documents = {name: {"revision": "frozen"} for name in COMPONENTS}
    documents["sampler"]["generation_seed"] = 42
    documents["protocol"]["scoring_budget"] = {"max_tokens": 8}
    return Work(
        key=key,
        suite=suite,
        model=model,
        identities=[
            ObservationIdentity(
                run_id="run",
                model_id=model,
                benchmark_id=suite,
                allocation_id="paired",
                sample_id=key,
                trial_id="0",
                metric_id="accuracy",
            )
        ],
        fingerprint=ExecutionFingerprint.model_validate(
            {
                name: {"document": document, "status": "verified"}
                for name, document in documents.items()
            }
        ),
        capability=ReplayCapability(adapter_id=suite, mode="manual", mechanism_version="1"),
        seed=42,
        scoring_budget={"max_tokens": 8},
        residency={"runtime": "synthetic-v1"},
        group_resident=True,
        **updates,
    )


def schedule(items, policy="continue-independent"):
    return Schedule(
        work=items,
        policy=policy,
        authorized_suites=["terminal", "tau", "direct", "bfcl"],
        amendment_reason="Synthetic grouping qualification",
    )


def terminal(intent):
    return TerminalAttempt(
        attempt_id=intent.attempt_id,
        observations=[
            Observation(
                observation_id=row.logical_id(),
                identity=row,
                attempt_id=intent.attempt_id,
                previous_attempt_id=intent.previous_attempt_id,
                accepted=False,
                execution="completed",
                outcome="observed",
                value=0,
                reason=None,
                native_status="ok",
                judge=None,
                artifacts=[],
            )
            for row in intent.identities
        ],
    )


class Service:
    def __init__(self, fail=None, cleanup=True):
        self.fail = fail
        self.cleanup = cleanup
        self.ran = []
        self.loaded = []
        self.checked = []

    def preflight(self, item):
        self.checked.append(item.key)
        return []

    def start(self, item):
        self.loaded.append(item.model)
        if self.fail == item.suite:
            raise SuiteFailure("admission rejected")

    def run(self, item, intent):
        self.ran.append((item.key, item.seed, item.identities[0].logical_id()))
        return terminal(intent)

    def stop(self):
        return self.cleanup


def test_deferred_untouched(tmp_path):
    with ObservationJournal(tmp_path / "journal.sqlite") as journal:
        service = Service()
        result = plan(
            schedule([work("tau", suite="tau", deferred=True), work("terminal")]),
            journal,
            service.preflight,
        )
    assert service.checked == ["terminal"]
    assert result["order"] == ["terminal"]
    assert result["entries"][0]["disposition"] == "deferred"


@pytest.mark.parametrize("policy,expected", [("stop", []), ("continue-independent", ["second"])])
def test_suite_failure_policy(tmp_path, policy, expected):
    with ObservationJournal(tmp_path / "journal.sqlite") as journal:
        service = Service(fail="tau")
        result = execute(
            schedule([work("first", suite="tau"), work("second")], policy),
            journal,
            service,
            tmp_path / "events.jsonl",
        )
    assert [row[0] for row in service.ran] == expected
    assert result["entries"][0]["disposition"] == "failed"


def test_global_cleanup_failure_stops(tmp_path):
    with ObservationJournal(tmp_path / "journal.sqlite") as journal:
        service = Service(fail="tau", cleanup=False)
        result = execute(
            schedule([work("first", suite="tau"), work("second")]),
            journal,
            service,
            tmp_path / "events.jsonl",
        )
    assert result["global_stop"]
    assert not service.ran
    assert result["entries"][1]["reasons"] == ["global_stop"]


def test_grouping_and_reuse_exact_identities(tmp_path):
    items = [work("one", "a", "direct"), work("two", "b", "bfcl"), work("three", "a", "bfcl")]
    with ObservationJournal(tmp_path / "journal.sqlite") as journal:
        service = Service()
        first = execute(schedule(items), journal, service, tmp_path / "events.jsonl")
        second = execute(schedule(items), journal, service, tmp_path / "events.jsonl")
    assert first["order"] == ["one", "three", "two"]
    assert first["expected_model_loads"] == first["observed_model_loads"] == 2
    assert second["expected_model_loads"] == second["observed_model_loads"] == 0
    assert all(row["disposition"] == "reused" for row in second["entries"])
    assert sorted(service.ran) == sorted(
        (item.key, item.seed, item.identities[0].logical_id()) for item in items
    )


def test_fingerprint_mismatch_retains_original(tmp_path):
    item = work("one", suite="direct")
    with ObservationJournal(tmp_path / "journal.sqlite") as journal:
        execute(schedule([item]), journal, Service(), tmp_path / "events.jsonl")
        changed = item.model_copy(deep=True)
        changed.fingerprint.prompt.document["revision"] = "changed"
        result = plan(schedule([changed]), journal, Service().preflight)
        assert result["entries"][0]["disposition"] == "invalidated"
        assert "component_mismatch:prompt" in result["entries"][0]["reasons"][0]
        assert journal.load_accepted(item.identities, item.fingerprint) is not None


def test_lost_ack_is_reused_and_interrupted_external_is_blocked(tmp_path):
    accepted, interrupted = work("accepted"), work("interrupted")
    with ObservationJournal(tmp_path / "journal.sqlite") as journal:
        for item in [accepted, interrupted]:
            intent = AttemptIntent(
                attempt_id=item.key,
                identities=item.identities,
                fingerprint=item.fingerprint,
                replay_capability=item.capability,
            )
            journal.record_intent(intent)
            if item is accepted:
                journal.commit_terminal(terminal(intent))
        result = execute(
            schedule([accepted, interrupted]), journal, Service(), tmp_path / "events.jsonl"
        )
        assert len(journal.list_attempts()) == 2
    assert [row["disposition"] for row in result["entries"]] == ["reused", "blocked"]


def _run_process(directory):
    root = Path(directory)
    _child_storage_seam(root)
    with ObservationJournal(root / "journal.sqlite") as journal:
        execute(
            schedule([work("admission", suite="tau"), work("independent")]),
            journal,
            Service(fail="tau"),
            root / "events.jsonl",
        )


def test_service_restart_accounting(tmp_path):
    # Each process constructs its own scheduler, service and SQLite connection.
    for _ in range(2):
        process = multiprocessing.get_context("spawn").Process(
            target=_run_process, args=(str(tmp_path),)
        )
        process.start()
        process.join(20)
        assert process.exitcode == 0
    import json

    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    reports = [row["report"] for row in events if row["event"] == "accounting"]
    assert reports[0]["execution_order"] == ["independent"]
    assert reports[1]["execution_order"] == []
    assert reports[1]["entries"][1]["disposition"] == "reused"
    with ObservationJournal(tmp_path / "journal.sqlite") as journal:
        assert len(journal.list_attempts()) == 1


def _http_service(connection):
    import json
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            request = json.loads(self.rfile.read(length))
            if self.path == "/admit/tau":
                self.send_response(503)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = (
                terminal(AttemptIntent.model_validate(request)).model_dump()
                if self.path == "/task"
                else {}
            )
            self.wfile.write(json.dumps(response).encode())

        def log_message(self, *args):
            pass

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        connection.send(server.server_port)
        connection.close()
        server.serve_forever()


class HTTPService(Service):
    def __init__(self):
        super().__init__()
        self.process = None

    def request(self, path, payload):
        import json
        import urllib.request

        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)

    def start(self, item):
        import urllib.error

        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe(duplex=False)
        self.process = context.Process(target=_http_service, args=(child,))
        self.process.start()
        child.close()
        assert parent.poll(10)
        self.port = parent.recv()
        parent.close()
        try:
            self.request("/admit/" + item.suite, {})
        except urllib.error.HTTPError as exc:
            if exc.code == 503:
                raise SuiteFailure("admission rejected") from exc
            raise

    def run(self, item, intent):
        return TerminalAttempt.model_validate(self.request("/task", intent.model_dump()))

    def stop(self):
        if self.process:
            self.process.terminate()
            self.process.join(10)
            return not self.process.is_alive()
        return True


def _run_http_process(directory):
    root = Path(directory)
    _child_storage_seam(root)
    with ObservationJournal(root / "journal.sqlite") as journal:
        execute(
            schedule([work("admission", suite="tau"), work("independent")]),
            journal,
            HTTPService(),
            root / "events.jsonl",
        )


def test_real_http_admission_failure_restart(tmp_path):
    import json

    for _ in range(2):
        process = multiprocessing.get_context("spawn").Process(
            target=_run_http_process, args=(str(tmp_path),)
        )
        process.start()
        process.join(30)
        assert process.exitcode == 0
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    reports = [row["report"] for row in events if row["event"] == "accounting"]
    assert reports[0]["execution_order"] == ["independent"]
    assert reports[1]["execution_order"] == []
    assert [row["disposition"] for row in reports[0]["entries"]] == ["failed", "completed"]
    assert [row["disposition"] for row in reports[1]["entries"]] == ["failed", "reused"]
    assert reports[0]["observed_model_loads"] == 2
    assert reports[1]["observed_model_loads"] == 1
    assert not any(report["global_stop"] for report in reports)


def test_invalid_terminal_retry_retains_lineage(tmp_path):
    import hashlib

    from matric_eval.results.contract import ArtifactReference
    from matric_eval.state.observation_identity import CleanupReceipt

    item = work("invalid")
    item.capability = ReplayCapability(
        adapter_id="isolated-fixture", mode="isolated", mechanism_version="1"
    )
    artifact = tmp_path / "cleanup.json"
    artifact.write_text("{}")
    evidence = ArtifactReference(
        uri=str(artifact), sha256=hashlib.sha256(b"{}").hexdigest(), unavailable_reason=None
    )
    intent = AttemptIntent(
        attempt_id="invalid-first",
        identities=item.identities,
        fingerprint=item.fingerprint,
        replay_capability=item.capability,
    )
    failed = terminal(intent)
    failed.observations[0].outcome = "grader_failed"
    failed.observations[0].value = None
    failed.observations[0].reason = "invalid grader"
    failed.cleanup = CleanupReceipt(
        attempt_id=intent.attempt_id,
        worker_id="fixture",
        status="verified_absent",
        evidence=evidence,
    )

    class Isolated(Service):
        def run(self, item, intent):
            result = terminal(intent)
            result.cleanup = CleanupReceipt(
                attempt_id=intent.attempt_id,
                worker_id="fixture",
                status="verified_absent",
                evidence=evidence,
            )
            return result

    with ObservationJournal(tmp_path / "journal.sqlite") as journal:
        journal.record_intent(intent)
        journal.retain_invalid_terminal(failed)
        assert journal.load_accepted(item.identities, item.fingerprint) is None
        result = execute(schedule([item]), journal, Isolated(), tmp_path / "events.jsonl")
        accepted = journal.load_accepted(item.identities, item.fingerprint)
        assert accepted.observations[0].previous_attempt_id == intent.attempt_id
        assert len(journal.list_attempts()) == 2
    assert result["entries"][0]["disposition"] == "completed"


def test_dependencies_and_authorization(tmp_path):
    items = [
        work("denied", suite="unknown"),
        work("dependent", dependencies=["denied"]),
        work("eligible"),
    ]
    with ObservationJournal(tmp_path / "journal.sqlite") as journal:
        service = Service()
        report = execute(schedule(items), journal, service, tmp_path / "events.jsonl")
    assert report["order"] == ["eligible"]
    assert [row["disposition"] for row in report["entries"]] == ["blocked", "blocked", "completed"]
    assert "denied" not in service.checked


def test_engine_lock_prevents_dispatch(tmp_path):
    import fcntl

    with (tmp_path / ".engine.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with ObservationJournal(tmp_path / "journal.sqlite") as journal:
            with pytest.raises(BlockingIOError):
                execute(
                    schedule([work("one")]), journal, Service(), tmp_path / "other-receipt.jsonl"
                )
            assert journal.list_attempts() == []


def test_unknown_failure_is_global_and_cleanup_attempted(tmp_path):
    class Broken(Service):
        stopped = False

        def run(self, item, intent):
            raise OSError("shared filesystem unavailable")

        def stop(self):
            self.stopped = True
            raise OSError("cleanup evidence unavailable")

    service = Broken()
    with ObservationJournal(tmp_path / "journal.sqlite") as journal:
        report = execute(
            schedule([work("one"), work("two", suite="direct")]),
            journal,
            service,
            tmp_path / "events.jsonl",
        )
        assert len(journal.list_attempts()) == 1
    assert report["global_stop"] and service.stopped
    assert report["entries"][1]["reasons"] == ["global_stop"]


@pytest.fixture
def command_services(tmp_path, monkeypatch):
    """Actual Unix broker RPC and CLI Docker shim; no GPU allocation is claimed."""
    import json
    import os
    import socketserver
    import sys
    import threading

    state = tmp_path / "docker-state"
    state.mkdir()
    binaries = tmp_path / "bin"
    binaries.mkdir()
    docker = binaries / "docker"
    docker.write_text(
        """#!"""
        + sys.executable
        + """
import json, os, pathlib, sys
root=pathlib.Path(os.environ['SCHEDULE_FAKE_DOCKER'])
a=sys.argv[3:]
if a[:2]==['container','ls']:
 print('\\n'.join(p.stem for p in root.glob('*.json')))
elif a[0]=='inspect':
 print('['+(root/(a[1]+'.json')).read_text()+']')
elif a[0] in ['stop','rm']:
 for p in root.glob('*.json'):
  data=json.loads(p.read_text())
  if data['Id']==a[-1]:
   if a[0]=='rm': p.unlink()
   else:
    data['State']['Running']=False
    p.write_text(json.dumps(data))
"""
    )
    docker.chmod(0o755)
    nvidia = binaries / "nvidia-smi"
    nvidia.write_text("#!/bin/sh\nexit 0\n")
    nvidia.chmod(0o755)
    monkeypatch.setenv("PATH", str(binaries) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("SCHEDULE_FAKE_DOCKER", str(state))
    service = tmp_path / "service.py"
    service.write_text("""import hashlib,json,os,pathlib,sys,time
container,resource,ready=sys.argv[1:]
root=pathlib.Path(os.environ['SCHEDULE_FAKE_DOCKER'])
(root/(container+'.json')).write_text(json.dumps({'Id':'synthetic-'+resource,'Config':{'Labels':{'matric.resource':resource}},'State':{'Running':True,'Pid':os.getpid()}}))
allocation=json.loads(os.environ['MATRIC_EVAL_GPU_ALLOCATION_JSON'])
assert allocation['gpu_uuids']==os.environ['CUDA_VISIBLE_DEVICES'].split(',')
token=os.environ['OLLAMA_UNIFY_GPU_LEASE']
pathlib.Path(ready+'.'+token+'.ready').write_text(json.dumps({'lease_token_sha256':hashlib.sha256(token.encode()).hexdigest()}))
while True: time.sleep(.1)
""")
    check = tmp_path / "check.py"
    check.write_text(
        "import os,pathlib\npathlib.Path(os.environ['MATRIC_PREFLIGHT_RECEIPT']).write_text('{\"passed\":true}')\n"
    )
    task = tmp_path / "task.py"
    task.write_text("""import json,os,pathlib,sys
from matric_eval.state.journal import AttemptIntent,TerminalAttempt
from matric_eval.results.contract import Observation
r=json.loads(pathlib.Path(os.environ['MATRIC_SCHEDULE_REQUEST']).read_text())
if r['work']['suite']=='direct': sys.exit(17)
i=AttemptIntent.model_validate(r['intent'])
t=TerminalAttempt(attempt_id=i.attempt_id,observations=[Observation(observation_id=x.logical_id(),identity=x,attempt_id=i.attempt_id,previous_attempt_id=i.previous_attempt_id,accepted=False,execution='completed',outcome='observed',value=0,reason=None,native_status='fixture',judge=None,artifacts=[]) for x in i.identities])
pathlib.Path(os.environ['MATRIC_SCHEDULE_TERMINAL']).write_text(t.model_dump_json())
""")
    leases = []
    acquisitions = []

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            request = json.loads(self.rfile.readline())
            action = request["action"]
            response = {"ok": True}
            if action == "acquire":
                acquisitions.append(request)
                lease = {
                    "owner": request["owner"],
                    "gpu_uuids": request["gpu_uuids"],
                    "requested_mib": request["requested_mib"],
                    "token": "synthetic-" + str(len(leases)),
                }
                leases.append(lease)
                response["lease"] = lease
            elif action == "status":
                response["leases"] = leases
            elif action == "release":
                leases[:] = [x for x in leases if x["token"] != request["token"]]
            self.wfile.write(json.dumps(response).encode() + b"\n")

    # Keep Unix socket path below sockaddr_un's limit on long pytest roots.
    import tempfile

    with tempfile.TemporaryDirectory(prefix="schedule-broker-") as sockets:
        broker = socketserver.UnixStreamServer(str(Path(sockets) / "broker.sock"), Handler)
        thread = threading.Thread(target=broker.serve_forever, daemon=True)
        thread.start()
        try:
            yield {
                "socket": broker.server_address,
                "service": service,
                "check": check,
                "task": task,
                "leases": leases,
                "acquisitions": acquisitions,
            }
        finally:
            broker.shutdown()
            broker.server_close()
            thread.join(5)


def test_resident_service_normalizes_legacy_scalar_to_native_allocation() -> None:
    from matric_eval.studies.schedule_cli import ResidentService

    gpu = "GPU-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    legacy = ResidentService(command=["true"], gpu=gpu, memory_mib=75_000)
    native = ResidentService(
        command=["true"],
        gpu_allocation={
            "schema": "matric-eval.gpu-allocation/1",
            "gpu_uuids": [gpu],
            "memory_mib": 75_000,
            "topology_policy": None,
        },
    )

    assert legacy.model_dump() == native.model_dump()


@pytest.mark.parametrize("scenario", ["suite", "global", "crash"])
def test_supported_command_cli_end_to_end(tmp_path, command_services, scenario):
    import json
    import os
    import subprocess
    import sys

    from matric_eval.studies.schedule_cli import (
        Binding,
        CommandPlan,
        ResidentService,
        capture_binding,
    )

    fixtures = command_services
    if scenario == "crash":
        fixtures["task"].write_text(
            fixtures["task"].read_text().replace("sys.exit(17)", "__import__('time').sleep(120)")
        )
    gpu_a = "GPU-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    gpu_b = "GPU-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    service = ResidentService(
        command=[
            sys.executable,
            str(fixtures["service"]),
            "{container}",
            "{resource_id}",
            "{ready_base}",
        ],
        gpu_allocation={
            "schema": "matric-eval.gpu-allocation/1",
            "gpu_uuids": [gpu_b, gpu_a],
            "memory_mib": 2,
            "topology_policy": None,
        },
        broker_socket=fixtures["socket"],
        ready_timeout_seconds=10,
    )
    checks = [
        {
            "id": stage,
            "stage": stage,
            "command": [sys.executable, str(fixtures["check"])],
            "inputs": [str(fixtures["check"]), str(fixtures["task"]), str(fixtures["service"])],
            "timeout_seconds": 5,
            "freshness_seconds": 600,
            "receipt_contract": {"passed": True},
            "deterministic": True,
        }
        for stage in ["static", "cpu", "auxiliary", "target"]
    ]
    binding = Binding(
        preflight={"schema": "matric-eval.study-preflight/1", "checks": checks},
        service=service,
        command=[sys.executable, str(fixtures["task"])],
        timeout_seconds=10,
        suite_failure_exit_codes=[17] if scenario != "global" else [],
    )
    items = [
        work("admission", suite="direct"),
        work("independent"),
        work("deferred", suite="tau", deferred=True),
    ]
    for item in items:
        item.residency = service.model_dump()
        item.fingerprint.environment.document["scheduler_binding_sha256"] = capture_binding(binding)
    config = CommandPlan(
        schedule=schedule(items),
        bindings={item.key: binding for item in items if not item.deferred},
    )
    source = tmp_path / "schedule.json"
    source.write_text(config.model_dump_json())
    directory = tmp_path / "execution"
    command = [
        sys.executable,
        "-m",
        "matric_eval.studies.schedule_cli",
        "execute",
        "--plan",
        str(source),
        "--journal",
        str(tmp_path / "journal.sqlite"),
        "--directory",
        str(directory),
    ]
    if not storage_profile(tmp_path)["supported"]:
        # Exercise the real CLI with a private storage seam, as journal tests do.
        # This qualifies scheduling/transactions, never the host filesystem.
        command[1:3] = [
            "-c",
            "import runpy; import matric_eval.state.journal as j; "
            "original=j.storage_profile; "
            "j.storage_profile=lambda p: {**original(p), 'supported':True, "
            "'profile':'TEST-ONLY-sqlite-transaction-semantics'}; "
            "runpy.run_module('matric_eval.studies.schedule_cli', run_name='__main__', alter_sys=True)",
        ]
    reports = []
    if scenario == "crash":
        import signal
        import time

        child = subprocess.Popen(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=os.environ
        )
        deadline = time.monotonic() + 30
        while not list(directory.glob("tasks/*/controller.json")) and time.monotonic() < deadline:
            assert child.poll() is None
            time.sleep(0.05)
        assert list(directory.glob("tasks/*/controller.json"))
        child.send_signal(signal.SIGKILL)
        child.wait(timeout=10)
        child.stderr.close()
    for _ in range(2 if scenario == "suite" else 1):
        result = subprocess.run(command, capture_output=True, text=True, timeout=50, env=os.environ)
        assert result.returncode == 1, result.stderr
        assert result.stdout, result.stderr
        reports.append(json.loads(result.stdout))
    assert fixtures["acquisitions"]
    assert all(
        request["gpu_uuids"] == [gpu_b, gpu_a] and request["requested_mib"] == 2
        for request in fixtures["acquisitions"]
    )
    if scenario == "global":
        assert reports[0]["global_stop"]
        assert [row["disposition"] for row in reports[0]["entries"]] == [
            "failed",
            "blocked",
            "deferred",
        ]
        assert reports[0]["execution_order"] == ["admission"]
        assert not fixtures["leases"]
        return
    if scenario == "crash":
        assert [row["disposition"] for row in reports[0]["entries"]] == [
            "blocked",
            "completed",
            "deferred",
        ]
        assert reports[0]["execution_order"] == ["independent"]
        assert not reports[0]["global_stop"]
        assert not fixtures["leases"]
        assert all(
            json.loads(p.read_text())["cleanup"] == "complete"
            for p in directory.glob("tasks/*/controller.json")
        )
        return
    assert [row["disposition"] for row in reports[0]["entries"]] == [
        "failed",
        "completed",
        "deferred",
    ]
    assert [row["disposition"] for row in reports[1]["entries"]] == [
        "blocked",
        "reused",
        "deferred",
    ]
    assert reports[0]["execution_order"] == ["admission", "independent"]
    assert reports[1]["execution_order"] == []
    assert reports[0]["observed_model_loads"] == 2
    assert reports[1]["observed_model_loads"] == 0
    assert not fixtures["leases"]
    assert all(
        json.loads(p.read_text())["cleanup"] == "complete"
        for p in directory.glob("resources/*/record.json")
    )
    fixtures["task"].write_text(fixtures["task"].read_text() + "\n# changed native adapter\n")
    dry_run = [*command]
    dry_run[3] = "plan"
    changed = subprocess.run(dry_run, capture_output=True, text=True, timeout=20, env=os.environ)
    assert changed.returncode == 1, changed.stderr
    invalidated = json.loads(changed.stdout)
    assert [row["disposition"] for row in invalidated["entries"]] == [
        "invalidated",
        "invalidated",
        "deferred",
    ]
    assert invalidated["expected_model_loads"] == 0
    with ObservationJournal(tmp_path / "journal.sqlite") as journal:
        assert len(journal.list_attempts()) == 2


def test_prior_direct_bfcl_reuse_only_needs_no_new_adapter_fingerprint(tmp_path):
    from matric_eval.studies.schedule_cli import CommandAdapter, CommandPlan

    direct, bfcl = work("prior-direct", suite="direct"), work("prior-bfcl", suite="bfcl")
    missing = work("missing", suite="bfcl")
    for item in [direct, bfcl, missing]:
        item.reuse_only = True
        item.fingerprint.protocol.document = {"profile": "recoverable-text-sample/1"}
        item.fingerprint.sampler.document["effective_config"] = item.scoring_budget
    config = CommandPlan(schedule=schedule([direct, bfcl, missing]), bindings={})
    adapter = CommandAdapter(config, tmp_path / "private")
    with ObservationJournal(tmp_path / "journal.sqlite") as journal:
        for item in [direct, bfcl]:
            intent = AttemptIntent(
                attempt_id=item.key,
                identities=item.identities,
                fingerprint=item.fingerprint,
                replay_capability=item.capability,
            )
            journal.record_intent(intent)
            journal.commit_terminal(terminal(intent))
        report = execute(config.schedule, journal, adapter, tmp_path / "events.jsonl")
        assert len(journal.list_attempts()) == 2
    assert [row["disposition"] for row in report["entries"]] == ["reused", "reused", "blocked"]
    assert report["observed_model_loads"] == 0


def test_suite_failure_does_not_suppress_other_model_suite(tmp_path):
    class ModelAdmission(Service):
        def start(self, item):
            if item.model == "source":
                raise SuiteFailure("model-local admission")
            super().start(item)

    service = ModelAdmission()
    with ObservationJournal(tmp_path / "journal.sqlite") as journal:
        report = execute(
            schedule([work("source-task", model="source"), work("other-task", model="other")]),
            journal,
            service,
            tmp_path / "events.jsonl",
        )
    assert [row["disposition"] for row in report["entries"]] == ["failed", "completed"]
