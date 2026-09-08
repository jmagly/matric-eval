"""Unit tests for durable Terminal runtime-canary receipts."""

from __future__ import annotations

import importlib.util
import json
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "canary_qwen38_terminal_runtime.py"
SPEC = importlib.util.spec_from_file_location("qwen38_terminal_runtime_canary", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
canary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(canary)


def test_receipt_is_exclusive_private_and_canonical(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "receipt.json"
    receipt = {
        "schema": canary.RECEIPT_SCHEMA,
        "schema_version": "1",
        "study_id": canary.STUDY_ID,
        "status": "passed",
    }

    canary._write_receipt(output, receipt)

    assert json.loads(output.read_text(encoding="utf-8")) == receipt
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        canary._write_receipt(output, receipt)


def test_preflight_refuses_existing_file_and_symlink(tmp_path: Path) -> None:
    existing = tmp_path / "existing.json"
    existing.write_text("sentinel", encoding="utf-8")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        canary._ensure_output_available(existing)

    symlink = tmp_path / "receipt-link.json"
    symlink.symlink_to(existing)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        canary._ensure_output_available(symlink)


@pytest.mark.parametrize("target_exists", [False, True])
def test_exclusive_write_refuses_symlink_after_preflight(
    tmp_path: Path, target_exists: bool
) -> None:
    output = tmp_path / "receipt.json"
    target = tmp_path / "target.json"
    if target_exists:
        target.write_text("sentinel", encoding="utf-8")
    canary._ensure_output_available(output)
    output.symlink_to(target)
    with pytest.raises(FileExistsError):
        canary._write_receipt(output, {"status": "passed"})
    assert output.is_symlink()
    if target_exists:
        assert target.read_text(encoding="utf-8") == "sentinel"
    else:
        assert not target.exists()


def test_main_records_content_free_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "failed.json"
    base = {
        "schema": canary.RECEIPT_SCHEMA,
        "schema_version": "1",
        "study_id": canary.STUDY_ID,
        "status": "failed",
        "failure": None,
    }
    monkeypatch.setattr(canary, "_base_receipt", lambda: dict(base))

    def fail(_: object) -> dict[str, object]:
        raise RuntimeError("sensitive fixture detail")

    monkeypatch.setattr(canary, "_run_canary", fail)
    arguments = [
        "--harbor-checkout",
        str(tmp_path),
        "--docker-host",
        "unix:///tmp/canary.sock",
        "--output",
        str(output),
    ]
    with pytest.raises(RuntimeError, match="sensitive fixture detail"):
        canary.main(arguments)
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "failed"
    assert receipt["failure"] == {"type": "RuntimeError"}
    assert "sensitive" not in output.read_text(encoding="utf-8")


def test_source_evidence_covers_patch_runner_and_canary() -> None:
    evidence = canary._source_evidence()
    assert set(evidence) == {path.as_posix() for path in canary.SOURCE_PATHS}
    assert all(len(value) == 64 for value in evidence.values())
