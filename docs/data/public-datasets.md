# Reusable public dataset sources

The versioned [public source catalog](../../src/matric_eval/data/public_sources.json)
registers 25 datasets for reusable evaluation, analysis, rubric development and
other explicitly authorized flows. It is separate from the benchmark registry:
choosing a source does not choose a task, scorer, judge, training objective or
export policy.

At this catalog revision, **19 sources have mapped public acquisition files and
6 are blocked**. Mapped means that selected files have pinned source revisions
and addressable URLs. It does not mean that their bytes have already been
downloaded, their labels qualify a judge, or every downstream use is licensed.
These are publicly discoverable, source-licensed datasets, not a collection of
public-domain works. Preserve attribution and incorporated corpus/model terms.

## Registered sources

Counts in the catalog are publisher-reported, not local row-count receipts.
Different publishers count prompts, response pairs, individual responses, steps
or ratings. They are not interchangeable sample sizes. The access column below
describes the catalog's acquisition decision, not a grant to train or release
data.

| Source ID and official source | Domains | Native label evidence | Acquisition |
| --- | --- | --- | --- |
| [`helpsteer3-preference`](https://huggingface.co/datasets/nvidia/HelpSteer3) | General, STEM, code, multilingual | Human pair preferences and reasons | Mapped; CC-BY-4.0 |
| [`helpsteer2`](https://huggingface.co/datasets/nvidia/HelpSteer2) | Response quality | Five human rating attributes; individual disagreements | Mapped; CC-BY-4.0 |
| [`helpsteer2-preference`](https://huggingface.co/datasets/nvidia/HelpSteer2) | Response quality | Dedicated human preferences and explanations | Mapped; CC-BY-4.0 |
| [`wildguardtest`](https://huggingface.co/datasets/allenai/wildguardmix) | Safety, harmfulness, refusal | Human prompt/response harmfulness and refusal; nullable labels | **Blocked:** responsible-use access gate; ODC-BY |
| [`processbench`](https://huggingface.co/datasets/Qwen/ProcessBench) | Math reasoning | Expert earliest-error-step judgments | Mapped; Apache-2.0 data |
| [`summeval`](https://github.com/Yale-LILY/SummEval) | Grounded summarization | Separate expert and crowd ratings | **Blocked:** source-article rights/access unresolved; repository MIT |
| [`halueval`](https://github.com/RUCAIBox/HaluEval) | Factuality, QA, dialogue, summaries | Human general subset; generated task-specific hallucinations | Mapped; repository MIT plus source terms |
| [`sorry-bench-human-judgment-202503`](https://huggingface.co/datasets/sorry-bench/sorry-bench-human-judgment-202503) | Refusal, fulfillment | Human response judgments | **Blocked:** gated custom agreement |
| [`xstest`](https://github.com/paul-rottger/xstest) | Over-refusal, safety | Prompt safety types and unsafe contrasts; not new-response judgments | Mapped prompts; CC-BY-4.0 |
| [`llmbar`](https://github.com/princeton-nlp/LLMBar) | Instruction following | Preferred-output labels; mixed adversarial construction | Mapped; repository MIT |
| [`truthfulqa`](https://github.com/sylinrl/TruthfulQA) | Factuality | True/false reference answers; not new-response judgments | Mapped; Apache-2.0 |
| [`humanevalplus`](https://huggingface.co/datasets/evalplus/humanevalplus) | Code | Reference solutions and executable tests | Mapped; Apache-2.0 |
| [`mbppplus`](https://huggingface.co/datasets/evalplus/mbppplus) | Code | Reference code and executable tests | Mapped; Apache-2.0 |
| [`ifeval`](https://huggingface.co/datasets/google/IFEval) | Instruction following | Programmatic compliance constraints | Mapped; Apache-2.0 |
| [`livecodebench`](https://huggingface.co/datasets/livecodebench/code_generation_lite) | Code | Competition problems and executable tests | **Blocked:** ambiguous data license `cc`; code MIT |
| [`prm800k`](https://github.com/openai/prm800k) | Math reasoning | Human step ratings, alternatives and uncertainty | Mapped; repository MIT plus MATH terms |
| [`rewardbench`](https://huggingface.co/datasets/allenai/reward-bench) | General, reasoning, safety, code | Source-dependent chosen/rejected pairs | Mapped; ODC-BY plus component terms |
| [`rewardbench2`](https://huggingface.co/datasets/allenai/reward-bench-2) | General, math, code, instruction following, safety | Mixed function, judge, voting and manual verification | Mapped; ODC-BY plus component terms |
| [`harmbench`](https://github.com/centerforaisafety/HarmBench) | Safety, agent risk | Behavior definitions and classifier validation; provenance varies | Mapped text subset; repository MIT plus content terms |
| [`flask`](https://github.com/kaistAI/FLASK) | Response quality, rubric taxonomy | Automatic metadata and GPT-4 reviews | **Blocked:** data/code license unverified |
| [`ragtruth`](https://github.com/ParticleMedia/RAGTruth) | Grounded factuality | Human response/span hallucination annotations | Mapped; repository MIT plus source terms |
| [`agentprocessbench`](https://huggingface.co/datasets/LulaCola/AgentProcessBench) | Tool use, agent process | Human step-level process labels | Mapped; MIT data plus source terms |
| [`mcjudgebench`](https://huggingface.co/datasets/jaelly/MCJudgeBench) | Instruction following | Human yes/no/partial constraint labels and reviewed perturbations | Mapped; Apache-2.0 |
| [`judgmentbench`](https://huggingface.co/datasets/judgmentbench/JudgmentBench) | Legal work quality | Lawyer rubric/pairwise labels, separate autograder tables | Mapped CSV tables; MIT data; linked PDFs excluded |
| [`rjudge`](https://github.com/Lordog/R-Judge) | Agent safety | Human-consensus binary labels and risk descriptions | **Blocked:** noncommercial intended-use review; CC-BY-NC-SA-4.0 |

HelpSteer3 selects the preference configuration; other upstream configurations
remain documented, not implicitly acquired. WildGuardTest excludes chiefly
machine-labeled WildGuard training data. JudgmentBench's human tables must stay
distinct from autograder and constructed quality labels. The catalog records
these boundaries and the selected file list for each source.

## From source bytes to reusable evidence

The workflow is **raw acquisition receipt → evidence records → selection/mix
manifest → explicit consumer projection**.

1. Inspect the catalog entry, license/access notes and selected file sizes.
   Acquisition refuses blocked sources; catalog registration does not accept a
   gated agreement. Source revisions are immutable commits. Scripts, notebooks,
   model weights and excluded media are not acquisition inputs.
2. Acquire selected bytes into a data directory outside Git. Successful
   acquisition writes content-addressed blobs and a receipt binding the catalog
   source, upstream revision, file paths, sizes and SHA-256 hashes. Preserve the
   receipt and blobs together. A failed acquisition is not a complete receipt.
3. Import through the receipt-bound importer. **The import command requires the
   acquisition receipt** so source claims can be checked against actual artifact
   hashes. A hand-written source name next to arbitrary JSON is not equivalent
   evidence. Retain native row payloads, IDs, nulls, source configuration/split,
   and declared grouping information.
4. Select exact per-source row quotas with an explicit seed, filters and intended
   role. Save the population evidence and selection manifest so selection can be
   replayed. Mixing sources does not pool their labels into a common metric.
5. Consume native evidence directly, or explicitly map representable fields to
   Inspect samples. Attach a separately chosen task/scorer/protocol when needed.

The catalog's selected file mapping is not an exhaustive upstream mirror.
SummEval's external annotation object has a GCS generation pin but remains
blocked for source-rights review. PRM800K uses pinned Git LFS media URLs so an
acquisition receives data rather than pointer text. HaluEval's `.json` filenames
contain JSONL, as confirmed by its upstream readers. File formats and exclusions
are explicit metadata, not instructions to run an upstream loader.

## CLI workflow

Discover sources and acquire one mapped source. The destination is a local data
directory outside the Git checkout; create the evidence/selection directories
before writing outputs. Commands emit JSON and output files are created
exclusively, so use fresh paths instead of overwriting evidence.

```bash
mkdir -p /srv/matric-data/public /srv/matric-data/evidence /srv/matric-data/selections
matric-eval datasets list
matric-eval datasets show humanevalplus
matric-eval datasets acquire humanevalplus \
  --destination /srv/matric-data/public \
  --max-bytes 10000000 > /srv/matric-data/acquisition-result.json
```

The command's result contains `receipt_path` and a `files` array. Find the
parquet entry's `blob` path relative to the acquisition destination; pass that
exact blob and the persisted receipt to `import-file`. For example, using `jq`
to read the acquisition result:

```bash
dataset_receipt=$(jq -r '.receipt_path' /srv/matric-data/acquisition-result.json)
dataset_blob=$(jq -r '.files[] | select(.format == "parquet") | .blob' \
  /srv/matric-data/acquisition-result.json)

matric-eval datasets import-file humanevalplus \
  "/srv/matric-data/public/$dataset_blob" \
  --receipt "$dataset_receipt" \
  --configuration default --split test \
  --id-pointer /task_id --cluster-pointer /task_id \
  --output /srv/matric-data/evidence/humanevalplus.jsonl
```

Here `task_id` identifies the original HumanEval+ problem. Do not apply this
cluster pointer to other sources without inspecting their schema. Native IDs
and clusters are explicit JSON Pointers; cluster values may be nonempty text or integers; the importer preserves their types in a canonical cluster key.
Configuration/split arguments must describe the actual imported artifact, not a
desired local role. Formats follow the receipt; a conflicting override is
refused. Import each selected data artifact separately, not its README/license.

Save this selection request as
`/srv/matric-data/selections/code-dev-request.json`:

```json
{
  "version": "1",
  "seed": 7,
  "role": "development",
  "sources": [
    {
      "source_id": "humanevalplus",
      "quota": 8,
      "configurations": ["default"],
      "splits": ["test"],
      "filters": {}
    }
  ]
}
```

Compose, replay, and explicitly project the selection:

```bash
matric-eval datasets compose /srv/matric-data/evidence/humanevalplus.jsonl \
  --request /srv/matric-data/selections/code-dev-request.json \
  --output /srv/matric-data/selections/code-dev.json

matric-eval datasets verify /srv/matric-data/selections/code-dev.json \
  --evidence /srv/matric-data/evidence/humanevalplus.jsonl

matric-eval datasets project /srv/matric-data/selections/code-dev.json \
  --input-pointer /prompt --target-pointer /canonical_solution \
  --input-format text \
  --output /srv/matric-data/selections/code-dev-samples.jsonl
```

`compose` accepts multiple evidence file arguments. Add one request allocation
per source for a mixture; repeat `--evidence` for each original population file
when verifying it. `project` checks the manifest's internal binding; use
`verify` for replay against the complete original population. These commands do
not run a model or scorer.

## Library use

Catalog discovery and raw acquisition are independent of model evaluation:

```python
from pathlib import Path

from matric_eval.data.acquisition import acquire_source
from matric_eval.data.catalog import get_source, load_catalog

catalog = load_catalog()
source = get_source("humanevalplus")
receipt = acquire_source(source, Path("/srv/matric-data/public"))
receipt_path = Path(receipt["receipt_path"])
```

Use the receipt-bound import workflow above to produce the evidence file before
selection. For an imported HumanEval+ population:

```python
from pathlib import Path

from matric_eval.data.evidence import load_evidence
from matric_eval.data.selection import (
    SelectionRequest,
    SourceSelection,
    select_records,
    verify_selection,
    write_selection,
)

population = load_evidence(Path("/srv/matric-data/evidence/humanevalplus.jsonl"))
request = SelectionRequest(
    seed=7,
    role="development",
    sources=[SourceSelection(source_id="humanevalplus", quota=8)],
)
manifest = select_records(population, request)
verify_selection(manifest, population)
Path("/srv/matric-data/selections/code-dev.json").write_text(
    write_selection(manifest), encoding="utf-8"
)
```

For a mixture, concatenate imported evidence populations and supply one
`SourceSelection` per source with its own quota. Optional `configurations` and
`splits` constrain native metadata; `filters` use JSON Pointer keys and exact
scalar equality, for example `{"/domain": "Code"}` when that is the source's
actual value. Boolean `true` is not numeric `1`; missing fields do not match.

Selection preserves declared source-local clusters and duplicate-content groups
whole. It rejects filters that cut a group and refuses an exact quota it cannot
fill without splitting groups. The deterministic greedy algorithm can refuse a
quota even when another combination could fit; it does not silently resample,
relax the quota or discard group members. A missing `cluster_id` is **unknown
grouping**, not proof of independence. Cross-source related prompts and near
duplicates need additional review; source-local IDs do not establish global
independent units.

### Preserve native evidence for non-generative flows

Each selected row retains its complete JSON-compatible native payload and source
identity:

```python
native_inputs = [
    {
        "selection_id": selected.selection_id,
        "source_id": selected.evidence.source_id,
        "record_id": selected.evidence.record_id,
        "payload": selected.evidence.payload,
    }
    for selected in manifest.records
]
```

A pairwise consumer can read both responses, preference strengths, ties and
rater reasons from `manifest.records[].evidence.payload`. A scalar consumer can
read separate native rating dimensions. A process consumer can traverse nested
steps, labels and alternatives while retaining their parent problem/trajectory.
These consumers supply their own reviewed semantics. They must not silently
convert preference into absolute correctness, average unrelated ratings, turn
null/partial labels into failure, or count steps as independent tasks.

CSV input retains strings; JSON/parquet types and nulls remain explicit where
representable. Unsupported non-JSON values fail rather than receiving an
invented conversion. Evidence hashes establish record integrity, not annotation
truth or authenticated human authorship.

### Project explicit fields to Inspect

For the HumanEval+ selection above, prompt and reference solution are text:

```python
from inspect_ai.dataset import MemoryDataset
from matric_eval.data.adapters import project_samples

samples = project_samples(
    manifest,
    input_pointer="/prompt",
    target_pointer="/canonical_solution",
    input_format="text",
)
dataset = MemoryDataset(samples, name="humanevalplus-code-dev")
```

The reference target alone does not execute the native tests or select a code
scorer. Samples retain the selection identity, intended role, projection and full
evidence in metadata. `input_format="chat"` supports explicit text-only
system/user/assistant messages with exactly `role` and `content`; tool traces and
extra message fields need another reviewed adapter. Targets must be text or a
nonempty list of text. Numeric ratings, pairwise preferences, step labels and
IFEval constraint specifications do not become suitable Inspect targets by
automatic stringification; consume their native evidence or author an explicit
separate transformation.

## Roles, qualification and release

Native names such as `train`, `test`, `validation` and `gsm8k` describe the
publisher's organization. A selection's intended `PartitionRole` does not grant
usage authorization or establish disjointness across other manifests. Preserve
the shared [role-use and export controls](../development/role-exports.md) when a
flow needs those guarantees. No source import or mixture automatically grants
SFT, judge training, final-holdout access or redistribution.

Public human annotations can support a compatible calibration flow; qualification
still follows the exact domain/rubric/model/protocol and review requirements in
[judge calibration](../development/judge-calibration.md). Executable labels and
machine reviews remain different evidence. Public benchmark exposure also means
that withholding rows locally does not establish that a pretrained judge never
saw them.

The first authorized ProcessBench qualification plan is retained in
[processbench-calibration-plan-2026-09-09.json](processbench-calibration-plan-2026-09-09.json).
It freezes the binary mapping, deterministic final allocation and application
criteria, but deliberately leaves judge identity and the human DomainReview
receipt pending until those exact inputs exist. The allocation contains whole
problem clusters; the assessment contract still requires a frozen deterministic
one-row-per-problem projection so repeated solutions cannot inflate its Wilson
denominators.
The exact replayable allocation input is
[processbench-calibration-selection-request-2026-09-09.json](processbench-calibration-selection-request-2026-09-09.json).

Store raw blobs, evidence JSONL, receipts and manifests outside the repository.
Commit catalog metadata, reviewed configuration and synthetic tests, not raw
public or gated data. The catalog originated in the September 2026 domain-source
research spike; its pinned source documents and current acquisition receipts,
not historical report counts, are the reproducibility references.

## Acquired snapshot

The [2026-09-07 acquisition receipt summary](acquisition-2026-09-07.json) records
19 acquired sources, 846,046,447 raw bytes, and 60 imported data artifacts containing
368,018 evidence records on A100. Raw bytes, notices, receipts and evidence files
live at `/srv/matric-eval/datasets/public-sources-2026-09-07`; they are not bundled
in the package or committed to Git. The other six sources retain their explicit
access/license status. Counts describe records, including nested collections,
not independent examples or qualified human judgments.

The prepared imports assign configurations/splits only when the source catalog
has exactly one choice. Multi-configuration or multi-split artifacts retain
unknown values and their original artifact paths; import with explicit selectors
when the path has been mapped for a particular flow. Group identities are also
unknown in these general imports; use the documented explicit cluster pointer
before drawing statistical conclusions from a selected sample.

## Run a frozen mixture and preserve result lineage

`matric_eval.data.flows.task_from_selection(manifest, projection, solver=..., scorer=...)`
creates an Inspect task from exactly the frozen records. Supply the solver and
scorer appropriate to your flow. It does not apply benchmark tier sampling.
Use `adapt_selection_log(log, manifest, run_id=..., model_id=..., benchmark_id=...)`
to retain each source, intended role and cluster in the version 2 result. This
bridge verifies task metadata, selected IDs and available logged inputs before
binding lineage; it refuses additional sample filtering or reordered selections.
Absent terminal samples remain absent observations with declared selection lineage.

The built-in AIWG dataset adapters can observe text/local records but cannot acquire
HF configurations, Parquet snapshots or Git/LFS datasets. Acquisition here is a
matric-eval product capability; the catalog and receipts do not claim an AIWG
indexing run occurred.
