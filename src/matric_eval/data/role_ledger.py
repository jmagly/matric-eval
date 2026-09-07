"""Private, append-only local role-use journal with serialized publication checks."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from matric_eval.data.access import SourceVault, private_descriptor
from matric_eval.data.roles import (
    Checkpoint,
    RoleError,
    RoleInventory,
    UseRecord,
    canonical,
    moment,
    now,
    sha256,
)
from matric_eval.state.journal import storage_profile

SCHEMA = """
CREATE TABLE IF NOT EXISTS identity (version TEXT NOT NULL, inventory_sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT,
 kind TEXT NOT NULL, request_id TEXT UNIQUE NOT NULL, content TEXT NOT NULL,
 actor_uid INTEGER NOT NULL, occurred_at TEXT NOT NULL,
 previous_sha256 TEXT NOT NULL, event_sha256 TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS publications (
 request_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL, request TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS receipts (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL,
 phase TEXT NOT NULL, content TEXT NOT NULL, actor_uid INTEGER NOT NULL, occurred_at TEXT NOT NULL);
"""


class RoleLedger:
    def __init__(self, vault: SourceVault):
        self.directory_fd = -1
        try:
            self._initialize(vault)
        except BaseException:
            if hasattr(self, "connection"):
                self.connection.close()
            if self.directory_fd >= 0:
                os.close(self.directory_fd)
            raise

    def _initialize(self, vault: SourceVault) -> None:
        self.vault = vault
        _, inventory_sha256 = vault.inventory()
        self._inventory_sha256 = inventory_sha256
        path = vault.root / "role-use.sqlite"
        self.path = path
        self.directory_fd = os.dup(vault.fd)
        parent = os.dup(self.directory_fd)
        try:
            private_descriptor(parent, directory=True)
            fd = os.open(path.name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            try:
                private_descriptor(fd, directory=False)
            finally:
                os.close(fd)
        finally:
            os.close(parent)
        self.storage = storage_profile(path)
        if not self.storage["supported"]:
            raise RoleError("unsupported_ledger_storage")
        self.connection = sqlite3.connect(
            f"/proc/self/fd/{self.directory_fd}/role-use.sqlite", isolation_level=None, timeout=5
        )
        self.connection.row_factory = sqlite3.Row
        if self.connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0] != "delete":
            raise RoleError("ledger_durability_profile_unverified")
        self.connection.execute("PRAGMA synchronous=EXTRA")
        if self.connection.execute("PRAGMA synchronous").fetchone()[0] != 3:
            raise RoleError("ledger_durability_profile_unverified")
        with self.transaction():
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    self.connection.execute(statement)
            identity = self.connection.execute("SELECT * FROM identity").fetchall()
            if not identity:
                self.connection.execute(
                    "INSERT INTO identity VALUES (?,?)", ("1", inventory_sha256)
                )
            elif len(identity) != 1 or tuple(identity[0]) != ("1", inventory_sha256):
                raise RoleError("ledger_inventory_or_version_mismatch")
            for table in ("identity", "events", "publications", "receipts"):
                for action in ("UPDATE", "DELETE"):
                    self.connection.execute(
                        f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable_role_ledger'); END"
                    )
            runtime = {
                key: self.storage[key]
                for key in ("profile", "python", "sqlite", "filesystem", "power_loss_qualified")
            }
            self._event("storage_profile", "storage:" + sha256(canonical(runtime)), runtime)
        self.verify()

    def close(self) -> None:
        self.connection.close()
        os.close(self.directory_fd)

    @property
    def inventory(self) -> RoleInventory:
        inventory, digest = self.vault.inventory()
        if digest != self._inventory_sha256:
            raise RoleError("ledger_inventory_or_version_mismatch")
        return inventory

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def verify(self) -> None:
        previous = "0" * 64
        for row in self.connection.execute("SELECT * FROM events ORDER BY sequence"):
            expected = sha256(
                canonical(
                    {
                        "previous": previous,
                        "kind": row["kind"],
                        "request_id": row["request_id"],
                        "content": json.loads(row["content"]),
                        "actor_uid": row["actor_uid"],
                        "occurred_at": row["occurred_at"],
                    }
                )
            )
            if row["previous_sha256"] != previous or row["event_sha256"] != expected:
                raise RoleError("ledger_chain_corrupt")
            previous = expected

    def cutoff(self) -> dict[str, Any]:
        self.verify()
        row = self.connection.execute(
            "SELECT sequence,event_sha256 FROM events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        return (
            {"sequence": row[0], "sha256": row[1]} if row else {"sequence": 0, "sha256": "0" * 64}
        )

    def _event(self, kind: str, request_id: str, content: dict[str, Any]) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}", request_id):
            raise RoleError("opaque_request_identifier_required")
        serialized = canonical(content).decode()
        prior = self.connection.execute(
            "SELECT kind,content FROM events WHERE request_id=?", (request_id,)
        ).fetchone()
        if prior:
            if tuple(prior) != (kind, serialized):
                raise RoleError("use_request_conflict")
            return
        previous = self.cutoff()["sha256"]
        timestamp = now()
        actor = os.geteuid()
        digest = sha256(
            canonical(
                {
                    "previous": previous,
                    "kind": kind,
                    "request_id": request_id,
                    "content": content,
                    "actor_uid": actor,
                    "occurred_at": timestamp,
                }
            )
        )
        self.connection.execute(
            "INSERT INTO events(kind,request_id,content,actor_uid,occurred_at,previous_sha256,event_sha256) VALUES(?,?,?,?,?,?,?)",
            (kind, request_id, serialized, actor, timestamp, previous, digest),
        )

    def events(self, kind: str) -> list[dict[str, Any]]:
        return [
            json.loads(row[0])
            for row in self.connection.execute(
                "SELECT content FROM events WHERE kind=? ORDER BY sequence", (kind,)
            )
        ]

    def checkpoint(self, value: Checkpoint) -> None:
        value = Checkpoint.model_validate(value.model_dump())
        with self.transaction():
            if (
                value.parent_sha256 is None
                and value.checkpoint_sha256 not in self.inventory.root_checkpoint_sha256
            ):
                raise RoleError("checkpoint_root_not_enrolled")
            if value.parent_sha256 is not None and value.parent_sha256 not in self.checkpoints():
                raise RoleError("checkpoint_parent_unknown")
            self._event("checkpoint", "checkpoint:" + value.checkpoint_sha256, value.model_dump())

    def checkpoints(self) -> dict[str, dict[str, Any]]:
        return {row["checkpoint_sha256"]: row for row in self.events("checkpoint")}

    def ancestors(self, checkpoint_sha256: str) -> set[str]:
        checkpoints = self.checkpoints()
        seen: set[str] = set()
        current: str | None = checkpoint_sha256
        while current is not None:
            if current in seen or current not in checkpoints:
                raise RoleError("checkpoint_lineage_unverified")
            seen.add(current)
            current = checkpoints[current]["parent_sha256"]
        return seen

    def disclose(
        self, request_id: str, checkpoint_sha256: str, row_ids: list[str], protocol_sha256: str
    ) -> None:
        self.record_use(
            UseRecord(
                event_id=request_id,
                purpose="checkpoint_selection",
                row_ids=row_ids,
                checkpoint_sha256=checkpoint_sha256,
                candidate_checkpoint_sha256=[checkpoint_sha256],
                protocol_sha256=protocol_sha256,
                policy_sha256=None,
                output_sha256=checkpoint_sha256,
            )
        )

    def record_use(self, value: UseRecord) -> None:
        """Audit declared use, including policy violations, without granting access."""
        value = UseRecord.model_validate(value.model_dump())
        with self.transaction():
            current, inventory_hash = self.vault.inventory()
            if (
                inventory_hash
                != self.connection.execute("SELECT inventory_sha256 FROM identity").fetchone()[0]
            ):
                raise RoleError("ledger_inventory_or_version_mismatch")
            for candidate in value.candidate_checkpoint_sha256:
                self.ancestors(candidate)
            rows = {row.data.row_id: row for row in self.inventory.rows}
            if not set(value.row_ids) <= set(rows):
                raise RoleError("use_requires_enrolled_rows")
            inputs = [
                {
                    "row_id": row_id,
                    "role": rows[row_id].data.role,
                    "data_reference_sha256": sha256(canonical(rows[row_id].data.model_dump())),
                    "input_sha256": rows[row_id].input_sha256,
                }
                for row_id in value.row_ids
            ]
            final_rows = [row for row in current.rows if row.data.role == "final_test"]
            protected_inputs = {row.input_sha256 for row in final_rows}
            protected_units = {row.data.independent_unit_id for row in final_rows}
            final_development = value.purpose in {
                "rubric_discovery",
                "prompt_example",
                "tuning",
                "checkpoint_selection",
                "sft_export",
            } and any(
                rows[row_id].input_sha256 in protected_inputs
                or rows[row_id].data.independent_unit_id in protected_units
                for row_id in value.row_ids
            )
            use_reasons = []
            if moment(now()) >= moment(current.expires_at):
                use_reasons.append("grant_expired")
            if final_development:
                use_reasons.append("final_holdout_disclosed_for_development")
            if any(row_id in self.withdrawn() for row_id in value.row_ids):
                use_reasons.append("withdrawn")
            if any(
                value.purpose not in rows[row_id].permitted_uses
                or rows[row_id].access != "permitted"
                for row_id in value.row_ids
            ):
                use_reasons.append("use_not_permitted")
            self._event(
                "role_use",
                value.event_id,
                {
                    **value.model_dump(),
                    "inputs": inputs,
                    "final_disclosure": final_development,
                    "use_granted": not use_reasons,
                    "use_denial_reasons": use_reasons,
                    "evidence_scope": "declared_use_not_execution_attestation",
                },
            )

    def untouched(self, checkpoint_sha256: str, row_ids: list[str]) -> dict[str, Any]:
        with self.transaction():
            final_ids = {
                row.data.row_id for row in self.inventory.rows if row.data.role == "final_test"
            }
            if not self.inventory.synthetic_only or not row_ids or not set(row_ids) <= final_ids:
                raise RoleError("untouched_scope_unverified")
            ancestors = self.ancestors(checkpoint_sha256)
            # Conservative first profile: exposure invalidates the complete
            # enrolled final inventory for every compared candidate lineage.
            disclosed = any(
                event["final_disclosure"] and set(event["candidate_checkpoint_sha256"]) & ancestors
                for event in self.events("role_use")
            )
            return {
                "eligible": not disclosed,
                "reasons": ["final_holdout_disclosed_for_selection"] if disclosed else [],
                "ledger_cutoff": self.cutoff(),
                "scope": "enrolled-synthetic-inventory-ledger/1",
                "external_lineage": "unverified",
            }

    def withdraw(self, request_id: str, row_ids: list[str]) -> None:
        with self.transaction():
            if not row_ids or not set(row_ids) <= {row.data.row_id for row in self.inventory.rows}:
                raise RoleError("withdrawal_requires_enrolled_rows")
            self._event("withdrawal", request_id, {"row_ids": sorted(set(row_ids))})

    def withdrawn(self) -> set[str]:
        return {item for row in self.events("withdrawal") for item in row["row_ids"]}

    def intent(self, request: dict[str, Any]) -> None:
        payload = canonical(request)
        request_id = request["request_id"]
        with self.transaction():
            prior = self.connection.execute(
                "SELECT request_sha256 FROM publications WHERE request_id=?", (request_id,)
            ).fetchone()
            if prior and prior[0] != sha256(payload):
                raise RoleError("export_request_conflict")
            if not prior:
                self.connection.execute(
                    "INSERT INTO publications VALUES(?,?,?)",
                    (request_id, sha256(payload), payload.decode()),
                )
                self.receipt(request_id, "intent", {"request_sha256": sha256(payload)})

    def receipt(self, request_id: str, phase: str, content: dict[str, Any]) -> None:
        self.connection.execute(
            "INSERT INTO receipts(request_id,phase,content,actor_uid,occurred_at) VALUES(?,?,?,?,?)",
            (request_id, phase, canonical(content).decode(), os.geteuid(), now()),
        )

    def accepted(self, request_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT content FROM receipts WHERE request_id=? AND phase='accepted' ORDER BY sequence DESC LIMIT 1",
            (request_id,),
        ).fetchone()
        return json.loads(row[0]) if row else None
