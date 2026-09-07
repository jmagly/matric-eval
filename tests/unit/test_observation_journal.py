"""Local-ext4 journal fixtures, including independently killed/racing processes."""

import hashlib
import json
import multiprocessing
import os
import signal
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from matric_eval.results.contract import Observation, ObservationIdentity
from matric_eval.state.journal import (
    AttemptIntent,
    JournalConflict,
    JournalCorruption,
    ObservationJournal,
    ReuseRefused,
    TerminalAttempt,
    UnsupportedStorage,
    storage_profile,
)
from matric_eval.state.observation_identity import (
    COMPONENTS,
    ExecutionFingerprint,
    ReplayCapability,
)


def fingerprint() -> ExecutionFingerprint:
    return ExecutionFingerprint.model_validate(
        {
            name: {
                "document": {"revision": "synthetic-1", "configuration": {}},
                "status": "verified",
            }
            for name in COMPONENTS
        }
    )


def intent(
    attempt: str = "attempt-1", previous: str | None = None, sample: str = "str:1"
) -> AttemptIntent:
    return AttemptIntent(
        attempt_id=attempt,
        previous_attempt_id=previous,
        identities=[
            ObservationIdentity(
                run_id="run",
                model_id="model:a/b",
                benchmark_id="benchmark",
                allocation_id="allocation",
                sample_id=sample,
                trial_id="trial-1",
                metric_id=metric,
            )
            for metric in ("accuracy", "latency")
        ],
        fingerprint=fingerprint(),
        replay_capability=ReplayCapability(
            adapter_id="synthetic", mode="manual", mechanism_version="1"
        ),
    )


def terminal(request: AttemptIntent, value: float = 1.0) -> TerminalAttempt:
    return TerminalAttempt(
        attempt_id=request.attempt_id,
        observations=[
            Observation(
                observation_id=identity.logical_id(),
                identity=identity,
                attempt_id=request.attempt_id,
                previous_attempt_id=request.previous_attempt_id,
                accepted=True,
                execution="completed",
                outcome="observed",
                value=value,
                reason=None,
                native_status="success",
                judge=None,
                artifacts=[],
            )
            for identity in request.identities
        ],
    )


@pytest.fixture
def journal_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, record_property: Any) -> Path:
    import matric_eval.state.journal as module

    path = tmp_path / "observations.sqlite"
    actual = storage_profile(path)
    record_property("actual_storage_profile", json.dumps(actual, sort_keys=True))
    record_property(
        "filesystem_qualification",
        "actual_ext4" if actual["supported"] else "sqlite_transaction_semantics_only",
    )
    if not actual["supported"]:
        # Private test seam only: ordinary CI still tests transactions/races but
        # cannot claim the filesystem qualification exercised on A100 ext4.
        monkeypatch.setattr(module, "storage_profile", _semantics_only_profile)
    return path


def _semantics_only_profile(path: Path) -> dict[str, Any]:
    return {
        **storage_profile(path),
        "supported": True,
        "profile": "TEST-ONLY-sqlite-transaction-semantics",
    }


def _child_storage_seam(path: str) -> None:
    import matric_eval.state.journal as module

    if not storage_profile(Path(path))["supported"]:
        module.storage_profile = _semantics_only_profile


def _kill_worker(path: str, stage: str, output: Any) -> None:
    _child_storage_seam(path)
    with ObservationJournal(path) as journal:
        request = intent()
        journal.record_intent(request)
        real_connection = journal.connection

        def trace(statement: str) -> None:
            if (
                stage == "terminal_insert"
                and statement.startswith("INSERT OR IGNORE INTO terminals")
            ) or (stage == "before_commit" and statement == "COMMIT"):
                os.kill(os.getpid(), signal.SIGKILL)

        real_connection.set_trace_callback(trace)

        class LostAcknowledgement:
            def __getattr__(self, name: str) -> Any:
                return getattr(real_connection, name)

            def commit(self) -> None:
                real_connection.commit()
                os.kill(os.getpid(), signal.SIGKILL)

        if stage == "after_commit":
            journal.connection = LostAcknowledgement()  # type: ignore[assignment]
        receipt = journal.commit_terminal(terminal(request))
        output.send(receipt.model_dump())
        if stage == "after_receipt":
            os.kill(os.getpid(), signal.SIGKILL)


def _race_worker(
    path: str, attempt_id: str, value: float, ready: Any, release: Any, output: Any
) -> None:
    _child_storage_seam(path)
    try:
        with ObservationJournal(path) as journal:
            request = intent(attempt_id)
            journal.record_intent(request)
            ready.send(True)
            if not release.wait(15):
                raise RuntimeError("parent did not release race")
            try:
                receipt = journal.commit_terminal(terminal(request, value))
                output.send(("accepted", receipt.model_dump()))
            except JournalConflict as exc:
                output.send(("conflict", str(exc)))
    except BaseException as exc:
        output.send(("error", repr(exc)))


def test_durable_intent_atomic_named_metrics_and_idempotent_receipt(journal_path: Path) -> None:
    request = intent()
    with ObservationJournal(journal_path) as journal:
        assert journal.connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)
        assert journal.connection.execute("PRAGMA synchronous").fetchone() == (3,)
        assert journal.connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        with pytest.raises(JournalConflict, match="durable intent"):
            journal.commit_terminal(terminal(request))
        before = journal.record_intent(request)
        assert journal.record_intent(request) == before
        partial = terminal(request).model_copy(
            update={"observations": terminal(request).observations[:1]}
        )
        with pytest.raises(JournalConflict, match="exact declared"):
            journal.commit_terminal(partial)
        assert journal.connection.execute("SELECT count(*) FROM terminals").fetchone() == (0,)
        receipt = journal.commit_terminal(terminal(request))
        assert journal.commit_terminal(terminal(request)) == receipt
        assert journal.connection.execute("SELECT count(*) FROM acceptances").fetchone() == (2,)
    with ObservationJournal(journal_path) as reopened:
        assert reopened.load_accepted(request.identities, fingerprint()) == terminal(request)
        with pytest.raises(ReuseRefused, match="metric set"):
            reopened.load_accepted(request.identities[:1], fingerprint())


@pytest.mark.parametrize(
    "stage,accepted",
    [
        ("terminal_insert", False),
        ("before_commit", False),
        ("after_commit", True),
        ("after_receipt", True),
    ],
)
def test_process_kills_and_lost_ack(stage: str, accepted: bool, journal_path: Path) -> None:
    with ObservationJournal(journal_path):
        pass
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_kill_worker, args=(str(journal_path), stage, sender))
    process.start()
    try:
        process.join(25)
        assert not process.is_alive(), "bounded fault worker did not finish"
        assert process.exitcode == -signal.SIGKILL
        if stage == "after_receipt":
            assert receiver.poll(2)
            assert receiver.recv()["observation_ids"] == sorted(
                identity.logical_id() for identity in intent().identities
            )
        with ObservationJournal(journal_path) as journal:
            assert len(journal.list_attempts()) == 1
            assert (
                journal.load_accepted(intent().identities, fingerprint()) is not None
            ) is accepted
            receipt = journal.commit_terminal(terminal(intent()))
            assert journal.commit_terminal(terminal(intent())) == receipt
            assert journal.connection.execute("SELECT count(*) FROM terminals").fetchone() == (1,)
            assert journal.connection.execute("SELECT count(*) FROM acceptances").fetchone() == (2,)
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)
        receiver.close()
        sender.close()


@pytest.mark.parametrize(
    "same_attempt,values",
    [(True, (1.0, 1.0)), (True, (0.0, 1.0)), (False, (1.0, 1.0)), (False, (0.0, 1.0))],
)
def test_independent_writers_preserve_loser_history(
    same_attempt: bool, values: tuple[float, float], journal_path: Path
) -> None:
    with ObservationJournal(journal_path):
        pass
    context = multiprocessing.get_context("spawn")
    release = context.Event()
    processes, readers, ready_readers, connections = [], [], [], []
    try:
        for index in range(2):
            ready_read, ready_write = context.Pipe(duplex=False)
            read, write = context.Pipe(duplex=False)
            process = context.Process(
                target=_race_worker,
                args=(
                    str(journal_path),
                    "attempt-1" if same_attempt else f"attempt-{index + 1}",
                    values[index],
                    ready_write,
                    release,
                    write,
                ),
            )
            process.start()
            processes.append(process)
            readers.append(read)
            ready_readers.append(ready_read)
            connections.extend((ready_read, ready_write, read, write))
        for ready in ready_readers:
            assert ready.poll(15) and ready.recv() is True
        release.set()
        outcomes = []
        for reader in readers:
            assert reader.poll(15)
            outcomes.append(reader.recv()[0])
        for process in processes:
            process.join(10)
            assert process.exitcode == 0
        assert sorted(outcomes) == (
            ["accepted", "accepted"]
            if same_attempt and values[0] == values[1]
            else ["accepted", "conflict"]
        )
        with ObservationJournal(journal_path) as journal:
            assert journal.connection.execute("SELECT count(*) FROM acceptances").fetchone() == (2,)
            assert journal.connection.execute("SELECT count(*) FROM terminals").fetchone() == (
                1 if same_attempt else 2,
            )
            assert len(journal.dispositions()) == (0 if outcomes == ["accepted", "accepted"] else 1)
            for attempt in journal.list_attempts():
                assert attempt["terminal"] is not None
                assert all(not row.accepted for row in attempt["terminal"].observations)
            projected = journal.load_accepted(intent().identities, fingerprint())
            assert projected is not None
            assert all(row.accepted for row in projected.observations)
    finally:
        release.set()
        for process in processes:
            if process.is_alive():
                process.kill()
            process.join(5)
        for connection in connections:
            connection.close()


def test_predecessors_scope_fingerprint_and_reused_payload_are_checked(journal_path: Path) -> None:
    with ObservationJournal(journal_path) as journal:
        with pytest.raises(JournalConflict, match="predecessor"):
            journal.record_intent(intent("child", "missing"))
        journal.record_intent(intent())
        journal.record_intent(intent("child", "attempt-1"))
        with pytest.raises(JournalConflict, match="predecessor"):
            journal.record_intent(intent("other", "attempt-1", "int:1"))
        changed = intent("different")
        changed.fingerprint.model.document["revision"] = "new"
        with pytest.raises(JournalConflict, match="fingerprint"):
            journal.record_intent(changed)
        journal.commit_terminal(terminal(intent()))
        with pytest.raises(JournalConflict, match="terminal_conflict"):
            journal.commit_terminal(terminal(intent(), 0.0))
        assert (
            journal.load_accepted(intent().identities, fingerprint()).observations[0].value == 1.0
        )


def test_unknown_fingerprint_retained_but_not_reused(journal_path: Path) -> None:
    request = intent()
    request.fingerprint.model.status = "unverified"
    request.fingerprint.model.unavailable_reason = "provider revision unknown"
    with ObservationJournal(journal_path) as journal:
        journal.record_intent(request)
        journal.commit_terminal(terminal(request))
        assert journal.list_attempts()[0]["terminal"] is not None
        with pytest.raises(ReuseRefused, match="component_unknown:model"):
            journal.load_accepted(request.identities, request.fingerprint)


@pytest.mark.parametrize("component", COMPONENTS)
def test_changed_effective_component_refused_through_storage(
    component: str, journal_path: Path
) -> None:
    with ObservationJournal(journal_path) as journal:
        journal.record_intent(intent())
        journal.commit_terminal(terminal(intent()))
        current = fingerprint()
        getattr(current, component).document["revision"] = "changed-effective-identity"
        with pytest.raises(ReuseRefused, match=f"component_mismatch:{component}"):
            journal.load_accepted(intent().identities, current)


def test_artifact_content_rechecked_without_mutating_evidence(journal_path: Path) -> None:
    artifact = journal_path.parent / "native.json"
    artifact.write_bytes(b"native evidence")
    completed = terminal(intent())
    from matric_eval.results.contract import ArtifactReference

    completed.artifacts = [
        ArtifactReference(
            uri=str(artifact),
            sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
            unavailable_reason=None,
        )
    ]
    with ObservationJournal(journal_path) as journal:
        journal.record_intent(intent())
        journal.commit_terminal(completed)
        assert artifact.read_bytes() == b"native evidence"
        artifact.unlink()
        with pytest.raises(ReuseRefused, match="missing"):
            journal.load_accepted(intent().identities, fingerprint())


def test_unknown_schema_corruption_and_immutability(journal_path: Path) -> None:
    with ObservationJournal(journal_path) as journal:
        journal.record_intent(intent())
        journal.commit_terminal(terminal(intent()))
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            journal.connection.execute("UPDATE terminals SET digest='wrong'")
        journal.connection.execute("DROP TRIGGER immutable_terminals_update")
        journal.connection.execute("UPDATE terminals SET digest='wrong'")
        with pytest.raises(JournalCorruption):
            journal.audit()
    with pytest.raises(JournalCorruption):
        ObservationJournal(journal_path)


def test_newer_schema_version_is_not_guessed(journal_path: Path) -> None:
    with ObservationJournal(journal_path) as journal:
        journal.connection.execute("DROP TRIGGER immutable_metadata_update")
        journal.connection.execute("UPDATE metadata SET value='2' WHERE key='schema_version'")
    with pytest.raises(JournalCorruption, match="schema version"):
        ObservationJournal(journal_path)


def test_unknown_storage_diagnostic_only(
    monkeypatch: pytest.MonkeyPatch, journal_path: Path
) -> None:
    import matric_eval.state.journal as module

    with ObservationJournal(journal_path) as journal:
        journal.record_intent(intent())
    monkeypatch.setattr(
        module,
        "storage_profile",
        lambda path: {"supported": False, "reason": "unsupported_storage"},
    )
    with pytest.raises(UnsupportedStorage):
        ObservationJournal(journal_path)
    with ObservationJournal(journal_path, read_only=True) as journal:
        assert len(journal.list_attempts()) == 1
        with pytest.raises(UnsupportedStorage):
            journal.record_intent(intent("other"))
        with pytest.raises(UnsupportedStorage):
            journal.load_accepted(intent().identities, fingerprint())


def test_strict_identity_and_cleanup_binding() -> None:
    with pytest.raises(ValidationError):
        intent().identities[0].model_validate(
            {**intent().identities[0].model_dump(), "sample_id": 1}
        )
    assert (
        intent(sample="int:1").identities[0].logical_id()
        != intent(sample="str:1").identities[0].logical_id()
    )
    with pytest.raises(ValidationError):
        TerminalAttempt.model_validate(
            {
                **terminal(intent()).model_dump(),
                "cleanup": {"attempt_id": "wrong", "status": "uncertain"},
            }
        )


@pytest.mark.parametrize("execution", ["partial", "unknown", "not_attempted"])
def test_nonterminal_measurement_cannot_complete_durable_intent(
    execution: str, journal_path: Path
) -> None:
    candidate = terminal(intent()).model_dump()
    for row in candidate["observations"]:
        row.update(
            execution=execution, outcome="unavailable", value=None, reason="execution not terminal"
        )
    with ObservationJournal(journal_path) as journal:
        journal.record_intent(intent())
        with pytest.raises(JournalConflict, match="not terminal"):
            journal.commit_terminal(TerminalAttempt.model_validate(candidate))
        assert journal.list_attempts()[0]["terminal"] is None
        for row in candidate["observations"]:
            row["accepted"] = False
        payload = json.dumps(
            TerminalAttempt.model_validate(candidate).model_dump(),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        journal.connection.execute(
            "INSERT INTO terminals VALUES (?,?,?)",
            ("attempt-1", payload, hashlib.sha256(payload.encode()).hexdigest()),
        )
        with pytest.raises(JournalCorruption, match="nonterminal"):
            journal.audit()
