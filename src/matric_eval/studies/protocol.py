"""Validation for preregistered, matched model-comparison studies."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from matric_eval.models import LineageRole, ModelSpec

_REVISION_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_SHA256_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_AXES = {
    "benign_overrefusal",
    "harmful_compliance",
    "capability",
    "agentic",
}
_EXECUTION_MODES = {"offline-batch", "official-agent-runner"}
_SELECTION_STRATEGIES = {
    "sha256-ranked-v1",
    "sha256-stratified-round-robin-v1",
}


def _required_string(data: dict[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value.strip()


def _required_positive_int(data: dict[str, Any], key: str, context: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{context}.{key} must be a positive integer")
    return value


@dataclass(frozen=True)
class BenchmarkAllocation:
    """One benchmark's fixed contribution to pilot and full cohorts."""

    id: str
    benchmark: str
    axis: str
    dataset_source: str
    dataset_revision: str
    scoring_protocol: str
    execution_mode: str
    selection_strategy: str
    pilot_samples: int
    full_samples: int
    available_samples: int
    dataset_sha256: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BenchmarkAllocation:
        context = f"benchmarks[{data.get('id', '?')}]"
        axis = _required_string(data, "axis", context)
        if axis not in _AXES:
            raise ValueError(f"{context}.axis must be one of {', '.join(sorted(_AXES))}")
        execution_mode = _required_string(data, "execution_mode", context)
        if execution_mode not in _EXECUTION_MODES:
            raise ValueError(
                f"{context}.execution_mode must be one of " + ", ".join(sorted(_EXECUTION_MODES))
            )
        selection_strategy = str(data.get("selection_strategy", "sha256-ranked-v1"))
        if selection_strategy not in _SELECTION_STRATEGIES:
            raise ValueError(
                f"{context}.selection_strategy must be one of "
                + ", ".join(sorted(_SELECTION_STRATEGIES))
            )
        revision = _required_string(data, "dataset_revision", context).lower()
        if not _REVISION_RE.fullmatch(revision):
            raise ValueError(f"{context}.dataset_revision must be an immutable revision")
        dataset_sha256 = data.get("dataset_sha256")
        if dataset_sha256 is not None:
            if not isinstance(dataset_sha256, str) or not _SHA256_RE.fullmatch(
                dataset_sha256.lower()
            ):
                raise ValueError(f"{context}.dataset_sha256 must be a SHA-256 digest")
            dataset_sha256 = dataset_sha256.lower().removeprefix("sha256:")
        pilot_samples = _required_positive_int(data, "pilot_samples", context)
        full_samples = _required_positive_int(data, "full_samples", context)
        available_samples = _required_positive_int(data, "available_samples", context)
        if pilot_samples > full_samples:
            raise ValueError(f"{context}.pilot_samples cannot exceed full_samples")
        if full_samples > available_samples:
            raise ValueError(f"{context}.full_samples cannot exceed available_samples")
        return cls(
            id=_required_string(data, "id", context),
            benchmark=_required_string(data, "benchmark", context),
            axis=axis,
            dataset_source=_required_string(data, "dataset_source", context),
            dataset_revision=revision,
            dataset_sha256=dataset_sha256,
            scoring_protocol=_required_string(data, "scoring_protocol", context),
            execution_mode=execution_mode,
            selection_strategy=selection_strategy,
            pilot_samples=pilot_samples,
            full_samples=full_samples,
            available_samples=available_samples,
        )


@dataclass(frozen=True)
class StudyProtocol:
    """A validated preregistration for a paired, multi-model evaluation."""

    id: str
    title: str
    seed: int
    pilot_samples_per_model: int
    full_samples_per_model: int
    models: tuple[ModelSpec, ...]
    benchmarks: tuple[BenchmarkAllocation, ...]
    raw: dict[str, Any]
    source_sha256: str | None = None

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        source_sha256: str | None = None,
        validate_registry: bool = True,
    ) -> StudyProtocol:
        root = data.get("study")
        if not isinstance(root, dict):
            raise ValueError("protocol must contain a study object")
        if str(root.get("schema_version")) != "1":
            raise ValueError("study.schema_version must be '1'")
        if root.get("status") != "preregistered":
            raise ValueError("study.status must be preregistered before pilot execution")

        seed = root.get("seed")
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**32:
            raise ValueError("study.seed must be an unsigned 32-bit integer")

        samples = root.get("samples_per_model")
        if not isinstance(samples, dict):
            raise ValueError("study.samples_per_model must be an object")
        pilot_samples = _required_positive_int(samples, "pilot", "study.samples_per_model")
        full_samples = _required_positive_int(samples, "full", "study.samples_per_model")
        if pilot_samples >= full_samples:
            raise ValueError("pilot sample count must be smaller than full sample count")
        if not 1000 <= full_samples <= 1500:
            raise ValueError(
                "full sample count must remain within the preregistered 1000-1500 range"
            )

        selection = root.get("sample_selection")
        if not isinstance(selection, dict):
            raise ValueError("study.sample_selection must be an object")
        required_selection = {
            "algorithm": "allocation-declared-v1",
            "shared_across_models": True,
            "pilot_nested_in_full": True,
            "ordered_manifest_required": True,
        }
        for key, expected in required_selection.items():
            if selection.get(key) != expected:
                raise ValueError(f"study.sample_selection.{key} must be {expected!r}")

        generation_seed = root.get("generation_seed")
        if not isinstance(generation_seed, dict):
            raise ValueError("study.generation_seed must be an object")
        required_seed_policy = {
            "algorithm": "sha256-uint32-v1",
            "key_format": "{seed}\\0{allocation_id}\\0{canonical_sample_id}",
            "shared_across_models": True,
        }
        for key, expected in required_seed_policy.items():
            if generation_seed.get(key) != expected:
                raise ValueError(f"study.generation_seed.{key} must be {expected!r}")

        raw_models = root.get("models")
        if not isinstance(raw_models, list) or len(raw_models) < 2:
            raise ValueError("study.models must contain at least two qualified models")
        if not all(isinstance(item, dict) for item in raw_models):
            raise ValueError("every study model must be a qualified model object")
        models = tuple(ModelSpec.from_dict(item) for item in raw_models)
        cls._validate_models(models, seed)

        raw_benchmarks = root.get("benchmarks")
        if not isinstance(raw_benchmarks, list) or not raw_benchmarks:
            raise ValueError("study.benchmarks must be a non-empty list")
        if not all(isinstance(item, dict) for item in raw_benchmarks):
            raise ValueError("every study benchmark allocation must be an object")
        benchmarks = tuple(BenchmarkAllocation.from_dict(item) for item in raw_benchmarks)
        ids = [item.id for item in benchmarks]
        if len(ids) != len(set(ids)):
            raise ValueError("study benchmark allocation ids must be unique")
        if sum(item.pilot_samples for item in benchmarks) != pilot_samples:
            raise ValueError("benchmark pilot allocations do not equal samples_per_model.pilot")
        if sum(item.full_samples for item in benchmarks) != full_samples:
            raise ValueError("benchmark full allocations do not equal samples_per_model.full")
        axes = {item.axis for item in benchmarks}
        if axes != _AXES:
            missing = ", ".join(sorted(_AXES - axes))
            raise ValueError(f"study must measure every required axis; missing: {missing}")
        if validate_registry:
            cls._validate_registry(benchmarks)

        cls._validate_analysis(root)
        cls._validate_reporting(root)
        cls._validate_execution(root)
        cls._validate_primary_comparison(root, models)
        cls._validate_judging(root)

        return cls(
            id=_required_string(root, "id", "study"),
            title=_required_string(root, "title", "study"),
            seed=seed,
            pilot_samples_per_model=pilot_samples,
            full_samples_per_model=full_samples,
            models=models,
            benchmarks=benchmarks,
            raw=data,
            source_sha256=source_sha256,
        )

    @staticmethod
    def _validate_models(models: tuple[ModelSpec, ...], seed: int) -> None:
        ids = [model.id for model in models]
        if len(ids) != len(set(ids)):
            raise ValueError("qualified model ids must be unique")
        groups = {model.comparison_group for model in models}
        if len(groups) != 1:
            raise ValueError("all study models must share one comparison_group")
        controls = [
            model
            for model in models
            if model.lineage_role in {LineageRole.OFFICIAL_INSTRUCT, LineageRole.UNTOUCHED_CONTROL}
        ]
        if len(controls) != 1:
            raise ValueError("study must contain exactly one untouched control")
        identities = {model.checkpoint_identity for model in models}
        for model in models:
            if model.runtime.sampler.get("seed") != seed:
                raise ValueError(f"model {model.id} runtime seed does not match study seed")
            for intervention in model.interventions:
                parent = (intervention.parent_source, intervention.parent_revision)
                if parent not in identities:
                    raise ValueError(f"model {model.id} intervention parent is not a study peer")
        runtime_signatures = {
            json.dumps(
                {
                    "execution_mode": model.runtime.execution_mode.value,
                    "dtype": model.runtime.dtype,
                    "chat_template_sha256": model.runtime.chat_template_sha256,
                    "reasoning_mode": model.runtime.reasoning_mode,
                    "context_limit": model.runtime.context_limit,
                    "tool_protocol": model.runtime.tool_protocol,
                    "sampler": model.runtime.sampler,
                },
                sort_keys=True,
            )
            for model in models
        }
        if len(runtime_signatures) != 1:
            raise ValueError(
                "primary model runtimes must be identical except for checkpoint identity"
            )

    @staticmethod
    def _validate_registry(benchmarks: tuple[BenchmarkAllocation, ...]) -> None:
        import matric_eval.tasks  # noqa: F401
        from matric_eval.tasks.registry import get_registry

        registry = get_registry()
        for allocation in benchmarks:
            metadata = registry.get(allocation.benchmark)
            if metadata is None:
                raise ValueError(
                    f"benchmark allocation {allocation.id} references unregistered "
                    f"benchmark {allocation.benchmark}"
                )
            if metadata.dataset_revision != allocation.dataset_revision:
                raise ValueError(
                    f"benchmark allocation {allocation.id} revision does not match registry: "
                    f"{allocation.dataset_revision} != {metadata.dataset_revision}"
                )
            if metadata.dataset_source != allocation.dataset_source:
                raise ValueError(
                    f"benchmark allocation {allocation.id} source does not match registry: "
                    f"{allocation.dataset_source} != {metadata.dataset_source}"
                )

    @staticmethod
    def _validate_analysis(root: dict[str, Any]) -> None:
        analysis = root.get("analysis")
        if not isinstance(analysis, dict):
            raise ValueError("study.analysis must be an object")
        if analysis.get("paired_by_sample_id") is not True:
            raise ValueError("study.analysis.paired_by_sample_id must be true")
        if analysis.get("pilot_use") != "timing-and-pipeline-validation-only":
            raise ValueError("study.analysis.pilot_use must be timing-and-pipeline-validation-only")
        if analysis.get("multiple_comparison_correction") != "holm":
            raise ValueError("study.analysis.multiple_comparison_correction must be holm")
        margin = analysis.get("capability_noninferiority_margin_pp")
        if isinstance(margin, bool) or not isinstance(margin, (int, float)) or margin >= 0:
            raise ValueError("capability non-inferiority margin must be a negative number")

    @staticmethod
    def _validate_reporting(root: dict[str, Any]) -> None:
        reporting = root.get("reporting")
        if not isinstance(reporting, dict):
            raise ValueError("study.reporting must be an object")
        formats = reporting.get("required_formats")
        if not isinstance(formats, list) or not {"html-site", "pdf", "json"}.issubset(formats):
            raise ValueError(
                "study.reporting.required_formats must include html-site, pdf, and json"
            )
        if reporting.get("publish_raw_sensitive_content") is not False:
            raise ValueError("raw sensitive prompts and completions must not be public")
        if reporting.get("publish_aggregate_metrics") is not True:
            raise ValueError("aggregate metrics must be publishable")

    @staticmethod
    def _validate_execution(root: dict[str, Any]) -> None:
        execution = root.get("execution")
        if not isinstance(execution, dict):
            raise ValueError("study.execution must be an object")
        if execution.get("host_alias") != "a100":
            raise ValueError("study execution host must be the a100 SSH alias")
        if execution.get("required_gpu_model") != "NVIDIA A100 80GB PCIe":
            raise ValueError("study requires NVIDIA A100 80GB PCIe GPUs")
        if execution.get("exclusive_gpu_lease_required") is not True:
            raise ValueError("study execution requires an exclusive GPU lease")
        server = execution.get("model_server")
        if not isinstance(server, dict) or server.get("engine") != "vllm":
            raise ValueError("study.execution.model_server must pin vllm")
        required_server_controls = {
            "offline_batch_inference_required": True,
            "batch_invariance": False,
            "v1_multiprocessing": False,
            "async_scheduling": False,
            "language_model_only": True,
            "speculative_decoding": False,
            "usage_stats": False,
        }
        for key, expected in required_server_controls.items():
            if server.get(key) is not expected:
                raise ValueError(f"study.execution.model_server.{key} must be {expected}")
        if server.get("architecture_registrations") != {
            "Qwen3_5ForCausalLM": "vllm.model_executor.models.qwen3_5:Qwen3_5ForCausalLM"
        }:
            raise ValueError(
                "study.execution.model_server.architecture_registrations must pin the "
                "vLLM Qwen3.5 text-only implementation"
            )
        if server.get("online_serving_scope") != "official-agent-runners-only":
            raise ValueError(
                "study.execution.model_server.online_serving_scope must be "
                "official-agent-runners-only"
            )
        if execution.get("agentic_request_concurrency") != 1:
            raise ValueError("study.execution.agentic_request_concurrency must be 1")
        version = server.get("version")
        if not isinstance(version, str) or not version.strip():
            raise ValueError("study.execution.model_server.version must be pinned")
        if server.get("tensor_parallel_size") != 1:
            raise ValueError("study.execution.model_server.tensor_parallel_size must be 1")
        if server.get("safetensors_load_strategy") != "prefetch":
            raise ValueError(
                "study.execution.model_server.safetensors_load_strategy must be prefetch"
            )
        gpu_memory_utilization = server.get("gpu_memory_utilization")
        if (
            isinstance(gpu_memory_utilization, bool)
            or not isinstance(gpu_memory_utilization, (int, float))
            or not 0.5 <= gpu_memory_utilization < 1
        ):
            raise ValueError(
                "study.execution.model_server.gpu_memory_utilization must be in [0.5, 1.0)"
            )
        image = server.get("image")
        if not isinstance(image, str) or not re.search(r"@sha256:[0-9a-f]{64}$", image):
            raise ValueError("study.execution.model_server.image must use an immutable digest")

    @staticmethod
    def _validate_primary_comparison(
        root: dict[str, Any],
        models: tuple[ModelSpec, ...],
    ) -> None:
        comparison = root.get("primary_comparison")
        if not isinstance(comparison, dict) or comparison.get("modality") != "text-only":
            raise ValueError("study.primary_comparison.modality must be text-only")
        template = comparison.get("common_chat_template")
        if not isinstance(template, dict) or template.get("force_server_override") is not True:
            raise ValueError("primary comparison must force the common chat template")
        template_hash = template.get("sha256")
        if not isinstance(template_hash, str) or not _SHA256_RE.fullmatch(template_hash):
            raise ValueError("primary common chat template must have a SHA-256 digest")
        runtime_hashes = {model.runtime.chat_template_sha256 for model in models}
        if runtime_hashes != {template_hash.removeprefix("sha256:")}:
            raise ValueError("primary common chat template hash must match every model runtime")

    @staticmethod
    def _validate_judging(root: dict[str, Any]) -> None:
        judging = root.get("judging")
        if not isinstance(judging, dict):
            raise ValueError("study.judging must be an object")
        required = {
            "blinded_model_labels": True,
            "order_randomized": True,
            "target_models_may_not_judge": True,
            "disagreement_policy": "adjudicate-all",
        }
        for key, expected in required.items():
            if judging.get(key) != expected:
                raise ValueError(f"study.judging.{key} must be {expected!r}")
        primary = _required_string(judging, "primary_judge", "study.judging")
        adjudicator = _required_string(judging, "adjudicator", "study.judging")
        if primary == adjudicator:
            raise ValueError("primary judge and adjudicator must be distinct")
        calibration = judging.get("calibration")
        if not isinstance(calibration, dict):
            raise ValueError("study.judging.calibration must be an object")
        _required_positive_int(
            calibration, "human_double_labeled_items", "study.judging.calibration"
        )

    @classmethod
    def from_yaml(
        cls,
        path: str | Path,
        *,
        validate_registry: bool = True,
    ) -> StudyProtocol:
        protocol_path = Path(path)
        payload = protocol_path.read_bytes()
        data = yaml.safe_load(payload)
        if not isinstance(data, dict):
            raise ValueError("study protocol YAML must contain an object")
        return cls.from_dict(
            data,
            source_sha256=hashlib.sha256(payload).hexdigest(),
            validate_registry=validate_registry,
        )

    @property
    def canonical_sha256(self) -> str:
        """Hash the parsed protocol independent of YAML comments and formatting."""
        canonical = json.dumps(self.raw, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(canonical).hexdigest()

    def select_ids(
        self,
        allocation_id: str,
        canonical_ids: list[str],
        cohort: str,
        strata: dict[str, str] | None = None,
    ) -> list[str]:
        """Select stable ordered IDs so pilot is always nested in the full cohort."""
        if cohort not in {"pilot", "full"}:
            raise ValueError("cohort must be pilot or full")
        allocation = next(
            (item for item in self.benchmarks if item.id == allocation_id),
            None,
        )
        if allocation is None:
            raise ValueError(f"unknown benchmark allocation id: {allocation_id}")
        normalized = [str(sample_id) for sample_id in canonical_ids]
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"allocation {allocation_id} contains duplicate canonical IDs")
        count = allocation.pilot_samples if cohort == "pilot" else allocation.full_samples
        if len(normalized) < count:
            raise ValueError(
                f"allocation {allocation_id} has {len(normalized)} IDs but {count} are required"
            )

        def rank(sample_id: str) -> tuple[str, str]:
            digest = hashlib.sha256(
                f"{self.seed}\0{allocation_id}\0{sample_id}".encode()
            ).hexdigest()
            return digest, sample_id

        if allocation.selection_strategy == "sha256-ranked-v1":
            ranked = sorted(normalized, key=rank)
        else:
            if strata is None or set(strata) != set(normalized):
                raise ValueError(
                    f"allocation {allocation_id} requires one stratum for every canonical ID"
                )
            groups: dict[str, list[str]] = {}
            for sample_id in normalized:
                stratum = strata[sample_id]
                if not stratum:
                    raise ValueError(f"allocation {allocation_id} contains an empty stratum")
                groups.setdefault(stratum, []).append(sample_id)
            for group in groups.values():
                group.sort(key=rank)
            stratum_order = sorted(
                groups,
                key=lambda stratum: (
                    hashlib.sha256(f"{self.seed}\0{allocation_id}\0{stratum}".encode()).hexdigest(),
                    stratum,
                ),
            )
            ranked = []
            round_index = 0
            while len(ranked) < count:
                advanced = False
                for stratum in stratum_order:
                    if round_index < len(groups[stratum]):
                        ranked.append(groups[stratum][round_index])
                        advanced = True
                        if len(ranked) == count:
                            break
                if not advanced:
                    break
                round_index += 1
        return ranked[:count]

    def generation_seed(self, allocation_id: str, canonical_sample_id: str) -> int:
        """Derive the stable per-sample uint32 seed shared by every model."""
        payload = f"{self.seed}\0{allocation_id}\0{canonical_sample_id}".encode()
        return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")

    def selection_manifest(
        self,
        id_catalog: dict[str, list[Any]],
        cohort: str,
    ) -> dict[str, Any]:
        """Build a content-addressed ordered manifest from canonical dataset IDs."""
        catalog_payload = json.dumps(
            id_catalog,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        allocations = []
        for allocation in self.benchmarks:
            if allocation.id not in id_catalog:
                raise ValueError(f"ID catalog is missing allocation {allocation.id}")
            raw_entries = id_catalog[allocation.id]
            canonical_ids: list[str] = []
            strata: dict[str, str] | None = None
            if all(isinstance(entry, str) for entry in raw_entries):
                canonical_ids = [str(entry) for entry in raw_entries]
            elif all(isinstance(entry, dict) for entry in raw_entries):
                strata = {}
                for entry in raw_entries:
                    sample_id = entry.get("id")
                    stratum = entry.get("stratum")
                    if not isinstance(sample_id, str) or not isinstance(stratum, str):
                        raise ValueError(
                            f"ID catalog allocation {allocation.id} entries require string id/stratum"
                        )
                    canonical_ids.append(sample_id)
                    strata[sample_id] = stratum
            else:
                raise ValueError(
                    f"ID catalog allocation {allocation.id} must use all strings or all objects"
                )
            selected_ids = self.select_ids(
                allocation.id,
                canonical_ids,
                cohort,
                strata=strata,
            )
            ids_payload = "\n".join(selected_ids).encode()
            selected_strata: dict[str, int] | None = None
            if strata is not None:
                selected_strata = {}
                for sample_id in selected_ids:
                    stratum = strata[sample_id]
                    selected_strata[stratum] = selected_strata.get(stratum, 0) + 1
            allocations.append(
                {
                    "allocation_id": allocation.id,
                    "benchmark": allocation.benchmark,
                    "dataset_source": allocation.dataset_source,
                    "dataset_revision": allocation.dataset_revision,
                    "dataset_sha256": allocation.dataset_sha256,
                    "selection_strategy": allocation.selection_strategy,
                    "selected_strata": selected_strata,
                    "selected_ids": selected_ids,
                    "ordered_ids_sha256": hashlib.sha256(ids_payload).hexdigest(),
                }
            )
        manifest: dict[str, Any] = {
            "schema_version": "1",
            "study_id": self.id,
            "protocol_sha256": self.canonical_sha256,
            "cohort": cohort,
            "seed": self.seed,
            "selection_algorithm": "allocation-declared-v1",
            "catalog_sha256": hashlib.sha256(catalog_payload).hexdigest(),
            "allocations": allocations,
        }
        manifest_payload = json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        manifest["manifest_sha256"] = hashlib.sha256(manifest_payload).hexdigest()
        return manifest

    def summary(self) -> dict[str, Any]:
        """Return validation evidence suitable for a run manifest."""
        axis_totals: dict[str, dict[str, int]] = {}
        for axis in sorted(_AXES):
            matching = [item for item in self.benchmarks if item.axis == axis]
            axis_totals[axis] = {
                "pilot": sum(item.pilot_samples for item in matching),
                "full": sum(item.full_samples for item in matching),
            }
        return {
            "status": "valid",
            "study_id": self.id,
            "seed": self.seed,
            "models": [model.id for model in self.models],
            "model_count": len(self.models),
            "benchmarks": len(self.benchmarks),
            "samples_per_model": {
                "pilot": self.pilot_samples_per_model,
                "full": self.full_samples_per_model,
            },
            "total_generations": {
                "pilot": self.pilot_samples_per_model * len(self.models),
                "full": self.full_samples_per_model * len(self.models),
            },
            "axis_allocations": axis_totals,
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
        }
