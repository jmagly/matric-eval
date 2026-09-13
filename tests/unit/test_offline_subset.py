"""The offline subset materializer must keep requests and scoring records joined.

The scorer requires identical ordered request IDs between a model's results and its
scoring records, and the batch runner requires request blocks in protocol order. A
hand-built subset can silently violate either; these tests pin the helper that
produces both files from one allocation list.
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROTOCOL = REPO / "studies" / "qwen38-obliteration-2026-09" / "protocol.yaml"
SCRIPT = REPO / "scripts" / "select_qwen38_offline_subset.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("select_subset", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_pair(directory: Path, allocation: str, ids: list[str]) -> None:
    with (directory / f"{allocation}-requests.jsonl").open("w") as fh:
        for sample in ids:
            fh.write(
                json.dumps(
                    {
                        "request_id": f"{allocation}:{sample}:turn-1",
                        "allocation_id": allocation,
                        "sample_id": sample,
                        "messages": [{"role": "user", "content": f"prompt {sample}"}],
                    }
                )
                + "\n"
            )
    with (directory / f"{allocation}-scoring.jsonl").open("w") as fh:
        for sample in ids:
            fh.write(
                json.dumps(
                    {
                        "request_id": f"{allocation}:{sample}:turn-1",
                        "allocation_id": allocation,
                        "sample_id": sample,
                        "metadata": {},
                    }
                )
                + "\n"
            )


@pytest.fixture
def inputs(tmp_path: Path) -> Path:
    _write_pair(tmp_path, "xstest-safe", ["xstest-1", "xstest-2"])
    _write_pair(tmp_path, "xstest-unsafe", ["xstest-9"])
    _write_pair(tmp_path, "ifeval", ["1000", "1001", "1002"])
    _write_pair(tmp_path, "mmlu-pro", ["10", "11"])
    return tmp_path


def test_subset_follows_protocol_order_regardless_of_request_order(
    inputs: Path, tmp_path: Path
) -> None:
    module = _load_module()
    receipt = module.select_subset(
        protocol_path=PROTOCOL,
        input_dir=inputs,
        allocation_ids=["mmlu-pro", "xstest-safe", "ifeval"],  # deliberately scrambled
        output_prefix=tmp_path / "subset",
    )
    assert receipt["allocations"] == ["xstest-safe", "ifeval", "mmlu-pro"]
    assert receipt["request_count"] == 7
    assert receipt["requests_per_allocation"] == {"xstest-safe": 2, "ifeval": 3, "mmlu-pro": 2}

    requests = [
        json.loads(line) for line in (tmp_path / "subset-requests.jsonl").read_text().splitlines()
    ]
    scoring = [
        json.loads(line) for line in (tmp_path / "subset-scoring.jsonl").read_text().splitlines()
    ]
    assert [r["request_id"] for r in requests] == [r["request_id"] for r in scoring]
    assert [r["allocation_id"] for r in requests] == (
        ["xstest-safe"] * 2 + ["ifeval"] * 3 + ["mmlu-pro"] * 2
    )


def test_receipt_carries_the_protocol_digest(inputs: Path, tmp_path: Path) -> None:
    module = _load_module()
    receipt = module.select_subset(
        protocol_path=PROTOCOL,
        input_dir=inputs,
        allocation_ids=["ifeval"],
        output_prefix=tmp_path / "one",
    )
    assert receipt["study_id"] == "qwen38-obliteration-2026-09"
    assert len(receipt["protocol_sha256"]) == 64
    assert len(receipt["requests_sha256"]) == 64 and len(receipt["scoring_sha256"]) == 64


def test_rejects_unknown_allocation(inputs: Path, tmp_path: Path) -> None:
    module = _load_module()
    with pytest.raises(ValueError, match="unknown allocation"):
        module.select_subset(
            protocol_path=PROTOCOL,
            input_dir=inputs,
            allocation_ids=["ifeval", "nonsense"],
            output_prefix=tmp_path / "x",
        )


def test_rejects_agent_runner_allocation(inputs: Path, tmp_path: Path) -> None:
    """tau3-bench is official-agent-runner; the offline runner cannot execute it."""
    module = _load_module()
    with pytest.raises(ValueError, match="not offline-batch"):
        module.select_subset(
            protocol_path=PROTOCOL,
            input_dir=inputs,
            allocation_ids=["tau3-bench"],
            output_prefix=tmp_path / "x",
        )


def test_rejects_duplicate_allocations(inputs: Path, tmp_path: Path) -> None:
    module = _load_module()
    with pytest.raises(ValueError, match="duplicates"):
        module.select_subset(
            protocol_path=PROTOCOL,
            input_dir=inputs,
            allocation_ids=["ifeval", "ifeval"],
            output_prefix=tmp_path / "x",
        )


def test_rejects_mismatched_scoring_records(inputs: Path, tmp_path: Path) -> None:
    """A scoring file whose IDs drift from its requests file is exactly the silent failure."""
    module = _load_module()
    scoring = inputs / "ifeval-scoring.jsonl"
    rows = scoring.read_text().splitlines()
    scoring.write_text("\n".join(rows[:-1]) + "\n")  # drop one record
    with pytest.raises(ValueError, match="disagree on request IDs"):
        module.select_subset(
            protocol_path=PROTOCOL,
            input_dir=inputs,
            allocation_ids=["ifeval"],
            output_prefix=tmp_path / "x",
        )


def test_refuses_to_overwrite(inputs: Path, tmp_path: Path) -> None:
    module = _load_module()
    kwargs = dict(
        protocol_path=PROTOCOL,
        input_dir=inputs,
        allocation_ids=["ifeval"],
        output_prefix=tmp_path / "again",
    )
    module.select_subset(**kwargs)
    with pytest.raises(ValueError, match="refusing to overwrite"):
        module.select_subset(**kwargs)
