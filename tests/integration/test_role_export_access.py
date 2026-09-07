"""Synthetic access qualification using the unchanged #123 container profile."""

import json
import os
import secrets

import pytest

from matric_eval.data.access import SourceVault
from matric_eval.data.exports import export_sft, read_sft_export
from matric_eval.data.role_ledger import RoleLedger
from matric_eval.data.roles import canonical
from matric_eval.scorers.isolated_execution import execute_python
from tests.unit.test_role_exports import checkpoint, prepare_vault, request

pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]

WORKER = """import json,os,pathlib,sys
request=json.load(sys.stdin)
protected=pathlib.Path(request['forbidden_path'])
alias=pathlib.Path('/tmp/role-export-alias')
alias.symlink_to(protected)
attempts=[protected,pathlib.Path('/tmp/..') / str(protected).lstrip('/'),alias]
denied=[]
for path in attempts:
    try:
        path.read_bytes()
        denied.append(False)
    except OSError:
        denied.append(True)
print(json.dumps({'uid':os.getuid(),'denied':denied,'records':request['records']},sort_keys=True,separators=(',',':')))
"""


def test_synthetic_roundtrip_cannot_access_host_holdout(tmp_path, record_property):
    if os.environ.get("MATRIC_EVAL_TEST_ISOLATION") != "1":
        pytest.skip("Role export access qualification requires explicit #123 isolation opt-in")
    assert os.environ.get("MATRIC_EVAL_SANDBOX_IMAGE"), "Pinned profile must be configured"
    secret = secrets.token_hex(32)
    protected_dir = tmp_path / "private-holdout"
    protected_dir.mkdir(mode=0o700)
    sentinel = protected_dir / "sentinel"
    sentinel.write_text(secret)
    sentinel.chmod(0o600)
    prepare_vault(tmp_path / "vault")
    vault = SourceVault(tmp_path / "vault")
    ledger = RoleLedger(vault)
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    try:
        ledger.checkpoint(checkpoint())
        report = export_sft(vault, ledger, request(), output)
        assert report["status"] == "accepted"
        payload = next(output.glob("*.jsonl")).read_bytes()
        manifest = next(output.glob("*.manifest.json")).read_bytes()
        _, records = read_sft_export(manifest, payload)
        # Only the path, never secret content, enters the isolated worker. There
        # are no mounts and the bootstrap input contains permitted synthetic rows.
        bounded_input = canonical(
            {"forbidden_path": str(sentinel), "records": [row.model_dump() for row in records]}
        ).decode()
        assert secret not in bounded_input and secret not in WORKER
        result = execute_python(WORKER, stdin_input=bounded_input)
        record_property(
            "role_export_isolation_provenance", json.dumps(result["provenance"], sort_keys=True)
        )
        assert result["status"] == "passed", result["error"]
        assert result["provenance"]["profile"] == "python-restricted/1"
        assert result["provenance"]["restrictions_verified"] is True
        assert result["provenance"]["cleanup"] == "verified_absent"
        response = json.loads(result["stdout"])
        assert response["uid"] == 65534
        assert response["denied"] == [True, True, True]
        roundtrip = b"".join(canonical(row) + b"\n" for row in response["records"])
        assert roundtrip == payload
        for artifact in [
            payload,
            manifest,
            ledger.path.read_bytes(),
            result["stdout"].encode(),
            result["stderr"].encode(),
        ]:
            assert secret.encode() not in artifact
        assert sentinel.read_text() == secret
    finally:
        ledger.close()
        vault.close()
