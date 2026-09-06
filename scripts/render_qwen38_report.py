#!/usr/bin/env python3
"""Render the sealed Qwen3.8 comparison into a public HTML/PDF/JSON bundle."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from matric_eval.studies import StudyProtocol

JsonObject = dict[str, Any]
PRIVATE_ROOT = Path("/srv/matric-eval/results/qwen38-obliteration-2026-09")
PUBLIC_ROOT = PRIVATE_ROOT / "public"
MODEL_LABELS = {
    "qwen38-27b-source-bf16": "Source",
    "qwen38-27b-e03-bf16": "E03",
    "qwen38-27b-pliny-v3-bf16": "Pliny V3",
}
AXIS_LABELS = {
    "capability_and_agentic": "Capability + agentic quality",
    "capability": "Capability",
    "agentic": "Agentic quality",
    "benign_overrefusal": "Benign over-refusal",
    "harmful_compliance": "Harmful compliance",
}
AXIS_DIRECTION = {
    "capability_and_agentic": "Higher is better",
    "capability": "Higher is better",
    "agentic": "Higher is better",
    "benign_overrefusal": "Lower is better",
    "harmful_compliance": "Lower indicates less harmful compliance; report separately from quality",
}
REQUIRED_SECTIONS = {
    "executive-summary",
    "preregistered-methods",
    "provenance-and-limitations",
    "pilot-runtime-estimate",
    "capability-and-agentic-results",
    "benign-overrefusal-results",
    "harmful-compliance-results",
    "paired-statistical-analysis",
    "error-and-missingness-analysis",
    "reproducibility-manifest",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path, label: str) -> JsonObject:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return payload


def _canonical_manifest_sha256(manifest: JsonObject) -> str:
    canonical = dict(manifest)
    declared = canonical.pop("manifest_sha256", None)
    actual = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if declared != actual:
        raise ValueError("manifest_sha256 does not match canonical manifest content")
    return actual


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not (-float("inf") < number < float("inf")):
        raise ValueError(f"{label} must be finite")
    return number


def _interval(value: Any, label: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} must be a two-element interval")
    low = _finite_number(value[0], f"{label}[0]")
    high = _finite_number(value[1], f"{label}[1]")
    if low > high:
        raise ValueError(f"{label} lower bound exceeds upper bound")
    return low, high


def validate_evidence(
    *,
    study: StudyProtocol,
    manifest: JsonObject,
    analysis: JsonObject,
    receipt: JsonObject,
    pilot: JsonObject,
    allow_incomplete_pilot: bool,
) -> bool:
    """Validate all public-evidence joins and return whether this is a draft."""
    root = study.raw["study"]
    reporting = root["reporting"]
    if set(reporting.get("required_sections", [])) != REQUIRED_SECTIONS:
        raise ValueError("protocol report sections do not match the renderer contract")
    manifest_sha256 = _canonical_manifest_sha256(manifest)
    model_ids = [model.id for model in study.models]
    allocation_ids = [allocation.id for allocation in study.benchmarks]
    common = {
        "study_id": study.id,
        "protocol_sha256": study.canonical_sha256,
    }
    for label, payload in (
        ("manifest", manifest),
        ("analysis", analysis),
        ("normalization receipt", receipt),
        ("pilot summary", pilot),
    ):
        if any(payload.get(key) != value for key, value in common.items()):
            raise ValueError(f"{label} identity does not match the protocol")
    if manifest.get("cohort") != "full" or manifest.get("seed") != study.seed:
        raise ValueError("report requires the full manifest at the preregistered seed")
    manifest_allocations = manifest.get("allocations")
    if not isinstance(manifest_allocations, list):
        raise ValueError("manifest.allocations must be a list")
    if [
        item.get("allocation_id") for item in manifest_allocations if isinstance(item, dict)
    ] != allocation_ids:
        raise ValueError("manifest allocation order does not match the protocol")
    for declared, allocation in zip(manifest_allocations, study.benchmarks, strict=True):
        selected = declared.get("selected_ids")
        if not isinstance(selected, list) or len(selected) != allocation.full_samples:
            raise ValueError(f"manifest allocation {allocation.id} is not the full cohort")
    expected_analysis = {
        "manifest_sha256": manifest_sha256,
        "cohort": "full",
        "study_seed": study.seed,
        "source_model_id": model_ids[0],
        "models": model_ids,
    }
    if any(analysis.get(key) != value for key, value in expected_analysis.items()):
        raise ValueError("analysis identity does not match the full study matrix")
    if analysis.get("schema_version") != "1":
        raise ValueError("unsupported analysis schema")
    allocations = analysis.get("allocations")
    axes = analysis.get("axes")
    if not isinstance(allocations, dict) or list(allocations) != allocation_ids:
        raise ValueError("analysis allocations do not match the protocol order")
    expected_axes = {
        *(allocation.axis for allocation in study.benchmarks),
        "capability_and_agentic",
    }
    if not isinstance(axes, dict) or set(axes) != expected_axes:
        raise ValueError("analysis axes do not match the protocol")
    interventions = model_ids[1:]
    for allocation in study.benchmarks:
        result = allocations[allocation.id]
        if not isinstance(result, dict) or result.get("axis") != allocation.axis:
            raise ValueError(f"analysis allocation {allocation.id} has the wrong axis")
        if not isinstance(result.get("metric_id"), str) or not result["metric_id"]:
            raise ValueError(f"analysis allocation {allocation.id} is missing its metric")
        models = result.get("models")
        comparisons = result.get("comparisons_to_source")
        if not isinstance(models, dict) or list(models) != model_ids:
            raise ValueError(f"analysis allocation {allocation.id} model order mismatch")
        if not isinstance(comparisons, dict) or list(comparisons) != interventions:
            raise ValueError(f"analysis allocation {allocation.id} comparisons mismatch")
        for model_id, summary in models.items():
            if not isinstance(summary, dict):
                raise ValueError(f"analysis summary for {allocation.id}/{model_id} is malformed")
            selected = summary.get("selected")
            counts = [
                summary.get("analyzed"),
                summary.get("infrastructure_excluded"),
                summary.get("judge_unresolved"),
                summary.get("model_timeouts"),
            ]
            if selected != allocation.full_samples or any(
                isinstance(count, bool) or not isinstance(count, int) or count < 0
                for count in counts
            ):
                raise ValueError(f"analysis accounting for {allocation.id}/{model_id} is invalid")
            _finite_number(summary.get("mean"), f"{allocation.id}/{model_id}.mean")
            _interval(summary.get("interval_95"), f"{allocation.id}/{model_id}.interval_95")
            _interval(
                summary.get("missingness_bounds"),
                f"{allocation.id}/{model_id}.missingness_bounds",
            )
        for model_id, comparison in comparisons.items():
            if not isinstance(comparison, dict):
                raise ValueError(f"comparison for {allocation.id}/{model_id} is malformed")
            _finite_number(comparison.get("delta"), f"{allocation.id}/{model_id}.delta")
            _interval(
                comparison.get("paired_bootstrap_interval_95"),
                f"{allocation.id}/{model_id}.paired_bootstrap_interval_95",
            )
            _interval(
                comparison.get("missingness_delta_bounds"),
                f"{allocation.id}/{model_id}.missingness_delta_bounds",
            )
    for axis_id, axis in axes.items():
        if not isinstance(axis, dict):
            raise ValueError(f"analysis axis {axis_id} is malformed")
        means = axis.get("model_macro_means")
        comparisons = axis.get("comparisons_to_source")
        if not isinstance(means, dict) or list(means) != model_ids:
            raise ValueError(f"analysis axis {axis_id} model order mismatch")
        if not isinstance(comparisons, dict) or list(comparisons) != interventions:
            raise ValueError(f"analysis axis {axis_id} comparisons mismatch")
        for model_id, value in means.items():
            _finite_number(value, f"{axis_id}/{model_id}.macro_mean")
        for model_id, comparison in comparisons.items():
            if not isinstance(comparison, dict):
                raise ValueError(f"axis comparison for {axis_id}/{model_id} is malformed")
            _finite_number(
                comparison.get("allocation_macro_delta"),
                f"{axis_id}/{model_id}.allocation_macro_delta",
            )
            _interval(
                comparison.get("paired_stratified_bootstrap_interval_95"),
                f"{axis_id}/{model_id}.paired_stratified_bootstrap_interval_95",
            )
            _interval(
                comparison.get("missingness_delta_bounds"),
                f"{axis_id}/{model_id}.missingness_delta_bounds",
            )
            if axis_id == "capability" and not isinstance(comparison.get("noninferior"), bool):
                raise ValueError(f"capability non-inferiority decision missing for {model_id}")
    expected_receipt = {
        "manifest_sha256": manifest_sha256,
        "cohort": "full",
        "models": model_ids,
        "observations": study.full_samples_per_model * len(model_ids),
        "observations_sha256": analysis.get("observations_sha256"),
    }
    if any(receipt.get(key) != value for key, value in expected_receipt.items()):
        raise ValueError("normalization receipt does not join to the analysis")
    if pilot.get("study_seed") != study.seed or not isinstance(pilot.get("models"), dict):
        raise ValueError("pilot summary does not match the study seed or model matrix")
    if list(pilot["models"]) != model_ids:
        raise ValueError("pilot summary model order does not match the protocol")
    complete = pilot.get("status") == "complete"
    if complete and pilot.get("schema_version") != "1":
        raise ValueError("unsupported complete pilot summary schema")
    if not complete and not allow_incomplete_pilot:
        raise ValueError(
            "final report requires pilot summary status 'complete'; use --draft explicitly"
        )
    return not complete


def _code_revision() -> str:
    root = Path(__file__).resolve().parents[1]
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if status.stdout:
        raise RuntimeError("report checkout must be clean")
    revision = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    if len(revision) != 40 or any(character not in "0123456789abcdef" for character in revision):
        raise RuntimeError("report checkout did not report a full lowercase Git revision")
    return revision


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _percent(value: Any, *, signed: bool = False) -> str:
    number = 100.0 * _finite_number(value, "reported proportion")
    return f"{number:+.2f}" if signed else f"{number:.2f}"


def _percent_interval(value: Any) -> str:
    low, high = _interval(value, "reported interval")
    return f"{100.0 * low:.2f}–{100.0 * high:.2f}"


def _page(*, title: str, body: str, draft: bool, active: str) -> str:
    watermark = '<div class="draft">DRAFT — incomplete pilot evidence</div>' if draft else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title><link rel="stylesheet" href="assets/report.css"></head>
<body>{watermark}<header class="site-header"><div class="wrap"><p class="eyebrow">Matched preregistered evaluation</p>
<h1>{_e(title)}</h1><nav aria-label="Report pages"><a class="{"active" if active == "results" else ""}" href="index.html">Results</a><a class="{"active" if active == "methods" else ""}" href="methods.html">Methods &amp; provenance</a><a href="aggregate-results.json">Aggregate JSON</a><a href="reproducibility.json">Reproducibility JSON</a></nav></div></header>
<main class="wrap">{body}</main><footer><div class="wrap">Aggregate-only publication bundle. Raw prompts and completions are not included.</div></footer></body></html>
"""


def _axis_cards(analysis: JsonObject) -> str:
    preferred = [
        "capability_and_agentic",
        "benign_overrefusal",
        "harmful_compliance",
    ]
    cards = []
    for axis_id in preferred:
        axis = analysis["axes"][axis_id]
        means = axis["model_macro_means"]
        rows = []
        for model_id in analysis["models"]:
            width = max(0.0, min(100.0, 100.0 * float(means[model_id])))
            rows.append(
                f'<div class="bar-row"><span>{_e(MODEL_LABELS[model_id])}</span>'
                f'<div class="track"><i style="width:{width:.3f}%"></i></div>'
                f"<strong>{_percent(means[model_id])}%</strong></div>"
            )
        cards.append(
            f'<article class="axis-card"><h3>{_e(AXIS_LABELS[axis_id])}</h3>'
            f'<p class="direction">{_e(AXIS_DIRECTION[axis_id])}</p>{"".join(rows)}</article>'
        )
    return '<div class="axis-grid">' + "".join(cards) + "</div>"


def _noninferiority(analysis: JsonObject) -> str:
    capability = analysis["axes"]["capability"]["comparisons_to_source"]
    items = []
    for model_id, result in capability.items():
        decision = "met" if result["noninferior"] else "not met"
        interval = _percent_interval(result["paired_stratified_bootstrap_interval_95"])
        missing = _percent_interval(result["missingness_delta_bounds"])
        margin = _finite_number(result["noninferiority_margin_percentage_points"], "margin")
        items.append(
            f"<li><strong>{_e(MODEL_LABELS[model_id])}: {decision}</strong> — "
            f"paired macro-delta {_percent(result['allocation_macro_delta'], signed=True)} pp; "
            f"95% interval {interval} pp; missingness bounds {missing} pp; margin {margin:.2f} pp.</li>"
        )
    return "<ul>" + "".join(items) + "</ul>"


def _allocation_table(study: StudyProtocol, analysis: JsonObject, axis_ids: set[str]) -> str:
    rows = []
    source_id = analysis["source_model_id"]
    for allocation in study.benchmarks:
        if allocation.axis not in axis_ids:
            continue
        result = analysis["allocations"][allocation.id]
        for model_id in analysis["models"]:
            summary = result["models"][model_id]
            if model_id == source_id:
                delta = "reference"
            else:
                comparison = result["comparisons_to_source"][model_id]
                delta = (
                    f"{_percent(comparison['delta'], signed=True)} "
                    f"({_percent_interval(comparison['paired_bootstrap_interval_95'])})"
                )
            rows.append(
                "<tr>"
                f"<td>{_e(allocation.id)}</td><td>{_e(result['metric_id'])}</td>"
                f"<td>{_e(MODEL_LABELS[model_id])}</td>"
                f"<td>{_percent(summary['mean'])}%</td>"
                f"<td>{_percent_interval(summary['interval_95'])}%</td>"
                f"<td>{_e(delta)}</td>"
                f"<td>{summary['analyzed']}/{summary['selected']}</td>"
                f"<td>{summary['model_timeouts']}</td><td>{summary['infrastructure_excluded']}</td>"
                f"<td>{summary['judge_unresolved']}</td></tr>"
            )
    return (
        """<div class="table-wrap"><table><thead><tr><th>Allocation</th><th>Metric</th><th>Model</th><th>Estimate</th><th>95% interval</th><th>Δ vs source (95%)</th><th>Analyzed</th><th>Timeout</th><th>Infra</th><th>Judge unresolved</th></tr></thead><tbody>"""
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _paired_table(analysis: JsonObject) -> str:
    rows = []
    for allocation_id, allocation in analysis["allocations"].items():
        for model_id, comparison in allocation["comparisons_to_source"].items():
            mcnemar = comparison.get("mcnemar_exact_p")
            adjusted = comparison.get("mcnemar_holm_adjusted_p")
            rows.append(
                f"<tr><td>{_e(allocation_id)}</td><td>{_e(MODEL_LABELS[model_id])}</td>"
                f"<td>{comparison['paired_analyzed']}</td>"
                f"<td>{_percent(comparison['delta'], signed=True)}</td>"
                f"<td>{_percent_interval(comparison['paired_bootstrap_interval_95'])}</td>"
                f"<td>{_percent_interval(comparison['missingness_delta_bounds'])}</td>"
                f"<td>{'—' if mcnemar is None else f'{float(mcnemar):.4g}'}</td>"
                f"<td>{'—' if adjusted is None else f'{float(adjusted):.4g}'}</td></tr>"
            )
    return (
        """<div class="table-wrap"><table><thead><tr><th>Allocation</th><th>Intervention</th><th>Pairs</th><th>Δ pp</th><th>Paired 95% CI pp</th><th>Missingness bounds pp</th><th>McNemar p</th><th>Holm p</th></tr></thead><tbody>"""
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _pilot_table(pilot: JsonObject) -> str:
    rows = []
    for model_id, result in pilot["models"].items():
        agentic = result.get("agentic")
        agentic_seconds = agentic.get("pilot_seconds") if isinstance(agentic, dict) else None
        full_gpu_hours = result.get("estimated_full_gpu_hours")
        agentic_display = (
            "—" if agentic_seconds is None else f"{float(agentic_seconds) / 60:.1f} min"
        )
        pilot_gpu = result.get("pilot_gpu_hours")
        pilot_gpu_display = "—" if pilot_gpu is None else f"{float(pilot_gpu):.2f} h"
        full_gpu_display = "—" if full_gpu_hours is None else f"{float(full_gpu_hours):.2f} h"
        rows.append(
            f"<tr><td>{_e(MODEL_LABELS[model_id])}</td>"
            f"<td>{float(result['total_generation_seconds']) / 60:.1f} min</td>"
            f"<td>{float(result['total_deterministic_scoring_seconds']):.1f} s</td>"
            f"<td>{agentic_display}</td><td>{pilot_gpu_display}</td>"
            f"<td>{full_gpu_display}</td></tr>"
        )
    return (
        """<div class="table-wrap"><table><thead><tr><th>Model</th><th>Direct generation</th><th>Executable scoring ×2</th><th>Agent harnesses</th><th>Pilot GPU</th><th>Forecast full GPU</th></tr></thead><tbody>"""
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _judge_runtime(pilot: JsonObject) -> str:
    judge = pilot.get("judge")
    if not isinstance(judge, dict):
        return '<p class="muted">External judge runtime is pending.</p>'
    return (
        '<div class="callout"><h3>External judge lane</h3><p>'
        f"Primary {float(judge['primary_seconds']) / 60:.1f} min across "
        f"{int(judge['primary_calls'])} calls; adjudication "
        f"{float(judge['adjudication_seconds']) / 60:.1f} min across "
        f"{int(judge['adjudicator_calls'])} calls; {int(judge['retries'])} retries. "
        f"Forecast full lane: {float(judge['estimated_full_seconds']) / 3600:.2f} h."
        "</p></div>"
    )


def _results_body(
    study: StudyProtocol, analysis: JsonObject, pilot: JsonObject, draft: bool
) -> str:
    draft_note = (
        '<div class="callout warning"><strong>Draft evidence.</strong> The pilot summary is not complete; no result in this rendering is publication-final.</div>'
        if draft
        else ""
    )
    return f"""
{draft_note}
<section id="executive-summary"><p class="eyebrow">Executive summary</p><h2>Three checkpoints, one matched test</h2>
<p class="lede">The untouched Qwen3.8 27B source checkpoint and two refusal interventions were evaluated on the same 1,200 selected sample IDs per model, with a shared generation seed and common text-only inference contract. Results remain a Pareto comparison: quality, benign over-refusal, and harmful compliance are never collapsed into one rank.</p>
{_axis_cards(analysis)}
<div class="callout"><h3>Preregistered capability non-inferiority</h3>{_noninferiority(analysis)}</div></section>
<section id="pilot-runtime-estimate"><p class="eyebrow">Pilot runtime estimate</p><h2>The 100-sample pilot</h2>
<p>Pilot measurements validate the pipeline and forecast runtime only; they do not contribute a separate confirmatory claim. Status: <code>{_e(pilot["status"])}</code>.</p>{_pilot_table(pilot)}{_judge_runtime(pilot)}</section>
<section id="capability-and-agentic-results"><p class="eyebrow">Capability and agentic results</p><h2>Quality under the common contract</h2>
<p>Higher values are better. Macro summaries give every allocation equal weight; component rows retain their original sample counts.</p>{_allocation_table(study, analysis, {"capability", "agentic"})}</section>
<section id="benign-overrefusal-results"><p class="eyebrow">Benign over-refusal</p><h2>Whether safe requests are refused</h2>
<p>Lower values are better. These results are reported independently of unsafe-request behavior.</p>{_allocation_table(study, analysis, {"benign_overrefusal"})}</section>
<section id="harmful-compliance-results"><p class="eyebrow">Harmful compliance</p><h2>Unsafe-request behavior</h2>
<p>Lower values indicate less harmful compliance under the declared primary metrics. This safety-behavior axis is descriptive and is not blended into a quality score.</p>{_allocation_table(study, analysis, {"harmful_compliance"})}</section>
<section id="paired-statistical-analysis"><p class="eyebrow">Paired statistical analysis</p><h2>Intervention minus source</h2>
<p>Every delta uses matched sample IDs. Binary outcomes additionally report exact McNemar tests with Holm correction within the preregistered axis family.</p>{_paired_table(analysis)}</section>
<section id="error-and-missingness-analysis"><p class="eyebrow">Error and missingness analysis</p><h2>Every selected sample is accounted for</h2>
<p>Infrastructure failures are excluded and reported; model timeouts score zero and remain separately counted; unresolved judge parses are excluded from point estimates and represented by worst/best bounds. The component tables expose all four counts.</p></section>
<section id="provenance-and-limitations"><p class="eyebrow">Provenance and limitations</p><h2>What this comparison can support</h2>
<p>Claims are limited to pinned text-only checkpoints, datasets, evaluator snapshots, the common chat template, and the evaluated context range. They do not identify a universal model ranking. E03 and Pliny V3 have reconstructed intervention provenance with documented gaps; native-template and reasoning-off lanes are sensitivity analyses, not headline evidence.</p><p><a class="button" href="methods.html">Read methods and provenance</a></p></section>
<section id="reproducibility-manifest"><p class="eyebrow">Reproducibility manifest</p><h2>Content-addressed evidence</h2>
<p>The public bundle includes the ordered sample manifest, normalization receipt, pilot summary, aggregate result model, exact source revisions, execution contract, and hashes for every published artifact. Raw prompts and completions remain access controlled.</p><p><a class="button" href="reproducibility.json">Open reproducibility JSON</a></p></section>
"""


def _methods_body(study: StudyProtocol, analysis: JsonObject, receipt: JsonObject) -> str:
    root = study.raw["study"]
    execution = root["execution"]
    server = execution["model_server"]
    model_rows = []
    for raw_model in root["models"]:
        gaps = raw_model.get("evidence_gaps", [])
        model_rows.append(
            f"<tr><td>{_e(MODEL_LABELS[raw_model['id']])}</td><td>{_e(raw_model['source'])}</td>"
            f"<td><code>{_e(raw_model['checkpoint_revision'])}</code></td>"
            f"<td>{_e(raw_model['lineage_role'])}</td><td>{_e('; '.join(gaps) if gaps else 'None declared')}</td></tr>"
        )
    dataset_rows = "".join(
        f"<tr><td>{_e(item.id)}</td><td>{_e(item.dataset_source)}</td>"
        f"<td><code>{_e(item.dataset_revision)}</code></td><td>{_e(item.scoring_protocol)}</td>"
        f"<td>{item.full_samples}</td></tr>"
        for item in study.benchmarks
    )
    missing = analysis["missingness_policy"]
    return f"""
<section id="preregistered-methods"><p class="eyebrow">Preregistered methods</p><h2>Design</h2>
<p>This was a matched, full-cohort comparison with {study.full_samples_per_model:,} samples per model and seed <code>{study.seed}</code>. Sample IDs were SHA-256 ranked within allocation, shared across models, and the 100-sample pilot was nested in the full cohort. Generation used per-sample derived seeds.</p>
<div class="facts"><div><span>Bootstrap</span><strong>{analysis["bootstrap_replicates"]:,} paired draws</strong></div><div><span>Interval</span><strong>{int(100 * analysis["confidence_level"])}%</strong></div><div><span>Weighting</span><strong>Equal allocation macro</strong></div><div><span>Headline</span><strong>Two-axis Pareto</strong></div></div>
<h3>Models</h3><div class="table-wrap"><table><thead><tr><th>Label</th><th>Artifact</th><th>Revision</th><th>Role</th><th>Known provenance gaps</th></tr></thead><tbody>{"".join(model_rows)}</tbody></table></div>
<h3>Datasets and scorers</h3><div class="table-wrap"><table><thead><tr><th>Allocation</th><th>Dataset</th><th>Revision</th><th>Scoring protocol</th><th>n/model</th></tr></thead><tbody>{dataset_rows}</tbody></table></div></section>
<section id="execution-environment"><p class="eyebrow">Execution environment</p><h2>Pinned A100 inference contract</h2>
<p>Host <code>{_e(execution["expected_hostname"])}</code>; GPU <code>{_e(execution["required_gpu_model"])}</code>; engine <code>{_e(server["engine"])} {_e(server["version"])}</code>; image <code>{_e(server["image"])}</code>. Tensor parallelism was {server["tensor_parallel_size"]}, bfloat16 was used, speculative decoding was disabled, and official agent runners used concurrency one.</p>
<p>The primary comparison forces one source chat template, reasoning-on behavior, a 32,768-token context limit, and identical sampler settings. Vision and MTP are excluded to preserve a matched E03 comparison.</p></section>
<section id="statistical-methods"><p class="eyebrow">Statistical methods</p><h2>Uncertainty and decision rules</h2>
<p>Continuous component means use percentile bootstrap intervals; binary proportions use Wilson intervals. Intervention deltas use paired bootstrap resampling and domain summaries resample within allocation before equal-weight macro-averaging. Binary paired hypotheses use two-sided exact McNemar tests and Holm correction within axis.</p>
<p>Capability non-inferiority uses the more conservative lower bound from the paired bootstrap interval and unresolved-missingness bound. It must exceed the fixed −3 percentage-point margin.</p>
<h3>Missing-data policy</h3><ul><li>Infrastructure: {_e(missing["infrastructure-error"])}</li><li>Model timeout: {_e(missing["model-timeout"])}</li><li>Judge parse failure: {_e(missing["judge-parse-failure"])}</li></ul></section>
<section id="judge-controls"><p class="eyebrow">Judge controls</p><h2>Blinding, calibration, adjudication</h2>
<p>Target models may not judge their own outputs. Model labels are blinded, presentation order is randomized, all primary/adjudicator disagreements are adjudicated, and the full cohort requires 100 human double-labeled calibration items with Cohen’s κ and a confusion matrix. The sealed judge-bundle digest is recorded in the normalization receipt.</p></section>
<section id="provenance"><p class="eyebrow">Evidence lineage</p><h2>Hash joins</h2>
<dl class="hashes"><dt>Protocol canonical SHA-256</dt><dd><code>{_e(study.canonical_sha256)}</code></dd><dt>Protocol file SHA-256</dt><dd><code>{_e(study.source_sha256)}</code></dd><dt>Manifest SHA-256</dt><dd><code>{_e(analysis["manifest_sha256"])}</code></dd><dt>Observations SHA-256</dt><dd><code>{_e(analysis["observations_sha256"])}</code></dd><dt>Judge bundle SHA-256</dt><dd><code>{_e(receipt["judge_bundle_sha256"])}</code></dd><dt>Analysis revision</dt><dd><code>{_e(analysis["analysis_code_revision"])}</code></dd></dl></section>
"""


CSS = """\
:root{--ink:#18212b;--muted:#5e6a75;--paper:#f7f4ed;--panel:#fff;--line:#d8d3c8;--accent:#b7462a;--deep:#123b43;--gold:#d99b31}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}.wrap{max-width:1180px;margin:auto;padding:0 28px}.site-header{padding:64px 0 28px;background:var(--deep);color:#fff;border-bottom:6px solid var(--gold)}h1{font:700 clamp(2.2rem,5vw,4.8rem)/.98 Georgia,serif;max-width:900px;margin:.15em 0 .45em;letter-spacing:-.035em}h2{font:700 clamp(1.8rem,3vw,2.8rem)/1.08 Georgia,serif;margin:.15em 0 .45em}h3{font-size:1.08rem}.eyebrow{text-transform:uppercase;letter-spacing:.14em;font-size:.75rem;font-weight:800;color:var(--accent);margin:0}.site-header .eyebrow{color:#f3c46f}.lede{font:1.25rem/1.55 Georgia,serif;max-width:900px}nav{display:flex;gap:18px;flex-wrap:wrap}nav a{color:#dceced;text-decoration:none;padding-bottom:4px;border-bottom:2px solid transparent}nav a.active,nav a:hover{border-color:var(--gold)}main section{padding:58px 0;border-bottom:1px solid var(--line)}.axis-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:30px 0}.axis-card,.callout,.facts>div{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:22px;box-shadow:0 4px 18px #123b4310}.direction{min-height:48px;color:var(--muted);font-size:.9rem}.bar-row{display:grid;grid-template-columns:72px 1fr 64px;align-items:center;gap:10px;margin:12px 0;font-size:.86rem}.bar-row strong{text-align:right}.track{height:9px;background:#e7e2d8;border-radius:8px;overflow:hidden}.track i{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--gold))}.callout{border-left:5px solid var(--accent);margin:28px 0}.warning{background:#fff0d5;border-color:#d47914}.draft{position:fixed;right:12px;top:12px;z-index:5;background:#8b1f11;color:#fff;padding:8px 12px;font-weight:800;border-radius:4px}.table-wrap{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:8px}.table-wrap table{width:100%;border-collapse:collapse;font-size:.83rem}.table-wrap th,.table-wrap td{text-align:left;padding:10px 12px;border-bottom:1px solid #e8e4dc;vertical-align:top}.table-wrap th{background:#ece8df;white-space:nowrap}.compact{max-width:800px}.facts{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}.facts span{display:block;color:var(--muted);font-size:.75rem;text-transform:uppercase;letter-spacing:.08em}.facts strong{display:block;margin-top:5px}.hashes{display:grid;grid-template-columns:220px 1fr;gap:7px 18px}.hashes dt{font-weight:700}.hashes dd{margin:0;overflow-wrap:anywhere}code{font-size:.83em;background:#e9e5db;padding:.12em .28em;border-radius:3px;overflow-wrap:anywhere}.button{display:inline-block;background:var(--deep);color:#fff;text-decoration:none;padding:10px 15px;border-radius:5px}footer{padding:36px 0;color:var(--muted)}@media(max-width:820px){.axis-grid,.facts{grid-template-columns:1fr}.hashes{grid-template-columns:1fr}.direction{min-height:0}}@media print{.site-header{padding:25px 0 14px}.site-header nav,footer,.button{display:none}.wrap{max-width:none;padding:0 18px}main section{padding:28px 0}.axis-grid{grid-template-columns:repeat(3,1fr)}.table-wrap{overflow:visible}.table-wrap table{font-size:7.5pt}.callout,.axis-card,.facts>div{box-shadow:none}section{break-inside:auto}h2,h3{break-after:avoid}.table-wrap{break-inside:avoid}.draft{position:absolute}}
"""


def _reproducibility(
    *,
    study: StudyProtocol,
    manifest: JsonObject,
    analysis: JsonObject,
    receipt: JsonObject,
    revision: str,
    input_hashes: Mapping[str, str],
    draft: bool,
) -> JsonObject:
    root = study.raw["study"]
    return {
        "schema_version": "1",
        "study_id": study.id,
        "publication_status": "draft" if draft else "final",
        "renderer_code_revision": revision,
        "protocol": {
            "source_sha256": study.source_sha256,
            "canonical_sha256": study.canonical_sha256,
        },
        "manifest": {
            "sha256": analysis["manifest_sha256"],
            "catalog_sha256": manifest.get("catalog_sha256"),
            "cohort": manifest["cohort"],
            "ordered_ids_sha256": {
                item["allocation_id"]: item["ordered_ids_sha256"]
                for item in manifest["allocations"]
            },
        },
        "analysis": {
            "code_revision": analysis["analysis_code_revision"],
            "observations_sha256": analysis["observations_sha256"],
            "bootstrap_replicates": analysis["bootstrap_replicates"],
        },
        "normalization": {
            "judge_bundle_sha256": receipt["judge_bundle_sha256"],
            "missingness_outcomes_sha256": receipt.get("missingness_outcomes_sha256"),
            "source_artifacts": receipt["source_artifacts"],
            "status_counts": receipt["status_counts"],
        },
        "models": [
            {
                "id": item["id"],
                "source": item["source"],
                "checkpoint_revision": item["checkpoint_revision"],
                "lineage_role": item["lineage_role"],
                "provenance_status": item.get("provenance_status", "upstream-control"),
                "evidence_gaps": item.get("evidence_gaps", []),
                "interventions": item.get("interventions", []),
            }
            for item in root["models"]
        ],
        "datasets": [
            {
                "allocation_id": item.id,
                "source": item.dataset_source,
                "revision": item.dataset_revision,
                "file_sha256": item.dataset_sha256,
                "scoring_protocol": item.scoring_protocol,
                "selected_ids_sha256": next(
                    entry["ordered_ids_sha256"]
                    for entry in manifest["allocations"]
                    if entry["allocation_id"] == item.id
                ),
            }
            for item in study.benchmarks
        ],
        "execution": root["execution"],
        "judging": root["judging"],
        "input_file_sha256": dict(input_hashes),
        "reproduction_commands": [
            "UV_PYTHON=3.11 uv run python -m matric_eval.studies.analysis_cli <protocol> <full-manifest> <full-observations> --output <aggregate-results>",
            "UV_PYTHON=3.11 uv run python scripts/render_qwen38_report.py --protocol <protocol> --manifest <full-manifest> --analysis <aggregate-results> --normalization-receipt <receipt> --pilot-summary <pilot-summary> --output-dir <public-report-dir>",
        ],
        "content_policy": "aggregate statistics, content-free receipts, sample IDs, and hashes only; raw prompts and completions excluded",
    }


def _write_json(path: Path, payload: JsonObject) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _render_pdf(chromium: Path, html_path: Path, pdf_path: Path) -> None:
    if not chromium.is_file():
        raise RuntimeError(f"Chromium executable not found: {chromium}")
    # Strictly confined snap Chromium reports success for /tmp and /srv output paths,
    # but writes them inside its private mount namespace. Stage the profile and PDF
    # below the invoking user's home, which the snap exposes to the host, then copy
    # the validated PDF into the atomic bundle build directory.
    # Snap's home interface also rejects hidden top-level directories, so keep
    # this transient directory non-hidden.
    with tempfile.TemporaryDirectory(prefix="matric-report-chromium-", dir=Path.home()) as raw:
        staging = Path(raw)
        rendered_pdf = staging / "report.pdf"
        subprocess.run(
            [
                str(chromium),
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--no-pdf-header-footer",
                f"--user-data-dir={staging / 'profile'}",
                f"--print-to-pdf={rendered_pdf}",
                html_path.resolve().as_uri(),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if not rendered_pdf.is_file() or rendered_pdf.stat().st_size < 1024:
            raise RuntimeError("Chromium did not produce a valid-sized PDF")
        if not rendered_pdf.read_bytes().startswith(b"%PDF-"):
            raise RuntimeError("Chromium output does not have a PDF header")
        shutil.copyfile(rendered_pdf, pdf_path)


def render_bundle(
    *,
    study: StudyProtocol,
    manifest: JsonObject,
    analysis: JsonObject,
    receipt: JsonObject,
    pilot: JsonObject,
    revision: str,
    input_paths: Mapping[str, Path],
    output_dir: Path,
    chromium: Path,
    draft: bool,
) -> JsonObject:
    """Render a validated bundle into a new directory."""
    if output_dir.exists():
        raise ValueError(f"refusing to overwrite report bundle: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{output_dir.name}-", dir=output_dir.parent
    ) as raw_tmp:
        temp = Path(raw_tmp)
        assets = temp / "assets"
        assets.mkdir()
        title = study.title
        (assets / "report.css").write_text(CSS, encoding="utf-8")
        (temp / "index.html").write_text(
            _page(
                title=title,
                body=_results_body(study, analysis, pilot, draft),
                draft=draft,
                active="results",
            ),
            encoding="utf-8",
        )
        (temp / "methods.html").write_text(
            _page(
                title=f"{title} — methods",
                body=_methods_body(study, analysis, receipt),
                draft=draft,
                active="methods",
            ),
            encoding="utf-8",
        )
        copies = {
            "protocol.yaml": input_paths["protocol"],
            "aggregate-results.json": input_paths["analysis"],
            "sample-manifest.json": input_paths["manifest"],
            "normalization-receipt.json": input_paths["normalization_receipt"],
            "pilot-summary.json": input_paths["pilot_summary"],
        }
        for destination, source in copies.items():
            shutil.copyfile(source, temp / destination)
        input_hashes = {label: _sha256(path) for label, path in input_paths.items()}
        _write_json(
            temp / "reproducibility.json",
            _reproducibility(
                study=study,
                manifest=manifest,
                analysis=analysis,
                receipt=receipt,
                revision=revision,
                input_hashes=input_hashes,
                draft=draft,
            ),
        )
        _render_pdf(chromium, temp / "index.html", temp / "report.pdf")
        files = [path for path in sorted(temp.rglob("*")) if path.is_file()]
        bundle_manifest = {
            "schema_version": "1",
            "study_id": study.id,
            "publication_status": "draft" if draft else "final",
            "renderer_code_revision": revision,
            "files": [
                {
                    "path": str(path.relative_to(temp)),
                    "size": path.stat().st_size,
                    "sha256": _sha256(path),
                }
                for path in files
            ],
        }
        _write_json(temp / "bundle-manifest.json", bundle_manifest)
        for path in temp.rglob("*"):
            if path.is_file():
                path.chmod(0o644)
        os.rename(temp, output_dir)
    return {
        "output_dir": str(output_dir),
        "publication_status": "draft" if draft else "final",
        "bundle_manifest_sha256": _sha256(output_dir / "bundle-manifest.json"),
        "files": len(bundle_manifest["files"]) + 1,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--normalization-receipt", type=Path, required=True)
    parser.add_argument("--pilot-summary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--chromium", type=Path, default=Path("/snap/bin/chromium"))
    parser.add_argument(
        "--draft",
        action="store_true",
        help="allow an explicitly watermarked report from an incomplete pilot summary",
    )
    args = parser.parse_args(argv)
    study = StudyProtocol.from_yaml(args.protocol, validate_registry=False)
    expected_hostname = study.raw["study"]["execution"].get("expected_hostname")
    if expected_hostname and platform.node() != expected_hostname:
        raise RuntimeError(f"study report must run on {expected_hostname}, found {platform.node()}")
    protected_inputs = {
        "manifest": args.manifest,
        "analysis": args.analysis,
        "normalization_receipt": args.normalization_receipt,
        "pilot_summary": args.pilot_summary,
    }
    for path in protected_inputs.values():
        if not path.is_absolute() or not path.is_relative_to(PRIVATE_ROOT):
            raise ValueError(f"study artifact path is outside {PRIVATE_ROOT}: {path}")
    if (
        not args.output_dir.is_absolute()
        or not args.output_dir.is_relative_to(PUBLIC_ROOT)
        or args.output_dir == PUBLIC_ROOT
    ):
        raise ValueError(f"report output must be a new directory below {PUBLIC_ROOT}")
    manifest = _json(args.manifest, "full manifest")
    analysis = _json(args.analysis, "aggregate analysis")
    receipt = _json(args.normalization_receipt, "normalization receipt")
    pilot = _json(args.pilot_summary, "pilot summary")
    draft = validate_evidence(
        study=study,
        manifest=manifest,
        analysis=analysis,
        receipt=receipt,
        pilot=pilot,
        allow_incomplete_pilot=args.draft,
    )
    if args.draft is False and draft:
        raise AssertionError("incomplete evidence escaped final-report validation")
    revision = _code_revision()
    result = render_bundle(
        study=study,
        manifest=manifest,
        analysis=analysis,
        receipt=receipt,
        pilot=pilot,
        revision=revision,
        input_paths={"protocol": args.protocol, **protected_inputs},
        output_dir=args.output_dir,
        chromium=args.chromium,
        draft=draft,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
