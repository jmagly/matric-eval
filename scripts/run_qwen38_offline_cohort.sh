#!/usr/bin/env bash
# Run several qualified Qwen3.8 study models concurrently, one per A100, through
# run_qwen38_offline_container.sh. Each model gets its own run-control directory
# under the study root and its own lease; the launcher staggers only long enough
# for each model to claim its lease and read its (freshly warmed) checkpoint before
# the next one competes for host memory. Generation then overlaps across all cards.
#
# Usage:
#   run_qwen38_offline_cohort.sh --tag TAG --manifest FILE --requests FILE \
#     --model LABEL:MODEL_ID:SNAPSHOT_DIR:QUALIFICATION:GPU_UUID [--model ...] \
#     [--stagger SECONDS] [--ready-timeout SECONDS]
#
# Writes ${study_root}/run-control/${TAG}-${LABEL}/{observations.jsonl,lease.private.json}
# per model, per-model runner logs under ${study_root}/cohort-${TAG}/, and a cohort
# receipt there once every model has exited.

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
study_repo="$(cd -- "${script_dir}/.." && pwd -P)"
study_root="/srv/matric-eval/results/qwen38-obliteration-2026-09"

tag=""
manifest=""
requests=""
stagger=25
ready_timeout=3600
models=()

while (( $# )); do
  case "$1" in
    --tag) tag="${2:-}"; shift 2 ;;
    --manifest) manifest="${2:-}"; shift 2 ;;
    --requests) requests="${2:-}"; shift 2 ;;
    --model) models+=("${2:-}"); shift 2 ;;
    --stagger) stagger="${2:-}"; shift 2 ;;
    --ready-timeout) ready_timeout="${2:-}"; shift 2 ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

for required in tag manifest requests; do
  if [[ -z "${!required}" ]]; then
    printf 'missing required option for %s\n' "$required" >&2
    exit 2
  fi
done
if (( ${#models[@]} == 0 )); then
  printf 'at least one --model is required\n' >&2
  exit 2
fi
if [[ ! "$tag" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  printf 'tag must be a simple identifier\n' >&2
  exit 2
fi
if [[ ! "$stagger" =~ ^[0-9]+$ ]]; then
  printf 'stagger must be an integer number of seconds\n' >&2
  exit 2
fi
for input in "$manifest" "$requests"; do
  [[ -e "$input" ]] || { printf 'required input does not exist: %s\n' "$input" >&2; exit 1; }
done

log_dir="${study_root}/cohort-${tag}"
if [[ -e "$log_dir" ]]; then
  printf 'refusing to reuse cohort directory: %s\n' "$log_dir" >&2
  exit 1
fi
install -d -m 0750 "$log_dir"

declare -a labels=() pids=() gpus=()
seen_gpus=""
for spec in "${models[@]}"; do
  IFS=":" read -r label model_id snapshot qualification gpu <<<"$spec"
  for field in label model_id snapshot qualification gpu; do
    if [[ -z "${!field}" ]]; then
      printf 'malformed --model spec (need LABEL:MODEL_ID:SNAPSHOT:QUALIFICATION:GPU): %s\n' "$spec" >&2
      exit 2
    fi
  done
  if [[ " $seen_gpus " == *" $gpu "* ]]; then
    printf 'two models target the same GPU %s; one card per model\n' "$gpu" >&2
    exit 2
  fi
  seen_gpus="$seen_gpus $gpu"

  run_dir="${study_root}/run-control/${tag}-${label}"
  if [[ -e "$run_dir" ]]; then
    printf 'refusing to reuse run-control directory: %s\n' "$run_dir" >&2
    exit 1
  fi
  install -d -m 0750 "$run_dir"

  # Each model runs detached so a lost controlling terminal cannot kill the cohort.
  setsid nohup bash "$script_dir/run_qwen38_offline_container.sh" \
    --gpu "$gpu" \
    --manifest "$manifest" \
    --requests "$requests" \
    --owner "${tag}-${label}" \
    --model-id "$model_id" \
    --model-path "$snapshot" \
    --qualification "$qualification" \
    --lease-receipt "${run_dir}/lease.private.json" \
    --output "${run_dir}/observations.jsonl" \
    --ready-base "${run_dir}/ready" \
    --ready-timeout "$ready_timeout" \
    > "${log_dir}/${label}-runner.log" 2>&1 < /dev/null &
  pids+=("$!"); labels+=("$label"); gpus+=("$gpu")
  printf 'launched %s (%s) on %s\n' "$label" "$model_id" "$gpu"
  if (( ${#models[@]} > ${#pids[@]} )); then
    sleep "$stagger"
  fi
done

status=0
declare -a exit_codes=()
for i in "${!pids[@]}"; do
  if wait "${pids[$i]}"; then
    exit_codes+=(0)
  else
    code=$?
    exit_codes+=("$code"); status=1
    printf '%s exited with %s (see %s)\n' "${labels[$i]}" "$code" "${log_dir}/${labels[$i]}-runner.log" >&2
  fi
done

receipt="${log_dir}/cohort-receipt.json"
{
  printf '{"tag":"%s","manifest":"%s","requests":"%s","stagger_seconds":%s,"ready_timeout_seconds":%s,"models":[' \
    "$tag" "$manifest" "$requests" "$stagger" "$ready_timeout"
  for i in "${!labels[@]}"; do
    run_dir="${study_root}/run-control/${tag}-${labels[$i]}"
    lines=0
    [[ -s "${run_dir}/observations.jsonl" ]] && lines="$(wc -l < "${run_dir}/observations.jsonl")"
    (( i > 0 )) && printf ','
    printf '{"label":"%s","gpu":"%s","exit_code":%s,"observations":%s,"run_control":"%s"}' \
      "${labels[$i]}" "${gpus[$i]}" "${exit_codes[$i]}" "$lines" "$run_dir"
  done
  printf ']}\n'
} > "$receipt"
chmod 0600 "$receipt"
printf 'cohort receipt: %s\n' "$receipt"
exit "$status"
