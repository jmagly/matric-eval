"""Opt-in, local SQLite observation journal; no engine or dispatch integration.

Writes and verified reuse require the Linux/ext4 profile. Read-only diagnosis is
available elsewhere. SQLite EXTRA is not evidence of power-loss qualification.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Literal, Self, TypeVar
from urllib.parse import unquote, urlparse

from pydantic import Field, model_validator

from matric_eval.results.contract import (
    ArtifactReference,
    Observation,
    ObservationIdentity,
    Record,
    Text,
)
from matric_eval.state.observation_identity import (
    CleanupReceipt,
    ExecutionFingerprint,
    ReplayCapability,
    canonical_json,
)

SCHEMA_VERSION = "1"
BUSY_TIMEOUT_MS = 5000
JournalRecord = TypeVar("JournalRecord", bound=Record)


class JournalError(RuntimeError):
    """The journal cannot establish the requested invariant."""


class UnsupportedStorage(JournalError):
    pass


class JournalConflict(JournalError):
    """An immutable-record conflict, retained durably where possible."""


class JournalCorruption(JournalError):
    pass


class ReuseRefused(JournalError):
    pass


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _scope(identity: ObservationIdentity) -> str:
    return canonical_json(identity.model_dump(exclude={"metric_id"}))


def _identity_documents(identities: list[ObservationIdentity]) -> list[str]:
    return sorted(canonical_json(identity.model_dump()) for identity in identities)


class AttemptIntent(Record):
    version: Literal["1"] = "1"
    attempt_id: Text
    previous_attempt_id: Text | None = None
    identities: list[ObservationIdentity] = Field(min_length=1)
    fingerprint: ExecutionFingerprint
    replay_capability: ReplayCapability

    @model_validator(mode="after")
    def complete_scope(self) -> Self:
        if len({_scope(identity) for identity in self.identities}) != 1:
            raise ValueError("one intent covers exactly one sample/trial scope")
        if len({identity.logical_id() for identity in self.identities}) != len(self.identities):
            raise ValueError("duplicate metric identity")
        if self.previous_attempt_id == self.attempt_id:
            raise ValueError("an attempt cannot precede itself")
        return self


class TerminalAttempt(Record):
    version: Literal["1"] = "1"
    attempt_id: Text
    observations: list[Observation] = Field(min_length=1)
    artifacts: list[ArtifactReference] = Field(default_factory=list)
    cleanup: CleanupReceipt | None = None

    @model_validator(mode="after")
    def attempt_binding(self) -> Self:
        if any(row.attempt_id != self.attempt_id for row in self.observations):
            raise ValueError("terminal observations must belong to the attempt")
        if self.cleanup is not None and self.cleanup.attempt_id != self.attempt_id:
            raise ValueError("cleanup receipt belongs to another attempt")
        if len({row.observation_id for row in self.observations}) != len(self.observations):
            raise ValueError("duplicate terminal metric")
        return self


class IntentReceipt(Record):
    attempt_id: Text
    payload_sha256: Text


class AcceptanceReceipt(Record):
    attempt_id: Text
    payload_sha256: Text
    observation_ids: list[Text]


def storage_profile(path: Path) -> dict[str, Any]:
    """Observe mount metadata, never accept a caller's filesystem attestation."""
    evidence: dict[str, Any] = {
        "supported": False,
        "reason": "unsupported_storage",
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
    }
    if platform.system() != "Linux":
        return evidence
    resolved = path.resolve()
    try:
        lines = Path("/proc/self/mountinfo").read_text().splitlines()
        candidates = []
        for line in lines:
            left, right = line.split(" - ", 1)
            fields, filesystem = left.split(), right.split()
            mount = Path(re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), fields[4]))
            if resolved.is_relative_to(mount):
                candidates.append((len(mount.parts), mount, fields, filesystem))
        _, mount, fields, filesystem = max(candidates, key=lambda item: item[0])
    except (OSError, ValueError, IndexError):
        return evidence
    options = set(fields[5].split(",")) | set(filesystem[2].split(","))
    supported = (
        filesystem[0] == "ext4"
        and "rw" in options
        and not ({"ro", "nobarrier", "barrier=0"} & options)
    )
    return {
        **evidence,
        "supported": supported,
        "reason": None if supported else "unsupported_storage",
        "filesystem": filesystem[0],
        "mount": str(mount),
        "device": filesystem[1],
        "options": sorted(options),
        "profile": "linux-local-ext4-sqlite-delete-extra/1" if supported else None,
        "power_loss_qualified": False,
    }


SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO metadata VALUES ('schema_version', '1');
CREATE TABLE scopes (scope_key TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE intents (attempt_id TEXT PRIMARY KEY, scope_key TEXT NOT NULL REFERENCES scopes(scope_key),
 predecessor TEXT REFERENCES intents(attempt_id), payload TEXT NOT NULL, digest TEXT NOT NULL);
CREATE TABLE terminals (attempt_id TEXT PRIMARY KEY REFERENCES intents(attempt_id), payload TEXT NOT NULL, digest TEXT NOT NULL);
CREATE TABLE acceptances (logical_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES terminals(attempt_id), digest TEXT NOT NULL);
CREATE TABLE dispositions (sequence INTEGER PRIMARY KEY AUTOINCREMENT, attempt_id TEXT NOT NULL, reason TEXT NOT NULL, payload_digest TEXT NOT NULL);
"""


def _configure(connection: sqlite3.Connection) -> None:
    connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    if connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0] != "delete":
        raise UnsupportedStorage("journal_mode DELETE was not applied")
    connection.execute("PRAGMA synchronous=EXTRA")
    connection.execute("PRAGMA foreign_keys=ON")
    if (
        connection.execute("PRAGMA synchronous").fetchone()[0] != 3
        or connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1
    ):
        raise UnsupportedStorage("required SQLite pragmas were not applied")


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class ObservationJournal:
    def __init__(self, path: str | Path, *, read_only: bool = False) -> None:
        self.path = Path(path).resolve()
        self.read_only = read_only
        self.storage = storage_profile(self.path)
        if not read_only and not self.storage["supported"]:
            raise UnsupportedStorage(
                "writes require the observed local Linux ext4 profile; use read_only=True for diagnosis"
            )
        if not self.path.exists() and not read_only:
            self._create()
        self.connection = sqlite3.connect(
            self.path.as_uri() + ("?mode=ro" if read_only else "?mode=rw"),
            uri=True,
            isolation_level=None,
            timeout=5,
        )
        if not read_only:
            _configure(self.connection)
        else:
            self.connection.execute("PRAGMA foreign_keys=ON")
            self.connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        try:
            row = self.connection.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()
            if row != (SCHEMA_VERSION,):
                raise JournalCorruption("unsupported journal schema version")
            self.audit()
        except BaseException:
            self.connection.close()
            raise

    def _create(self) -> None:
        # Require an existing parent so its own creation/durability is not hidden.
        if not self.path.parent.is_dir():
            raise UnsupportedStorage(
                "create and qualify the journal directory before opening the journal"
            )
        descriptor, temporary = tempfile.mkstemp(
            prefix=".observation-journal-", dir=self.path.parent
        )
        os.close(descriptor)
        candidate = Path(temporary)
        try:
            connection = sqlite3.connect(candidate, isolation_level=None)
            try:
                _configure(connection)
                connection.executescript("BEGIN IMMEDIATE;" + SCHEMA)
                for table in (
                    "metadata",
                    "scopes",
                    "intents",
                    "terminals",
                    "acceptances",
                    "dispositions",
                ):
                    for operation in ("UPDATE", "DELETE"):
                        connection.execute(
                            f"CREATE TRIGGER immutable_{table}_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable journal record'); END"
                        )
                connection.commit()
            finally:
                connection.close()
            with candidate.open("rb") as source:
                os.fsync(source.fileno())
            try:
                os.link(
                    candidate, self.path
                )  # atomic publication, never replace a racing initializer
            except FileExistsError:
                pass
            _sync_directory(self.path.parent)
        finally:
            candidate.unlink(missing_ok=True)
            _sync_directory(self.path.parent)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> ObservationJournal:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        if self.read_only or not self.storage["supported"]:
            raise UnsupportedStorage("journal is diagnostic-only")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self._audit()
            yield
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def _disposition(self, attempt_id: str, reason: str, digest: str) -> None:
        self.connection.execute(
            "INSERT INTO dispositions(attempt_id,reason,payload_digest) VALUES (?,?,?)",
            (attempt_id, reason, digest),
        )

    def record_intent(self, intent: AttemptIntent) -> IntentReceipt:
        intent = AttemptIntent.model_validate(intent.model_dump())
        payload = canonical_json(intent.model_dump())
        digest = _digest(payload)
        scope = _scope(intent.identities[0])
        scope_key = _digest(scope)
        declared = canonical_json(
            {
                "scope": json.loads(scope),
                "identities": sorted(identity.logical_id() for identity in intent.identities),
                "fingerprint": intent.fingerprint.model_dump(),
            }
        )
        conflict = None
        with self._transaction():
            existing = self.connection.execute(
                "SELECT payload,digest FROM intents WHERE attempt_id=?", (intent.attempt_id,)
            ).fetchone()
            if existing is not None:
                if existing != (payload, digest):
                    conflict = "attempt_intent_conflict"
            else:
                previous = (
                    self.connection.execute(
                        "SELECT scope_key FROM intents WHERE attempt_id=?",
                        (intent.previous_attempt_id,),
                    ).fetchone()
                    if intent.previous_attempt_id
                    else None
                )
                current_scope = self.connection.execute(
                    "SELECT payload FROM scopes WHERE scope_key=?", (scope_key,)
                ).fetchone()
                if intent.previous_attempt_id and previous != (scope_key,):
                    conflict = "invalid_predecessor"
                elif current_scope is not None and current_scope != (declared,):
                    conflict = "scope_or_fingerprint_conflict"
                else:
                    self.connection.execute(
                        "INSERT OR IGNORE INTO scopes VALUES (?,?)", (scope_key, declared)
                    )
                    self.connection.execute(
                        "INSERT INTO intents VALUES (?,?,?,?,?)",
                        (intent.attempt_id, scope_key, intent.previous_attempt_id, payload, digest),
                    )
            if conflict:
                self._disposition(intent.attempt_id, conflict, digest)
        if conflict:
            raise JournalConflict(conflict)
        return IntentReceipt(attempt_id=intent.attempt_id, payload_sha256=digest)

    def _intent(self, attempt_id: str) -> AttemptIntent:
        row = self.connection.execute(
            "SELECT payload,digest FROM intents WHERE attempt_id=?", (attempt_id,)
        ).fetchone()
        if row is None:
            raise JournalConflict("durable intent required before terminal acceptance")
        return self._decode(row, AttemptIntent)

    @staticmethod
    def _decode(row: tuple[str, str], model: type[JournalRecord]) -> JournalRecord:
        payload, digest = row
        try:
            parsed = model.model_validate_json(payload)
            if _digest(payload) != digest or canonical_json(parsed.model_dump()) != payload:
                raise ValueError("canonical payload/digest mismatch")
            return parsed
        except (ValueError, TypeError) as exc:
            raise JournalCorruption("invalid immutable journal payload") from exc

    @staticmethod
    def _verify_artifacts(terminal: TerminalAttempt) -> None:
        artifacts = [
            *terminal.artifacts,
            *(item for row in terminal.observations for item in row.artifacts),
        ]
        if terminal.cleanup and terminal.cleanup.evidence:
            artifacts.append(terminal.cleanup.evidence)
        for artifact in artifacts:
            if artifact.sha256 is None:
                continue  # Explicitly unavailable evidence is never upgraded.
            parsed = urlparse(artifact.uri)
            if parsed.scheme not in ("", "file") or parsed.netloc:
                raise ReuseRefused("verified artifacts require locally hashable files")
            path = Path(unquote(parsed.path))
            if not path.is_absolute() or not path.is_file():
                raise ReuseRefused("verified artifact is missing or not a regular local file")
            digest = hashlib.sha256()
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != artifact.sha256:
                raise ReuseRefused("verified artifact digest mismatch")

    def commit_terminal(self, terminal: TerminalAttempt) -> AcceptanceReceipt:
        terminal = TerminalAttempt.model_validate(terminal.model_dump())
        # Acceptance is an index projection, never an immutable candidate claim.
        # Both winning and losing terminal evidence retain accepted=False.
        for observation in terminal.observations:
            observation.accepted = False
        payload = canonical_json(terminal.model_dump())
        digest = _digest(payload)
        conflict = None
        ids = sorted(row.observation_id for row in terminal.observations)
        with self._transaction():
            intent = self._intent(terminal.attempt_id)
            if _identity_documents(
                [row.identity for row in terminal.observations]
            ) != _identity_documents(intent.identities) or any(
                row.previous_attempt_id != intent.previous_attempt_id
                for row in terminal.observations
            ):
                raise JournalConflict(
                    "terminal must contain the exact declared metric set and predecessor"
                )
            if any(
                row.execution not in {"completed", "failed", "cancelled"}
                for row in terminal.observations
            ):
                raise JournalConflict("an interrupted intent is not terminal execution evidence")
            self._verify_artifacts(terminal)
            existing = self.connection.execute(
                "SELECT payload,digest FROM terminals WHERE attempt_id=?", (terminal.attempt_id,)
            ).fetchone()
            if existing is not None and existing != (payload, digest):
                conflict = "attempt_terminal_conflict"
            else:
                self.connection.execute(
                    "INSERT OR IGNORE INTO terminals VALUES (?,?,?)",
                    (terminal.attempt_id, payload, digest),
                )
                accepted = [
                    self.connection.execute(
                        "SELECT attempt_id,digest FROM acceptances WHERE logical_id=?",
                        (logical_id,),
                    ).fetchone()
                    for logical_id in ids
                ]
                if any(
                    row is not None and row != (terminal.attempt_id, digest) for row in accepted
                ):
                    conflict = "acceptance_conflict"
                elif any(row is not None for row in accepted) and not all(
                    row is not None for row in accepted
                ):
                    raise JournalCorruption("partially accepted metric set")
                else:
                    for logical_id in ids:
                        self.connection.execute(
                            "INSERT OR IGNORE INTO acceptances VALUES (?,?,?)",
                            (logical_id, terminal.attempt_id, digest),
                        )
            if conflict:
                self._disposition(terminal.attempt_id, conflict, digest)
        if conflict:
            raise JournalConflict(conflict)
        return AcceptanceReceipt(
            attempt_id=terminal.attempt_id, payload_sha256=digest, observation_ids=ids
        )

    def load_accepted(
        self, identities: list[ObservationIdentity], current_fingerprint: ExecutionFingerprint
    ) -> TerminalAttempt | None:
        if not self.storage["supported"]:
            raise UnsupportedStorage("unsupported storage cannot authorize verified reuse")
        self.audit()
        ids = sorted(identity.logical_id() for identity in identities)
        if not ids or len(set(ids)) != len(ids):
            raise ValueError("requested identities must be nonempty and unique")
        rows = [
            self.connection.execute(
                "SELECT attempt_id,digest FROM acceptances WHERE logical_id=?", (logical_id,)
            ).fetchone()
            for logical_id in ids
        ]
        if all(row is None for row in rows):
            return None
        if any(row is None for row in rows) or len(set(rows)) != 1:
            raise ReuseRefused("request does not cover one complete accepted metric set")
        attempt_id = rows[0][0]
        intent = self._intent(attempt_id)
        if _identity_documents(identities) != _identity_documents(intent.identities):
            raise ReuseRefused("request changes the declared metric set")
        reasons = intent.fingerprint.mismatch_reasons(current_fingerprint)
        if reasons:
            raise ReuseRefused(",".join(reasons))
        terminal = self._decode(
            self.connection.execute(
                "SELECT payload,digest FROM terminals WHERE attempt_id=?", (attempt_id,)
            ).fetchone(),
            TerminalAttempt,
        )
        self._verify_artifacts(terminal)
        if intent.replay_capability.mode == "isolated" and (
            terminal.cleanup is None or terminal.cleanup.status != "verified_absent"
        ):
            raise ReuseRefused("cleanup_unverified")
        for observation in terminal.observations:
            observation.accepted = True
        return terminal

    def list_attempts(self) -> list[dict[str, Any]]:
        self.audit()
        return [
            {
                "intent": self._decode((payload, digest), AttemptIntent),
                "terminal": self._decode(terminal, TerminalAttempt)
                if terminal is not None
                else None,
            }
            for attempt_id, payload, digest in self.connection.execute(
                "SELECT attempt_id,payload,digest FROM intents ORDER BY attempt_id"
            )
            for terminal in [
                self.connection.execute(
                    "SELECT payload,digest FROM terminals WHERE attempt_id=?", (attempt_id,)
                ).fetchone()
            ]
        ]

    def dispositions(self) -> list[dict[str, Any]]:
        return [
            dict(zip(("sequence", "attempt_id", "reason", "payload_digest"), row, strict=True))
            for row in self.connection.execute(
                "SELECT sequence,attempt_id,reason,payload_digest FROM dispositions ORDER BY sequence"
            )
        ]

    def audit(self) -> None:
        owned_transaction = not self.connection.in_transaction
        if owned_transaction:
            self.connection.execute("BEGIN")
        try:
            self._audit()
        finally:
            if owned_transaction:
                self.connection.rollback()

    def _audit(self) -> None:
        if (
            self.connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]
            or self.connection.execute("PRAGMA foreign_key_check").fetchall()
        ):
            raise JournalCorruption("SQLite integrity check failed")
        intents: dict[str, AttemptIntent] = {}
        for attempt_id, scope_key, predecessor, payload, digest in self.connection.execute(
            "SELECT * FROM intents"
        ):
            intent = self._decode((payload, digest), AttemptIntent)
            if (
                intent.attempt_id != attempt_id
                or intent.previous_attempt_id != predecessor
                or _digest(_scope(intent.identities[0])) != scope_key
            ):
                raise JournalCorruption("intent index mismatch")
            declared = canonical_json(
                {
                    "scope": json.loads(_scope(intent.identities[0])),
                    "identities": sorted(identity.logical_id() for identity in intent.identities),
                    "fingerprint": intent.fingerprint.model_dump(),
                }
            )
            if self.connection.execute(
                "SELECT payload FROM scopes WHERE scope_key=?", (scope_key,)
            ).fetchone() != (declared,):
                raise JournalCorruption("scope declaration mismatch")
            intents[attempt_id] = intent
        for intent in intents.values():
            seen = {intent.attempt_id}
            previous = intent.previous_attempt_id
            while previous is not None:
                if (
                    previous in seen
                    or previous not in intents
                    or _scope(intents[previous].identities[0]) != _scope(intent.identities[0])
                ):
                    raise JournalCorruption("invalid predecessor lineage")
                seen.add(previous)
                previous = intents[previous].previous_attempt_id
        for attempt_id, payload, digest in self.connection.execute("SELECT * FROM terminals"):
            terminal = self._decode((payload, digest), TerminalAttempt)
            intent = intents[attempt_id]
            if any(
                row.execution not in {"completed", "failed", "cancelled"}
                for row in terminal.observations
            ):
                raise JournalCorruption("nonterminal execution in immutable terminal record")
            ids = sorted(row.observation_id for row in terminal.observations)
            if (
                terminal.attempt_id != attempt_id
                or _identity_documents([row.identity for row in terminal.observations])
                != _identity_documents(intent.identities)
                or any(
                    row.previous_attempt_id != intent.previous_attempt_id or row.accepted
                    for row in terminal.observations
                )
            ):
                raise JournalCorruption("terminal declaration mismatch")
            accepted = self.connection.execute(
                "SELECT logical_id,digest FROM acceptances WHERE attempt_id=? ORDER BY logical_id",
                (attempt_id,),
            ).fetchall()
            if accepted and accepted != [(logical_id, digest) for logical_id in ids]:
                raise JournalCorruption("acceptance index mismatch or partial metric set")
