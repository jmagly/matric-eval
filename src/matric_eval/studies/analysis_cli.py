"""Build the content-free preregistered analysis from normalized full-study outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any, Sequence

from matric_eval.studies.analysis import analyze_observations, load_observations
from matric_eval.studies.protocol import StudyProtocol


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _json_object(path: Path, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return payload


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"observation line {line_number} must contain a JSON object")
        rows.append(payload)
    if not rows:
        raise ValueError("observation JSONL is empty")
    return rows


def _code_revision() -> str:
    root = Path(__file__).resolve().parents[3]
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if status.stdout:
        raise RuntimeError("analysis checkout must be clean")
    revision = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    if len(revision) != 40 or any(character not in "0123456789abcdef" for character in revision):
        raise RuntimeError("analysis checkout did not report a full lowercase Git revision")
    return revision


def _write_public_json(path: Path, payload: dict[str, Any]) -> str:
    if path.exists():
        raise ValueError(f"refusing to overwrite analysis output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8") as handle:
        handle.write(serialized)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o644)
    return _sha256(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("observations", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    study = StudyProtocol.from_yaml(args.protocol, validate_registry=False)
    expected_hostname = study.raw["study"]["execution"].get("expected_hostname")
    if expected_hostname and platform.node() != expected_hostname:
        raise RuntimeError(
            f"study analysis must run on {expected_hostname}, found {platform.node()}"
        )
    analysis = analyze_observations(
        study,
        _json_object(args.manifest, "study manifest"),
        load_observations(_jsonl(args.observations)),
    )
    analysis.update(
        {
            "analysis_code_revision": _code_revision(),
            "observations_sha256": _sha256(args.observations),
        }
    )
    output_sha256 = _write_public_json(args.output, analysis)
    print(
        json.dumps(
            {
                "study_id": study.id,
                "output": str(args.output),
                "output_sha256": output_sha256,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
