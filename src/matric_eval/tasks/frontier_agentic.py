"""Pinned frontier agentic and general-capability benchmark integrations."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.scorer import Scorer
from inspect_ai.solver import Solver, generate

from matric_eval.tasks.registry import (
    BenchmarkStatus,
    BenchmarkUnavailableError,
    register_benchmark,
)
from matric_eval.tasks.upstream import INSPECT_EVALS_REVISION, adapt_upstream_task

BROWSECOMP_DATASET_URL = (
    "https://openaipublic.blob.core.windows.net/simple-evals/browse_comp_test_set.csv"
)
BROWSECOMP_DATASET_SHA256 = "7b24471cd5b3eb2a46830a14802b5c029ea62f488ff75a0f88af7923d1454abf"

HLE_DATASET = "cais/hle"
HLE_DATASET_REVISION = "5a81a4c7271a2a2a312b9a690f0c2fde837e4c29"

GDPVAL_DATASET = "openai/gdpval"
GDPVAL_DATASET_REVISION = "a3848a2a812d5d4d0f08003fac3c8eac40805962"

ARC_AGI_3_REPOSITORY = "arcprize/ARC-AGI"
ARC_AGI_3_REVISION = "f12822c4d550121c35a275008d964afbbed47d2f"
ARC_AGI_3_VERSION = "0.9.9"
ARC_AGI_3_PUBLIC_SNAPSHOT = "2026-09-05"
ARC_AGI_3_PUBLIC_ENVIRONMENTS = (
    "ar25-0c556536",
    "bp35-0a0ad940",
    "cd82-fb555c5d",
    "cn04-2fe56bfb",
    "dc22-fdcac232",
    "ft09-0d8bbf25",
    "g50t-5849a774",
    "ka59-38d34dbb",
    "lf52-271a04aa",
    "lp85-305b61c3",
    "ls20-9607627b",
    "m0r0-492f87ba",
    "r11l-495a7899",
    "re86-8af5384d",
    "s5i5-18d95033",
    "sb26-7fbdac44",
    "sc25-635fd71a",
    "sk48-d8078629",
    "sp80-589a99af",
    "su15-1944f8ab",
    "tn36-ef4dde99",
    "tr87-cd924810",
    "tu93-0768757b",
    "vc33-5430563c",
    "wa30-ee6fef47",
)
ARC_AGI_3_PUBLIC_MANIFEST_SHA256 = (
    "8b944e67bef56e094c907443c1bd4852d35d32902ca5c18e49e8686d6878b638"
)

OSWORLD2_REPOSITORY = "xlang-ai/OSWorld-V2"
OSWORLD2_REVISION = "d578d2d4e0dc82b43e270fdaa7fa89d9708cd154"
OSWORLD2_RELEASE = "osworld-v2-2026.08.08"
OSWORLD2_TASK_DATASET = "xlangai/osworld_v2_tasks"
OSWORLD2_TASK_REVISION = "3736efa55d9d5dc78f57e873ef78886663e41200"
OSWORLD2_ASSET_DATASET = "xlangai/osworld_v2_assets_gated"
OSWORLD2_ASSET_REVISION = "acad110ef3136405f95434b54862bf9066176c2a"
OSWORLD2_TASK_MANIFEST_SHA256 = "42f8f6f8939b8712997d5891456a575f8a2a5f53465e9e3e6747af5d6efd0915"
OSWORLD2_VM_SHA256 = "eb737ae70b49849e24af407de6a518439a23de05a8497096a948334ce0a909aa"


@register_benchmark(
    name="browsecomp",
    description="BrowseComp - 1,266 hard web research questions with browsing and judge scoring",
    category="agentic",
    tier_samples={"smoke": 5, "quick": 100, "full": 1266},
    total_samples=1266,
    requires_sandbox=True,
    sandbox_profile="browsecomp",
    scoring_type="inspect_evals_llm_judge",
    provider_requirements=("web_search_or_browser", "network", "judge-model"),
    status=BenchmarkStatus.GATED,
    status_reason="Requires networked browsing tools and a configured judge model.",
    protocol_version="3-B",
    dataset_source=BROWSECOMP_DATASET_URL,
    dataset_revision=BROWSECOMP_DATASET_SHA256,
    dataset_configs=("encrypted_test",),
    dataset_splits=("test",),
    evaluator_source="UKGovernmentBEIS/inspect_evals",
    evaluator_revision=INSPECT_EVALS_REVISION,
    release_date="2025-04-10",
    license="upstream terms",
    access="public",
    source_kind="other",
    release_policy="immutable",
)
@task
def browsecomp(tier: str = "smoke") -> Task:
    """Run the maintained BrowseComp protocol with browsing enabled."""
    from inspect_evals.browse_comp import browse_comp as upstream_browse_comp

    upstream = upstream_browse_comp(with_browsing=True)
    return adapt_upstream_task(
        upstream,
        benchmark="browsecomp",
        tier=tier,
        task_name="browsecomp",
        protocol_metadata={
            "protocol_version": "3-B",
            "dataset_source": BROWSECOMP_DATASET_URL,
            "dataset_revision": BROWSECOMP_DATASET_SHA256,
        },
    )


@register_benchmark(
    name="hle",
    description="Humanity's Last Exam - 2,500 expert questions across broad disciplines",
    category="knowledge",
    tier_samples={"smoke": 5, "quick": 100, "full": 2500},
    total_samples=2500,
    requires_vision=True,
    scoring_type="inspect_evals_hle_judge",
    provider_requirements=("huggingface-token", "vision", "two-judge-model-roles"),
    status=BenchmarkStatus.GATED,
    status_reason="Requires accepted Hugging Face dataset terms and configured grader roles.",
    protocol_version="5-C",
    dataset_source=HLE_DATASET,
    dataset_revision=HLE_DATASET_REVISION,
    dataset_configs=("default",),
    dataset_splits=("test",),
    evaluator_source="UKGovernmentBEIS/inspect_evals",
    evaluator_revision=INSPECT_EVALS_REVISION,
    release_date="2025-01-23",
    license="MIT code; gated dataset terms",
    access="gated",
    source_kind="huggingface",
    release_policy="immutable",
)
@task
def hle(tier: str = "smoke") -> Task:
    """Run the pinned static HLE set using the maintained current protocol."""
    from inspect_evals.hle import hle as upstream_hle

    upstream = upstream_hle()
    return adapt_upstream_task(
        upstream,
        benchmark="hle",
        tier=tier,
        task_name="hle",
        protocol_metadata={
            "protocol_version": "5-C",
            "dataset_source": HLE_DATASET,
            "dataset_revision": HLE_DATASET_REVISION,
        },
    )


def create_gdpval_task(
    *, scorer: Scorer, tier: str = "smoke", solver: Solver | None = None
) -> Task:
    """Create GDPval only when an explicit deliverable scorer has been supplied."""
    from inspect_evals.gdpval import gdpval as upstream_gdpval

    upstream = upstream_gdpval(scorer=scorer, solver=solver or generate())
    return adapt_upstream_task(
        upstream,
        benchmark="gdpval",
        tier=tier,
        task_name="gdpval",
        protocol_metadata={
            "protocol_version": "2-A",
            "dataset_source": GDPVAL_DATASET,
            "dataset_revision": GDPVAL_DATASET_REVISION,
        },
    )


@register_benchmark(
    name="gdpval",
    description="GDPval open set - 220 realistic professional knowledge-work tasks",
    category="agentic",
    tier_samples={"smoke": 5, "quick": 50, "full": 220},
    total_samples=220,
    requires_sandbox=True,
    sandbox_profile="gdpval",
    scoring_type="expert_or_validated_rubric_judge",
    provider_requirements=("docker", "deliverable-scorer"),
    status=BenchmarkStatus.GATED,
    status_reason="A validated deliverable scorer must be selected explicitly; exact match is invalid.",
    protocol_version="2-A",
    dataset_source=GDPVAL_DATASET,
    dataset_revision=GDPVAL_DATASET_REVISION,
    dataset_configs=("default",),
    dataset_splits=("train",),
    evaluator_source="UKGovernmentBEIS/inspect_evals",
    evaluator_revision=INSPECT_EVALS_REVISION,
    release_date="2025-09-25",
    license="CC-BY-NC-4.0",
    access="public",
    source_kind="huggingface",
    release_policy="immutable",
)
@task
def gdpval(tier: str = "smoke") -> Task:
    del tier
    raise BenchmarkUnavailableError(
        "GDPval deliverables require an explicit expert or validated rubric scorer. "
        "Use create_gdpval_task(scorer=...) so the upstream exact-match capture scorer "
        "cannot be mistaken for a quality metric."
    )


def build_arc_agi_3_server_command(repository: str | Path, *, port: int = 8001) -> list[str]:
    """Build a pinned ARC-AGI-3 toolkit REST server command."""
    repository = Path(repository)
    expression = (
        "from arc_agi import Arcade; "
        f"Arcade().listen_and_serve(port={port}, save_all_recordings=True)"
    )
    return [
        "uv",
        "run",
        "--project",
        str(repository),
        "--python",
        "3.12",
        "python",
        "-c",
        expression,
    ]


def arc_agi_3_environment_manifest(environment_ids: Iterable[str]) -> dict[str, object]:
    """Normalize and hash the live public environment identity returned by the API."""
    ids = tuple(sorted(environment_ids))
    digest = hashlib.sha256(("\n".join(ids) + "\n").encode()).hexdigest()
    return {"count": len(ids), "environment_ids": ids, "sha256": digest}


@register_benchmark(
    name="arc_agi_3",
    description="ARC-AGI-3 v0.9.9 - 25 public interactive environments (2026-09-05)",
    category="agentic",
    tier_samples={"smoke": 1, "quick": 10, "full": 25},
    total_samples=25,
    requires_sandbox=True,
    requires_vision=True,
    sandbox_profile="arc-agi-3",
    scoring_type="official_scorecard",
    provider_requirements=("arc-agi-sdk", "python-3.12", "network", "vision-actions"),
    status=BenchmarkStatus.GATED,
    status_reason="Requires an interactive ARC agent adapter and official scorecard service.",
    protocol_version=f"toolkit-{ARC_AGI_3_VERSION}-public-{ARC_AGI_3_PUBLIC_SNAPSHOT}",
    dataset_source=ARC_AGI_3_REPOSITORY,
    dataset_revision=ARC_AGI_3_REVISION,
    dataset_configs=ARC_AGI_3_PUBLIC_ENVIRONMENTS,
    dataset_splits=(f"public-api-{ARC_AGI_3_PUBLIC_SNAPSHOT}",),
    evaluator_source=ARC_AGI_3_REPOSITORY,
    evaluator_revision=ARC_AGI_3_REVISION,
    prompt_revision=ARC_AGI_3_PUBLIC_MANIFEST_SHA256,
    release_date="2026-06-11",
    license="Apache-2.0",
    access="gated",
    source_kind="github",
    release_policy="continuous",
)
@task
def arc_agi_3(tier: str = "smoke") -> Task:
    del tier
    raise BenchmarkUnavailableError(
        "ARC-AGI-3 requires a stateful visual-action agent adapter. Start the official "
        f"toolkit {ARC_AGI_3_VERSION} service with build_arc_agi_3_server_command() and "
        "retain the scorecard plus recordings; it is not a completion-only task."
    )


def build_osworld2_download_commands(repository: str | Path) -> list[list[str]]:
    """Build release-pinned task and gated-asset download commands."""
    repository = Path(repository)
    return [
        [
            "uv",
            "run",
            str(repository / "scripts/tools/download_osworld_v2_tasks.py"),
            "--benchmark-release",
            OSWORLD2_RELEASE,
        ],
        [
            "uv",
            "run",
            str(repository / "scripts/tools/download_osworld_v2_assets.py"),
            "--benchmark-release",
            OSWORLD2_RELEASE,
        ],
    ]


@register_benchmark(
    name="osworld2",
    description="OSWorld 2.0 - 108 versioned computer-use tasks across realistic workflows",
    category="agentic",
    tier_samples={"smoke": 5, "quick": 30, "full": 108},
    total_samples=108,
    requires_sandbox=True,
    requires_vision=True,
    sandbox_profile="osworld2",
    scoring_type="official_execution_reward",
    provider_requirements=("python-3.12", "kvm-or-aws", "docker", "gated-assets", "network"),
    status=BenchmarkStatus.GATED,
    status_reason="Requires matched gated assets, VM images, websites, and a computer-use agent.",
    protocol_version=OSWORLD2_RELEASE,
    dataset_source=OSWORLD2_TASK_DATASET,
    dataset_revision=OSWORLD2_TASK_REVISION,
    dataset_configs=(OSWORLD2_RELEASE,),
    dataset_splits=("test",),
    evaluator_source=OSWORLD2_REPOSITORY,
    evaluator_revision=OSWORLD2_REVISION,
    container_revision=OSWORLD2_VM_SHA256,
    release_date="2026-08-08",
    license="Apache-2.0 code; gated asset terms",
    access="gated",
    source_kind="huggingface",
    release_policy="versioned",
)
@task
def osworld2(tier: str = "smoke") -> Task:
    del tier
    raise BenchmarkUnavailableError(
        f"OSWorld 2.0 must run through the official {OSWORLD2_RELEASE} external runtime. "
        "Use build_osworld2_download_commands(), verify the task manifest and VM hashes, "
        "then configure the matching provider-specific multienvironment runner."
    )
