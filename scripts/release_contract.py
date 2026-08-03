#!/usr/bin/env python3
"""Verify and describe immutable matric-eval release artifacts."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import tarfile
import tomllib
import zipfile
from datetime import datetime, timezone
from importlib.metadata import Distribution, distributions
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = 1
EXPRESSION_OPERATORS = {"AND", "OR", "WITH"}
GENERIC_LICENSE_VALUES = {"", "UNKNOWN", "Dual License"}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object in {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_version(root: Path) -> str:
    version_file = root / "src/matric_eval/version.py"
    module = ast.parse(version_file.read_text(encoding="utf-8"), filename=str(version_file))
    for statement in module.body:
        target: ast.expr | None = None
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
        elif isinstance(statement, ast.AnnAssign):
            target = statement.target
        if (
            isinstance(target, ast.Name)
            and target.id == "__version__"
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            return statement.value.value
    raise ValueError(f"No literal __version__ assignment found in {version_file}")


def version_surfaces(root: Path) -> dict[str, str]:
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    package = _read_json(root / "bindings/typescript/package.json")
    package_lock = _read_json(root / "bindings/typescript/package-lock.json")
    lock_root = package_lock.get("packages", {}).get("", {})
    return {
        "pyproject": str(pyproject["project"]["version"]),
        "python_runtime": _source_version(root),
        "typescript_package": str(package["version"]),
        "typescript_lock": str(package_lock["version"]),
        "typescript_lock_root": str(lock_root.get("version", "")),
    }


def verify_versions(root: Path, expected: str | None = None) -> str:
    surfaces = version_surfaces(root)
    values = set(surfaces.values())
    if len(values) != 1 or "" in values:
        raise ValueError(f"Release versions disagree: {surfaces}")
    version = values.pop()
    if expected is not None and version != expected:
        raise ValueError(f"Expected release {expected}, found {version}")
    return version


def _archive_member_payload(path: Path, member_name: str) -> bytes:
    with tarfile.open(path, "r:gz") as archive:
        member = archive.getmember(member_name)
        handle = archive.extractfile(member)
        if handle is None:
            raise ValueError(f"Cannot read {member_name} from {path}")
        return handle.read()


def verify_artifacts(root: Path, version: str) -> dict[str, str]:
    python_dir = root / "packages/python"
    typescript_dir = root / "packages/typescript"
    wheel = _one(python_dir.glob(f"matric_eval-{version}-*.whl"), "wheel")
    sdist = _one(python_dir.glob(f"matric_eval-{version}.tar.gz"), "sdist")
    npm = _one(typescript_dir.glob(f"matric-eval-client-{version}.tgz"), "npm package")

    with zipfile.ZipFile(wheel) as archive:
        _reject_workspace_members(archive.namelist(), wheel)
        metadata_names = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_names) != 1:
            raise ValueError(f"Expected one wheel METADATA file, found {metadata_names}")
        metadata = archive.read(metadata_names[0]).decode("utf-8")
        if f"Version: {version}\n" not in metadata:
            raise ValueError(f"Wheel metadata does not declare version {version}")

    with tarfile.open(sdist, "r:gz") as archive:
        relative_names = [name.split("/", 1)[1] for name in archive.getnames() if "/" in name]
        _reject_workspace_members(relative_names, sdist)
        package_info = [name for name in archive.getnames() if name.endswith("/PKG-INFO")]
        if len(package_info) != 1:
            raise ValueError("Source distribution is missing a unique PKG-INFO")

    package_json_name = "package/package.json"
    with tarfile.open(npm, "r:gz") as archive:
        _reject_workspace_members(archive.getnames(), npm)
    package_json = json.loads(_archive_member_payload(npm, package_json_name))
    if package_json.get("version") != version:
        raise ValueError(f"npm package does not declare version {version}")

    return {"wheel": str(wheel), "sdist": str(sdist), "npm": str(npm)}


def _reject_workspace_members(names: list[str], archive: Path) -> None:
    forbidden_parts = {
        "node_modules",
        ".git",
        ".aiwg",
        ".claude",
        ".codex",
        "__pycache__",
        "test",
        "tests",
    }
    forbidden_suffixes = (".bak", ".pyc")
    leaked = [
        name
        for name in names
        if forbidden_parts.intersection(PurePosixPath(name).parts)
        or name.endswith(forbidden_suffixes)
    ]
    if leaked:
        raise ValueError(f"{archive.name} contains workspace-only paths: {leaked[:10]}")


def _one(paths: Any, label: str) -> Path:
    matches = list(paths)
    if len(matches) != 1:
        raise ValueError(f"Expected one {label}, found {[str(path) for path in matches]}")
    return matches[0]


def _license_file_texts(distribution: Distribution) -> list[tuple[str, str]]:
    texts: list[tuple[str, str]] = []
    for entry in distribution.files or ():
        name = str(entry)
        if not re.search(r"(^|/)(license|copying|notice)([._-]|$)", name, re.IGNORECASE):
            continue
        path = distribution.locate_file(entry)
        try:
            texts.append((name, path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    return texts


def _expression_ids(value: str) -> set[str]:
    if not value or value in GENERIC_LICENSE_VALUES:
        return set()
    tokens = set(re.findall(r"[A-Za-z0-9][A-Za-z0-9.+-]*", value))
    return {token for token in tokens if token.upper() not in EXPRESSION_OPERATORS}


def _infer_license_ids(values: list[str], license_texts: list[str]) -> set[str]:
    expression = values[0] if values else ""
    identifiers = _expression_ids(expression)
    if identifiers and not any(" " in token for token in identifiers):
        return identifiers

    combined = "\n".join([*values, *license_texts]).lower()
    inferred: set[str] = set()
    mappings = (
        ("apache", "Apache-2.0"),
        ("mozilla public license 2.0", "MPL-2.0"),
        ("mpl-2.0", "MPL-2.0"),
        ("gnu lesser general public license v2", "LGPL-2.0-only"),
        ("python software foundation", "PSF-2.0"),
        ("psfl", "PSF-2.0"),
        ("mit-cmu", "MIT-CMU"),
        ("permission is hereby granted", "MIT"),
        ("mit license", "MIT"),
        ("mit", "MIT"),
        ("redistribution and use in source and binary forms", "BSD-3-Clause"),
        ("bsd 3-clause", "BSD-3-Clause"),
        ("bsd-3-clause", "BSD-3-Clause"),
        ("modified bsd", "BSD-3-Clause"),
        ("bsd-2-clause", "BSD-2-Clause"),
        ("bsd", "BSD-3-Clause"),
        ("isc license", "ISC"),
        ("isc", "ISC"),
        ("0bsd", "0BSD"),
        ("cc0-1.0", "CC0-1.0"),
        ("cnri-python", "CNRI-Python"),
        ("zlib", "Zlib"),
    )
    for marker, identifier in mappings:
        if marker in combined:
            inferred.add(identifier)
    if re.search(r"gnu affero general public license\s+(?:version\s+)?3", combined):
        inferred.add("AGPL-3.0-only")
    if re.search(r"gnu general public license\s+(?:version\s+)?3", combined):
        inferred.add("GPL-3.0-only")
    if re.search(r"gnu general public license\s+(?:version\s+)?2", combined):
        inferred.add("GPL-2.0-only")
    return inferred


def _python_license_records() -> list[dict[str, Any]]:
    records: dict[tuple[str, str], dict[str, Any]] = {}
    for distribution in distributions():
        name = distribution.metadata.get("Name", "unknown")
        expression = distribution.metadata.get("License-Expression", "")
        declared = distribution.metadata.get("License", "")
        classifiers = [
            value
            for value in distribution.metadata.get_all("Classifier", [])
            if value.startswith("License ::")
        ]
        files = _license_file_texts(distribution)
        values = [expression, declared, *classifiers]
        identifiers = _infer_license_ids(values, [text for _, text in files])
        records[(name.lower(), distribution.version)] = {
            "ecosystem": "PyPI",
            "name": name,
            "version": distribution.version,
            "license_expression": expression or None,
            "declared_license": declared or None,
            "classifiers": classifiers,
            "license_files": [
                {"path": path, "sha256": hashlib.sha256(text.encode()).hexdigest()}
                for path, text in files
            ],
            "normalized_licenses": sorted(identifiers),
        }
    return [records[key] for key in sorted(records)]


def _npm_license_records(sbom: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for component in sbom.get("components", []):
        declared: list[str] = []
        for item in component.get("licenses", []):
            license_value = item.get("license", {})
            value = license_value.get("id") or license_value.get("name")
            if value:
                declared.append(str(value))
        identifiers: set[str] = set()
        for value in declared:
            identifiers.update(_expression_ids(value))
        records.append(
            {
                "ecosystem": "npm",
                "name": component.get("name", "unknown"),
                "version": component.get("version", "unknown"),
                "declared_licenses": declared,
                "normalized_licenses": sorted(identifiers),
            }
        )
    return sorted(records, key=lambda item: (item["name"].lower(), item["version"]))


def generate_license_report(
    npm_sbom_path: Path,
    policy_path: Path,
    json_output: Path,
    markdown_output: Path,
) -> None:
    policy = _read_json(policy_path)
    accepted = set(policy["accepted_licenses"])
    prohibited = set(policy["prohibited_licenses"])
    records = [*_python_license_records(), *_npm_license_records(_read_json(npm_sbom_path))]

    unresolved: list[str] = []
    unaccepted: list[str] = []
    for record in records:
        identifiers = set(record["normalized_licenses"])
        if not identifiers:
            unresolved.append(f"{record['ecosystem']}:{record['name']}@{record['version']}")
            record["review_status"] = "unresolved"
        elif identifiers & prohibited or not identifiers.issubset(accepted):
            unaccepted.append(f"{record['ecosystem']}:{record['name']}@{record['version']}")
            record["review_status"] = "unaccepted"
        else:
            record["review_status"] = "accepted"

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": str(policy_path),
        "summary": {
            "components": len(records),
            "accepted": len(records) - len(unresolved) - len(unaccepted),
            "unresolved": len(unresolved),
            "unaccepted": len(unaccepted),
        },
        "unresolved": unresolved,
        "unaccepted": unaccepted,
        "components": records,
    }
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary = report["summary"]
    lines = [
        "# Dependency License Review",
        "",
        f"Generated: {report['generated_at']}",
        "",
        f"- Components reviewed: {summary['components']}",
        f"- Accepted: {summary['accepted']}",
        f"- Unresolved: {summary['unresolved']}",
        f"- Unaccepted: {summary['unaccepted']}",
        "",
        "The machine-readable JSON report contains each declaration, classifier,",
        "license-file digest, normalized identifier, and policy decision.",
    ]
    markdown_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if unresolved or unaccepted:
        raise ValueError(f"License review failed: unresolved={unresolved}, unaccepted={unaccepted}")


def review_vulnerabilities(
    python_audit_path: Path,
    npm_audit_path: Path,
    policy_path: Path,
    json_output: Path,
    markdown_output: Path,
) -> None:
    python_audit = _read_json(python_audit_path)
    npm_audit = _read_json(npm_audit_path)
    policy = _read_json(policy_path)
    accepted = {
        (item["id"], item["package"], item["version"]): item for item in policy["accepted_findings"]
    }
    today = datetime.now(timezone.utc).date()
    findings: list[dict[str, Any]] = []
    unaccepted: list[str] = []

    for dependency in python_audit.get("dependencies", []):
        package = str(dependency["name"])
        version = str(dependency["version"])
        for vulnerability in dependency.get("vulns", []):
            identifier = str(vulnerability["id"])
            decision = accepted.get((identifier, package, version))
            record = {
                "ecosystem": "PyPI",
                "package": package,
                "version": version,
                "id": identifier,
                "aliases": vulnerability.get("aliases", []),
                "fix_versions": vulnerability.get("fix_versions", []),
            }
            if decision is None:
                record["review_status"] = "unaccepted"
                unaccepted.append(f"PyPI:{package}@{version}:{identifier}")
            else:
                expires = datetime.fromisoformat(decision["expires"]).date()
                severity = str(decision["severity"]).lower()
                record.update(
                    {
                        "severity": severity,
                        "rationale": decision["rationale"],
                        "expires": decision["expires"],
                        "references": decision["references"],
                    }
                )
                if severity == "critical" or expires < today:
                    record["review_status"] = "unaccepted"
                    unaccepted.append(f"PyPI:{package}@{version}:{identifier}")
                else:
                    record["review_status"] = "accepted"
            findings.append(record)

    npm_counts = npm_audit.get("metadata", {}).get("vulnerabilities", {})
    npm_critical = int(npm_counts.get("critical", 0))
    if npm_critical:
        unaccepted.append(f"npm:critical:{npm_critical}")

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": str(policy_path),
        "summary": {
            "python_findings": len(findings),
            "accepted_python_findings": sum(
                finding["review_status"] == "accepted" for finding in findings
            ),
            "npm_vulnerabilities": npm_counts,
            "unaccepted": len(unaccepted),
        },
        "unaccepted": unaccepted,
        "python_findings": findings,
    }
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_output.write_text(
        "\n".join(
            [
                "# Dependency Vulnerability Review",
                "",
                f"Generated: {report['generated_at']}",
                "",
                f"- Python findings: {report['summary']['python_findings']}",
                f"- Accepted Python findings: {report['summary']['accepted_python_findings']}",
                f"- npm Critical findings: {npm_critical}",
                f"- Unaccepted findings: {report['summary']['unaccepted']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    if unaccepted:
        raise ValueError(f"Vulnerability review failed: {unaccepted}")


def generate_manifest(root: Path, version: str, output: Path, sums_output: Path) -> None:
    excluded = {output.resolve(), sums_output.resolve()}
    files = sorted(
        path for path in root.rglob("*") if path.is_file() and path.resolve() not in excluded
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    entries = [
        {
            "path": str(path.relative_to(root)),
            "size": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in files
    ]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "version": version,
        "source_commit": commit,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": entries,
    }
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checksum_files = [*files, output]
    sums_output.write_text(
        "".join(f"{_sha256(path)}  {path.relative_to(root)}\n" for path in checksum_files),
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    versions = subparsers.add_parser("versions", help="Verify all package versions agree")
    versions.add_argument("--expected")
    versions.add_argument("--output", type=Path)

    artifacts = subparsers.add_parser("artifacts", help="Verify built package contents")
    artifacts.add_argument("--artifact-root", type=Path, required=True)
    artifacts.add_argument("--expected")

    licenses = subparsers.add_parser("licenses", help="Generate and enforce license review")
    licenses.add_argument("--npm-sbom", type=Path, required=True)
    licenses.add_argument("--policy", type=Path, required=True)
    licenses.add_argument("--json-output", type=Path, required=True)
    licenses.add_argument("--markdown-output", type=Path, required=True)

    vulnerabilities = subparsers.add_parser(
        "vulnerabilities", help="Review dependency audit findings"
    )
    vulnerabilities.add_argument("--python-audit", type=Path, required=True)
    vulnerabilities.add_argument("--npm-audit", type=Path, required=True)
    vulnerabilities.add_argument("--policy", type=Path, required=True)
    vulnerabilities.add_argument("--json-output", type=Path, required=True)
    vulnerabilities.add_argument("--markdown-output", type=Path, required=True)

    manifest = subparsers.add_parser("manifest", help="Hash release artifacts")
    manifest.add_argument("--artifact-root", type=Path, required=True)
    manifest.add_argument("--expected")
    manifest.add_argument("--output", type=Path, required=True)
    manifest.add_argument("--sums-output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.root.resolve()
    version = verify_versions(root, getattr(args, "expected", None))
    if args.command == "versions":
        result = {"version": version, "surfaces": version_surfaces(root)}
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps(result, sort_keys=True))
    elif args.command == "artifacts":
        print(json.dumps(verify_artifacts(args.artifact_root, version), sort_keys=True))
    elif args.command == "licenses":
        generate_license_report(args.npm_sbom, args.policy, args.json_output, args.markdown_output)
    elif args.command == "vulnerabilities":
        review_vulnerabilities(
            args.python_audit,
            args.npm_audit,
            args.policy,
            args.json_output,
            args.markdown_output,
        )
    elif args.command == "manifest":
        generate_manifest(args.artifact_root, version, args.output, args.sums_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
