# Evaluation matrix examples

`qwen38-e03-agentic.yaml` is the initial matched cohort for the untouched
Qwen3.8-27B checkpoint, the qualified E03 BF16 intervention, and its separately
qualified BitsAndBytes NF4 deployment artifact.

The file is a provenance-bearing study specification, not a one-command launcher
for every listed benchmark. `tool_calling` uses the matric-eval execution path;
BFCL V4 and tau3-bench require their pinned official external runners. Translate
the same qualified model/runtime fields into each runner's configuration and
retain the runner output beside the validated matrix.

The E03 entries intentionally use `reconstructed-with-gaps`. Their model cards
and retained A100 artifacts identify the relevant component commits and exact
checkpoints, but the original run did not retain all fields required by the new
prospective standard. The new sampler values define this evaluation study; they
do not backfill the historical intervention run.
