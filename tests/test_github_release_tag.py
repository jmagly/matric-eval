"""Local tag administration through a qualified forge helper; no remote tags created."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


@pytest.fixture
def github_tag_checkout(tmp_path: Path):
    repo = tmp_path / "source"
    remote = tmp_path / "remote.git"
    git_binary = shutil.which("git")
    assert git_binary
    subprocess.run([git_binary, "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run([git_binary, "init", "-b", "main", str(repo)], check=True, capture_output=True)

    def git(*args: str) -> str:
        return subprocess.run(
            [git_binary, "-C", str(repo), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    for key, value in (
        ("user.name", "Fixture"),
        ("user.email", "fixture@example.invalid"),
        ("commit.gpgsign", "false"),
        ("tag.gpgsign", "false"),
    ):
        git("config", key, value)
    (repo / "scripts").mkdir()
    (repo / "scripts/release_contract.py").write_text(
        "import sys\nassert sys.argv[1:] == ['versions', '--expected', '2026.9.0']\n"
    )
    # API and ancestry behavior are covered by the real-HTTP helper tests.
    # This seam checks the wrapper forwards forge/token/source correctly.
    (repo / "scripts/publish_forge_release.py").write_text(
        "import json,os,subprocess,sys\n"
        "args=sys.argv[1:]\n"
        "assert args[0]=='verify-source'\n"
        "assert args[args.index('--forge')+1]=='github'\n"
        "assert os.environ['GITHUB_TOKEN']=='native-fixture-token'\n"
        "assert subprocess.check_output(['git','remote','get-url','origin'],text=True).strip()"
        "=='https://github.com/jmagly/matric-eval.git'\n"
        "assert args[args.index('--commit')+1]==subprocess.check_output"
        "(['git','rev-parse','HEAD'],text=True).strip()\n"
        "with open(os.environ['HELPER_CALLS'],'a') as stream: stream.write(json.dumps(args)+'\\n')\n"
    )
    notes = repo / "docs/releases/2026.9.0.md"
    notes.parent.mkdir(parents=True)
    notes.write_text("Prepared release\n")
    (repo / "CHANGELOG.md").write_text("## [2026.9.0]\n")
    git("add", ".")
    git("commit", "-qm", "fixture")
    git("remote", "add", "origin", "https://github.com/jmagly/matric-eval.git")
    git("update-ref", "refs/remotes/origin/main", git("rev-parse", "HEAD"))
    # Substitute only the remote tag inventory network call. Local Git commands
    # and the canonical origin value remain real, and any push is refused.
    commands = tmp_path / "bin"
    commands.mkdir()
    shim = commands / "git"
    shim.write_text(
        "#!/usr/bin/env python3\nimport os,subprocess,sys\n"
        "args=sys.argv[1:]\nassert 'push' not in args\n"
        "if args[:3]==['ls-remote','--tags','origin']: args[2]=os.environ['FIXTURE_REMOTE']\n"
        "sys.exit(subprocess.run([os.environ['REAL_GIT'],*args]).returncode)\n"
    )
    shim.chmod(0o755)
    calls = tmp_path / "helper-calls.jsonl"
    env = {
        **os.environ,
        "PATH": str(commands) + os.pathsep + os.environ["PATH"],
        "REAL_GIT": git_binary,
        "FIXTURE_REMOTE": str(remote),
        "HELPER_CALLS": str(calls),
        "GITHUB_TOKEN": "native-fixture-token",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    command = ["bash", str(ROOT / "tools/release/cut-tag.sh"), "2026.9.0"]

    def invoke(*args: str):
        return subprocess.run([*command, *args], cwd=repo, env=env, capture_output=True, text=True)

    return repo, remote, git, invoke, calls


@pytest.mark.parametrize(
    "options", [("--forge", "github", "--check"), ("--check", "--forge", "github")]
)
def test_github_check_forwards_forge_and_never_creates_tag(github_tag_checkout, options):
    _, remote, git, invoke, calls = github_tag_checkout
    result = invoke(*options)
    assert result.returncode == 0, result.stderr
    assert git("tag", "--list") == ""
    assert git("ls-remote", "--tags", str(remote)) == ""
    recorded = json.loads(calls.read_text().splitlines()[0])
    assert recorded[recorded.index("--forge") + 1] == "github"
    assert "native-fixture-token" not in calls.read_text()


def test_github_creates_only_local_annotated_tag_and_refuses_existing(github_tag_checkout):
    _, remote, git, invoke, _ = github_tag_checkout
    result = invoke("--forge", "github")
    assert result.returncode == 0, result.stderr
    assert git("cat-file", "-t", "v2026.9.0") == "tag"
    assert git("rev-parse", "v2026.9.0^{commit}") == git("rev-parse", "HEAD")
    assert "git push origin refs/tags/v2026.9.0" in result.stdout
    assert git("ls-remote", "--tags", str(remote)) == ""
    assert invoke("--forge", "github").returncode != 0


@pytest.mark.parametrize("failure", ["dirty", "ahead", "origin", "remote_tag"])
def test_github_tag_rejects_unready_source_and_used_remote_tag(github_tag_checkout, failure):
    repo, remote, git, invoke, _ = github_tag_checkout
    if failure == "dirty":
        (repo / "untracked").write_text("not reviewed")
    elif failure == "ahead":
        (repo / "CHANGELOG.md").write_text("## [2026.9.0]\nnew commit\n")
        git("add", ".")
        git("commit", "-qm", "not current origin main")
    elif failure == "origin":
        git("remote", "set-url", "origin", "https://github.com/attacker/matric-eval.git")
    else:
        # Seed only the local bare fixture, never a live remote.
        git("push", str(remote), "HEAD:refs/tags/v2026.9.0")
    assert invoke("--forge", "github").returncode != 0
    assert git("tag", "--list") == ""


@pytest.mark.parametrize(
    "options",
    [
        ("--forge",),
        ("--forge", "other"),
        ("--check", "--check"),
        ("--forge", "github", "--forge", "gitea"),
    ],
)
def test_tag_wrapper_rejects_invalid_options(github_tag_checkout, options):
    _, _, git, invoke, calls = github_tag_checkout
    assert invoke(*options).returncode == 2
    assert not calls.exists()
    assert git("tag", "--list") == ""
