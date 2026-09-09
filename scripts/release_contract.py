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
from datetime import date, datetime, timezone
from importlib.metadata import Distribution, distribution, distributions
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
    uv_lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    locked = [item for item in uv_lock["package"] if item["name"] == "matric-eval"]
    if len(locked) != 1:
        raise ValueError("Expected exactly one matric-eval package in uv.lock")
    return {
        "pyproject": str(pyproject["project"]["version"]),
        "python_runtime": _source_version(root),
        "python_lock": str(locked[0]["version"]),
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
    parse_calver(version)
    if expected is not None and version != expected:
        raise ValueError(f"Expected release {expected}, found {version}")
    return version


def parse_calver(version: str) -> tuple[int, int, int]:
    """Canonical YYYY.M.PATCH: unpadded month and monthly release counter."""
    if not re.fullmatch(r"[2-9][0-9]{3}\.(?:[1-9]|1[0-2])\.(?:0|[1-9][0-9]*)", version):
        raise ValueError(f"Invalid CalVer {version!r}; expected YYYY.M.PATCH")
    year, month, patch = map(int, version.split("."))
    return year, month, patch


def next_version(current: str, today: date) -> str:
    year, month, patch = parse_calver(current)
    if (year, month) > (today.year, today.month):
        raise ValueError("Current release is ahead of the UTC calendar month")
    patch = patch + 1 if (year, month) == (today.year, today.month) else 0
    return f"{today.year}.{today.month}.{patch}"


def bump_version(root: Path, requested: str | None = None, *, today: date | None = None) -> str:
    """Update package versions and root lock identities without resolving dependencies."""
    surfaces = version_surfaces(root)
    if len(set(surfaces.values())) != 1:
        raise ValueError(f"Release versions disagree: {surfaces}")
    current = surfaces["pyproject"]
    version = (
        requested
        if requested is not None
        else next_version(current, today or datetime.now(timezone.utc).date())
    )
    target = parse_calver(version)
    try:
        previous = parse_calver(current)
    except ValueError:
        # Migration is deliberate: never infer a calendar version from SemVer.
        if requested is None or not re.fullmatch(
            r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", current
        ):
            raise ValueError("Migration requires an explicit initial CalVer version") from None
        if int(current.split(".")[0]) >= 2000:
            raise ValueError("Cannot migrate malformed calendar version") from None
    else:
        if target <= previous:
            raise ValueError("Release version must increase monotonically")
    replacements: dict[Path, str] = {}
    for relative, pattern in (
        ("pyproject.toml", r'(?ms)(^\[project\]\n.*?^version\s*=\s*")[^"]+(")'),
        ("src/matric_eval/version.py", r'(?m)(^__version__\s*=\s*")[^"]+(")'),
        ("uv.lock", r'(?m)(^name = "matric-eval"\nversion = ")[^"]+(")'),
    ):
        path = root / relative
        text, count = re.subn(
            pattern, lambda match: match[1] + version + match[2], path.read_text()
        )
        if count != 1:
            raise ValueError(f"Expected one version assignment in {relative}")
        replacements[path] = text
    for relative in ("bindings/typescript/package.json", "bindings/typescript/package-lock.json"):
        path = root / relative
        value = _read_json(path)
        value["version"] = version
        if relative.endswith("package-lock.json"):
            value["packages"][""]["version"] = version
        replacements[path] = json.dumps(value, indent=2) + "\n"
    originals = {path: path.read_bytes() for path in replacements}
    try:
        for path, text in replacements.items():
            path.write_text(text, encoding="utf-8")
        verify_versions(root, version)
    except Exception:
        for path, content in originals.items():
            path.write_bytes(content)
        raise
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
        metadata = _archive_member_payload(sdist, package_info[0]).decode("utf-8")
        if f"Version: {version}\n" not in metadata:
            raise ValueError(f"Source distribution metadata does not declare version {version}")

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
    for installed in distributions():
        name = installed.metadata.get("Name", "unknown")
        expression = installed.metadata.get("License-Expression", "")
        declared = installed.metadata.get("License", "")
        classifiers = [
            value
            for value in installed.metadata.get_all("Classifier", [])
            if value.startswith("License ::")
        ]
        files = _license_file_texts(installed)
        values = [expression, declared, *classifiers]
        identifiers = _infer_license_ids(values, [text for _, text in files])
        records[(name.lower(), installed.version)] = {
            "ecosystem": "PyPI",
            "name": name,
            "version": installed.version,
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


def _package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _verify_installed_files(installed: Distribution, files: list[dict[str, str]]) -> None:
    """Bind a reviewed declaration or source payload to distribution-owned bytes."""
    owned = {str(path) for path in installed.files or ()}
    seen: set[str] = set()
    if not files:
        raise ValueError("A distribution review must bind installed evidence files")
    for item in files:
        path = PurePosixPath(item["path"])
        if (
            path.is_absolute()
            or ".." in path.parts
            or str(path) not in owned
            or str(path) in seen
            or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
        ):
            raise ValueError("Invalid or duplicate reviewed distribution path")
        actual = Path(installed.locate_file(str(path)))
        base = Path(installed.locate_file(""))
        symlink = any(
            (base.joinpath(*path.parts[:index])).is_symlink()
            for index in range(1, len(path.parts) + 1)
        )
        if (
            symlink
            or not actual.resolve().is_relative_to(base.resolve())
            or _sha256(actual) != item["sha256"]
        ):
            raise ValueError(f"Reviewed distribution evidence changed: {path}")
        seen.add(str(path))


def _apply_license_review(record: dict[str, Any], review: dict[str, Any]) -> None:
    from packaging.licenses import canonicalize_license_expression

    installed = distribution(record["name"])
    if installed.version != review["version"]:
        raise ValueError("Installed license review version mismatch")
    observed = sorted(record["license_files"], key=lambda item: item["path"])
    expected = sorted(review["license_files"], key=lambda item: item["path"])
    if observed != expected:
        raise ValueError(f"Reviewed license inventory changed: {record['name']}")
    _verify_installed_files(installed, [*expected, *review["evidence_files"]])
    identifiers = review["normalized_licenses"]
    expression = canonicalize_license_expression(review["license_expression"])
    terms = {
        term
        for term in re.findall(r"[^()\s]+(?: WITH [^()\s]+)?", expression)
        if term not in {"AND", "OR"}
    }
    if (
        not identifiers
        or not all(isinstance(value, str) and value for value in identifiers)
        or len(set(identifiers)) != len(identifiers)
        or not review["rationale"]
        or not review["source_urls"]
        or set(identifiers) != terms
    ):
        raise ValueError("Incomplete distribution license review")
    if artifact := review.get("artifact"):
        lock = tomllib.loads((Path(__file__).resolve().parents[1] / "uv.lock").read_text())
        packages = [
            package
            for package in lock["package"]
            if _package_name(package["name"]) == _package_name(record["name"])
            and package["version"] == record["version"]
        ]
        if (
            len(packages) != 1
            or packages[0].get("sdist", {}).get("hash") != ("sha256:" + artifact["sha256"])
            or packages[0]["sdist"]["url"] != artifact["url"]
        ):
            raise ValueError("Reviewed license source archive differs from lock")
    record["inferred_licenses"] = record["normalized_licenses"]
    record["normalized_licenses"] = identifiers
    record["license_review"] = review


def verify_source_reviews(directory: Path | None) -> dict[tuple[str, str], dict[str, Any]]:
    """Verify explicit, expiring source reviews for non-indexed VCS dependencies."""
    verified: dict[tuple[str, str], dict[str, Any]] = {}
    if directory is None:
        return verified
    paths = [directory] if directory.is_file() else sorted(directory.glob("*.review.json"))
    if not paths:
        raise ValueError("Source review directory has no receipts")
    today = datetime.now(timezone.utc).date()
    for path in paths:
        review = _read_json(path)
        if (
            review["schema_version"] != 1
            or review["disposition"] != "accepted-scoped-source-review"
            or not isinstance(review["findings"], list)
            or any(item.get("status") != "resolved" for item in review["findings"])
            or not review["references"]
            or not review["limitations"]
            or not date.fromisoformat(review["reviewed_at"])
            <= today
            <= date.fromisoformat(review["expires"])
            or not re.fullmatch(r"[0-9a-f]{40}", review["commit"])
        ):
            raise ValueError("Unaccepted, incomplete or expired source review")
        installed = distribution(review["name"])
        lock = tomllib.loads((Path(__file__).resolve().parents[1] / "uv.lock").read_text())
        locked = [
            package
            for package in lock["package"]
            if _package_name(package["name"]) == _package_name(review["name"])
            and package["version"] == review["version"]
        ]
        expected_git = f"{review['repository']}?rev={review['commit']}#{review['commit']}"
        if len(locked) != 1 or locked[0].get("source", {}).get("git") != expected_git:
            raise ValueError("Source review differs from locked VCS identity")
        direct = json.loads(installed.read_text("direct_url.json") or "null")
        if (
            installed.version != review["version"]
            or not isinstance(direct, dict)
            or direct.get("url") != review["repository"]
            or direct.get("vcs_info", {}).get("vcs") != "git"
            or direct.get("vcs_info", {}).get("commit_id") != review["commit"]
            or direct.get("dir_info", {}).get("editable")
        ):
            raise ValueError("Installed source differs from reviewed VCS identity")
        files = review["installed_files"]
        _verify_installed_files(installed, files)
        payload = {
            str(item)
            for item in installed.files or ()
            if not any(
                part.endswith((".dist-info", ".egg-info"))
                for part in PurePosixPath(str(item)).parts
            )
            and "__pycache__" not in PurePosixPath(str(item)).parts
            and not str(item).endswith(".pyc")
        }
        actual_payload: set[str] = set()
        base = Path(installed.locate_file(""))
        for name in {PurePosixPath(item).parts[0] for item in payload}:
            location = base / name
            children = location.rglob("*") if location.is_dir() else [location]
            for child in children:
                relative = child.relative_to(base)
                if "__pycache__" in relative.parts or child.suffix == ".pyc":
                    continue
                if child.is_symlink():
                    raise ValueError("Reviewed source payload contains a symlink")
                if child.is_file():
                    actual_payload.add(relative.as_posix())
        if actual_payload != payload:
            raise ValueError("Unrecorded files in reviewed source payload")
        if payload != {item["path"] for item in files}:
            raise ValueError("Reviewed installed source payload is incomplete")
        for name, version in review["runtime_dependencies"].items():
            if distribution(name).version != version:
                raise ValueError(f"Reviewed source runtime changed: {name}")
        identity = (_package_name(review["name"]), review["version"])
        if identity in verified:
            raise ValueError("Duplicate source review identity")
        verified[identity] = {**review, "receipt_sha256": _sha256(path)}
    return verified


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
    reviews = policy.get("reviewed_distributions", [])
    identities = [(_package_name(item["name"]), item["version"]) for item in reviews]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate distribution license review")
    for record in records:
        for review in reviews:
            if record["ecosystem"] == "PyPI" and (
                _package_name(record["name"]),
                record["version"],
            ) == (_package_name(review["name"]), review["version"]):
                _apply_license_review(record, review)
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


def validate_audit_reports(
    python_audit: dict[str, Any],
    npm_audit: dict[str, Any],
    exits: dict[str, Any],
    source_reviews: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> None:
    """Require complete pip-audit JSON and npm audit v2 at --audit-level=critical."""
    for producer in ("python", "typescript"):
        status = exits.get(producer)
        if type(status) is not int or status not in (0, 1):
            raise ValueError(f"Invalid or failed {producer} audit exit status")
    error_fields = {"error", "errors", "skip_reason", "skipped"}
    if error_fields.intersection(python_audit) or error_fields.intersection(npm_audit):
        raise ValueError("Audit producer reported an error or skipped work")
    dependencies = python_audit.get("dependencies")
    if not isinstance(dependencies, list) or not dependencies:
        raise ValueError("Python audit is missing its nonempty dependency inventory")
    python_findings = 0
    seen = set()
    reviewed_skips: set[tuple[str, str]] = set()
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            raise ValueError("Python audit contains an invalid dependency record")
        matches = [
            identity
            for identity in (source_reviews or {})
            if identity[0] == _package_name(str(dependency.get("name", "")))
        ]
        if "skip_reason" in dependency and matches:
            if len(matches) != 1:
                raise ValueError("Ambiguous reviewed source audit identity")
            identity = matches[0]
            expected_reason = f"Dependency not found on PyPI and could not be audited: {dependency['name']} ({identity[1]})"
            if (
                dependency["skip_reason"] != expected_reason
                or set(dependency)
                not in ({"name", "skip_reason"}, {"name", "version", "skip_reason"})
                or dependency.get("version", identity[1]) != identity[1]
            ):
                raise ValueError("Source review cannot cover this audit producer failure")
            if identity in seen:
                raise ValueError("Python audit contains a duplicate dependency")
            seen.add(identity)
            reviewed_skips.add(identity)
            continue
        if error_fields.intersection(dependency):
            raise ValueError(
                f"Python audit skipped or failed dependency: {dependency.get('name', '<unknown>')}; "
                "see the retained producer report; complete audit evidence is required"
            )
        for field in ("name", "version"):
            if not isinstance(dependency.get(field), str) or not dependency[field]:
                raise ValueError(f"Python audit dependency is missing {field}")
        identity = (dependency["name"].lower().replace("_", "-"), dependency["version"])
        if identity in seen:
            raise ValueError("Python audit contains a duplicate dependency")
        seen.add(identity)
        vulns = dependency.get("vulns")
        if not isinstance(vulns, list):
            raise ValueError("Python audit dependency is missing vulnerability results")
        for vuln in vulns:
            if (
                not isinstance(vuln, dict)
                or error_fields.intersection(vuln)
                or not isinstance(vuln.get("id"), str)
                or not vuln["id"]
                or not isinstance(vuln.get("fix_versions"), list)
                or not all(isinstance(item, str) for item in vuln["fix_versions"])
            ):
                raise ValueError("Python audit contains an incomplete vulnerability")
        python_findings += len(vulns)
    if source_reviews and reviewed_skips != source_reviews.keys():
        raise ValueError("Source review does not match the non-indexed audit inventory")
    if exits["python"] != int(python_findings > 0):
        raise ValueError("Python audit exit status disagrees with findings")

    if npm_audit.get("auditReportVersion") != 2:
        raise ValueError("Expected npm audit report version 2")
    metadata = npm_audit.get("metadata")
    vulnerabilities = npm_audit.get("vulnerabilities")
    if not isinstance(metadata, dict) or not isinstance(vulnerabilities, dict):
        raise ValueError("npm audit is missing metadata or vulnerability results")
    counts = metadata.get("vulnerabilities")
    inventory = metadata.get("dependencies")
    severities = ("info", "low", "moderate", "high", "critical")
    for values, fields in (
        (counts, (*severities, "total")),
        (inventory, ("prod", "dev", "optional", "peer", "peerOptional", "total")),
    ):
        if not isinstance(values, dict) or any(
            type(values.get(field)) is not int or values[field] < 0 for field in fields
        ):
            raise ValueError("npm audit contains incomplete or invalid summary counts")
    assert isinstance(counts, dict) and isinstance(inventory, dict)
    if inventory["total"] < 1:
        raise ValueError("npm audit has an empty dependency inventory")
    measured = dict.fromkeys(severities, 0)
    for name, vuln in vulnerabilities.items():
        if (
            not isinstance(vuln, dict)
            or error_fields.intersection(vuln)
            or vuln.get("name") != name
            or vuln.get("severity") not in severities
            or not isinstance(vuln.get("via"), list)
            or not vuln["via"]
            or not isinstance(vuln.get("nodes"), list)
            or not vuln["nodes"]
        ):
            raise ValueError("npm audit contains an incomplete vulnerability")
        measured[vuln["severity"]] += 1
    if any(counts[field] != measured[field] for field in severities) or counts["total"] != sum(
        measured.values()
    ):
        raise ValueError("npm audit summary disagrees with vulnerability inventory")
    if exits["typescript"] != int(counts["critical"] > 0):
        raise ValueError("npm audit exit status disagrees with critical audit threshold")


def review_vulnerabilities(
    python_audit_path: Path,
    npm_audit_path: Path,
    policy_path: Path,
    json_output: Path,
    markdown_output: Path,
    audit_exit_codes_path: Path,
    source_reviews_path: Path | None = None,
) -> None:
    python_audit = _read_json(python_audit_path)
    npm_audit = _read_json(npm_audit_path)
    exits = _read_json(audit_exit_codes_path)
    source_reviews = verify_source_reviews(source_reviews_path)
    validate_audit_reports(python_audit, npm_audit, exits, source_reviews)
    policy = _read_json(policy_path)
    accepted = {
        (item["id"], item["package"], item["version"]): item for item in policy["accepted_findings"]
    }
    today = datetime.now(timezone.utc).date()
    findings: list[dict[str, Any]] = []
    unaccepted: list[str] = []

    for dependency in python_audit["dependencies"]:
        if "skip_reason" in dependency:
            # This exact raw skip was matched to a verified source review above.
            # Preserve it as separate evidence; never label it PyPI audit coverage.
            continue
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

    npm_counts = npm_audit["metadata"]["vulnerabilities"]
    npm_critical = npm_counts["critical"]
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
        "audit_exit_codes": exits,
        "npm_audit_level": "critical",
        "source_reviews": list(source_reviews.values()),
        "source_reviewed_producer_skips": [
            item for item in python_audit["dependencies"] if "skip_reason" in item
        ],
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
                f"- Separately reviewed VCS dependencies: {len(source_reviews)} (not PyPI audit coverage)",
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

    bump = subparsers.add_parser("bump", help="Bump all package versions and root lock identities")
    bump.add_argument("--version", help="Explicit strictly increasing YYYY.M.PATCH version")

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
    vulnerabilities.add_argument("--audit-exit-codes", type=Path, required=True)
    vulnerabilities.add_argument("--policy", type=Path, required=True)
    vulnerabilities.add_argument("--source-reviews", type=Path)
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
    if args.command == "bump":
        version = bump_version(root, args.version)
        print(json.dumps({"version": version, "surfaces": version_surfaces(root)}, sort_keys=True))
        return 0
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
            args.audit_exit_codes,
            args.source_reviews,
        )
    elif args.command == "manifest":
        generate_manifest(args.artifact_root, version, args.output, args.sums_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
