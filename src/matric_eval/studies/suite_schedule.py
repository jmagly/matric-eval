"""Serial suite scheduling over the existing immutable observation journal.

Adapters own execution evidence and resource cleanup. Planning never dispatches.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import Field, model_validator
from typing_extensions import Self

from matric_eval.results.contract import ObservationIdentity, Record, Text
from matric_eval.state.journal import (
    AttemptIntent,
    ObservationJournal,
    ReuseRefused,
    TerminalAttempt,
)
from matric_eval.state.observation_identity import (
    ExecutionFingerprint,
    ReplayCapability,
    canonical_json,
)


class Work(Record):
    key: Text
    suite: Text
    model: Text
    identities: list[ObservationIdentity] = Field(min_length=1)
    fingerprint: ExecutionFingerprint
    capability: ReplayCapability
    seed: int
    scoring_budget: dict[str, Any]
    # Includes runtime, model digest, placement and isolation requirements.
    residency: dict[str, Any]
    dependencies: list[str] = Field(default_factory=list)
    deferred: bool = False
    group_resident: bool = False

    @model_validator(mode="after")
    def identity(self) -> Self:
        AttemptIntent(
            attempt_id="validation",
            identities=self.identities,
            fingerprint=self.fingerprint,
            replay_capability=self.capability,
        )
        if any(
            row.model_id != self.model or row.benchmark_id != self.suite for row in self.identities
        ):
            raise ValueError("work model/suite contradict observation identity")
        if self.fingerprint.sampler.document.get("generation_seed") != self.seed:
            raise ValueError("seed must match captured sampler fingerprint")
        if self.fingerprint.protocol.document.get("scoring_budget") != self.scoring_budget:
            raise ValueError("scoring budget must match captured protocol fingerprint")
        return self

    @property
    def resident_key(self) -> str:
        document = {
            "model": self.model,
            "identity": self.fingerprint.model.model_dump(),
            "residency": self.residency,
        }
        if not self.group_resident:
            document["work"] = self.key
        return hashlib.sha256(canonical_json(document).encode()).hexdigest()


class Schedule(Record):
    work: list[Work]
    policy: Literal["stop", "continue-independent"]
    authorized_suites: list[str]
    amendment_reason: Text

    @model_validator(mode="after")
    def unique(self) -> Self:
        keys = [work.key for work in self.work]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate work key")
        ids = [row.logical_id() for work in self.work for row in work.identities]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate observation identity")
        seen: set[str] = set()
        for work in self.work:
            if not set(work.dependencies) <= seen:
                raise ValueError("dependencies must precede work in frozen order")
            seen.add(work.key)
        return self


class Adapter(Protocol):
    def preflight(self, work: Work) -> list[str]:
        """Return blockers after validating current #155 admission evidence."""
        ...

    def start(self, work: Work) -> None:
        """Acquire lifecycle ownership and load the requested resident model."""
        ...

    def run(self, work: Work, intent: AttemptIntent) -> TerminalAttempt:
        """Reset task state; preserve IDs, seed and budgets; return native evidence."""
        ...

    def stop(self) -> bool:
        """True only with verified resource cleanup; uncertainty stops all work."""
        ...


class SuiteFailure(Exception):
    """Confirmed suite-local failure, such as rejected admission."""


class GlobalFailure(Exception):
    """Shared resource, ownership or integrity failure."""


def plan(
    schedule: Schedule, journal: ObservationJournal, preflight: Callable[[Work], list[str]]
) -> dict[str, Any]:
    """Revalidate all eligible suites before choosing the serial model-load order."""
    schedule = Schedule.model_validate(schedule.model_dump())
    entries: dict[str, dict[str, Any]] = {}
    attempts = journal.list_attempts()
    for work in schedule.work:
        entry: dict[str, Any] = {
            "key": work.key,
            "suite": work.suite,
            "model": work.model,
            "seed": work.seed,
            "identities": [row.model_dump() for row in work.identities],
            "scoring_budget": work.scoring_budget,
            "fingerprint": work.fingerprint.sha256,
            "disposition": "ready",
            "reasons": [],
            "attempt_id": None,
        }
        entries[work.key] = entry
        if work.deferred:
            entry.update(disposition="deferred", reasons=["explicitly_deferred"])
            continue
        if work.suite not in schedule.authorized_suites:
            entry.update(disposition="blocked", reasons=["suite_not_authorized"])
            continue
        reasons = [*work.fingerprint.eligibility.reasons, *preflight(work)]
        if reasons:
            entry.update(disposition="blocked", reasons=reasons)
            continue
        try:
            accepted = journal.load_accepted(work.identities, work.fingerprint)
        except ReuseRefused as exc:
            entry.update(disposition="invalidated", reasons=[str(exc)])
            continue
        if accepted is not None:
            if all(
                row.execution == "completed" and row.outcome == "observed"
                for row in accepted.observations
            ):
                entry.update(
                    disposition="reused",
                    attempt_id=accepted.attempt_id,
                    observation_ids=[row.observation_id for row in accepted.observations],
                )
            else:
                entry.update(
                    disposition="blocked", reasons=["accepted_invalid_result_requires_review"]
                )
            continue
        scope = work.identities[0].model_dump(exclude={"metric_id"})
        previous = [
            row
            for row in attempts
            if row["intent"].identities[0].model_dump(exclude={"metric_id"}) == scope
        ]
        if previous:
            predecessors = {row["intent"].previous_attempt_id for row in previous}
            tips = [row for row in previous if row["intent"].attempt_id not in predecessors]
            if len(tips) != 1:
                entry.update(disposition="blocked", reasons=["ambiguous_attempt_lineage"])
                continue
            prior = tips[0]
            entry["attempt_id"] = prior["intent"].attempt_id
            mismatch = prior["intent"].fingerprint.mismatch_reasons(work.fingerprint)
            terminal = prior["terminal"]
            if mismatch:
                entry.update(disposition="invalidated", reasons=mismatch)
            elif (
                terminal is None
                or work.capability.mode != "isolated"
                or terminal.cleanup is None
                or terminal.cleanup.status != "verified_absent"
            ):
                entry.update(disposition="blocked", reasons=["unsafe_external_replay"])
            else:
                entry["reasons"] = ["retry_invalid_with_verified_cleanup"]
    # Stable topological grouping; only explicit compatible-residency opt-in moves work.
    pending = [work for work in schedule.work if entries[work.key]["disposition"] == "ready"]
    satisfied = {key for key, row in entries.items() if row["disposition"] == "reused"}
    order: list[str] = []
    resident = None
    loads = 0
    while pending:
        eligible = [work for work in pending if set(work.dependencies) <= satisfied]
        if not eligible:
            for work in pending:
                entries[work.key].update(disposition="blocked", reasons=["dependency_not_eligible"])
            break
        chosen = next((work for work in eligible if work.resident_key == resident), eligible[0])
        if chosen.resident_key != resident:
            loads += 1
        resident = chosen.resident_key
        order.append(chosen.key)
        satisfied.add(chosen.key)
        pending.remove(chosen)
    return {
        "schema": "matric-eval.suite-schedule/1",
        "schedule_sha256": hashlib.sha256(
            canonical_json(schedule.model_dump()).encode()
        ).hexdigest(),
        "policy": schedule.policy,
        "amendment_reason": schedule.amendment_reason,
        "frozen_order": [work.key for work in schedule.work],
        "order": order,
        "expected_model_loads": loads,
        "entries": list(entries.values()),
    }


def _event(path: Path, event: dict[str, Any]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, "a") as output:
        output.write(canonical_json(event) + "\n")
        output.flush()
        os.fsync(output.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def execute(
    schedule: Schedule, journal: ObservationJournal, adapter: Adapter, receipt: Path
) -> dict[str, Any]:
    """Hold a single-writer schedule lock and persist intent before any task action."""
    receipt.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (journal.path.parent / ".engine.lock").open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _execute(schedule, journal, adapter, receipt)


def _stop(adapter: Adapter) -> bool:
    try:
        return adapter.stop() is True
    except Exception:
        return False


def _execute(
    schedule: Schedule, journal: ObservationJournal, adapter: Adapter, receipt: Path
) -> dict[str, Any]:
    report = plan(schedule, journal, adapter.preflight)
    _event(receipt, {"event": "plan", "plan": report})
    entries = {row["key"]: row for row in report["entries"]}
    work_by_key = {work.key: work for work in schedule.work}
    resident: str | None = None
    failed_suites: set[str] = set()
    global_stop = False
    report["observed_model_loads"] = 0
    report["execution_order"] = []
    try:
        for key in report["order"]:
            work, entry = work_by_key[key], entries[key]
            if global_stop or (failed_suites and schedule.policy == "stop"):
                entry.update(
                    disposition="blocked", reasons=["global_stop" if global_stop else "stop_policy"]
                )
                continue
            if work.suite in failed_suites or any(
                entries[dep]["disposition"] not in {"completed", "reused"}
                for dep in work.dependencies
            ):
                entry.update(disposition="blocked", reasons=["suite_or_dependency_failed"])
                continue
            try:
                if adapter.preflight(work):
                    raise SuiteFailure("preflight_changed")
                if resident != work.resident_key:
                    if resident is not None:
                        resident = None
                        if not _stop(adapter):
                            raise GlobalFailure("cleanup_unverified")
                    # Set ownership marker before start: partial acquisition also needs cleanup.
                    resident = work.resident_key
                    report["observed_model_loads"] += 1
                    adapter.start(work)
                intent = AttemptIntent(
                    attempt_id=str(uuid.uuid4()),
                    previous_attempt_id=entry["attempt_id"],
                    identities=work.identities,
                    fingerprint=work.fingerprint,
                    replay_capability=work.capability,
                )
                journal.record_intent(intent)
                entry["attempt_id"] = intent.attempt_id
                entry["disposition"] = "running"
                report["execution_order"].append(key)
                _event(receipt, {"event": "dispatch", "key": key, "attempt_id": intent.attempt_id})
                terminal = adapter.run(work, intent)
                if adapter.preflight(work):
                    raise GlobalFailure("execution_identity_changed")
                if work.capability.mode == "isolated" and (
                    terminal.cleanup is None or terminal.cleanup.status != "verified_absent"
                ):
                    raise GlobalFailure("task_cleanup_unverified")
                if terminal.attempt_id != intent.attempt_id:
                    raise GlobalFailure("adapter_attempt_mismatch")
                if all(
                    row.execution == "completed" and row.outcome == "observed"
                    for row in terminal.observations
                ):
                    journal.commit_terminal(terminal)
                    entry["disposition"] = "completed"
                else:
                    journal.retain_invalid_terminal(terminal)
                    raise SuiteFailure("invalid_terminal")
            except SuiteFailure:
                entry.update(disposition="failed", reasons=["suite_failure"])
                failed_suites.add(work.suite)
                if resident is not None:
                    resident = None
                    if not _stop(adapter):
                        global_stop = True
            except Exception:
                entry.update(disposition="failed", reasons=["global_resource_or_integrity_failure"])
                global_stop = True
            _event(receipt, {"event": "disposition", "entry": entry})
    finally:
        if resident is not None and not _stop(adapter):
            global_stop = True
        for entry in entries.values():
            if entry["disposition"] == "running":
                entry.update(disposition="unknown", reasons=["interrupted_execution"])
                global_stop = True
        report["global_stop"] = global_stop
        _event(receipt, {"event": "accounting", "report": report})
    return report
