"""Explicit, single-writer sample/trial recovery for the text-generate profile.

The journal authorizes reuse. A successful current commit receipt authorizes only
that dispatch's acceptance projection; unknown identities never authorize reuse.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from inspect_ai import Task, eval
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.log import read_eval_log
from inspect_ai.model import GenerateConfig, get_model

from matric_eval.core.execution_fingerprint import (
    capture_execution_fingerprint,
    validate_recovery_task,
)
from matric_eval.results.contract import (
    ArtifactReference,
    BenchmarkResult,
    MetricDescriptor,
    ObservationIdentity,
)
from matric_eval.results.inspect_adapter import adapt_log, sample_identity
from matric_eval.state.journal import (
    AttemptIntent,
    JournalError,
    ObservationJournal,
    TerminalAttempt,
)
from matric_eval.state.observation_identity import ReplayCapability, canonical_json


def _failure_reason(exc: Exception) -> str:
    """Never echo provider or validation exception content into the public report."""
    message = str(exc)
    if message.startswith("intent_without_reusable_acceptance:"):
        return "intent_without_reusable_acceptance"
    if message.startswith("frozen_plan_reuse_refused:"):
        return "frozen_plan_reuse_refused"
    known = {
        "native sample content does not match frozen dispatch": "native_sample_content_mismatch",
        "native generation configuration does not match effective dispatch identity": "native_generation_configuration_mismatch",
        "native model does not match effective dispatch identity": "native_model_identity_mismatch",
        "effective_identity_changed_during_dispatch": "effective_identity_changed_during_dispatch",
        "verified artifact digest mismatch": "native_artifact_digest_mismatch",
        "native direct metric set differs from durable intent": "native_metric_set_mismatch",
    }
    if message in known:
        return known[message]
    return (
        "journal_acceptance_unavailable"
        if isinstance(exc, JournalError)
        else "dispatch_or_native_evidence_unavailable"
    )


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _retain_native(source: Path, dispatch_dir: Path, destination: Path) -> ArtifactReference:
    source = source.resolve(strict=True)
    if not source.is_relative_to(dispatch_dir.resolve()) or not source.is_file():
        raise ValueError("native artifact is outside the owned dispatch directory")
    descriptor, temporary = tempfile.mkstemp(prefix=".native-", dir=destination)
    temporary_path = Path(temporary)
    digest = hashlib.sha256()
    try:
        with os.fdopen(descriptor, "wb") as target, source.open("rb") as origin:
            for chunk in iter(lambda: origin.read(1024 * 1024), b""):
                digest.update(chunk)
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        final = destination / f"{digest.hexdigest()}.eval"
        try:
            os.link(temporary_path, final)
        except FileExistsError:
            if hashlib.sha256(final.read_bytes()).hexdigest() != digest.hexdigest():
                raise ValueError("owned native artifact content conflict") from None
        _sync_directory(destination)
        return ArtifactReference(uri=str(final), sha256=digest.hexdigest(), unavailable_reason=None)
    finally:
        temporary_path.unlink(missing_ok=True)
        _sync_directory(destination)


def retain_legacy_state(paths: list[Path], directory: Path) -> list[dict[str, Any]]:
    """Retain original live-state bytes before other benchmarks mutate that state."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    _sync_directory(directory.parent)
    references = []
    for source in paths:
        if not source.exists():
            continue
        payload = source.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        destination = directory / f"{digest}.json"
        descriptor, temporary = tempfile.mkstemp(prefix=".state-", dir=directory)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, destination)
            except FileExistsError:
                if destination.read_bytes() != payload:
                    raise JournalError("historical state artifact conflict") from None
            _sync_directory(directory)
        finally:
            Path(temporary).unlink(missing_ok=True)
        references.append(
            {
                "source_uri": str(source.resolve()),
                "artifact": {
                    "uri": str(destination.resolve()),
                    "sha256": digest,
                    "unavailable_reason": None,
                },
            }
        )
    _sync_directory(directory)
    return references


def _project(
    artifact: ArtifactReference,
    *,
    run_id: str,
    model: str,
    benchmark: str,
    primary_metric_id: str,
    descriptors: dict[str, MetricDescriptor],
    sample_id: str,
    trial_id: str,
    attempt_id: str,
    effective_config: GenerateConfig,
    expected_sample: Sample,
) -> BenchmarkResult:
    # Decode retained bytes rather than trusting a mutable in-memory EvalLog.
    log = read_eval_log(artifact.uri)
    if len(log.samples or []) != 1:
        raise ValueError("native sample content does not match frozen dispatch")
    native_sample = (log.samples or [])[0]
    if (
        native_sample.input != expected_sample.input
        or native_sample.target != expected_sample.target
        or native_sample.choices != expected_sample.choices
        or native_sample.metadata != (expected_sample.metadata or {})
    ):
        raise ValueError("native sample content does not match frozen dispatch")
    if log.eval.model != model:
        raise ValueError("native model does not match effective dispatch identity")
    applied = log.eval.model_generate_config.model_dump(mode="json")
    if any(
        applied.get(key) != value
        for key, value in effective_config.model_dump(mode="json", exclude_none=True).items()
    ):
        raise ValueError(
            "native generation configuration does not match effective dispatch identity"
        )
    result = adapt_log(
        log,
        run_id=run_id,
        model_id=model,
        benchmark_id=benchmark,
        primary_metric_id=primary_metric_id,
        descriptors=descriptors,
    )
    if len(result.selection) != 1 or result.selection[0].sample_id != sample_id:
        raise ValueError("native manifest does not match the dispatched sample")
    if result.selection[0].trial_id != "epoch-1":
        raise ValueError("native execution must have exactly one epoch")
    result.selection[0].trial_id = trial_id
    for row in result.observations:
        if row.identity.sample_id != sample_id or row.identity.trial_id != "epoch-1":
            raise ValueError("unexpected native sample or epoch")
        row.identity = row.identity.model_copy(update={"trial_id": trial_id})
        row.observation_id = row.identity.logical_id()
        row.attempt_id = attempt_id
        row.previous_attempt_id = None
        row.artifacts = [artifact]
    return BenchmarkResult.model_validate(result.model_dump())


def run_recoverable(
    *,
    task: Task,
    benchmark: str,
    model: str,
    recovery_dir: Path,
    run_id: str,
    metric_descriptors: dict[str, MetricDescriptor],
    primary_metric_id: str,
    generation_seeds: list[int],
    selection_seed: int = 42,
    generation_config: GenerateConfig | None = None,
    model_base_url: str | None = None,
    model_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run frozen sample/trial scopes; refuse ambiguous automatic replay.

    A caller must retain run_id, directory, full task and seed schedule for reuse.
    Unverified first executions are accepted from their commit receipts, explicitly
    distinct from qualified later reuse. No cross-trial aggregate is produced.
    """
    if not run_id.strip() or not benchmark.strip() or not model.strip():
        raise ValueError("run, benchmark and model IDs must be nonempty")
    if (
        not generation_seeds
        or len(set(generation_seeds)) != len(generation_seeds)
        or any(
            type(seed) is not int or not 0 <= seed <= 9007199254740991
            for seed in [selection_seed, *generation_seeds]
        )
    ):
        raise ValueError("seeds must be unique nonnegative safe integers")
    if task.sample_source is not None:
        raise ValueError("dynamic sample sources are unsupported for frozen recovery")
    frozen = copy.deepcopy(task)
    samples = copy.deepcopy(list(frozen.dataset))
    frozen.dataset = MemoryDataset(
        copy.deepcopy(samples), name=frozen.dataset.name, location=frozen.dataset.location
    )
    validate_recovery_task(frozen)
    if not samples or any(type(sample.id) not in (str, int) for sample in samples):
        raise ValueError("recovery requires explicit integer or string sample IDs")
    sample_ids = []
    for sample in samples:
        assert isinstance(sample.id, (str, int))
        sample_ids.append(sample_identity(sample.id))
    if len(set(sample_ids)) != len(sample_ids):
        raise ValueError("duplicate sample identity")
    descriptors = copy.deepcopy(metric_descriptors)
    if primary_metric_id not in descriptors or any(
        key != item.metric_id or item.aggregation_id not in {"mean/1", "accuracy/1"}
        for key, item in descriptors.items()
    ):
        raise ValueError("recovery requires declared decomposable direct metrics")
    if len({item.scorer_id for item in descriptors.values()}) != len(descriptors):
        raise ValueError("recovery requires exactly one direct metric per scorer")
    config = (generation_config or frozen.config).model_copy(deep=True, update={"max_retries": 0})
    args = copy.deepcopy(model_args or {})
    directory = Path(recovery_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    _sync_directory(directory.parent)
    native_dir = directory / "native"
    native_dir.mkdir(exist_ok=True, mode=0o700)
    _sync_directory(directory)
    report: dict[str, Any] = {
        "recovery_schema_version": "1",
        "run_id": run_id,
        "model_id": model,
        "benchmark_id": benchmark,
        "generation_seeds": list(generation_seeds),
        "selection_seed": selection_seed,
        "recovery_status": "complete",
        "sample_results": [],
        "limitations": [
            "no_automatic_external_replay",
            "no_cross_trial_aggregate",
            "storage_power_loss_unqualified",
        ],
    }
    with (directory / ".engine.lock").open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise JournalError(
                "recovery execution already owned; do not dispatch concurrently"
            ) from exc
        with ObservationJournal(directory / "observations.sqlite") as journal:
            # Bind the whole frozen plan before dispatching any previously unseen
            # scope. Adding samples/trials must not bypass old-scope mismatch.
            plan_reasons: list[str] = []
            for existing in journal.list_attempts():
                intent = existing["intent"]
                identity = intent.identities[0]
                if (identity.run_id, identity.model_id, identity.benchmark_id) != (
                    run_id,
                    model,
                    benchmark,
                ):
                    continue
                prior_seed = intent.fingerprint.sampler.document.get("generation_seed")
                if type(prior_seed) is not int:
                    raise JournalError("retained_generation_seed_invalid")
                prior_trial = identity.trial_id
                current = capture_execution_fingerprint(
                    frozen,
                    benchmark=benchmark,
                    model=model,
                    metric_descriptors=descriptors,
                    generation_config=config.model_copy(update={"seed": prior_seed}),
                    selection_seed=selection_seed,
                    generation_seed=prior_seed,
                    trial_id=prior_trial,
                    generation_seeds=generation_seeds,
                    primary_metric_id=primary_metric_id,
                    model_base_url=model_base_url,
                    model_args=args,
                    effective_model=get_model(
                        model,
                        base_url=model_base_url,
                        config=config.model_copy(update={"seed": prior_seed}),
                        memoize=False,
                        **args,
                    ),
                )
                plan_reasons.extend(intent.fingerprint.mismatch_reasons(current))
            plan_reasons = sorted(set(plan_reasons))
            for index, seed in enumerate(generation_seeds):
                trial_id = f"trial-{index}"
                effective = config.model_copy(update={"seed": seed})
                effective_model = get_model(
                    model, base_url=model_base_url, config=effective, memoize=False, **args
                )
                validate_recovery_task(frozen)

                def capture() -> Any:
                    return capture_execution_fingerprint(
                        frozen,
                        benchmark=benchmark,
                        model=model,
                        metric_descriptors=descriptors,
                        generation_config=effective,
                        selection_seed=selection_seed,
                        generation_seed=seed,
                        trial_id=trial_id,
                        generation_seeds=generation_seeds,
                        primary_metric_id=primary_metric_id,
                        model_base_url=model_base_url,
                        model_args=args,
                        effective_model=effective_model,
                    )

                for sample, sid in zip(samples, sample_ids, strict=True):
                    fingerprint = capture()
                    scorer_names = {
                        item["name"].rsplit("/", 1)[-1]
                        for item in fingerprint.scorer.document.get("registered_scorers", [])
                    }
                    if scorer_names != {item.scorer_id for item in descriptors.values()}:
                        raise ValueError("declared direct scorers do not match the reviewed task")
                    identities = [
                        ObservationIdentity(
                            run_id=run_id,
                            model_id=model,
                            benchmark_id=benchmark,
                            allocation_id=benchmark,
                            sample_id=sid,
                            trial_id=trial_id,
                            metric_id=mid,
                        )
                        for mid in sorted(descriptors)
                    ]
                    entry: dict[str, Any] = {
                        "sample_id": sid,
                        "trial_id": trial_id,
                        "generation_seed": seed,
                        "fingerprint_sha256": fingerprint.sha256,
                        "reuse_eligibility": fingerprint.eligibility.model_dump(),
                        "disposition": "manual",
                        "reasons": [],
                        "attempt_id": None,
                        "acceptance_basis": None,
                        "observations": [],
                        "native_result": None,
                        "diagnostic_artifacts": [],
                    }
                    report["sample_results"].append(entry)
                    try:
                        if plan_reasons:
                            raise JournalError(
                                "frozen_plan_reuse_refused: " + ",".join(plan_reasons)
                            )
                        terminal = journal.load_accepted(identities, fingerprint)
                        if terminal is not None:
                            entry.update(
                                disposition="reused", acceptance_basis="qualified_journal_reuse"
                            )
                        else:
                            scope = identities[0].model_dump(exclude={"metric_id"})
                            previous = [
                                item
                                for item in journal.list_attempts()
                                if item["intent"].identities[0].model_dump(exclude={"metric_id"})
                                == scope
                            ]
                            if previous:
                                entry["attempt_id"] = previous[-1]["intent"].attempt_id
                                raise JournalError(
                                    "intent_without_reusable_acceptance: manual external reconciliation required"
                                )
                            attempt_id = str(uuid.uuid4())
                            entry["attempt_id"] = attempt_id
                            journal.record_intent(
                                AttemptIntent(
                                    attempt_id=attempt_id,
                                    identities=identities,
                                    fingerprint=fingerprint,
                                    replay_capability=ReplayCapability(
                                        adapter_id="inspect-text-generate",
                                        mode="manual",
                                        mechanism_version="1",
                                    ),
                                )
                            )
                            dispatch_dir = directory / "dispatch" / attempt_id
                            dispatch_dir.mkdir(parents=True, mode=0o700)
                            instance = copy.deepcopy(frozen)
                            instance.dataset = MemoryDataset(
                                [copy.deepcopy(sample)],
                                name=frozen.dataset.name,
                                location=frozen.dataset.location,
                            )
                            instance.epochs = 1
                            instance.epochs_reducer = None
                            instance.config = effective.model_copy(deep=True)
                            validate_recovery_task(instance)
                            logs = eval(
                                instance,
                                model=effective_model,
                                log_dir=str(dispatch_dir),
                                log_format="eval",
                                epochs=1,
                                sample_shuffle=False,
                                retry_on_error=0,
                                checkpoint=False,
                                max_samples=1,
                                display="none",
                                **effective.model_dump(exclude_none=True),
                            )
                            if len(logs) != 1 or not logs[0].location:
                                raise ValueError(
                                    "dispatch did not return exactly one native artifact"
                                )
                            artifact = _retain_native(
                                Path(logs[0].location), dispatch_dir, native_dir
                            )
                            entry["diagnostic_artifacts"] = [artifact.model_dump()]
                            after = capture()
                            if after.model_dump() != fingerprint.model_dump():
                                raise ValueError("effective_identity_changed_during_dispatch")
                            measured = _project(
                                artifact,
                                run_id=run_id,
                                model=model,
                                benchmark=benchmark,
                                primary_metric_id=primary_metric_id,
                                descriptors=descriptors,
                                sample_id=sid,
                                trial_id=trial_id,
                                attempt_id=attempt_id,
                                effective_config=effective,
                                expected_sample=sample,
                            )
                            if {row.identity.metric_id for row in measured.observations} != set(
                                descriptors
                            ):
                                raise ValueError(
                                    "native direct metric set differs from durable intent"
                                )
                            terminal = TerminalAttempt(
                                attempt_id=attempt_id,
                                observations=measured.observations,
                                artifacts=[artifact],
                                cleanup=None,
                            )
                            receipt = journal.commit_terminal(terminal)
                            terminal = TerminalAttempt.model_validate(terminal.model_dump())
                            for row in terminal.observations:
                                row.accepted = False
                            digest = hashlib.sha256(
                                canonical_json(terminal.model_dump()).encode()
                            ).hexdigest()
                            if receipt.payload_sha256 != digest or set(receipt.observation_ids) != {
                                row.observation_id for row in terminal.observations
                            }:
                                raise JournalError(
                                    "acceptance receipt does not bind the complete terminal"
                                )
                            for row in terminal.observations:
                                row.accepted = True
                            entry.update(
                                disposition="executed",
                                acceptance_basis="same_dispatch_commit_receipt",
                            )
                        entry["attempt_id"] = terminal.attempt_id
                        native = _project(
                            terminal.artifacts[0],
                            run_id=run_id,
                            model=model,
                            benchmark=benchmark,
                            primary_metric_id=primary_metric_id,
                            descriptors=descriptors,
                            sample_id=sid,
                            trial_id=trial_id,
                            attempt_id=terminal.attempt_id,
                            effective_config=effective,
                            expected_sample=sample,
                        )
                        if [
                            row.model_dump(exclude={"accepted"}) for row in native.observations
                        ] != [
                            row.model_dump(exclude={"accepted"}) for row in terminal.observations
                        ]:
                            raise JournalError(
                                "accepted measurements differ from retained native artifact"
                            )
                        entry["observations"] = [row.model_dump() for row in terminal.observations]
                        entry["native_result"] = native.model_dump()
                    except Exception as exc:
                        entry.update(
                            disposition="manual",
                            acceptance_basis=None,
                            observations=[],
                            native_result=None,
                        )
                        entry["reasons"] = [_failure_reason(exc)]
                        report["recovery_status"] = "manual_recovery_required"
    entries = report["sample_results"]
    captured = all(item["native_result"] is not None for item in entries)
    completed = sum(
        item["native_result"] is not None and item["native_result"]["execution"] == "completed"
        for item in entries
    )
    report["journal_capture_complete"] = captured
    report["execution"] = (
        "completed"
        if completed == len(entries)
        else "partial"
        if completed
        else "failed"
        if captured
        else "unknown"
    )
    report["status"] = (
        "success" if report["execution"] == "completed" else "partial" if completed else "error"
    )
    reasons = []
    if not captured:
        reasons.append("recovery_incomplete")
    if completed != len(entries):
        reasons.append("execution_incomplete")
    if any(
        item["native_result"] is not None and not item["native_result"]["eligibility"]["eligible"]
        for item in entries
    ):
        reasons.append("native_measurement_ineligible")
    if any(not item["reuse_eligibility"]["eligible"] for item in entries):
        reasons.append("effective_identity_unverified")
    report["eligibility"] = {"eligible": not reasons, "reasons": reasons}
    return report
