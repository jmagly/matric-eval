"""Content-addressed Tau simulator/interface patch-chain support."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qwen38_tau_context import (
    TauPatchContract,
    apply_tau_patch,
    load_patch_contract,
    sha256_file,
    verify_tau_checkout,
)

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class TauSimulatorPatchContract:
    """One simulator patch layered on the immutable target-context patch."""

    upstream_revision: str
    context_manifest_path: Path
    context_manifest_sha256: str
    context_contract: TauPatchContract
    patch_path: Path
    patch_sha256: str
    layer_diff_sha256: str
    cumulative_diff_sha256: str
    changed_paths: tuple[str, ...]


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _git(checkout: Path, arguments: list[str], *, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(checkout), *arguments],
        check=True,
        capture_output=True,
        text=text,
        timeout=60,
    )
    stdout = result.stdout
    if text:
        if not isinstance(stdout, str):
            raise TypeError("text Git command returned non-text output")
        return stdout
    if not isinstance(stdout, bytes):
        raise TypeError("binary Git command returned non-binary output")
    return stdout


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 value")
    return value


def load_simulator_patch_contract(manifest_path: Path) -> TauSimulatorPatchContract:
    """Load the second patch layer and verify every prerequisite by hash."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != "1":
        raise ValueError("Tau simulator patch manifest must be a schema-version 1 object")
    patch_name = payload.get("patch_file")
    context_name = payload.get("context_manifest_file")
    if not isinstance(patch_name, str) or Path(patch_name).name != patch_name:
        raise ValueError("Tau simulator patch filename must be a basename")
    if not isinstance(context_name, str) or Path(context_name).name != context_name:
        raise ValueError("Tau context manifest filename must be a basename")
    patch_path = (manifest_path.parent / patch_name).resolve()
    context_path = (manifest_path.parent / context_name).resolve()
    patch_sha256 = sha256_file(patch_path)
    context_manifest_sha256 = sha256_file(context_path)
    if patch_sha256 != payload.get("patch_sha256"):
        raise ValueError("Tau simulator patch SHA-256 does not match its manifest")
    if context_manifest_sha256 != payload.get("context_manifest_sha256"):
        raise ValueError("Tau context manifest SHA-256 does not match the patch chain")
    context_contract = load_patch_contract(context_path)
    if context_contract.patch_sha256 != payload.get("context_patch_sha256"):
        raise ValueError("Tau context patch SHA-256 does not match the prerequisite")
    if context_contract.patched_diff_sha256 != payload.get("context_diff_sha256"):
        raise ValueError("Tau context diff SHA-256 does not match the prerequisite")
    upstream_revision = payload.get("upstream_revision")
    if upstream_revision != context_contract.upstream_revision:
        raise ValueError("Tau simulator and context patches pin different revisions")
    if (
        not isinstance(upstream_revision, str)
        or re.fullmatch(r"[0-9a-f]{40}", upstream_revision) is None
    ):
        raise ValueError("Tau upstream revision must be a full lowercase Git SHA")
    changed_paths = payload.get("changed_paths")
    if not isinstance(changed_paths, list) or not all(
        isinstance(path, str) and path for path in changed_paths
    ):
        raise ValueError("Tau cumulative changed_paths must be a nonempty string list")
    if changed_paths != sorted(set(changed_paths)):
        raise ValueError("Tau cumulative changed_paths must be sorted and unique")
    if not set(context_contract.changed_paths).issubset(changed_paths):
        raise ValueError("Tau simulator changed_paths omit a context-patch prerequisite")
    layer_diff_sha256 = _require_sha256(payload.get("layer_diff_sha256"), "layer diff")
    if layer_diff_sha256 != patch_sha256:
        raise ValueError("Tau simulator patch bytes differ from the declared layer diff")
    return TauSimulatorPatchContract(
        upstream_revision=upstream_revision,
        context_manifest_path=context_path,
        context_manifest_sha256=context_manifest_sha256,
        context_contract=context_contract,
        patch_path=patch_path,
        patch_sha256=patch_sha256,
        layer_diff_sha256=layer_diff_sha256,
        cumulative_diff_sha256=_require_sha256(
            payload.get("cumulative_diff_sha256"), "cumulative diff"
        ),
        changed_paths=tuple(changed_paths),
    )


def verify_tau_simulator_checkout(
    checkout: Path, contract: TauSimulatorPatchContract
) -> JsonObject:
    """Verify the exact upstream HEAD and cumulative two-layer worktree diff."""
    revision = str(_git(checkout, ["rev-parse", "HEAD"])).strip()
    if revision != contract.upstream_revision:
        raise RuntimeError("Tau checkout is not at the patch chain's upstream revision")
    status = str(_git(checkout, ["status", "--porcelain=v1", "--untracked-files=all"]))
    changed_paths = tuple(
        sorted(line[3:].strip() for line in status.splitlines() if len(line) >= 4)
    )
    if changed_paths != contract.changed_paths:
        raise RuntimeError("Tau checkout changed paths do not match the patch chain")
    diff = _git(
        checkout,
        ["diff", "HEAD", "--binary", "--", *contract.changed_paths],
        text=False,
    )
    assert isinstance(diff, bytes)
    digest = _sha256_bytes(diff)
    if digest != contract.cumulative_diff_sha256:
        raise RuntimeError("Tau checkout diff does not match the cumulative patch chain")
    subprocess.run(
        ["git", "-C", str(checkout), "apply", "--reverse", "--check", str(contract.patch_path)],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return {
        "upstream_revision": revision,
        "tracked_changes": list(changed_paths),
        "context_manifest_sha256": contract.context_manifest_sha256,
        "context_patch_sha256": contract.context_contract.patch_sha256,
        "simulator_patch_sha256": contract.patch_sha256,
        "cumulative_diff_sha256": digest,
    }


def apply_tau_simulator_patch(checkout: Path, contract: TauSimulatorPatchContract) -> JsonObject:
    """Apply only the second layer to a verified context-patched checkout."""
    verify_tau_checkout(checkout, contract.context_contract)
    subprocess.run(
        ["git", "-C", str(checkout), "apply", "--check", str(contract.patch_path)],
        check=True,
        timeout=60,
    )
    subprocess.run(
        ["git", "-C", str(checkout), "apply", str(contract.patch_path)],
        check=True,
        timeout=60,
    )
    return verify_tau_simulator_checkout(checkout, contract)


def prepare_tau_simulator_checkout(
    checkout: Path, contract: TauSimulatorPatchContract
) -> JsonObject:
    """Apply missing layers or verify an already-complete exact patch chain."""
    status = str(_git(checkout, ["status", "--porcelain=v1", "--untracked-files=all"]))
    changed_paths = tuple(
        sorted(line[3:].strip() for line in status.splitlines() if len(line) >= 4)
    )
    if not changed_paths:
        apply_tau_patch(checkout, contract.context_contract)
        return apply_tau_simulator_patch(checkout, contract)
    if changed_paths == tuple(sorted(contract.context_contract.changed_paths)):
        return apply_tau_simulator_patch(checkout, contract)
    return verify_tau_simulator_checkout(checkout, contract)
