"""OmniDocBench v1.7 manifest support and official batch-evaluator routing."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessageUser, ContentText

from matric_eval.config import get_sample_count, get_seed
from matric_eval.datasets import get_dataset_path, seeded_sample
from matric_eval.multimodal import image_content
from matric_eval.tasks.registry import (
    BenchmarkStatus,
    BenchmarkUnavailableError,
    register_benchmark,
)

OMNIDOC_DATASET = "opendatalab/OmniDocBench"
OMNIDOC_REPOSITORY = "opendatalab/OmniDocBench"
OMNIDOC_EVALUATOR_REVISION = "193627ae9e97d89188468ed1ee3b7a856ff76044"
OMNIDOC_VERSION = "1.7"
OMNIDOC_PAGES = 1651
OMNIDOC_PROMPT = (
    "Convert this complete document page to Markdown. Preserve reading order, text, "
    "display formulas, and tables. Return only the page Markdown."
)


def omnidoc_overall(
    *,
    text_edit_distance: float,
    table_teds: float,
    formula_cdm: float,
) -> float:
    """Compute the official v1.5+ three-component overall score."""
    return ((1.0 - text_edit_distance) * 100.0 + table_teds + formula_cdm) / 3.0


def record_to_sample(
    record: dict[str, Any],
    *,
    image_path: str | Path | None = None,
) -> Sample:
    page_info = record.get("page_info", {})
    relative_image = str(page_info.get("image_path", record.get("image_path", "")))
    source = image_path or record.get("image") or relative_image
    content = [image_content(source), ContentText(text=OMNIDOC_PROMPT)]
    attributes = page_info.get("page_attribute", {})
    return Sample(
        input=[ChatMessageUser(content=content)],
        target="",
        id=relative_image,
        metadata={
            "image_path": relative_image,
            "page_no": page_info.get("page_no"),
            "width": page_info.get("width"),
            "height": page_info.get("height"),
            "page_attribute": attributes,
            "requires_vision": True,
            "protocol_version": OMNIDOC_VERSION,
            "evaluator_revision": OMNIDOC_EVALUATOR_REVISION,
        },
    )


def load_omnidocbench(tier: str = "smoke") -> list[Sample]:
    """Load page images and annotations from an accepted local v1.7 snapshot."""
    root_value = get_dataset_path("omnidocbench")
    if not root_value:
        raise FileNotFoundError(
            "OmniDocBench v1.7 requires its local images and ground-truth JSON. Set "
            "MATRIC_EVAL_OMNIDOCBENCH_DATA_PATH to the accepted dataset snapshot."
        )
    root = Path(root_value)
    annotation_candidates = [
        root / "OmniDocBench.json",
        root / "OmniDocBench_v1.7.json",
        root / "annotations.json",
    ]
    annotation = next((path for path in annotation_candidates if path.exists()), None)
    if annotation is None:
        raise FileNotFoundError(f"OmniDocBench v1.7 ground-truth JSON not found under {root}")
    records = json.loads(annotation.read_text(encoding="utf-8"))
    if len(records) != OMNIDOC_PAGES:
        raise ValueError(f"Expected {OMNIDOC_PAGES} OmniDocBench pages, found {len(records)}")
    samples = []
    for record in records:
        relative = Path(record["page_info"]["image_path"])
        candidates = [root / relative, root / "images" / relative, root / "imgs" / relative]
        image_path = next((path for path in candidates if path.exists()), candidates[0])
        if not image_path.exists():
            raise FileNotFoundError(f"OmniDocBench page image not found: {relative}")
        samples.append(record_to_sample(record, image_path=image_path))
    sample_count = get_sample_count("omnidocbench", tier)
    if 0 < sample_count < len(samples):
        samples = seeded_sample(samples, sample_count, get_seed())
    return samples


def build_omnidocbench_command(
    repository: str | Path,
    *,
    config: str | Path,
) -> list[str]:
    """Build the official MGAM/CDM/TEDS batch-evaluation command."""
    return ["uv", "run", "python", "pdf_validation.py", "--config", str(config)]


def run_omnidocbench(
    repository: str | Path,
    *,
    config: str | Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        build_omnidocbench_command(repository, config=config),
        cwd=repository,
        check=True,
        text=True,
    )


def omnidocbench_scorer():
    raise BenchmarkUnavailableError(
        "OmniDocBench v1.7 uses batch MGAM matching plus Edit Distance, TEDS, and CDM. "
        "Use run_omnidocbench() after writing one Markdown prediction per page."
    )


@register_benchmark(
    name="omnidocbench",
    description="OmniDocBench v1.7 - 1,651-page document parsing benchmark",
    category="multimodal",
    tier_samples={"smoke": 5, "quick": 50, "full": OMNIDOC_PAGES},
    total_samples=OMNIDOC_PAGES,
    requires_vision=True,
    scoring_type="official_mgam_edit_teds_cdm",
    provider_requirements=("vision", "omnidocbench-runtime"),
    status=BenchmarkStatus.GATED,
    status_reason="Requires accepted page images and the official batch evaluator runtime.",
    protocol_version=OMNIDOC_VERSION,
    dataset_source=OMNIDOC_DATASET,
    dataset_revision="v1.7-2026-04-30",
    dataset_splits=("test",),
    license="Apache-2.0 code; upstream dataset terms",
    access="gated",
    source_kind="github",
    release_policy="versioned",
    evaluator_source=OMNIDOC_REPOSITORY,
    evaluator_revision=OMNIDOC_EVALUATOR_REVISION,
)
@task
def omnidocbench(tier: str = "smoke") -> Task:
    del tier
    raise BenchmarkUnavailableError(
        "OmniDocBench is batch-scored across page predictions. Use run_omnidocbench() "
        "with a pinned upstream checkout and generated prediction directory."
    )
