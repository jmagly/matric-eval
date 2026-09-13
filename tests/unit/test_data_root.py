"""The benchmark corpora root must be redirectable and must not embed a home directory.

A loader that hardcodes an absolute path under one operator's home is not
portable, and on a host the project does not own it reads from a personal
directory rather than the study's data root. These tests pin both halves of the
fix: the override works, and no loader re-introduces a literal home path.
"""

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import matric_eval.config.settings as settings_module
from matric_eval.config import data_path, get_data_root

TASK_MODULES = (
    "arc",
    "ds1000",
    "gpqa",
    "gsm8k",
    "humaneval",
    "ifeval",
    "livecodebench",
    "locomo",
    "longmemeval",
    "mbpp",
    "memoryagentbench",
    "mmlu",
    "mtbench",
    "tool_calling",
)

HISTORICAL_DEFAULT = "/home/roctinam/data/evals"


@pytest.fixture(autouse=True)
def _reset_settings_singleton(monkeypatch: pytest.MonkeyPatch):
    """Settings are a process singleton, so the env is read once per process."""
    monkeypatch.setattr(settings_module, "_settings", None)
    yield
    monkeypatch.setattr(settings_module, "_settings", None)


def test_default_root_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unset variable keeps the historical path so deployments do not move."""
    monkeypatch.delenv("EVAL_DATA_ROOT", raising=False)
    assert get_data_root() == Path(HISTORICAL_DEFAULT)


def test_environment_overrides_the_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_DATA_ROOT", "/srv/matric-eval/datasets")
    assert get_data_root() == Path("/srv/matric-eval/datasets")
    assert data_path("ifeval", "input_data.jsonl") == (
        "/srv/matric-eval/datasets/ifeval/input_data.jsonl"
    )


def test_data_path_joins_beneath_the_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_DATA_ROOT", "/data")
    assert data_path() == "/data"
    assert data_path("mmlu", "data", "test") == "/data/mmlu/data/test"


def test_loader_constants_follow_the_override() -> None:
    """Every loader's path constant resolves beneath the redirected root.

    The constants are module-level, so the variable is read at import time. A
    subprocess is the faithful check: reloading in-process would re-run the
    benchmark registration decorators and collide on the existing registry.
    """
    program = textwrap.dedent(
        """
        import importlib, json
        from pathlib import Path

        names = %r
        found = {}
        for name in names:
            module = importlib.import_module("matric_eval.tasks." + name)
            for key, value in vars(module).items():
                if (
                    key.isupper()
                    and key.endswith(("_PATH", "_DIR"))
                    and isinstance(value, (str, Path))
                ):
                    found.setdefault(name, {})[key] = str(value)
        print(json.dumps(found))
        """
    ) % (TASK_MODULES,)
    environment = dict(os.environ, EVAL_DATA_ROOT="/tmp/matric-eval-root")
    completed = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        env=environment,
        check=True,
    )
    found = json.loads(completed.stdout)
    missing = [name for name in TASK_MODULES if not found.get(name)]
    assert not missing, f"no dataset path constant exposed by: {missing}"
    for name, constants in found.items():
        for key, value in constants.items():
            assert value.startswith("/tmp/matric-eval-root"), f"{name}.{key} = {value}"


def test_no_loader_embeds_a_home_directory() -> None:
    """Guard the regression directly: no literal home path outside the default."""
    source_root = Path(__file__).resolve().parents[2] / "src" / "matric_eval"
    home_literal = re.compile(r"[\"']/home/[A-Za-z0-9._-]+/")
    offenders = []
    for path in sorted(source_root.rglob("*.py")):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if "data_root:" in line or "default=" in line:
                continue  # the documented Settings default, deliberately retained
            if home_literal.search(line):
                offenders.append(f"{path.relative_to(source_root)}:{number}")
    assert not offenders, "hardcoded home paths: " + ", ".join(offenders)
