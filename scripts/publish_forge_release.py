#!/usr/bin/env python3
"""Verify canonical source/CI and publish immutable artifacts through a draft release."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

SERVER = "https://git.integrolabs.net"
REPOSITORY = "roctinam/matric-eval"
API = f"/api/v1/repos/{REPOSITORY}"
MAX_ASSET = 128 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024
PAGE_SIZE = 50
MAX_PAGES = 100


class Refused(RuntimeError):
    """A publication condition was not established."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Refused(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def version_for(tag: str, commit: str) -> str:
    require(
        bool(re.fullmatch(r"v[1-9][0-9]{3}\.(?:[1-9]|1[0-2])\.(?:0|[1-9][0-9]*)", tag)),
        "invalid CalVer tag",
    )
    require(
        bool(re.fullmatch(r"[0-9a-f]{40}", commit)),
        "full lowercase source SHA required",
    )
    return tag[1:]


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        require(
            urllib.parse.urlsplit(newurl).netloc == urllib.parse.urlsplit(SERVER).netloc
            and urllib.parse.urlsplit(newurl).scheme == urllib.parse.urlsplit(SERVER).scheme,
            "cross-origin redirect refused",
        )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Forge:
    def __init__(self, token: str) -> None:
        require(bool(token), "RELEASE_TOKEN is required")
        self.token = token
        self.opener = urllib.request.build_opener(SafeRedirect())

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        content_type: str = "application/json",
        *,
        missing: bool = False,
        maximum: int = MAX_ASSET,
    ) -> bytes | None:
        url = path if path.startswith(("https://", "http://")) else SERVER + path
        parsed, canonical = urllib.parse.urlsplit(url), urllib.parse.urlsplit(SERVER)
        require(
            (parsed.scheme, parsed.netloc) == (canonical.scheme, canonical.netloc)
            and not parsed.username
            and not parsed.password
            and not parsed.fragment,
            "noncanonical request refused",
        )
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Authorization": f"token {self.token}",
                "Content-Type": content_type,
                "Accept": "application/json",
            },
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                data = response.read(maximum + 1)
                require(len(data) <= maximum, "response exceeds bound")
                return data
        except urllib.error.HTTPError as error:
            if missing and error.code == 404:
                return None
            raise Refused(f"canonical API {method} failed with HTTP {error.code}") from None
        except (OSError, urllib.error.URLError) as error:
            raise Refused(
                f"canonical API {method} transport failed ({type(error).__name__})"
            ) from None

    def json(self, method: str, path: str, value: Any = None, *, missing: bool = False) -> Any:
        data = self.request(
            method,
            path,
            json.dumps(value).encode() if value is not None else None,
            missing=missing,
            maximum=8 * 1024 * 1024,
        )
        return json.loads(data) if data is not None else None

    def pages(self, path: str, key: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for page in range(1, MAX_PAGES + 1):
            result = self.json(
                "GET",
                path
                + ("&" if "?" in path else "?")
                + urllib.parse.urlencode({"limit": PAGE_SIZE, "page": page}),
            )
            values = result[key] if key else result
            require(isinstance(values, list), "invalid paginated response")
            rows.extend(values)
            if (
                not values
                or (key and len(rows) >= result["total_count"])
                or (not key and len(values) < PAGE_SIZE)
            ):
                return rows
        raise Refused("canonical API pagination bound exceeded")


def git(root: Path, *args: str) -> str:
    environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    token = os.environ.get("RELEASE_TOKEN")
    if token:
        header = "Authorization: Basic " + base64.b64encode(("oauth2:" + token).encode()).decode()
        environment.update(
            GIT_CONFIG_COUNT="3",
            GIT_CONFIG_KEY_0="http.https://git.integrolabs.net/.extraheader",
            GIT_CONFIG_VALUE_0=header,
            GIT_CONFIG_KEY_1="http.followRedirects",
            GIT_CONFIG_VALUE_1="false",
            GIT_CONFIG_KEY_2="credential.helper",
            GIT_CONFIG_VALUE_2="",
        )
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
            env=environment,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        raise Refused("canonical source ancestry verification failed") from None


def verify_source(forge: Forge, tag: str | None, commit: str, root: Path) -> None:
    require(
        bool(re.fullmatch(r"[0-9a-f]{40}", commit)),
        "full lowercase source SHA required",
    )
    if tag is not None:
        version_for(tag, commit)
    origin = git(root, "remote", "get-url", "origin")
    parsed = urllib.parse.urlsplit(origin)
    require(
        origin == f"git@git.integrolabs.net:{REPOSITORY}.git"
        or (
            parsed.scheme == "https"
            and parsed.hostname == "git.integrolabs.net"
            and parsed.port in (None, 443)
            and parsed.path == f"/{REPOSITORY}.git"
            and not parsed.query
            and not parsed.fragment
        ),
        "origin is not the canonical repository",
    )
    require(git(root, "rev-parse", "HEAD") == commit, "checkout does not match source SHA")
    git(root, "diff", "--quiet", "HEAD", "--")
    arguments = ["fetch", "--no-tags"]
    if git(root, "rev-parse", "--is-shallow-repository") == "true":
        arguments.append("--unshallow")
    git(root, *arguments, "origin", "+refs/heads/main:refs/remotes/origin/main")
    git(root, "merge-base", "--is-ancestor", commit, "refs/remotes/origin/main")
    if tag is not None:
        remote = forge.json("GET", f"{API}/tags/{urllib.parse.quote(tag, safe='')}")
        require(
            remote["name"] == tag and remote["commit"]["sha"] == commit,
            "remote tag does not identify source SHA",
        )


def verify(
    forge: Forge, tag: str | None, commit: str, root: Path, wait_seconds: float = 0
) -> dict[str, Any]:
    require(0 <= wait_seconds <= 1800, "wait must be finite and between 0 and 1800 seconds")
    verify_source(forge, tag, commit, root)
    deadline = time.monotonic() + wait_seconds
    while True:
        runs = forge.pages(f"{API}/actions/runs?head_sha={commit}", "workflow_runs")
        candidates = [
            row
            for row in runs
            if row.get("head_sha") == commit
            and str(row.get("path", "")).split("@", 1)[0] in ("ci.yml", ".gitea/workflows/ci.yml")
        ]
        if candidates:
            latest = max(
                candidates,
                key=lambda row: (int(row["id"]), int(row.get("run_attempt", 0))),
            )
            latest = forge.json("GET", f"{API}/actions/runs/{int(latest['id'])}")
            require(
                latest.get("head_sha") == commit
                and str(latest.get("path", "")).split("@", 1)[0]
                in ("ci.yml", ".gitea/workflows/ci.yml"),
                "CI detail source/workflow mismatch",
            )
            status = latest.get("status")
            if status == "completed":
                status = latest.get("conclusion")
            if status == "success":
                require(
                    latest.get("repository", {}).get("full_name") == REPOSITORY
                    and latest.get("head_repository", {}).get("full_name", REPOSITORY)
                    == REPOSITORY,
                    "CI repository identity mismatch",
                )
                verify_source(forge, tag, commit, root)
                return {
                    "tag": tag,
                    "source_commit": commit,
                    "ci_run_id": latest["id"],
                    "ci_attempt": latest.get("run_attempt", 0),
                }
            require(
                status in ("", "queued", "pending", "waiting", "running", "in_progress"),
                "latest exact-SHA canonical CI did not succeed",
            )
        require(
            time.monotonic() < deadline,
            "successful exact-SHA canonical CI is unavailable",
        )
        time.sleep(min(5, max(0, deadline - time.monotonic())))


def snapshot(artifact_root: Path, bundle: Path, tag: str, commit: str) -> dict[str, bytes]:
    version = version_for(tag, commit)
    root = artifact_root.resolve(strict=True)
    files: dict[str, bytes] = {}
    total = 0
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "artifact symlink refused")
        if path.is_file():
            require(path.stat().st_size <= MAX_ASSET, "artifact exceeds size bound")
            data = path.read_bytes()
            require(len(data) <= MAX_ASSET, "artifact exceeds size bound")
            total += len(data)
            require(total <= MAX_TOTAL, "artifact set exceeds size bound")
            files[path.relative_to(root).as_posix()] = data
    require(
        {"release-manifest.json", "SHA256SUMS"} <= files.keys(),
        "manifest and checksums required",
    )
    manifest = json.loads(files["release-manifest.json"])
    require(
        manifest["version"] == version
        and manifest["source_commit"] == commit
        and manifest["schema_version"] == 1,
        "manifest source/version mismatch",
    )
    entries = manifest["artifacts"]
    paths = [entry["path"] for entry in entries]
    require(
        len(paths) == len(set(paths))
        and set(paths) == set(files) - {"release-manifest.json", "SHA256SUMS"},
        "manifest inventory mismatch",
    )
    for entry in entries:
        data = files[entry["path"]]
        require(
            entry["sha256"] == digest(data) and entry["size"] == len(data),
            "manifest content mismatch",
        )
    sums = {
        line.split("  ", 1)[1]: line.split("  ", 1)[0]
        for line in files["SHA256SUMS"].decode().splitlines()
    }
    require(
        set(sums) == set(files) - {"SHA256SUMS"}
        and len(sums) == len(files["SHA256SUMS"].decode().splitlines()),
        "checksum inventory mismatch",
    )
    require(
        all(sums[name] == digest(data) for name, data in files.items() if name != "SHA256SUMS"),
        "checksum content mismatch",
    )
    required = {
        "version-surfaces.json",
        "clean-install-validation.json",
        "dependency-licenses.json",
        "vulnerability-review.json",
        "python-sbom.cdx.json",
        "typescript-sbom.cdx.json",
    }
    require(
        {
            f"evidence/{name}"
            for name in required
            | {
                "dependency-licenses.md",
                "vulnerability-review.md",
                "python-requirements.txt",
                "python-vulnerabilities.json",
                "typescript-vulnerabilities.json",
                "audit-exit-codes.json",
            }
        }
        <= files.keys(),
        "complete release evidence required",
    )
    reports = {name: json.loads(files[f"evidence/{name}"]) for name in required}
    versions = reports["version-surfaces.json"]
    require(
        versions["version"] == version and set(versions["surfaces"].values()) == {version},
        "version evidence mismatch",
    )
    clean = reports["clean-install-validation.json"]
    require(
        clean["status"] == "passed" and clean["expected_version"] == version,
        "clean consumer validation failed",
    )
    packages = {name for name in files if name.startswith("packages/")}
    require(
        len(packages) == 3
        and sum(name.endswith(".whl") for name in packages) == 1
        and sum(name.endswith(".tar.gz") for name in packages) == 1
        and sum(name.endswith(".tgz") for name in packages) == 1,
        "wheel, sdist and npm artifacts required",
    )
    require(
        len(clean["artifacts"]) == 3
        and {entry["path"] for entry in clean["artifacts"]} == packages
        and all(
            entry["sha256"] == digest(files[entry["path"]])
            and entry["size"] == len(files[entry["path"]])
            for entry in clean["artifacts"]
        ),
        "consumer evidence does not identify packaged bytes",
    )
    require(
        {(row["requested_python"], row["artifact_kind"]) for row in clean["python"]}
        == {
            (version, kind)
            for version in ("3.11", "3.12", "3.13", "3.14")
            for kind in ("wheel", "sdist")
        }
        and len(clean["python"]) == 8
        and clean["typescript"]["package_version"] == version
        and clean["typescript"]["package_name"] == "@matric/eval-client",
        "complete supported consumer matrix required",
    )
    licenses, vulnerabilities = (
        reports["dependency-licenses.json"],
        reports["vulnerability-review.json"],
    )
    require(
        licenses["unresolved"] == []
        and licenses["unaccepted"] == []
        and licenses["summary"]["unresolved"] == 0
        and licenses["summary"]["unaccepted"] == 0,
        "license review not accepted",
    )
    require(
        vulnerabilities["unaccepted"] == [] and vulnerabilities["summary"]["unaccepted"] == 0,
        "vulnerability review not accepted",
    )
    require(
        all(
            reports[name]["bomFormat"] == "CycloneDX"
            for name in ("python-sbom.cdx.json", "typescript-sbom.cdx.json")
        ),
        "SBOM format mismatch",
    )
    require(
        bundle.name == f"matric-eval-{version}-release-bundle.tar.gz"
        and not bundle.is_symlink()
        and bundle.stat().st_size <= MAX_ASSET,
        "invalid release bundle",
    )
    packed = bundle.read_bytes()
    require(len(packed) <= MAX_ASSET, "bundle exceeds size bound")
    seen: set[str] = set()
    with tarfile.open(fileobj=io.BytesIO(packed), mode="r:gz") as archive:
        for member in archive:
            name = member.name.removeprefix("./")
            require(
                not PurePosixPath(name).is_absolute() and ".." not in PurePosixPath(name).parts,
                "unsafe bundle path",
            )
            if member.isdir():
                continue
            require(
                member.isfile()
                and name in files
                and name not in seen
                and member.size == len(files[name]),
                "bundle inventory mismatch",
            )
            stream = archive.extractfile(member)
            require(
                stream is not None and stream.read(MAX_ASSET + 1) == files[name],
                "bundle content mismatch",
            )
            seen.add(name)
    require(seen == set(files), "bundle is incomplete")
    assets = {Path(name).name: data for name, data in files.items()}
    require(
        len(assets) == len(files)
        and all(re.fullmatch(r"[A-Za-z0-9_.-]+", name) for name in assets),
        "asset basename collision or unsafe name",
    )
    require(bundle.name not in assets, "bundle asset collision")
    assets[bundle.name] = packed
    return assets


def publish(
    forge: Forge,
    *,
    tag: str,
    commit: str,
    root: Path,
    artifact_root: Path,
    bundle: Path,
    notes: Path,
    wait_seconds: float = 0,
) -> dict[str, Any]:
    version = version_for(tag, commit)
    assets = snapshot(artifact_root, bundle, tag, commit)
    require(
        notes.resolve() == (root / "docs/releases" / f"{version}.md").resolve(),
        "release notes path mismatch",
    )
    body = notes.read_text()
    require(
        git(root, "show", f"{commit}:docs/releases/{version}.md") == body.strip(),
        "release notes differ from tagged source",
    )
    gate = verify(forge, tag, commit, root, wait_seconds)
    release_path = f"{API}/releases/tags/{urllib.parse.quote(tag, safe='')}"
    release = forge.json("GET", release_path, missing=True)
    if release is None:
        release = forge.json(
            "POST",
            f"{API}/releases",
            {
                "tag_name": tag,
                "target_commitish": commit,
                "name": f"matric-eval {version}",
                "body": body,
                "draft": True,
                "prerelease": False,
            },
        )
    require(
        release["tag_name"] == tag
        and release["target_commitish"] == commit
        and release["body"] == body
        and release["name"] == f"matric-eval {version}"
        and release["prerelease"] is False,
        "existing release content/source mismatch",
    )
    path = f"{API}/releases/{int(release['id'])}"
    existing = forge.pages(path + "/assets")
    by_name = {item["name"]: item for item in existing}
    require(
        len(by_name) == len(existing) and set(by_name) <= assets.keys(),
        "unexpected or duplicate release assets",
    )
    for name, data in assets.items():
        item = by_name.get(name)
        if item is None:
            require(
                release["draft"] is True,
                "published release is incomplete; mutation refused",
            )
            boundary = "matric-" + uuid.uuid4().hex
            upload = (
                f'--{boundary}\r\nContent-Disposition: form-data; name="attachment"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
                + data
                + f"\r\n--{boundary}--\r\n".encode()
            )
            response = forge.request(
                "POST",
                path + "/assets?" + urllib.parse.urlencode({"name": name}),
                upload,
                f"multipart/form-data; boundary={boundary}",
            )
            item = json.loads(response or b"null")
        require(
            item["name"] == name and item["size"] == len(data),
            "release asset metadata mismatch",
        )
        downloaded = forge.request("GET", item["browser_download_url"], maximum=len(data))
        require(
            downloaded is not None and digest(downloaded) == digest(data),
            "release asset content mismatch",
        )
    if release["draft"]:
        verify(forge, tag, commit, root, 0)
    # Re-list and verify the final bytes before making anything public.
    final = forge.pages(path + "/assets")
    require(
        {item["name"] for item in final} == set(assets) and len(final) == len(assets),
        "final release asset inventory mismatch",
    )
    for item in final:
        data = assets[item["name"]]
        require(
            item["size"] == len(data)
            and digest(forge.request("GET", item["browser_download_url"], maximum=len(data)) or b"")
            == digest(data),
            "final release asset content mismatch",
        )
    current = forge.json("GET", release_path)
    require(
        all(
            current.get(key) == release.get(key)
            for key in (
                "id",
                "tag_name",
                "target_commitish",
                "name",
                "body",
                "draft",
                "prerelease",
            )
        ),
        "release changed during verification",
    )
    if release["draft"]:
        release = forge.json("PATCH", path, {"draft": False})
        require(release["draft"] is False, "release publication not acknowledged")
    return {
        **gate,
        "release_id": release["id"],
        "assets_verified": len(assets),
        "published": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify-source", "verify", "publish"))
    parser.add_argument("--tag")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--wait-seconds", type=float, default=0)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--notes", type=Path)
    args = parser.parse_args()
    try:
        forge = Forge(os.environ.get("RELEASE_TOKEN", ""))
        require(args.command == "verify-source" or args.tag is not None, "tag is required")
        require(
            args.command != "verify-source" or args.tag is None,
            "verify-source does not take a tag",
        )
        if args.command in ("verify-source", "verify"):
            result = verify(forge, args.tag, args.commit, args.root, args.wait_seconds)
        else:
            require(
                all((args.artifact_root, args.bundle, args.notes)),
                "publish requires artifact root, bundle and notes",
            )
            result = publish(
                forge,
                tag=args.tag,
                commit=args.commit,
                root=args.root,
                artifact_root=args.artifact_root,
                bundle=args.bundle,
                notes=args.notes,
                wait_seconds=args.wait_seconds,
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (
        Refused,
        ValueError,
        KeyError,
        TypeError,
        OSError,
        tarfile.TarError,
    ) as error:
        # Do not echo arbitrary API payloads or credentials through exceptions.
        print(
            f"Publication refused: {error if isinstance(error, Refused) else type(error).__name__}",
            file=__import__("sys").stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
