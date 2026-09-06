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
cd "$REPO"
uv run python -m matric_eval.studies.scoring_cli \
  "$PROTOCOL" \
  "$RESULTS" \
  "$SCORING_RECORDS" \
  --docker-code-sandbox \
  --output "$OUTPUT" > "$RECEIPT"

chmod 0600 "$OUTPUT" "$RECEIPT"
