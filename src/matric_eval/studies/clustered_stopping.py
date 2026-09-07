"""Locked append-only stopping records; actor strings are declarations, not authentication."""

from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import model_validator

from matric_eval.results.contract import ArtifactReference, Count, Record, Text
from matric_eval.studies.clustered_protocol import ClusteredProtocol, canonical, content_hash


class StoppingEvent(Record):
    version: Literal["1"]
    event_id: Text
    timestamp: Text
    actor: Text
    event_type: Literal[
        "enrollment_closed",
        "analysis_access",
        "stopping_evaluation",
        "operational_pause",
        "missingness_decision",
        "deviation_proposed",
        "deviation_approved",
        "deviation_rejected",
        "correction",
    ]
    reason: Text
    information_snapshot: Text
    authorized_action: Text
    tasks_accrued: Count
    clusters_accrued: Count
    outcomes_inspected: bool
    proposed_task_budget: Count | None = None
    proposed_cluster_budget: Count | None = None
    proposal_id: Text | None = None
    approved_deviation_id: Text | None = None
    supersedes_event_id: Text | None = None
    artifacts: list[ArtifactReference]

    @model_validator(mode="after")
    def event_fields(self) -> Self:
        timestamp = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must include timezone")
        if self.event_type == "deviation_proposed":
            if self.proposed_task_budget is None or self.proposed_cluster_budget is None:
                raise ValueError("deviation proposal must expose both revised budgets")
        elif self.proposed_task_budget is not None or self.proposed_cluster_budget is not None:
            raise ValueError("only proposals declare revised budgets")
        if (self.event_type in {"deviation_approved", "deviation_rejected"}) != (
            self.proposal_id is not None
        ):
            raise ValueError("approval/rejection must reference a proposal")
        if (self.event_type == "correction") != (self.supersedes_event_id is not None):
            raise ValueError("corrections append a reference, never edit history")
        return self


def _check_event(
    protocol: ClusteredProtocol, previous: list[StoppingEvent], event: StoppingEvent
) -> None:
    by_id = {item.event_id: item for item in previous}
    if event.event_id in by_id:
        raise ValueError("duplicate stopping event ID")
    if previous:
        if (
            event.tasks_accrued < previous[-1].tasks_accrued
            or event.clusters_accrued < previous[-1].clusters_accrued
        ):
            raise ValueError("accrual cannot silently decrease")
        if previous[-1].outcomes_inspected and not event.outcomes_inspected:
            raise ValueError("outcome access cannot be undone")
        if datetime.fromisoformat(event.timestamp.replace("Z", "+00:00")) < datetime.fromisoformat(
            previous[-1].timestamp.replace("Z", "+00:00")
        ):
            raise ValueError("event timestamps cannot run backwards")
    task_budget, cluster_budget = protocol.task_budget, protocol.cluster_budget
    if event.approved_deviation_id is not None:
        approval = by_id.get(event.approved_deviation_id)
        if approval is None or approval.event_type != "deviation_approved":
            raise ValueError("expansion requires a previously recorded approval event")
        assert approval.proposal_id is not None
        approved_proposal = by_id[approval.proposal_id]
        assert approved_proposal.proposed_task_budget is not None
        assert approved_proposal.proposed_cluster_budget is not None
        task_budget, cluster_budget = (
            approved_proposal.proposed_task_budget,
            approved_proposal.proposed_cluster_budget,
        )
    if event.tasks_accrued > task_budget or event.clusters_accrued > cluster_budget:
        raise ValueError("unreported fixed-budget expansion refused")
    if event.proposal_id is not None:
        proposal = by_id.get(event.proposal_id)
        if proposal is None or proposal.event_type != "deviation_proposed":
            raise ValueError("decision must reference an earlier proposal")
        if any(item.proposal_id == event.proposal_id for item in previous):
            raise ValueError("proposal decision is immutable; submit a new proposal")
    if event.supersedes_event_id is not None and event.supersedes_event_id not in by_id:
        raise ValueError("correction must reference an earlier event")
    if event.event_type in {"enrollment_closed", "stopping_evaluation"} and (
        event.tasks_accrued != task_budget or event.clusters_accrued != cluster_budget
    ):
        raise ValueError("early stopping requires an explicit approved budget deviation")
    if event.event_type == "analysis_access":
        if not event.outcomes_inspected:
            raise ValueError("analysis_access must explicitly record outcomes_inspected=True")
        if not any(item.event_type == "enrollment_closed" for item in previous):
            raise ValueError("outcome analysis requires recorded enrollment closure")
    if event.outcomes_inspected and not any(item.outcomes_inspected for item in previous):
        if event.event_type not in {"analysis_access", "deviation_proposed"}:
            raise ValueError("first outcome access must be authorized or recorded as a deviation")


class StoppingLedger:
    def __init__(
        self,
        path: Path,
        protocol: ClusteredProtocol,
        *,
        actor: str,
        outcomes_previously_accessed: bool,
    ) -> None:
        if type(outcomes_previously_accessed) is not bool:
            raise ValueError("outcome-access declaration must be boolean")
        if not actor.strip():
            raise ValueError("declared actor is required")
        self.path = path
        self.protocol = ClusteredProtocol.model_validate(protocol.model_dump())
        self.actor = actor
        try:
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            created = True
        except FileExistsError:
            descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
            created = False
        with os.fdopen(descriptor, "r+", encoding="utf-8") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                if not created:
                    raise ValueError("empty existing stopping log requires manual recovery")
                if outcomes_previously_accessed:
                    raise ValueError("initial plan must be frozen before outcome access")
                header = {
                    "ledger_version": "1",
                    "protocol_sha256": self.protocol.sha256,
                    "protocol": self.protocol.model_dump(),
                    "event_type": "plan_frozen",
                    "actor": actor,
                    "outcomes_previously_accessed": False,
                }
                stream.write(canonical({"payload": header, "sha256": content_hash(header)}) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            recorded, _ = self._read(stream)
            if outcomes_previously_accessed and not any(
                event.outcomes_inspected for event in recorded
            ):
                raise ValueError(
                    "declared outcome access requires a durable access or deviation event"
                )

    def _read(self, stream: Any) -> tuple[list[StoppingEvent], str]:
        stream.seek(0)
        raw = stream.read()
        if not raw.endswith("\n"):
            raise ValueError("incomplete stopping record; preserve it for manual recovery")
        records = [json.loads(line) for line in raw.splitlines()]
        header = records[0]
        payload = header["payload"]
        expected = {
            "ledger_version",
            "protocol_sha256",
            "protocol",
            "event_type",
            "actor",
            "outcomes_previously_accessed",
        }
        if (
            set(header) != {"payload", "sha256"}
            or set(payload) != expected
            or payload["ledger_version"] != "1"
            or payload["event_type"] != "plan_frozen"
            or payload["outcomes_previously_accessed"] is not False
            or payload["protocol_sha256"] != self.protocol.sha256
            or canonical(payload["protocol"]) != canonical(self.protocol.model_dump())
            or header["sha256"] != content_hash(payload)
        ):
            raise ValueError("frozen protocol or ledger header mismatch")
        previous_hash = header["sha256"]
        events: list[StoppingEvent] = []
        for record in records[1:]:
            if set(record) != {"event", "previous_sha256", "protocol_sha256", "sha256"}:
                raise ValueError("unknown stopping record fields")
            expected_hash = content_hash(
                {key: value for key, value in record.items() if key != "sha256"}
            )
            if (
                record["previous_sha256"] != previous_hash
                or record["protocol_sha256"] != self.protocol.sha256
                or record["sha256"] != expected_hash
            ):
                raise ValueError("stopping chain mismatch")
            event = StoppingEvent.model_validate(record["event"])
            _check_event(self.protocol, events, event)
            events.append(event)
            previous_hash = record["sha256"]
        return events, previous_hash

    def append(self, event: StoppingEvent) -> str:
        event = StoppingEvent.model_validate(event.model_dump())
        descriptor = os.open(self.path, os.O_RDWR | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "r+", encoding="utf-8") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            events, previous = self._read(stream)
            _check_event(self.protocol, events, event)
            payload = {
                "event": event.model_dump(),
                "previous_sha256": previous,
                "protocol_sha256": self.protocol.sha256,
            }
            digest = content_hash(payload)
            stream.seek(0, os.SEEK_END)
            stream.write(canonical({**payload, "sha256": digest}) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            return digest

    def read(self) -> dict[str, Any]:
        descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, encoding="utf-8") as stream:
            fcntl.flock(stream, fcntl.LOCK_SH)
            events, digest = self._read(stream)
        return {
            "ledger_version": "1",
            "protocol_sha256": self.protocol.sha256,
            "head_sha256": digest,
            "events": [event.model_dump() for event in events],
            "original_confirmatory_interpretation_retained": not any(
                event.event_type.startswith("deviation_") for event in events
            ),
            "actor_authentication": "not_established",
            "coverage_qualification": None,
        }
