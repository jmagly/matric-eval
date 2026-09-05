"""Pinned command contracts for modern external agentic benchmarks."""

import pytest

from matric_eval.tasks.bfcl_v4 import (
    BFCL_AGENTIC_TASKS,
    BFCL_PACKAGE,
    BFCL_PACKAGE_VERSION,
    BFCL_REVISION,
    bfcl_v4_agentic,
    build_bfcl_evaluate_command,
    build_bfcl_generate_command,
)
from matric_eval.tasks.swebench_live import (
    SWEBENCH_LIVE_DATASET,
    SWEBENCH_LIVE_DATASET_REVISION,
    build_swebench_live_evaluate_command,
    swebench_live_multilang,
)
from matric_eval.tasks.tau2 import TAU2_REVISION, build_tau2_command, tau2


def test_bfcl_v4_uses_official_agentic_protocol() -> None:
    command = build_bfcl_generate_command(model="qwen-e03", endpoint=True)
    assert command[:2] == ["bfcl", "generate"]
    assert command[command.index("--test-category") + 1 : command.index("--num-threads")] == [
        "web_search",
        "memory",
    ]
    assert "--skip-server-setup" in command
    assert build_bfcl_evaluate_command(model="qwen-e03")[:2] == ["bfcl", "evaluate"]
    metadata = bfcl_v4_agentic._benchmark_metadata
    assert metadata.total_samples == BFCL_AGENTIC_TASKS == 665
    assert metadata.dataset_revision == BFCL_REVISION
    assert metadata.evaluator_revision == BFCL_PACKAGE_VERSION
    assert BFCL_PACKAGE == "bfcl-eval==2026.3.23"


def test_bfcl_local_backend_keeps_gpu_controls() -> None:
    command = build_bfcl_generate_command(
        model="qwen-e03",
        endpoint=False,
        local_model_path="/models/e03",
        num_gpus=2,
        gpu_memory_utilization=0.8,
    )
    assert "--skip-server-setup" not in command
    assert command[command.index("--num-gpus") + 1] == "2"
    assert command[command.index("--local-model-path") + 1] == "/models/e03"


def test_tau2_command_pins_base_split_and_seed() -> None:
    command = build_tau2_command(
        domain="retail",
        agent_model="qwen-e03",
        user_model="user-simulator",
        task_ids=("1", "4"),
        trials=4,
    )
    assert command[command.index("--task-split-name") + 1] == "base"
    assert command[command.index("--seed") + 1] == "300"
    assert command[command.index("--task-ids") + 1 :] == ["1", "4"]
    assert tau2._benchmark_metadata.evaluator_revision == TAU2_REVISION


def test_tau2_rejects_ambiguous_subset() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        build_tau2_command(
            domain="retail",
            agent_model="agent",
            user_model="user",
            num_tasks=5,
            task_ids=("1",),
        )


def test_swebench_live_uses_frozen_dataset_and_official_evaluator() -> None:
    command = build_swebench_live_evaluate_command(
        patch_dir="predictions",
        output_dir="results",
        instance_ids=("repo__issue-1",),
    )
    assert command[:3] == ["python", "-m", "evaluation.evaluation"]
    assert command[command.index("--dataset") + 1] == SWEBENCH_LIVE_DATASET
    assert command[command.index("--instance_ids") + 1] == "repo__issue-1"
    metadata = swebench_live_multilang._benchmark_metadata
    assert metadata.dataset_revision == SWEBENCH_LIVE_DATASET_REVISION
    assert metadata.release_policy.value == "continuous"
