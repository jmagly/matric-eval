"""Actual HTTP publication fixtures, with no live forge credential or publication."""

import email.parser
import importlib.util
import io
import json
import subprocess
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

SPEC = importlib.util.spec_from_file_location(
    "forge_release", Path(__file__).parents[1] / "scripts/publish_forge_release.py"
)
assert SPEC and SPEC.loader
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
VERSION = "2026.9.0"
TAG = "v" + VERSION


@pytest.fixture
def source(tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for key, value in (
        ("user.email", "fixture@example.invalid"),
        ("user.name", "Fixture"),
    ):
        subprocess.run(["git", "-C", str(root), "config", key, value], check=True)
    notes = root / "docs/releases" / f"{VERSION}.md"
    notes.parent.mkdir(parents=True)
    notes.write_text("Verified release notes.\n")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
    commit = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "remote",
            "add",
            "origin",
            "git@git.integrolabs.net:roctinam/matric-eval.git",
        ],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(root), "update-ref", "refs/remotes/origin/main", commit],
        check=True,
    )
    original = release.git

    def local_git(path, *args):
        if args[0] == "fetch":
            return ""  # Network fetch is the only substituted git operation.
        return original(path, *args)

    monkeypatch.setattr(release, "git", local_git)
    return root, commit, notes


@pytest.fixture
def forge(source, monkeypatch):
    state = {
        "release": None,
        "assets": {},
        "events": [],
        "drop": None,
        "commit": source[1],
        "runs": [],
    }
    state["runs"] = [
        {
            "id": 7,
            "run_attempt": 1,
            "head_sha": source[1],
            "status": "completed",
            "conclusion": "success",
            "path": "ci.yml@refs/heads/main",
            "repository": {"full_name": release.REPOSITORY},
            "head_repository": {"full_name": release.REPOSITORY},
        }
    ]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, value, code=200):
            data = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path, query = urlsplit(self.path).path, parse_qs(urlsplit(self.path).query)
            if "/tags/" in path and "/releases/" not in path:
                self.reply({"name": TAG, "commit": {"sha": state["commit"]}})
            elif path.endswith("/actions/runs"):
                page, limit = int(query["page"][0]), int(query["limit"][0])
                self.reply(
                    {
                        "workflow_runs": state["runs"][(page - 1) * limit : page * limit],
                        "total_count": len(state["runs"]),
                    }
                )
            elif "/actions/runs/" in path:
                self.reply(
                    next(row for row in state["runs"] if row["id"] == int(path.rsplit("/", 1)[1]))
                )
            elif "/releases/tags/" in path:
                self.reply(state["release"] or {}, 200 if state["release"] else 404)
            elif path.endswith("/assets"):
                items = [item[0] for item in state["assets"].values()]
                page, limit = int(query["page"][0]), int(query["limit"][0])
                self.reply(items[(page - 1) * limit : page * limit])
            elif path.startswith("/attachments/"):
                self.reply(
                    next(
                        data
                        for item, data in state["assets"].values()
                        if item["id"] == int(path.rsplit("/", 1)[1])
                    )
                )
            else:
                self.reply({}, 404)

        def do_POST(self):
            payload = self.rfile.read(int(self.headers["Content-Length"]))
            if urlsplit(self.path).path.endswith("/releases"):
                state["release"] = {**json.loads(payload), "id": 1}
                state["events"].append("draft")
                if state["drop"] == "draft":
                    state["drop"] = None
                    self.close_connection = True
                    return
                self.reply(state["release"], 201)
            else:
                assert state["release"]["draft"]
                message = email.parser.BytesParser().parsebytes(
                    b"Content-Type: "
                    + self.headers["Content-Type"].encode()
                    + b"\r\n\r\n"
                    + payload
                )
                data = message.get_payload()[0].get_payload(decode=True)
                name = parse_qs(urlsplit(self.path).query)["name"][0]
                assert name not in state["assets"]
                item = {
                    "id": len(state["assets"]) + 1,
                    "name": name,
                    "size": len(data),
                    "browser_download_url": release.SERVER
                    + f"/attachments/{len(state['assets']) + 1}",
                }
                state["assets"][name] = (item, data)
                state["events"].append("upload")
                if state["drop"] == "upload":
                    state["drop"] = None
                    self.close_connection = True
                    return
                self.reply(item, 201)

        def do_PATCH(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert payload == {"draft": False}
            state["events"].append("publish")
            state["release"].update(payload)
            if state["drop"] == "publish":
                state["drop"] = None
                self.close_connection = True
                return
            self.reply(state["release"])

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(release, "SERVER", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setattr(release, "PAGE_SIZE", 2)
    try:
        yield release.Forge("fixture-not-a-live-token"), state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture
def artifacts(source, tmp_path):
    root, commit, notes = source
    target = tmp_path / "artifacts"
    target.mkdir()
    files = {
        "packages/python/package.whl": b"wheel fixture",
        "packages/python/package.tar.gz": b"sdist fixture",
        "packages/typescript/package.tgz": b"npm fixture",
    }
    package_rows = [
        {"path": name, "size": len(data), "sha256": release.digest(data)}
        for name, data in files.items()
    ]
    reports = {
        "version-surfaces.json": {
            "version": VERSION,
            "surfaces": {"python": VERSION, "typescript": VERSION},
        },
        "clean-install-validation.json": {
            "status": "passed",
            "expected_version": VERSION,
            "artifacts": package_rows,
            "python": [
                {"requested_python": v, "artifact_kind": k}
                for v in ("3.11", "3.12", "3.13", "3.14")
                for k in ("wheel", "sdist")
            ],
            "typescript": {
                "package_version": VERSION,
                "package_name": "@matric/eval-client",
            },
        },
        "dependency-licenses.json": {
            "unresolved": [],
            "unaccepted": [],
            "summary": {"unresolved": 0, "unaccepted": 0},
        },
        "vulnerability-review.json": {"unaccepted": [], "summary": {"unaccepted": 0}},
        "python-sbom.cdx.json": {"bomFormat": "CycloneDX"},
        "typescript-sbom.cdx.json": {"bomFormat": "CycloneDX"},
    }
    files.update(
        {"evidence/" + name: json.dumps(value).encode() for name, value in reports.items()}
    )
    files.update(
        {
            "evidence/" + name: b"fixture evidence"
            for name in (
                "dependency-licenses.md",
                "vulnerability-review.md",
                "python-requirements.txt",
                "python-vulnerabilities.json",
                "typescript-vulnerabilities.json",
                "audit-exit-codes.json",
            )
        }
    )
    manifest = {
        "schema_version": 1,
        "version": VERSION,
        "source_commit": commit,
        "artifacts": [
            {"path": name, "size": len(data), "sha256": release.digest(data)}
            for name, data in files.items()
        ],
    }
    files["release-manifest.json"] = json.dumps(manifest).encode()
    files["SHA256SUMS"] = "".join(
        f"{release.digest(data)}  {name}\n" for name, data in files.items()
    ).encode()
    for name, data in files.items():
        path = target / name
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_bytes(data)
    bundle = tmp_path / f"matric-eval-{VERSION}-release-bundle.tar.gz"
    with tarfile.open(bundle, "w:gz") as archive:
        for name, data in files.items():
            item = tarfile.TarInfo(name)
            item.size = len(data)
            archive.addfile(item, io.BytesIO(data))
    return {
        "tag": TAG,
        "commit": commit,
        "root": root,
        "artifact_root": target,
        "bundle": bundle,
        "notes": notes,
    }


def test_draft_published_only_after_all_assets_and_published_retry_read_only(forge, artifacts):
    client, state = forge
    result = release.publish(client, **artifacts)
    assert result["published"] and state["events"][0] == "draft"
    assert state["events"][-1] == "publish"
    assert state["events"].count("upload") == result["assets_verified"]
    before = list(state["events"])
    assert release.publish(client, **artifacts) == result
    assert state["events"] == before


def test_lost_upload_ack_retry_reuses_exact_asset(forge, artifacts):
    client, state = forge
    state["drop"] = "upload"
    with pytest.raises(release.Refused, match="transport"):
        release.publish(client, **artifacts)
    assert state["release"]["draft"] and len(state["assets"]) == 1
    release.publish(client, **artifacts)
    assert state["events"].count("draft") == 1
    assert state["events"].count("upload") == len(state["assets"])


@pytest.mark.parametrize("published", [False, True])
def test_existing_asset_mismatch_never_replaced(forge, artifacts, published):
    client, state = forge
    release.publish(client, **artifacts)
    state["release"]["draft"] = not published
    name = next(iter(state["assets"]))
    item, data = state["assets"][name]
    state["assets"][name] = (item, b"x" * len(data))
    before = list(state["events"])
    with pytest.raises(release.Refused, match="content mismatch"):
        release.publish(client, **artifacts)
    assert state["events"] == before


def test_published_incomplete_release_is_never_repaired(forge, artifacts):
    client, state = forge
    release.publish(client, **artifacts)
    state["assets"].pop(next(iter(state["assets"])))
    before = list(state["events"])
    with pytest.raises(release.Refused, match="incomplete"):
        release.publish(client, **artifacts)
    assert state["events"] == before


@pytest.mark.parametrize(
    "failure",
    ["tag", "sha", "workflow", "latest", "origin", "dirty", "manifest", "bundle"],
)
def test_unproved_source_or_evidence_prevents_every_mutation(forge, artifacts, failure):
    client, state = forge
    if failure == "tag":
        state["commit"] = "f" * 40
    elif failure == "sha":
        state["runs"][0]["head_sha"] = "f" * 40
    elif failure == "workflow":
        state["runs"][0]["path"] = ".gitea/workflows/release.yml"
    elif failure == "latest":
        state["runs"].append({**state["runs"][0], "id": 8, "conclusion": "failure"})
    elif failure == "origin":
        subprocess.run(
            [
                "git",
                "-C",
                str(artifacts["root"]),
                "remote",
                "set-url",
                "origin",
                "https://github.com/roctinam/matric-eval.git",
            ],
            check=True,
        )
    elif failure == "dirty":
        artifacts["notes"].write_text("mutated\n")
    elif failure == "manifest":
        (artifacts["artifact_root"] / "packages/python/package.whl").write_bytes(b"changed")
    else:
        with tarfile.open(artifacts["bundle"], "w:gz"):
            pass
    with pytest.raises(release.Refused):
        release.publish(client, **artifacts)
    assert not state["events"]


def test_paginated_ci_and_latest_pending_attempt_do_not_accept_old_success(forge, artifacts):
    client, state = forge
    good = state["runs"][0]
    state["runs"] = [
        {**good, "id": 1, "head_sha": "f" * 40},
        {**good, "id": 2, "head_sha": "e" * 40},
        good,
    ]
    assert release.verify(client, TAG, artifacts["commit"], artifacts["root"])["ci_run_id"] == 7
    state["runs"].insert(0, {**good, "id": 9, "status": "in_progress", "conclusion": "success"})
    with pytest.raises(release.Refused, match="unavailable"):
        release.verify(client, TAG, artifacts["commit"], artifacts["root"])


def test_source_only_verification_does_not_require_a_tag(forge, artifacts):
    client, state = forge
    state["commit"] = "f" * 40
    assert release.verify(client, None, artifacts["commit"], artifacts["root"])["tag"] is None


@pytest.mark.parametrize(
    "tag",
    [
        "v0.4.1",
        "v2026.09.0",
        "v2026.13.0",
        "v2026.9.01",
        "v2026.9.0-rc1",
        "2026.9.0",
        "v2026.9.0/../../main",
    ],
)
def test_noncanonical_tags_refused(tag):
    with pytest.raises(release.Refused):
        release.version_for(tag, "a" * 40)


def test_source_not_ancestor_of_main_is_refused_with_real_git(forge, artifacts):
    client, state = forge
    root = artifacts["root"]
    tree = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD^{tree}"], text=True
    ).strip()
    other = subprocess.check_output(
        ["git", "-C", str(root), "commit-tree", tree, "-m", "unrelated main history"],
        text=True,
    ).strip()
    subprocess.run(
        ["git", "-C", str(root), "update-ref", "refs/remotes/origin/main", other],
        check=True,
    )
    with pytest.raises(release.Refused, match="ancestry"):
        release.verify(client, TAG, artifacts["commit"], root)
    assert not state["events"]


def test_noncanonical_asset_url_refused_before_credential_request(forge, artifacts):
    client, state = forge
    release.publish(client, **artifacts)
    item, _ = next(iter(state["assets"].values()))
    item["browser_download_url"] = "https://example.invalid/attachment"
    before = list(state["events"])
    with pytest.raises(release.Refused, match="noncanonical"):
        release.publish(client, **artifacts)
    assert state["events"] == before


@pytest.mark.parametrize("wait", [-1, float("nan"), float("inf"), 1801])
def test_wait_is_bounded(forge, artifacts, wait):
    client, _ = forge
    with pytest.raises(release.Refused, match="finite"):
        release.verify(client, TAG, artifacts["commit"], artifacts["root"], wait)


@pytest.mark.parametrize("evidence", ["license", "consumer", "matrix", "source", "missing"])
def test_rebound_manifest_cannot_bypass_evidence_contract(forge, artifacts, evidence):
    client, state = forge
    target = artifacts["artifact_root"]
    if evidence == "license":
        path = target / "evidence/dependency-licenses.json"
        value = json.loads(path.read_text())
        value["unaccepted"] = ["unknown dependency"]
        path.write_text(json.dumps(value))
    elif evidence in ("consumer", "matrix"):
        path = target / "evidence/clean-install-validation.json"
        value = json.loads(path.read_text())
        if evidence == "consumer":
            value["artifacts"][0]["sha256"] = "f" * 64
        else:
            value["python"].pop()
        path.write_text(json.dumps(value))
    elif evidence == "missing":
        (target / "evidence/python-vulnerabilities.json").unlink()
    files = {
        path.relative_to(target).as_posix(): path.read_bytes()
        for path in target.rglob("*")
        if path.is_file() and path.name not in ("SHA256SUMS", "release-manifest.json")
    }
    manifest = {
        "schema_version": 1,
        "version": VERSION,
        "source_commit": "f" * 40 if evidence == "source" else artifacts["commit"],
        "artifacts": [
            {"path": name, "sha256": release.digest(data), "size": len(data)}
            for name, data in files.items()
        ],
    }
    files["release-manifest.json"] = json.dumps(manifest).encode()
    files["SHA256SUMS"] = "".join(
        f"{release.digest(data)}  {name}\n" for name, data in files.items()
    ).encode()
    for name, data in files.items():
        (target / name).write_bytes(data)
    with tarfile.open(artifacts["bundle"], "w:gz") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    with pytest.raises(release.Refused):
        release.publish(client, **artifacts)
    assert state["events"] == []


@pytest.mark.parametrize("phase", ["draft", "publish"])
def test_lost_release_ack_is_idempotent_on_retry(forge, artifacts, phase):
    client, state = forge
    state["drop"] = phase
    with pytest.raises(release.Refused, match="transport"):
        release.publish(client, **artifacts)
    release.publish(client, **artifacts)
    assert state["events"].count("draft") == 1
    assert state["events"].count("publish") == 1
    assert state["events"].count("upload") == len(state["assets"])


def test_wait_observes_pending_ci_become_success(forge, artifacts, monkeypatch):
    client, state = forge
    state["runs"][0].update(status="in_progress", conclusion="")

    def finish(_):
        state["runs"][0].update(status="completed", conclusion="success")

    monkeypatch.setattr(release.time, "sleep", finish)
    result = release.verify(client, TAG, artifacts["commit"], artifacts["root"], wait_seconds=1)
    assert result["ci_run_id"] == 7


def test_git_auth_is_ephemeral_environment_not_argv_or_saved_config(tmp_path, monkeypatch):
    from types import SimpleNamespace

    captured = {}
    secret = "fixture-private-token"
    monkeypatch.setenv("RELEASE_TOKEN", secret)

    def invoke(command, **kwargs):
        captured.update(command=command, **kwargs)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(release.subprocess, "run", invoke)
    release.git(tmp_path, "fetch", "origin")
    assert secret not in repr(captured["command"])
    assert "config" not in captured["command"]
    assert captured["env"]["GIT_CONFIG_KEY_0"] == "http.https://git.integrolabs.net/.extraheader"
    assert captured["env"]["GIT_CONFIG_VALUE_0"].startswith("Authorization: Basic ")
    assert captured["env"]["GIT_CONFIG_KEY_1"] == "http.followRedirects"
    assert captured["env"]["GIT_CONFIG_VALUE_1"] == "false"
