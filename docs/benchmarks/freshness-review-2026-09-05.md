# Dataset Freshness Review — 2026-09-05

This record distinguishes source availability from actual upstream freshness. The
automated live audit verifies that immutable revisions resolve and that registry
metadata is structurally complete. This review additionally compared every public
Hugging Face and GitHub pin with its upstream tip, release history, and data-bearing
changes. All executable verification was performed on the A100 evaluation host.

## Outcome

- `inspect-ai==0.3.263` and `inspect-evals==0.19.0` were the latest PyPI releases.
- The repository's stale Inspect Evals provenance constant was advanced from 0.16.0
  to 0.19.0 at tag commit `1eda2bfd205dc7d97e4dc91cfb1e7f05a2d4c504`.
- SWE-bench Verified and Multilingual advanced to their August 2026 v5-harness
  snapshots. Counts and IDs are unchanged; two Verified records and one Multilingual
  record have normalized test-list changes.
- Video-MME-v2 advanced to its August 2026 snapshot. All 3,200 IDs, questions,
  answers, and columns are unchanged; 52 media URLs changed. Protocol identity
  therefore remains v2 while the exact retrieval snapshot changes.
- No other existing data-bearing pin required advancement.

The pre-change A100 live audit covered 42 registered benchmarks with zero warnings
and zero errors: 7 immutable, 12 current, 16 gated, 3 successor-available, 3 local,
and 1 unavailable. Its retained machine-readable artifact is
`/srv/matric-eval/results/freshness-audit-20260905/baseline.json`.

## Changed snapshots

| Benchmark | Previous revision | Reviewed revision | Material difference |
| --- | --- | --- | --- |
| SWE-bench Verified | `91aa3ed51b709be6457e12d00300a6a596d4c6a3` | `78f471bf655a3137b2e8a75af1501690ec009ec3` | 500 IDs retained; v5 image/eval metadata added; 2 normalized test lists changed |
| SWE-bench Multilingual | `e5c585e008e2cb5eecc7c64192d855c53279d788` | `846e647b9f33c0b51b739d005d13d85493c9af09` | 300 IDs retained; v5 image/eval metadata added; 1 normalized test list changed |
| Video-MME-v2 | `31ca5db7bc5ccfc3033a1075efc7858e783c6203` | `6e4bebb03202e1ddbf3d37703e560e51c5aa2d64` | 3,200 IDs and answers retained; 52 URL-only repairs |

SWE-bench results produced before and after this refresh must not be pooled without
the exact dataset and evaluator revisions. Video-MME results remain protocol-v2
comparable, but manifests must retain the dataset revision so failed media retrieval
can be separated from model quality.

## Reviewed and retained pins

The following public source pins matched their upstream data tip at review time:
ARC, BABILong, BFCL V4 Agentic, Claw-Eval, DS-1000, GAIA, GAIA2, GSM8K, HELMET,
HumanEval, IFEval, InfiniteBench, InjecAgent, LiveCodeBench, MBPP, MemoryBench,
MMMU, MMMU Pro, NL2Repo, NoLiMa, QwenClawBench, RealWorldQA, SWE-bench Pro,
tau3-bench, and Tulving.

Pins that differed from a repository tip were retained after inspecting the delta:

| Benchmark | Disposition |
| --- | --- |
| CyberSecEval 4 | Later PurpleLlama commits are unrelated type-suppression changes; the maintained Inspect Evals protocol remains CyberSecEval 4. |
| EvalPlus | `v0.3.1` is still the latest release and resolves to the existing pin; later branch commits are not a release. |
| MMLU-Pro | Later commits change README/eval metadata only; benchmark data is unchanged. |
| OmniDocBench | The versioned `v1.7-2026-04-30` dataset remains pinned; later repository work changes models/docs. |
| RULER | RULER v1 remains pinned inside a broader NVIDIA repository that has since added unrelated skills. |
| Terminal-Bench 2.1 | The fixed Harbor 2.1 protocol is retained; there is no newer verified public data repository to advance to. |

Local MATRIC CLI, MATRIC Memory, and tool-calling sets are versioned with this
repository. QwenWebBench remains unavailable because a canonical public data and
scoring protocol is still absent. HumanEval, MBPP, and MMLU remain as historical
controls with their registered Plus/Pro successors evaluated separately.

## New agentic and AGI lanes

| Lane | Pin | Why it is useful | Execution gate |
| --- | --- | --- | --- |
| BrowseComp | Inspect Evals `3-B`; dataset SHA-256 `7b24471c…1454abf` | Hard web discovery and synthesis with auditable single answers | Networked browser/search and judge model |
| Humanity's Last Exam | Inspect Evals `5-C`; `cais/hle@5a81a4c…4c29` | Broad frontier knowledge/reasoning, including multimodal items | Accepted dataset terms, vision, two grader roles |
| GDPval open set | Inspect Evals `2-A`; `openai/gdpval@a3848a2…05962` | Realistic professional deliverables across 44 occupations | Explicit expert or validated rubric scorer; exact match is rejected |
| ARC-AGI-3 public | Toolkit `0.9.9` at `f12822c…d2f` | Interactive exploration, planning, memory, and adaptation | Stateful visual-action adapter and official scorecards |
| OSWorld 2.0 | Release `osworld-v2-2026.08.08` at `d578d2d…154` | Long-horizon computer use in realistic workflows | Matched gated assets, VM image, websites, and agent adapter |

ARC-AGI-3 and OSWorld 2.0 are distinct successor lanes, not silent replacements for
ARC or OSWorld v1. ARC-AGI-3 currently registers the three named public environments
only. OSWorld 2.0 pins all 108 tasks, task/assets revisions, task-manifest hash, and VM
image hash from the official release manifest.

## Candidates for the next integration wave

- MLE-bench: 75 full / 22 lite Kaggle engineering tasks; valuable but GPU-, Docker-,
  competition-data-, and runtime-intensive.
- PaperBench: 20 production and 3 development paper-reproduction tasks; excellent
  long-horizon evidence but unusually costly and dependent on containerized grading.
- SWE-Lancer: 460 freelance software tasks maintained in Inspect Evals.
- AgentDojo: 1,014 utility and prompt-injection-resilience tasks maintained in
  Inspect Evals; particularly useful for capability/security joint measurement.
- LiveDRBench: 100 periodically refreshed deep-research tasks; requires a deliberate
  immutable snapshot policy before score comparisons.
- WorkArena: realistic enterprise browser work, gated by provisioned ServiceNow
  instances and environment control.

TheAgentCompany is deferred: the current maintained Inspect implementation covers 34
tasks, not the original 175, so results could be mislabeled without a separate subset
protocol.

## Repeating the review

Run the live audit on the A100 host and retain the report alongside the run manifest:

```bash
uv run matric-eval audit-benchmarks --live --output-format json \
  --output /srv/matric-eval/results/freshness-audit-YYYYMMDD/report.json
```

Then compare public source tips to the registered immutable revisions. A differing tip
is a review trigger, not automatic permission to move a pin. Compare schemas, IDs,
prompts, targets, assets, scorers, and evaluator code before assigning a new protocol
identity.
