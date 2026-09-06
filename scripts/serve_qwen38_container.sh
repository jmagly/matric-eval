#!/usr/bin/env bash
# Serve one qualified Qwen3.8 study model to localhost for official agent runners.

set -euo pipefail

study_image="vllm/vllm-openai@sha256:770fe65b2c73ee74a5c42165cf3433de4048cc2cd9c57a937ca4e35aba5aa87b"
study_repo="/srv/matric-eval/workspaces/matric-eval"
study_root="/srv/matric-eval/results/qwen38-obliteration-2026-09"
study_protocol="studies/qwen38-obliteration-2026-09/protocol.yaml"
study_docker_host="unix:///run/matric-eval-docker.sock"
study_broker_socket="/run/ollama-unify/gpu-negotiator.sock"

gpu_uuid=""
owner=""
model_id=""
model_path=""
qualification=""
lease_receipt=""
server_receipt=""
ready_base=""
container_name=""
port="18083"

while (( $# )); do
  case "$1" in
    --gpu) gpu_uuid="${2:-}"; shift 2 ;;
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

for required in gpu_uuid owner model_id model_path qualification lease_receipt server_receipt ready_base container_name; do
  if [[ -z "${!required}" ]]; then
    printf 'missing required option for %s\n' "$required" >&2
    exit 2
  fi
done

if [[ "$(hostname)" != "basilisk" ]]; then
  printf 'this runner requires host basilisk\n' >&2
  exit 1
fi
if [[ "$gpu_uuid" != GPU-* ]]; then
  printf 'GPU must be specified by its exact UUID\n' >&2
  exit 2
fi
if [[ ! "$port" =~ ^[0-9]+$ ]] || (( port < 1024 || port > 65535 )); then
  printf 'port must be an integer between 1024 and 65535\n' >&2
  exit 2
fi
if [[ ! "$container_name" =~ ^[A-Za-z0-9_.-]+$ ]]; then
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
if [[ "$ready_base" != "${study_root}/run-control/"* ]]; then
  printf 'ready-base must be inside the study run-control directory\n' >&2
  exit 2
fi
if [[ -n "$(git -C "$study_repo" status --porcelain)" ]]; then
  printf 'study checkout must be clean before execution\n' >&2
  exit 1
fi

actual_image_id="$(
  sudo docker --host "$study_docker_host" image inspect "$study_image" --format '{{.Id}}'
)"
if [[ "$actual_image_id" != "${study_image#*@}" ]]; then
  printf 'pinned runtime image is unavailable or has the wrong identity\n' >&2
  exit 1
fi

sudo docker gpu discover >/dev/null
ready_command="test -s \"${ready_base}.\${OLLAMA_UNIFY_GPU_LEASE}.ready\""
code_revision="$(git -C "$study_repo" rev-parse HEAD)"
evidence_uid="$(id -u)"
evidence_gid="$(id -g)"

sudo docker gpu run \
  --owner "$owner" \
  --vram-mib 75000 \
  --ttl 300 \
  --gpu "$gpu_uuid" \
  --ready-timeout 900 \
  --ready-command "$ready_command" \
  -- \
  /usr/bin/docker --host "$study_docker_host" run --rm \
    --name "$container_name" \
    --network host \
    --hostname basilisk \
    --read-only \
    --runtime nvidia \
    --gpus "device=${gpu_uuid}" \
    --ipc host \
    --ulimit memlock=-1 \
    --ulimit stack=67108864 \
    --tmpfs /tmp:rw,nosuid,nodev,exec,size=8g \
    --tmpfs /root/.cache:rw,nosuid,nodev,exec,size=32g \
    --tmpfs /root/.triton:rw,nosuid,nodev,exec,size=8g \
    --mount type=bind,src="$study_repo",dst=/workspace,readonly \
    --mount type=bind,src=/srv/obliteratus/matric-eval,dst=/srv/obliteratus/matric-eval,readonly \
    --mount type=bind,src=/srv/matric-eval/results,dst=/srv/matric-eval/results \
    --mount type=bind,src="$study_broker_socket",dst="$study_broker_socket" \
    --workdir /workspace \
    --env PYTHONPATH=/workspace/src \
    --env PYTHONDONTWRITEBYTECODE=1 \
    --env HF_HUB_OFFLINE=1 \
    --env TRANSFORMERS_OFFLINE=1 \
    --env VLLM_NO_USAGE_STATS=1 \
    --env VLLM_ENABLE_V1_MULTIPROCESSING=0 \
    --env OLLAMA_UNIFY_GPU_LEASE \
    --env CUDA_VISIBLE_DEVICES \
    --env MATRIC_EVAL_RUNTIME_IMAGE="$study_image" \
    --env MATRIC_EVAL_CODE_REVISION="$code_revision" \
    --env MATRIC_EVAL_EVIDENCE_UID="$evidence_uid" \
    --env MATRIC_EVAL_EVIDENCE_GID="$evidence_gid" \
    --env MATRIC_EVAL_GPU_BROKER_SOCKET="$study_broker_socket" \
    --env MATRIC_EVAL_MODEL_READY_BASE="$ready_base" \
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
