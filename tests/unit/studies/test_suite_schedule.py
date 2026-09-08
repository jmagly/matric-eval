"""Real journal scheduling qualification, with process restart and admission failure."""

import multiprocessing
from pathlib import Path

import pytest

from matric_eval.results.contract import Observation, ObservationIdentity
from matric_eval.state.journal import AttemptIntent, ObservationJournal, TerminalAttempt
from matric_eval.state.observation_identity import (
    COMPONENTS,
    ExecutionFingerprint,
    ReplayCapability,
)
from matric_eval.studies.suite_schedule import Schedule, SuiteFailure, Work, execute, plan


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
