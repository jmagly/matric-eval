#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ $# -ne 4 ]]; then
  echo "usage: $0 MODEL_RESULTS SCORING_RECORDS OUTPUT SCORES_RECEIPT" >&2
  exit 2
fi

RESULTS=$1
SCORING_RECORDS=$2
OUTPUT=$3
RECEIPT=$4
REPO=/srv/matric-eval/workspaces/matric-eval
PROTOCOL=$REPO/studies/qwen38-obliteration-2026-09/protocol.yaml
IMAGE='vllm/vllm-openai@sha256:770fe65b2c73ee74a5c42165cf3433de4048cc2cd9c57a937ca4e35aba5aa87b'
DOCKER_HOST='unix:///run/matric-eval-docker.sock'

if [[ "$(hostname)" != "basilisk" ]]; then
  echo "this scorer must run on the A100 host basilisk" >&2
  exit 1
fi

for path in "$RESULTS" "$SCORING_RECORDS" "$PROTOCOL"; do
  [[ -f "$path" ]] || { echo "required file is missing: $path" >&2; exit 1; }
done
[[ ! -e "$OUTPUT" ]] || { echo "refusing to overwrite: $OUTPUT" >&2; exit 1; }
[[ ! -e "$RECEIPT" ]] || { echo "refusing to overwrite: $RECEIPT" >&2; exit 1; }

install -d -m 0750 "$(dirname "$OUTPUT")"
sudo docker --host "$DOCKER_HOST" run --rm \
  --network none \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 256 \
  --memory 8g \
  --cpus 8 \
  --user "$(id -u):$(id -g)" \
  --workdir /workspace \
  --env PYTHONPATH=/workspace/src \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=2g \
  --mount "type=bind,src=$REPO,dst=/workspace,readonly" \
  --mount "type=bind,src=$(dirname "$OUTPUT"),dst=/results" \
  --mount "type=bind,src=$RESULTS,dst=/inputs/results.jsonl,readonly" \
  --mount "type=bind,src=$SCORING_RECORDS,dst=/inputs/scoring.jsonl,readonly" \
  --entrypoint python3 \
  "$IMAGE" \
  -m matric_eval.studies.scoring_cli \
  /workspace/studies/qwen38-obliteration-2026-09/protocol.yaml \
  /inputs/results.jsonl \
  /inputs/scoring.jsonl \
  --output "/results/$(basename "$OUTPUT")" > "$RECEIPT"

chmod 0600 "$OUTPUT" "$RECEIPT"
