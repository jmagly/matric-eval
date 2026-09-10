"""Tests that A100 wrappers attest the checkout from which they are invoked."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPERS = (
    ROOT / "scripts/run_qwen38_offline_container.sh",
    ROOT / "scripts/score_qwen38_offline_container.sh",
    ROOT / "scripts/serve_qwen38_container.sh",
)


def test_qwen38_wrappers_resolve_their_own_checkout() -> None:
    for wrapper in WRAPPERS:
        source = wrapper.read_text(encoding="utf-8")
        assert "${BASH_SOURCE[0]}" in source
        assert '"${script_dir}/.."' in source or '"${SCRIPT_DIR}/.."' in source
        assert "/srv/matric-eval/workspaces/matric-eval" not in source


def test_agentic_server_exposes_allowlisted_plugin_to_all_vllm_processes() -> None:
    source = (ROOT / "scripts/serve_qwen38_container.sh").read_text(encoding="utf-8")

    assert "PYTHONPATH=/workspace/src:/workspace/runtime/vllm-plugin" in source
    assert "VLLM_PLUGINS=matric_eval_architecture_registry" in source


def test_gpu_wrappers_preserve_repeated_uuid_arguments_and_exact_selector() -> None:
    for wrapper in WRAPPERS:
        if wrapper.name == "score_qwen38_offline_container.sh":
            continue
        source = wrapper.read_text(encoding="utf-8")
        assert "gpu_uuids=()" in source
        assert 'gpu_uuids+=("${2:-}")' in source
        assert 'contract_arguments+=(--gpu "$gpu_uuid")' in source
        assert '--gpus "$gpu_selector"' in source
        assert 'MATRIC_EVAL_GPU_ALLOCATION_JSON="$gpu_allocation_json"' in source


def test_qwen38_shell_wrappers_are_valid_bash() -> None:
    for wrapper in WRAPPERS:
        subprocess.run(["bash", "-n", str(wrapper)], check=True)
