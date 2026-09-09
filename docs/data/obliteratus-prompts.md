# OBLITERATUS prompt-source preparation

The OBLITERATUS source map is packaged as
`matric_eval.data/obliteratus_sources.json`. It records original projects separately
from distributions, pins immutable revisions and exact artifacts, and assigns every
imported row the shared partition role `unknown`. An import proves byte and lineage
identity; it does not prove that a model saw the data or that a locally withheld row
is an untouched final holdout.

List the complete manifest or inspect one source:

```bash
matric-eval datasets obliteratus-sources
matric-eval datasets obliteratus-sources advbench
```

`prepare-obliteratus` creates three new files without overwriting existing evidence:
lossless source-row evidence, canonical prompt views, and a receipt binding their
hashes, counts, transformation version, source revision, optional selection, and
limitations. It does not register a benchmark, select a scorer, run a model, or
execute source repository code. The built-in Python file is parsed with `ast` and
literal extraction only.

## Reproducible commands

The following commands fetch exact public artifacts into a content-addressed cache
when they are absent and prepare the complete source. Re-run with `--offline` to
require the already verified cache bytes and forbid network fallback.

```bash
matric-eval datasets prepare-obliteratus obliteratus-builtin \
  --cache /srv/matric-data/obliteratus/cache \
  --output-dir /srv/matric-data/obliteratus/obliteratus-builtin

matric-eval datasets prepare-obliteratus advbench \
  --cache /srv/matric-data/obliteratus/cache \
  --legacy-control-snapshot /srv/matric-data/obliteratus/cache/blobs/873726b92136d756529ab98e73eb2d1009b6ef5a86147bfc8f753f6bb1c01cfb \
  --output-dir /srv/matric-data/obliteratus/advbench

matric-eval datasets prepare-obliteratus harmbench \
  --cache /srv/matric-data/obliteratus/cache \
  --legacy-control-snapshot /srv/matric-data/obliteratus/cache/blobs/873726b92136d756529ab98e73eb2d1009b6ef5a86147bfc8f753f6bb1c01cfb \
  --output-dir /srv/matric-data/obliteratus/harmbench

matric-eval datasets prepare-obliteratus anthropic-red-team \
  --cache /srv/matric-data/obliteratus/cache \
  --legacy-control-snapshot /srv/matric-data/obliteratus/cache/blobs/873726b92136d756529ab98e73eb2d1009b6ef5a86147bfc8f753f6bb1c01cfb \
  --output-dir /srv/matric-data/obliteratus/anthropic-red-team

matric-eval datasets prepare-obliteratus jailbreakbench-harmful \
  --cache /srv/matric-data/obliteratus/cache \
  --output-dir /srv/matric-data/obliteratus/jailbreakbench-harmful

matric-eval datasets prepare-obliteratus jailbreakbench-benign \
  --cache /srv/matric-data/obliteratus/cache \
  --output-dir /srv/matric-data/obliteratus/jailbreakbench-benign

matric-eval datasets prepare-obliteratus wikitext-2-raw-test \
  --cache /srv/matric-data/obliteratus/cache \
  --output-dir /srv/matric-data/obliteratus/wikitext-2-raw-test
```

WildJailbreak train and evaluation are distinct configurations. Both require the
publisher's access conditions. When the current Hugging Face account has accepted
them, the same command resolves the pinned revision through Hugging Face Hub and
records the downloaded payload hash. Without accepted access it fails with a typed
access error; it never substitutes another dataset.

```bash
matric-eval datasets prepare-obliteratus wildjailbreak-train \
  --cache /srv/matric-data/obliteratus/cache \
  --output-dir /srv/matric-data/obliteratus/wildjailbreak-train

matric-eval datasets prepare-obliteratus wildjailbreak-eval \
  --cache /srv/matric-data/obliteratus/cache \
  --output-dir /srv/matric-data/obliteratus/wildjailbreak-eval
```

A reviewed, manually acquired gated artifact may instead be supplied with
`--artifact` and its independently reviewed `--reviewed-sha256`. This records the
hash but does not claim that a repository OID is a payload SHA-256.

## Canonical and compatibility semantics

- The 842 OBLITERATUS built-in pair positions retain both literal source-line
  offsets. The file has no per-row severity field, so tier remains `unknown`.
- AdvBench imports the original `llm-attacks` CSV. Its `target` is retained in raw
  evidence and is not mislabeled as a benign counterpart. The gated
  `walledai/AdvBench` distribution used by OBLITERATUS is recorded separately.
- HarmBench preserves behavior ID, functional/semantic categories, context, tags,
  and the exact 400-row text artifact. It does not silently include the 110
  multimodal behaviors or substitute the inaccessible HF locator.
- Anthropic preserves all 38,961 red-team records and ratings. The canonical view
  emits 38,284 parseable first human turns, including duplicates, and labels their
  semantics `unknown`. It never falls back to the general preference corpus.
- WildJailbreak assigns both vanilla and adversarial text from `data_type`; a harmful
  vanilla row stays harmful and a benign adversarial row stays benign. Completion
  and tactics remain in parent evidence. There is no silent 2,000-row cap.
- JailbreakBench imports the official pinned harmful and benign split files. Package,
  HF, and bundled fallbacks cannot masquerade as one another.
- WikiText is ancillary capability data. All 4,358 rows remain evidence; the 2,891
  nonblank texts form prompt views.

`--legacy-control-snapshot` additionally emits a separately named
`*.obliteratus-legacy-pairs.jsonl`. AdvBench and HarmBench are paired with the
cycled 99-entry OBLITERATUS control pool. Anthropic reproduces first-seen text
de-duplication and the historical 2,000-row cap before the same cycling. These rows
have distinct IDs and explicitly state that the controls are repeated,
repository-derived, and not upstream paired labels. WildJailbreak's incorrect
historical relabeling is not reproduced.

Optional `--limit N --seed S` selects prompt views by a stable SHA-256 rank and
records both values. Omitting `--limit` imports every accepted view. Raw evidence is
never truncated by this option.

## Role, overlap, and study boundaries

Prompt views use the shared `DataReference` vocabulary from the versioned result
contract. Their role begins as `unknown`; use the governed role ledger and selection
manifests before calibration, tuning, export, or final assessment. Run
`matric-eval overlap-diagnostics` on approved text projections when comparing reuse
across sources. A detected overlap is evidence only: it does not rewrite scores or
create unsupported trust labels.

The frozen Qwen3.8 study in issue #114 is unchanged. Import availability is not
authorization to revise its seed, allocation, judge panel, model cohort, or data
roles. Any use there requires an explicit versioned protocol amendment.

The retained public-source qualification summary is
[obliteratus-qualification-2026-09-08.json](obliteratus-qualification-2026-09-08.json).
The model publisher's separate Qwen3.8 lineage artifacts are summarized in
[obliteratus-qwen38-publisher-lineage-2026-09-09.json](obliteratus-qwen38-publisher-lineage-2026-09-09.json),
and the reviewed multi-axis evaluation guidance is in
[obliteratus-adversarial-evaluation.md](obliteratus-adversarial-evaluation.md).
Raw prompt content, cache blobs, and generated evidence remain outside Git.
