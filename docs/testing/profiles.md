# Verification profiles and skip dispositions

This is the finite support/evidence disposition for REQ-EI-11 and #130. It
preserves the release/install decisions owned by #93 and live-platform ownership
under #109. The [strategy](strategy.md) identifies implemented gates; a profile
row is a bounded claim to verify, not a recorded pass or a new CI job.

## Platform and Python disposition

| Scope | Finite target | Evidence boundary / promotion owner |
| --- | --- | --- |
| PR semantics/quality | CPython 3.11, Linux Gitea `python:3.11` jobs | The image tag and host architecture are not immutable pins. Record resolved interpreter, image/platform and package inventory with each retained run. No full-suite claim for other interpreters follows. |
| Clean release installation | CPython 3.11, 3.12, 3.13, 3.14, Linux | Existing release.yml explicitly invokes all four versions for exact wheel and sdist artifacts. #93 owns current-candidate and subsequent registry-install evidence. These checks exercise base installs, inventory/audit/provider registration and consumer contract, not every optional evaluator or live provider. |
| Current A100 program | CPython 3.11, Linux x86_64 on attested `basilisk` | Separate clean checkout and pinned/recorded dependencies for the invoked revision; [A100 policy](a100-execution.md), frozen study requirements and actual run inventory apply. GPU execution additionally requires the owned lease. |
| Other targets | Python below 3.11, later unlisted CPython, PyPy, Windows/macOS and other architectures | Below 3.11 is excluded by metadata. Other targets have no qualification here even if metadata permits installation. #93 reviews clean-install expansion; semantic/measurement support requires additional profile-specific tests and evidence. |

`requires-python = ">=3.11"` remains unchanged. The finite release matrix has an
existing reviewed implementation; this documentation does not narrow metadata or
promote four-version install evidence into four-version measurement support.
Retain interpreter patch versions and architectures; do not infer them from a job
name. No new alternate CI or live platform pipeline is introduced.

## Dependency and runtime profiles

All Python profiles name [pyproject.toml](../../pyproject.toml) and
[uv.lock](../../uv.lock); record both hashes and the actual installed inventory.
An extra's presence permits import/use; it does not qualify the corresponding
benchmark. CI's `uv sync` is not an enforced locked install; A100 commands below
use `--locked` and must record a lock-check failure rather than silently resolve.

| Profile ID | Environment / inventory | Capability and actual gate |
| --- | --- | --- |
| `core-install` | Exact wheel/sdist SHA; no extras; resolved consumer inventory and Python version from `validate_release_candidate.py` | Base package/CLI/import/audit/provider registration. Release clean-install gate on 3.11–3.14; #93 registry validation remains distinct. |
| `core-dev` | `uv sync --locked --python 3.11 --extra dev`; uv.lock and package inventory | Python quality and deterministic tests that do not require the study/optional runtime. Gitea quality uses dev only. Do not treat missing optional collections as conformance. |
| `study-dev` | `uv sync --locked --python 3.11 --extra dev --extra study`; installed upstream distributions and source revisions | Full collected Python CI test/coverage and current A100 deterministic semantics. The study extra installs selected Inspect eval extras and the pinned instruction-following dependency; no blanket external-runner qualification follows. |
| `ds1000-dev` | Separate environment, `--extra dev --extra study --extra ds1000`, same recorded lock; numerical library/interpreter inventory | Optional data-science package imports. Actual execution requires the intended isolated image with its own library inventory; host extra installation does not inject libraries into `python-restricted/1`. Profile-specific scorer/evaluator parity remains required. |
| `evalplus-dev` | Separate environment, `--extra dev --extra study --extra evalplus`, same lock and installed EvalPlus revision | Optional evaluator integration. Record dataset/tests, sandbox/runtime and reference scorer identity before claiming benchmark capability. Missing installation/runtime is unqualified, not a passing code grade. |
| `typescript` | [package-lock.json](../../bindings/typescript/package-lock.json), Node/npm/TypeScript versions; `npm ci`, build, test | Wire contract and binding fixture tests in Gitea build/release and A100. Clean tarball installation is separate release evidence; actual matric-cli adoption remains #94. |
| `isolated-python` | `study-dev` controller plus explicitly configured launcher, local socket, pinned image digest/platform, recorded image ID/runc/version/profile/bootstrap hashes | [python-restricted/1](../development/isolated-code-execution.md), opt-in real runtime probes; require start and verified cleanup evidence. Docker's presence alone is insufficient. No host fallback, automatic sudo, live model or GPU is required for these bounded code fixtures. |
| `external-runner` | Separate checkout/image per declared benchmark runtime; source/image/lock/platform/tool versions, task manifest and resource inventory | Controlled canary followed by the declared external evaluator. Core/dev/all-extras installs do not establish SWE-bench/GAIA/agent-platform capability. #109 owns platform adapters and pipeline matrix; current A100 studies retain their own attestation and replay boundaries. |
| `real-provider-smoke` | Workflow-pinned Ollama service version, recorded resolved image/model digest, Python lock/inventory and fixed fixture | Scheduled/manual CPU transport/evaluation persistence fixture only; [guide](real-provider-smoke.md). No credentialed or long-running model qualification in PR CI. |

The release build's `--all-extras --no-extra dev --no-dev --frozen` environment
supports package/SBOM/audit work; it does not replace separate optional-evaluator
or external-runner runtime evidence. Keep profiles in separate environments;
changing extras in a checkout attested by a live process invalidates that source
of evidence.

## Accountable skip records

For each retained run, preserve the selected/collected node IDs (including
collection errors), `pytest -ra` output and JUnit `<skipped>` reasons. Produce a
reviewed `skip-dispositions.json` alongside that run's JUnit using the record
shape below. This is an evidence format for the run reviewer, not an existing
automatically enforced CI schema. No matrix generator or unimplemented check is
claimed. An unexplained skip or reduced collection remains an evidence gap.

```json
{
  "version": "1",
  "source_sha256": "<source-manifest-sha256>",
  "profile_id": "study-dev",
  "records": [{
    "node_id": "tests/integration/test_ollama.py::<collected-test>",
    "reason": "Ollama not available",
    "capability": "live Ollama transport/inference for the selected fixture",
    "owner_role": "platform engineer",
    "promotion_condition": "attest the endpoint/model and run the named fixture on A100",
    "disposition": "unqualified",
    "evidence": "junit.xml"
  }]
}
```

Use actual node IDs/reasons and hashes, not these placeholders. One reason shared
by many parametrized cases can share a reviewed policy entry, but preserve each
case in JUnit or an explicit node-ID list. A skip is never a pass, zero grade, or
negative contamination finding. Record test failures before reruns; flakiness
requires diagnosis and retained original failure, not a silent skip conversion.

| Current skip source / reason | Impacted capability | Accountable role | Promotion condition |
| --- | --- | --- | --- |
| `tests/conftest.py` dataset availability decorators: ARC, GSM8K, HumanEval, MBPP, IFEval, LiveCodeBench, DS-1000, MTBench, MMLU | Real dataset loading/task construction for the named dataset | Benchmark/data maintainer | Record permitted dataset revision/manifest and source cache on A100, then execute affected node IDs. A mocked loader does not replace these cases. |
| Same file: GPQA, CyberSecEval, GAIA, LongMemEval, MemoryAgentBench, LoCoMo | Access-gated or external dataset/runtime fixtures | Benchmark/data maintainer, access owner where required | Obtain permitted data and declared evaluator environment, attest identities, rerun explicit cases; do not add access credentials to PR CI. |
| `requires_docker` / `requires_ffmpeg` decorators | External container/video capabilities | Platform engineer | Binary presence is only discovery; record runtime/image or ffmpeg version plus actual fixture execution and cleanup. |
| `test_isolated_execution_runtime.py`: opt-in or explicit launcher/pinned image absent | Real bounded generated-code isolation | Security/platform engineer | Configure the reviewed runtime on A100 and run all controlled probes with effective restrictions, start and exact-ID cleanup evidence. |
| `test_ollama.py`: endpoint unavailable | Selected live Ollama endpoint behavior | Platform engineer | Attest endpoint and model, run named integration cases. Separate recurring smoke remains narrowly scoped. |
| `test_ollama.py` unconditional slow-inference skip; `test_tasks.py` unconditional Ollama skip; `test_thinking.py` unconditional model skips | Unexecuted end-to-end inference and thinking-model fixtures | Provider/task maintainer | Review/replace the unconditional gate with an explicit bounded opt-in profile, then retain an actual run. Merely installing a model does not unskip these tests. |
| `test_datasets.py` unconditional actual-data skips | Historical real-data loader examples | Data maintainer | Implement/review executable versioned fixtures and explicit selection; supplying files alone does not activate unconditional decorators. |
| Any newly observed skip, deselection or import/collection loss | Capability named by the affected test or module | PR author proposes; test architect reviews | Record why it was absent, intended profile and measurable promotion condition. Do not infer a smaller denominator means better qualification. |

## Reviewed historical skip evidence

The [#128 skip receipt](evidence/README.md) and
[machine-readable dispositions](evidence/ei-128-skip-dispositions.json) retain
all 321 actual skipped node IDs/reasons from A100 source
`be8e9886f6ff82c5503e6ac890d278751bd16085`, with exact lock/JUnit/environment/
inventory/full-log digests. `policy_id` joins each record to its capability,
owner role and promotion condition. All reasons are mapped; every disposition
remains unqualified for that skipped capability. This is a historical #128 run,
not #130 validation or proof that every optional evaluator is supported.

## Evidence bundle and promotion

A profile receipt identifies source commit/tree, profile ID, lock and inventory,
interpreter/platform, fixture hashes, commands and exits, JUnit/skip records,
initial failures and rerun linkage. Add image/runtime/native artifact hashes for
isolated/external execution and GPU broker lease/configuration for measurement.
Use `/srv/matric-eval/results/<work-item-or-run>/` on A100; retain sensitive data
under the study's access policy. Public issue/PR receipts use content-free paths
and digests plus reviewer role.

Promotion requires evidence matching the claimed scope and owner review. The
profile tables and historical #93 receipts do not themselves qualify a new
revision. No fabricated pass totals, universal statistical thresholds, or
unsupported hardware/platform expansion are implied by this documentation.
