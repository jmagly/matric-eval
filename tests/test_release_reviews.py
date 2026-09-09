"""Release reviews must match installed bytes and cannot hide failed audits."""

import hashlib
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "review_contract", Path(__file__).parents[1] / "scripts/release_contract.py"
)
assert SPEC and SPEC.loader
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)


@pytest.fixture
def installed(tmp_path, monkeypatch):
    payload = tmp_path / "site"
    (payload / "example").mkdir(parents=True)
    (payload / "example/__init__.py").write_text("VALUE = 1\n")
    (payload / "example/LICENSE").write_text("reviewed license\n")
    files = ["example/__init__.py", "example/LICENSE"]
    direct = {
        "url": "https://github.com/example/source.git",
        "vcs_info": {"vcs": "git", "commit_id": "a" * 40},
    }
    obj = SimpleNamespace(
        version="1.0",
        files=files,
        locate_file=lambda path: payload / path,
        read_text=lambda name: json.dumps(direct),
    )
    runtime = SimpleNamespace(version="3.10.3")
    monkeypatch.setattr(contract, "distribution", lambda name: runtime if name == "nltk" else obj)
    monkeypatch.setattr(contract, "__file__", str(tmp_path / "scripts/release_contract.py"))
    source = direct["url"] + "?rev=" + "a" * 40 + "#" + "a" * 40
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname="example"\nversion="1.0"\nsource={git="' + source + '"}\n'
    )
    return obj, runtime, direct, payload


def hashes(installed):
    obj, _, _, payload = installed
    return [
        {"path": name, "sha256": hashlib.sha256((payload / name).read_bytes()).hexdigest()}
        for name in obj.files
    ]


def source_review(installed):
    today = datetime.now(timezone.utc).date()
    return {
        "schema_version": 1,
        "name": "example",
        "version": "1.0",
        "repository": "https://github.com/example/source.git",
        "commit": "a" * 40,
        "reviewed_at": today.isoformat(),
        "expires": (today + timedelta(days=1)).isoformat(),
        "disposition": "accepted-scoped-source-review",
        "findings": [],
        "references": ["https://github.com/example/source"],
        "limitations": ["Not registry audit coverage"],
        "installed_files": hashes(installed),
        "runtime_dependencies": {"nltk": "3.10.3"},
    }


def write_review(tmp_path, review):
    path = tmp_path / "source-review.json"
    path.write_text(json.dumps(review))
    return path


def test_source_review_binds_installed_payload_and_receipt(tmp_path, installed):
    path = write_review(tmp_path, source_review(installed))
    result = contract.verify_source_reviews(path)
    assert (
        result[("example", "1.0")]["receipt_sha256"]
        == hashlib.sha256(path.read_bytes()).hexdigest()
    )


@pytest.mark.parametrize(
    "change",
    [
        "payload",
        "extra_root",
        "omitted_root",
        "metadata_only",
        "source",
        "version",
        "runtime",
        "expiry",
        "unresolved",
        "lock",
        "duplicate",
        "traversal",
        "unrecorded",
        "parent_link",
    ],
)
def test_source_review_rejects_changed_or_incomplete_evidence(tmp_path, installed, change):
    obj, runtime, direct, payload = installed
    review = source_review(installed)
    if change == "payload":
        (payload / "example/__init__.py").write_text("CHANGED = True\n")
    elif change in ("extra_root", "omitted_root"):
        (payload / "unreviewed.py").write_text("CHANGED = True\n")
        obj.files.append("unreviewed.py")
    elif change == "metadata_only":
        (payload / "example.dist-info").mkdir()
        (payload / "example.dist-info/METADATA").write_text("Name: example\n")
        obj.files.append("example.dist-info/METADATA")
        review["installed_files"] = hashes(installed)[-1:]
    elif change == "source":
        direct["vcs_info"]["commit_id"] = "b" * 40
    elif change == "version":
        obj.version = "2.0"
    elif change == "runtime":
        runtime.version = "3.11.0"
    elif change == "expiry":
        review["expires"] = "2000-01-01"
    elif change == "unresolved":
        review["findings"] = [{"status": "unresolved"}]
    elif change == "lock":
        (tmp_path / "uv.lock").write_text("package=[]\n")
    elif change == "duplicate":
        review["installed_files"].append(review["installed_files"][0])
    elif change == "traversal":
        review["installed_files"][0]["path"] = "../outside"
    elif change == "unrecorded":
        (payload / "example/extra.py").write_text("unrecorded code")
    elif change == "parent_link":
        (payload / "example").rename(tmp_path / "elsewhere")
        (payload / "example").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    with pytest.raises(ValueError):
        contract.verify_source_reviews(write_review(tmp_path, review))


def license_review(installed):
    evidence = hashes(installed)
    record = {
        "name": "example",
        "version": "1.0",
        "license_files": evidence[1:],
        "normalized_licenses": ["GPL-3.0-only"],
    }
    review = {
        "name": "example",
        "version": "1.0",
        "license_files": evidence[1:],
        "evidence_files": evidence[:1],
        "license_expression": "GPL-3.0-or-later WITH GCC-exception-3.1",
        "normalized_licenses": ["GPL-3.0-or-later WITH GCC-exception-3.1"],
        "rationale": "Exact runtime exception reviewed",
        "source_urls": ["https://spdx.org/licenses/GCC-exception-3.1.html"],
    }
    return record, review


def test_license_review_preserves_atomic_runtime_exception(installed):
    record, review = license_review(installed)
    contract._apply_license_review(record, review)
    assert record["inferred_licenses"] == ["GPL-3.0-only"]
    assert record["normalized_licenses"] == ["GPL-3.0-or-later WITH GCC-exception-3.1"]


@pytest.mark.parametrize(
    "change", ["bytes", "inventory", "version", "expression", "unowned", "empty"]
)
def test_license_review_does_not_override_unverified_evidence(installed, change):
    obj, _, _, payload = installed
    record, review = license_review(installed)
    if change == "bytes":
        (payload / "example/__init__.py").write_text("changed")
    elif change == "inventory":
        review["license_files"] = []
    elif change == "version":
        obj.version = "2.0"
    elif change == "expression":
        review["normalized_licenses"] = ["MIT"]
    elif change == "unowned":
        review["evidence_files"][0]["path"] = "unowned.py"
    elif change == "empty":
        review["normalized_licenses"] = []
    with pytest.raises(ValueError):
        contract._apply_license_review(record, review)


def audit_reports():
    return (
        {
            "dependencies": [
                {
                    "name": "example",
                    "skip_reason": "Dependency not found on PyPI and could not be audited: example (1.0)",
                }
            ]
        },
        {
            "auditReportVersion": 2,
            "vulnerabilities": {},
            "metadata": {
                "vulnerabilities": dict.fromkeys(
                    ["info", "low", "moderate", "high", "critical", "total"], 0
                ),
                "dependencies": {
                    "prod": 1,
                    "dev": 0,
                    "optional": 0,
                    "peer": 0,
                    "peerOptional": 0,
                    "total": 1,
                },
            },
        },
        {"python": 0, "typescript": 0},
    )


def test_unindexed_producer_skip_requires_separate_source_evidence():
    python, npm, exits = audit_reports()
    with pytest.raises(ValueError, match="skipped"):
        contract.validate_audit_reports(python, npm, exits)
    contract.validate_audit_reports(python, npm, exits, {("example", "1.0"): {}})
    assert "vulns" not in python["dependencies"][0]


@pytest.mark.parametrize(
    "change", ["error", "timeout", "version", "extra", "missing", "duplicate", "exit"]
)
def test_source_review_cannot_cover_other_audit_failures(change):
    python, npm, exits = audit_reports()
    record = python["dependencies"][0]
    if change == "error":
        record["error"] = "audit failed"
    elif change == "timeout":
        record["skip_reason"] = "network timeout"
    elif change == "version":
        record["skip_reason"] = record["skip_reason"].replace("1.0", "2.0")
    elif change == "extra":
        python["dependencies"].append({"name": "other", "skip_reason": "missing"})
    elif change == "missing":
        python["dependencies"] = [{"name": "other", "version": "1.0", "vulns": []}]
    elif change == "duplicate":
        python["dependencies"].append(record.copy())
    elif change == "exit":
        exits["python"] = 2
    with pytest.raises(ValueError):
        contract.validate_audit_reports(python, npm, exits, {("example", "1.0"): {}})
