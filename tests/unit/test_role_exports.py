"""Independent synthetic role, disclosure, revocation and publication fixtures."""

import json
import os
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from click.testing import CliRunner

from matric_eval.cli import cli
from matric_eval.data.access import SourceVault
from matric_eval.data.exports import dry_run, export_sft, read_sft_export
from matric_eval.data.role_ledger import RoleLedger
from matric_eval.data.roles import (
    Checkpoint,
    ExportRequest,
    RoleError,
    RoleInventory,
    UseRecord,
    canonical,
    sha256,
)
from matric_eval.state.journal import storage_profile

FIXTURES = Path(__file__).parents[1] / "fixtures" / "data" / "roles"
ROOT = "a" * 64
CHILD = "b" * 64
PROTOCOL = "c" * 64


def _semantics_only_profile(path):
    actual = storage_profile(path)
    return {
        **actual,
        "supported": True,
        "profile": "TEST-ONLY-sqlite-transaction-semantics",
        "filesystem": actual.get("filesystem", "unverified"),
        "power_loss_qualified": False,
    }


def _child_storage_seam(path):
    import matric_eval.data.role_ledger as module

    if not storage_profile(Path(path))["supported"]:
        module.storage_profile = _semantics_only_profile


@pytest.fixture(autouse=True)
def unit_storage_profile(tmp_path, monkeypatch, record_property):
    actual = storage_profile(tmp_path / "profile-probe.sqlite")
    record_property("actual_role_storage_profile", json.dumps(actual, sort_keys=True))
    record_property(
        "role_filesystem_qualification",
        "actual_ext4" if actual["supported"] else "sqlite_transaction_semantics_only",
    )
    if not actual["supported"]:
        monkeypatch.setattr("matric_eval.data.role_ledger.storage_profile", _semantics_only_profile)


def prepare_vault(path: Path, **changes):
    path.mkdir(mode=0o700)
    inputs = path / "inputs"
    inputs.mkdir(mode=0o700)
    fixture = json.loads((FIXTURES / "inventory.json").read_text())
    for source in (FIXTURES / "inputs").iterdir():
        target = inputs / source.name
        target.write_bytes(source.read_bytes())
        target.chmod(0o600)
    consent = path / "consent.txt"
    consent.write_bytes(b"Synthetic fixture export permission only.\n")
    consent.chmod(0o600)
    document = {
        "synthetic_only": True,
        "source_id": fixture["source_id"],
        "source_revision": "d" * 64,
        "completeness_scope": "all nine declared synthetic fixture rows",
        "owner": fixture["owner"],
        "retention_owner": "fixture-owner",
        "recipient": "synthetic-consumer",
        "license_id": fixture["license_id"],
        "consent_file": "consent.txt",
        "consent_sha256": sha256(consent.read_bytes()),
        "expires_at": "2999-01-01T00:00:00Z",
        "near_duplicate_threshold": 1.0,
        "root_checkpoint_sha256": [ROOT],
        "rows": [
            {
                "data": {
                    "partition_schema_version": "1",
                    "source_id": fixture["source_id"],
                    "row_id": row["row_id"],
                    "role": row["role"],
                    "independent_unit_id": row["independent_unit_id"],
                },
                "input_file": row["input_file"],
                "input_sha256": sha256((path / row["input_file"]).read_bytes()),
                "target": row["target"],
                "access": row["access"],
                "permitted_uses": row["permitted_uses"],
                "label_origin": "synthetic",
                "scorer_version": "synthetic-human/1",
                "rubric_version": "fixture/1",
                "calibration_sha256": None,
            }
            for row in fixture["rows"]
        ],
    }
    document.update(changes)
    inventory = RoleInventory.model_validate(document)
    (path / "inventory.json").write_bytes(canonical(inventory.model_dump()))
    (path / "inventory.json").chmod(0o600)
    return inventory


def checkpoint(digest=ROOT, parent=None, quality=None, reward=None):
    return Checkpoint(
        checkpoint_sha256=digest,
        parent_sha256=parent,
        independent_quality_evidence_sha256=quality,
        reward_evidence_sha256=reward,
    )


def request(**changes):
    values = {
        "request_id": "export-1",
        "row_ids": ["train-a", "dev-b"],
        "protocol_sha256": PROTOCOL,
        "checkpoint_sha256": ROOT,
        "recipient": "synthetic-consumer",
    }
    values.update(changes)
    return ExportRequest(**values)


@pytest.fixture
def setup(tmp_path):
    prepare_vault(tmp_path / "vault")
    vault = SourceVault(tmp_path / "vault")
    ledger = RoleLedger(vault)
    ledger.checkpoint(checkpoint())
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    try:
        yield vault, ledger, output
    finally:
        ledger.close()
        vault.close()


def test_mixed_roles_match_hand_authored_expected_subset(setup):
    vault, ledger, output = setup
    expected = json.loads((FIXTURES / "expectations.json").read_text())["mixed_role_subset"]
    mixed = request(row_ids=expected["request_order"])
    denied = export_sft(vault, ledger, mixed, output)
    assert denied["status"] == "denied" and not list(output.iterdir())
    mixed = mixed.model_copy(update={"request_id": "approved-subset", "allow_subset": True})
    accepted = export_sft(vault, ledger, mixed, output)
    assert accepted["status"] == "accepted"
    assert accepted["plan"]["allowed_row_ids"] == expected["allowed_row_ids"]
    decisions = {row["row_id"]: row for row in accepted["plan"]["decisions"]}
    for row, reason in expected["required_reasons"].items():
        assert reason in decisions[row]["reasons"]
    payload = next(output.glob("*.jsonl")).read_bytes()
    assert payload == (FIXTURES / "expected-sft.jsonl").read_bytes()
    assert sha256(payload) == expected["approved_subset_payload_sha256"]
    manifest, records = read_sft_export(next(output.glob("*.manifest.json")).read_bytes(), payload)
    assert [row.data.row_id for row in manifest.rows] == ["train-a", "dev-b"]
    assert records[0].target == "amber"


def test_same_input_changed_target_and_shared_cluster_are_rejected(setup):
    vault, ledger, _ = setup
    result = dry_run(vault, ledger, request(row_ids=["renamed-target-c", "cluster-peer-c"]))
    assert not result["eligible"]
    assert "input_matches_final_holdout" in result["decisions"][0]["reasons"]
    assert "independent_unit_crosses_holdout_boundary" in result["decisions"][1]["reasons"]
    assert (FIXTURES / "heldout-record.json").read_bytes() != (
        FIXTURES / "changed-target-record.json"
    ).read_bytes()


def test_payload_and_manifest_stable_while_execution_receipts_are_separate(setup):
    vault, ledger, output = setup
    first = export_sft(vault, ledger, request(), output)
    second = export_sft(vault, ledger, request(request_id="export-2"), output)
    assert first["manifest"] == second["manifest"]
    assert len(list(output.glob("*.jsonl"))) == 2
    reused = export_sft(vault, ledger, request(), output)
    assert reused["status"] == "reused"
    receipts = ledger.connection.execute("SELECT actor_uid,occurred_at FROM receipts").fetchall()
    assert all(row[0] == os.geteuid() and row[1] for row in receipts)


def test_withdrawal_precedes_idempotent_success_and_preserves_prior_bytes(setup):
    vault, ledger, output = setup
    export_sft(vault, ledger, request(), output)
    prior = {path.name: path.read_bytes() for path in output.iterdir()}
    ledger.withdraw("withdraw-1", ["train-a"])
    result = export_sft(vault, ledger, request(), output)
    assert result["status"] == "denied"
    assert "withdrawn" in result["plan"]["decisions"][0]["reasons"]
    assert prior == {path.name: path.read_bytes() for path in output.iterdir()}


def test_expiry_precedes_idempotent_success(setup, monkeypatch):
    vault, ledger, output = setup
    export_sft(vault, ledger, request(), output)
    monkeypatch.setattr("matric_eval.data.exports.now", lambda: "3000-01-01T00:00:00Z")
    result = export_sft(vault, ledger, request(), output)
    assert result["status"] == "denied"
    assert all("grant_expired" in item["reasons"] for item in result["plan"]["decisions"])


@pytest.mark.parametrize(
    "change",
    [{"recipient": "other"}, {"protocol_sha256": "f" * 64}, {"row_ids": ["dev-b", "train-a"]}],
)
def test_request_identity_includes_recipient_protocol_and_order(setup, change):
    vault, ledger, output = setup
    export_sft(vault, ledger, request(), output)
    with pytest.raises(RoleError):
        export_sft(vault, ledger, request(**change), output)
    assert len(list(output.glob("*.jsonl"))) == 1


def test_orphan_after_payload_creation_is_not_accepted_or_overwritten(setup, monkeypatch):
    import matric_eval.data.exports as exports

    vault, ledger, output = setup
    writer = exports._write_exclusive

    def interrupt(directory, name, payload):
        if name.endswith("manifest.json"):
            raise OSError("synthetic private exception must not enter audit")
        writer(directory, name, payload)

    monkeypatch.setattr(exports, "_write_exclusive", interrupt)
    with pytest.raises(RoleError):
        export_sft(vault, ledger, request(), output)
    assert ledger.accepted("export-1") is None
    assert len(list(output.glob("*.jsonl"))) == 1
    monkeypatch.setattr(exports, "_write_exclusive", writer)
    with pytest.raises(RoleError):
        export_sft(vault, ledger, request(), output)
    ledger.withdraw("revoke-orphan", ["train-a"])
    assert export_sft(vault, ledger, request(), output)["status"] == "denied"
    assert b"synthetic private exception" not in ledger.path.read_bytes()


def test_final_selection_taints_descendants_and_is_idempotent(setup):
    _, ledger, _ = setup
    assert ledger.untouched(ROOT, ["final-c"])["eligible"]
    ledger.disclose("selection-1", ROOT, ["final-c"], PROTOCOL)
    ledger.disclose("selection-1", ROOT, ["final-c"], PROTOCOL)
    ledger.checkpoint(checkpoint(CHILD, ROOT))
    assert len(ledger.events("role_use")) == 1
    assert not ledger.untouched(CHILD, ["final-c"])["eligible"]
    assert ledger.untouched(CHILD, ["final-c"])["external_lineage"] == "unverified"
    with pytest.raises(RoleError, match="root_not_enrolled"):
        ledger.checkpoint(checkpoint("e" * 64))
    with pytest.raises(RoleError):
        ledger.checkpoint(checkpoint(CHILD))
    with pytest.raises(RoleError, match="lineage_unverified"):
        ledger.untouched("f" * 64, ["final-c"])
    assert ledger.inventory.rows[2].data.role == "final_test"


@pytest.mark.parametrize(
    "purpose",
    ["rubric_discovery", "prompt_example", "tuning", "checkpoint_selection", "sft_export"],
)
def test_all_development_uses_of_final_rows_are_durable_disclosures(setup, purpose):
    _, ledger, _ = setup
    ledger.record_use(
        UseRecord(
            event_id="declared-use",
            purpose=purpose,
            row_ids=["final-c"],
            checkpoint_sha256=ROOT,
            candidate_checkpoint_sha256=[ROOT],
            protocol_sha256=PROTOCOL,
            policy_sha256=None,
            output_sha256=ROOT,
        )
    )
    assert not ledger.untouched(ROOT, ["final-c"])["eligible"]
    use = ledger.events("role_use")[0]
    assert not use["use_granted"]
    assert use["inputs"][0]["input_sha256"] == ledger.inventory.rows[2].input_sha256
    assert use["output_sha256"] == ROOT


def test_quality_reference_cannot_be_overwritten_by_reward_change(setup):
    _, ledger, _ = setup
    quality = (FIXTURES / "independent-quality.json").read_bytes()
    ledger.checkpoint(
        checkpoint(
            CHILD, ROOT, sha256(quality), sha256((FIXTURES / "reward-before.json").read_bytes())
        )
    )
    with pytest.raises(RoleError, match="conflict"):
        ledger.checkpoint(
            checkpoint(CHILD, ROOT, "f" * 64, sha256((FIXTURES / "reward-after.json").read_bytes()))
        )
    assert ledger.checkpoints()[CHILD]["independent_quality_evidence_sha256"] == sha256(quality)
    assert (FIXTURES / "independent-quality.json").read_bytes() == quality


def test_no_sensitive_input_or_target_in_audit_and_immutable_sql_rows(setup):
    vault, ledger, output = setup
    export_sft(vault, ledger, request(), output)
    for path in (FIXTURES / "inputs").iterdir():
        assert path.read_bytes().strip() not in ledger.path.read_bytes()
    with pytest.raises(sqlite3.IntegrityError):
        ledger.connection.execute("DELETE FROM events")


@pytest.mark.parametrize("path", ["../consent.txt", "/etc/passwd", "inputs/../consent.txt"])
def test_source_traversal_rejected(setup, path):
    vault, _, _ = setup
    with pytest.raises(RoleError):
        vault.read(path)


def test_source_symlink_and_permissive_permissions_reject(setup):
    vault, _, _ = setup
    link = vault.root / "alias"
    link.symlink_to(vault.root / "inputs", target_is_directory=True)
    with pytest.raises(RoleError):
        vault.read("alias/training.txt")
    (vault.root / "inputs/training.txt").chmod(0o644)
    with pytest.raises(RoleError):
        vault.inventory()


def test_held_inventory_is_not_replaced_by_caller_subset(setup):
    vault, ledger, _ = setup
    payload = json.loads((vault.root / "inventory.json").read_text())
    payload["rows"] = [row for row in payload["rows"] if row["data"]["row_id"] != "final-c"]
    (vault.root / "inventory.json").write_bytes(canonical(payload))
    with pytest.raises(RoleError, match="inventory"):
        dry_run(vault, ledger, request(row_ids=["renamed-target-c"]))


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"synthetic_only": False}, "real_materialization_unsupported"),
        ({"near_duplicate_threshold": None}, "protected_near_duplicate_check_unavailable"),
    ],
)
def test_unqualified_profile_or_near_check_never_clears_rows(tmp_path, changes, reason):
    prepare_vault(tmp_path / "vault", **changes)
    vault = SourceVault(tmp_path / "vault")
    ledger = RoleLedger(vault)
    try:
        ledger.checkpoint(checkpoint())
        result = dry_run(vault, ledger, request())
        assert not result["eligible"]
        assert reason in result["decisions"][0]["reasons"]
    finally:
        ledger.close()
        vault.close()


def test_unsupported_export_kind_preserves_requested_scope(setup):
    vault, ledger, _ = setup
    result = dry_run(vault, ledger, request(kind="preference"))
    assert not result["eligible"]
    assert result["decisions"][0]["scorer_version"] == "synthetic-human/1"
    assert "export_kind_unsupported" in result["decisions"][0]["reasons"]


def test_reader_rejects_unknown_schema_nonfinite_and_tampered_payload(setup):
    vault, ledger, output = setup
    export_sft(vault, ledger, request(), output)
    manifest = next(output.glob("*.manifest.json")).read_bytes()
    payload = next(output.glob("*.jsonl")).read_bytes()
    for mutated in [
        manifest.replace(b'"export_schema_version":"1"', b'"export_schema_version":"99"'),
        b'{"bad":NaN}',
    ]:
        with pytest.raises(RoleError):
            read_sft_export(mutated, payload)
    with pytest.raises(RoleError):
        read_sft_export(manifest, payload.replace(b"amber", b"wrong"))


def test_cli_dry_run_is_strict_content_free_and_does_not_materialize(setup, tmp_path):
    vault, ledger, output = setup
    request_file = tmp_path / "request.json"
    request_file.write_text(request().model_dump_json())
    result = CliRunner().invoke(
        cli, ["export-role-sft", str(vault.root), str(request_file), "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["eligible"]
    assert not list(output.iterdir())
    assert "Return the word" not in result.output
    request_file.write_text('{"private":"secret input sentinel"}')
    error = CliRunner().invoke(
        cli, ["export-role-sft", str(vault.root), str(request_file), "--dry-run"]
    )
    assert error.exit_code != 0 and "secret input sentinel" not in error.output


def test_concurrent_withdrawal_serializes_after_publication_and_blocks_reuse(setup, monkeypatch):
    import matric_eval.data.exports as exports

    vault, ledger, output = setup
    attempted = threading.Event()
    complete = threading.Event()
    failures = []
    writer = exports._write_exclusive
    # Open the peer before publication so database initialization cannot be the
    # barrier under test. The thread owns its own SQLite connection.
    ready = threading.Event()
    start = threading.Event()

    def enrolled_withdraw():
        try:
            other = RoleLedger(vault)
            ready.set()
            assert start.wait(5)
            attempted.set()
            other.withdraw("concurrent-withdrawal", ["train-a"])
            complete.set()
            other.close()
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=enrolled_withdraw)
    worker.start()
    assert ready.wait(5)

    def publication_barrier(directory, name, payload):
        if name.endswith(".jsonl"):
            start.set()
            assert attempted.wait(5)
            assert not complete.is_set()
        writer(directory, name, payload)

    monkeypatch.setattr(exports, "_write_exclusive", publication_barrier)
    try:
        assert export_sft(vault, ledger, request(), output)["status"] == "accepted"
    finally:
        start.set()
        worker.join(10)
    assert not worker.is_alive() and not failures and complete.is_set()
    assert export_sft(vault, ledger, request(), output)["status"] == "denied"


@pytest.mark.parametrize("origin", ["judge", "human", "unknown"])
def test_unsupported_label_origin_preserves_calibration_identity_without_false_judgment(
    tmp_path, origin
):
    prepare_vault(tmp_path / "vault")
    path = tmp_path / "vault/inventory.json"
    payload = json.loads(path.read_text())
    payload["rows"][0]["label_origin"] = origin
    payload["rows"][0]["calibration_sha256"] = "f" * 64
    path.write_bytes(canonical(payload))
    vault = SourceVault(path.parent)
    ledger = RoleLedger(vault)
    try:
        ledger.checkpoint(checkpoint())
        decision = dry_run(vault, ledger, request())["decisions"][0]
        assert not decision["allowed"]
        assert decision["label_origin"] == origin
        assert decision["calibration_sha256"] == "f" * 64
        assert not any("unqualified" in reason for reason in decision["reasons"])
    finally:
        ledger.close()
        vault.close()


def test_declared_near_duplicate_threshold_flags_reordered_holdout_words(tmp_path):
    prepare_vault(tmp_path / "vault")
    path = tmp_path / "vault/inventory.json"
    payload = json.loads(path.read_text())
    candidate = tmp_path / "vault/inputs/training.txt"
    candidate.write_bytes(b"cedar. word the Return\n")
    payload["rows"][0]["input_sha256"] = sha256(candidate.read_bytes())
    path.write_bytes(canonical(payload))
    vault = SourceVault(path.parent)
    ledger = RoleLedger(vault)
    try:
        ledger.checkpoint(checkpoint())
        decision = dry_run(vault, ledger, request())["decisions"][0]
        assert "suspected_near_duplicate_holdout" in decision["reasons"]
        assert "input_matches_final_holdout" not in decision["reasons"]
    finally:
        ledger.close()
        vault.close()


def test_process_exit_after_payload_fsync_retains_intent_and_unreleased_orphan(setup):
    vault, ledger, output = setup
    child = """import os,sys
from pathlib import Path
from matric_eval.data.access import SourceVault
from matric_eval.data.role_ledger import RoleLedger
import matric_eval.data.exports as exports
from matric_eval.data.roles import ExportRequest
from tests.unit.test_role_exports import _child_storage_seam
_child_storage_seam(sys.argv[1])
vault=SourceVault(Path(sys.argv[1]))
ledger=RoleLedger(vault)
original=exports._write_exclusive
def interrupted(directory,name,payload):
    original(directory,name,payload)
    if name.endswith('.jsonl'):
        os._exit(73)
exports._write_exclusive=interrupted
exports.export_sft(vault,ledger,ExportRequest.model_validate_json(sys.argv[3]),Path(sys.argv[2]))
"""
    result = subprocess.run(
        [sys.executable, "-c", child, str(vault.root), str(output), request().model_dump_json()],
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 73, result.stderr.decode()
    assert ledger.accepted("export-1") is None
    assert len(list(output.glob("*.jsonl"))) == 1
    phases = [
        row[0]
        for row in ledger.connection.execute(
            "SELECT phase FROM receipts WHERE request_id='export-1'"
        )
    ]
    assert "intent" in phases and "policy_checked" in phases and "accepted" not in phases
    ledger.withdraw("post-crash-withdrawal", ["train-a"])
    assert export_sft(vault, ledger, request(), output)["status"] == "denied"


def test_selection_exposes_every_candidate_and_descendant(setup):
    _, ledger, _ = setup
    sibling = "e" * 64
    grandchild = "f" * 64
    ledger.checkpoint(checkpoint(CHILD, ROOT))
    ledger.checkpoint(checkpoint(sibling, ROOT))
    ledger.checkpoint(checkpoint(grandchild, sibling))
    ledger.record_use(
        UseRecord(
            event_id="compare-siblings",
            purpose="checkpoint_selection",
            row_ids=["final-c"],
            checkpoint_sha256=CHILD,
            candidate_checkpoint_sha256=[CHILD, sibling],
            protocol_sha256=PROTOCOL,
            policy_sha256=PROTOCOL,
            output_sha256=CHILD,
        )
    )
    assert not ledger.untouched(sibling, ["final-c"])["eligible"]
    assert not ledger.untouched(grandchild, ["final-c"])["eligible"]


def test_expired_use_is_recorded_without_claiming_a_grant(setup, monkeypatch):
    _, ledger, _ = setup
    monkeypatch.setattr("matric_eval.data.role_ledger.now", lambda: "3000-01-01T00:00:00Z")
    ledger.record_use(
        UseRecord(
            event_id="expired-use",
            purpose="sft_export",
            row_ids=["train-a"],
            checkpoint_sha256=ROOT,
            candidate_checkpoint_sha256=[ROOT],
            protocol_sha256=PROTOCOL,
            policy_sha256=PROTOCOL,
            output_sha256=ROOT,
        )
    )
    assert not ledger.events("role_use")[0]["use_granted"]


@pytest.mark.parametrize("row_id", ["renamed-target-c", "cluster-peer-c"])
def test_declared_use_of_holdout_alias_also_discloses_final_inventory(setup, row_id):
    _, ledger, _ = setup
    original_roles = {row.data.row_id: row.data.role for row in ledger.inventory.rows}
    ledger.record_use(
        UseRecord(
            event_id="alias-use",
            purpose="prompt_example",
            row_ids=[row_id],
            checkpoint_sha256=ROOT,
            candidate_checkpoint_sha256=[ROOT],
            protocol_sha256=PROTOCOL,
            policy_sha256=PROTOCOL,
            output_sha256=ROOT,
        )
    )
    assert not ledger.untouched(ROOT, ["final-c"])["eligible"]
    assert ledger.events("role_use")[0]["final_disclosure"]
    assert original_roles == {row.data.row_id: row.data.role for row in ledger.inventory.rows}


def test_production_storage_gate_still_refuses_unsupported_filesystem(tmp_path, monkeypatch):
    prepare_vault(tmp_path / "vault")
    vault = SourceVault(tmp_path / "vault")
    monkeypatch.setattr(
        "matric_eval.data.role_ledger.storage_profile",
        lambda path: {"supported": False, "reason": "unsupported_storage"},
    )
    try:
        with pytest.raises(RoleError, match="unsupported_ledger_storage"):
            RoleLedger(vault)
    finally:
        vault.close()


def test_mutating_inventory_view_cannot_enroll_a_fresh_root(setup):
    _, ledger, _ = setup
    view = ledger.inventory
    view.root_checkpoint_sha256.append("e" * 64)
    with pytest.raises(RoleError, match="root_not_enrolled"):
        ledger.checkpoint(checkpoint("e" * 64))
