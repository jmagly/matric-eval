#!/usr/bin/env bash
# Serve one qualified Qwen3.8 study model to localhost for official agent runners.

set -euo pipefail

study_image="vllm/vllm-openai@sha256:770fe65b2c73ee74a5c42165cf3433de4048cc2cd9c57a937ca4e35aba5aa87b"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
study_repo="$(cd -- "${script_dir}/.." && pwd -P)"
study_root="/srv/matric-eval/results/qwen38-obliteration-2026-09"
study_protocol="studies/qwen38-obliteration-2026-09/protocol.yaml"
study_docker_host="unix:///run/matric-eval-docker.sock"
study_broker_socket="/run/ollama-unify/gpu-negotiator.sock"

gpu_uuids=()
parallelism_profile=""
owner=""
model_id=""
model_path=""
qualification=""
lease_receipt=""
server_receipt=""
ready_base=""
container_name=""
port="18083"
run_id=""
attempt_id=""
resource_directory=""
preflight_plan=""
storage_plan=""
broker_acquire_timeout="10"

while (( $# )); do
  case "$1" in
    --broker-acquire-timeout) broker_acquire_timeout="${2:-}"; shift 2 ;;
    --storage-plan) storage_plan="${2:-}"; shift 2 ;;
    --preflight-plan) preflight_plan="${2:-}"; shift 2 ;;
    --run-id) run_id="${2:-}"; shift 2 ;;
    --attempt-id) attempt_id="${2:-}"; shift 2 ;;
    --resource-directory) resource_directory="${2:-}"; shift 2 ;;
    --gpu) gpu_uuids+=("${2:-}"); shift 2 ;;
    --parallelism-profile) parallelism_profile="${2:-}"; shift 2 ;;
    --owner) owner="${2:-}"; shift 2 ;;
    --model-id) model_id="${2:-}"; shift 2 ;;
    --model-path) model_path="${2:-}"; shift 2 ;;
    --qualification) qualification="${2:-}"; shift 2 ;;
    --lease-receipt) lease_receipt="${2:-}"; shift 2 ;;
    --server-receipt) server_receipt="${2:-}"; shift 2 ;;
    --ready-base) ready_base="${2:-}"; shift 2 ;;
    --container-name) container_name="${2:-}"; shift 2 ;;
    --port) port="${2:-}"; shift 2 ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

for required in storage_plan preflight_plan run_id attempt_id resource_directory owner model_id model_path qualification lease_receipt server_receipt; do
  if [[ -z "${!required}" ]]; then
    printf 'missing required option for %s\n' "$required" >&2
    exit 2
  fi
done
if (( ${#gpu_uuids[@]} == 0 )); then
  printf 'missing required option for gpu\n' >&2
  exit 2
fi

if [[ "$(hostname)" != "basilisk" ]]; then
  printf 'this runner requires host basilisk\n' >&2
  exit 1
fi
if [[ ! "$port" =~ ^[0-9]+$ ]] || (( port < 1024 || port > 65535 )); then
  printf 'port must be an integer between 1024 and 65535\n' >&2
  exit 2
fi
if [[ -n "$container_name" && ! "$container_name" =~ ^[A-Za-z0-9_.-]+$ ]]; then
  printf 'container name contains unsafe characters\n' >&2
  exit 2
fi
for input in "$model_path" "$qualification" "${study_root}/chat_template.jinja"; do
  if [[ ! -e "$input" ]]; then
    printf 'required input does not exist: %s\n' "$input" >&2
    exit 1
  fi
done
if [[ "$model_path" != /srv/obliteratus/matric-eval/* ]]; then
  printf 'model path must remain inside the qualified model filesystem\n' >&2
  exit 2
fi
if [[ "$qualification" != "${study_root}/"* ]]; then
  printf 'qualification must remain inside the private study result root\n' >&2
  exit 2
fi
for private_output in "$lease_receipt" "$server_receipt"; do
  if [[ "$private_output" != "${study_root}/"* ]]; then
    printf 'output must remain inside the private study result root: %s\n' "$private_output" >&2
    exit 2
  fi
  if [[ -e "$private_output" ]]; then
    printf 'refusing to overwrite study evidence: %s\n' "$private_output" >&2
    exit 1
  fi
done
if [[ -n "$ready_base" && "$ready_base" != "${study_root}/run-control/"* ]]; then
  printf 'ready-base must be inside the study run-control directory\n' >&2
  exit 2
fi
if [[ "$resource_directory" != "${study_root}/run-control/"* ]]; then
  printf 'resource-directory must remain inside study run-control\n' >&2
  exit 2
fi
if [[ -n "$(git -C "$study_repo" status --porcelain)" ]]; then
  printf 'study checkout must be clean before execution\n' >&2
  exit 1
fi

lifecycle_python="${MATRIC_LIFECYCLE_PYTHON:-$study_repo/.venv/bin/python}"
contract_arguments=(--protocol "$study_repo/$study_protocol" --format lines)
if [[ -n "$parallelism_profile" ]]; then
  contract_arguments+=(--parallelism-profile "$parallelism_profile")
fi
for gpu_uuid in "${gpu_uuids[@]}"; do
  contract_arguments+=(--gpu "$gpu_uuid")
done
gpu_contract="$(PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$study_repo/src" "$lifecycle_python" -m matric_eval.studies.wrapper "${contract_arguments[@]}")"
mapfile -t gpu_fields <<<"$gpu_contract"
if (( ${#gpu_fields[@]} != 5 )); then
  printf 'GPU wrapper contract returned malformed output\n' >&2
  exit 1
fi
gpu_selector="${gpu_fields[0]}"
gpu_memory_mib="${gpu_fields[1]}"
gpu_topology_policy="${gpu_fields[2]}"
gpu_allocation_json="${gpu_fields[4]}"
lifecycle_gpu_arguments=(--memory-mib "$gpu_memory_mib")
if [[ "$gpu_topology_policy" != "-" ]]; then
  lifecycle_gpu_arguments+=(--topology-policy "$gpu_topology_policy")
fi
for gpu_uuid in "${gpu_uuids[@]}"; do
  lifecycle_gpu_arguments+=(--gpu "$gpu_uuid")
done

actual_image_id="$(
  sudo docker --host "$study_docker_host" image inspect "$study_image" --format '{{.Id}}'
)"
if [[ "$actual_image_id" != "${study_image#*@}" ]]; then
  printf 'pinned runtime image is unavailable or has the wrong identity\n' >&2
  exit 1
fi

mapfile -t budget_paths < <(python3 -c 'import json,sys; data=json.load(open(sys.argv[1])); paths={a["kind"]:a["path"] for a in data["allocations"]}; [print(paths[k]) for k in ("temporary","download_cache","scratch","evidence","logs")]' "$storage_plan")
if (( ${#budget_paths[@]} != 5 )); then
  printf 'storage plan must declare all runtime paths\n' >&2
  exit 2
fi
for output in "$lease_receipt" "$server_receipt" "${MATRIC_RUN_STATUS_DIR:-${budget_paths[3]}/unused}"; do
  if [[ "$output" != "${budget_paths[3]}/"* ]]; then
    printf 'output and inherited status must be beneath bounded evidence storage\n' >&2
    exit 2
  fi
done

code_revision="$(git -C "$study_repo" rev-parse HEAD)"
evidence_uid="$(id -u)"
evidence_gid="$(id -g)"

sudo env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$study_repo/src" MATRIC_RUN_STATUS_DIR="${MATRIC_RUN_STATUS_DIR:-}" "$lifecycle_python" -m matric_eval.studies.resource_lifecycle run \
  --directory "$resource_directory" --preflight-plan "$preflight_plan" --storage-plan "$storage_plan" \
  --run-id "$run_id" --attempt-id "$attempt_id" \
  --owner "$owner" "${lifecycle_gpu_arguments[@]}" \
  --broker-acquire-timeout "$broker_acquire_timeout" --ready-timeout 900 -- \
  /usr/bin/docker --host "$study_docker_host" run \
    --name '{container}' \
    --label 'matric.resource={resource_id}' \
    --network host \
    --hostname basilisk \
    --read-only \
    --pull never \
    --log-driver none \
    --runtime nvidia \
    --gpus "$gpu_selector" \
    --ipc private \
    --ulimit memlock=-1 \
    --ulimit stack=67108864 \
    --mount type=bind,src="${budget_paths[0]}",dst=/tmp \
    --mount type=bind,src="${budget_paths[1]}",dst=/root/.cache \
    --mount type=bind,src="${budget_paths[2]}",dst=/root/.triton \
    --mount type=bind,src="${budget_paths[2]}",dst=/dev/shm \
    --mount type=bind,src="${budget_paths[3]}",dst="${budget_paths[3]}" \
    --mount type=bind,src="$study_repo",dst=/workspace,readonly \
    --mount type=bind,src=/srv/obliteratus/matric-eval,dst=/srv/obliteratus/matric-eval,readonly \
    --mount type=bind,src=/srv/matric-eval/results,dst=/srv/matric-eval/results,readonly \
    --mount type=bind,src="$study_broker_socket",dst="$study_broker_socket" \
    --workdir /workspace \
    --env PYTHONPATH=/workspace/src:/workspace/runtime/vllm-plugin \
    --env PYTHONDONTWRITEBYTECODE=1 \
    --env HF_HUB_OFFLINE=1 \
    --env TRANSFORMERS_OFFLINE=1 \
    --env VLLM_NO_USAGE_STATS=1 \
    --env VLLM_PLUGINS=matric_eval_architecture_registry \
    --env VLLM_ENABLE_V1_MULTIPROCESSING=0 \
    --env OLLAMA_UNIFY_GPU_LEASE \
    --env CUDA_VISIBLE_DEVICES \
    --env MATRIC_EVAL_GPU_ALLOCATION_JSON="$gpu_allocation_json" \
    --env MATRIC_EVAL_RUNTIME_IMAGE="$study_image" \
    --env MATRIC_EVAL_CODE_REVISION="$code_revision" \
    --env MATRIC_RUN_STATUS_DIR="${MATRIC_RUN_STATUS_DIR:-}" \
    --env MATRIC_EVAL_EVIDENCE_UID="$evidence_uid" \
    --env MATRIC_EVAL_EVIDENCE_GID="$evidence_gid" \
    --env MATRIC_EVAL_GPU_BROKER_SOCKET="$study_broker_socket" \
    --env 'MATRIC_EVAL_MODEL_READY_BASE={ready_base}' \
    --entrypoint /usr/bin/python3 \
    "$study_image" \
    -m matric_eval.studies.server_cli serve \
    "$study_protocol" \
    --model-id "$model_id" \
    --model-path "$model_path" \
    --qualification "$qualification" \
    --chat-template "${study_root}/chat_template.jinja" \
    --lease-receipt "$lease_receipt" \
    --server-receipt "$server_receipt" \
    --host 127.0.0.1 \
    --port "$port" \
    --ready-timeout 900
