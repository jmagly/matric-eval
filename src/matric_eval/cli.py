"""
matric-eval CLI - Model evaluation runner.

Click-based CLI with rich progress reporting and JSON output support.
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import click
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from matric_eval.config import get_seed, get_settings, get_tier
from matric_eval.core.engine import EvaluationEngine
from matric_eval.logging import (
    EvalLogger,
    configure_logging,
    get_logger,
    set_context,
)
from matric_eval.models.detection import has_thinking_capability
from matric_eval.providers import get_provider, list_providers
from matric_eval.providers.base import ProviderConfig, ProviderConnectionError
from matric_eval.state import StateManager
from matric_eval.state.manager import Status
from matric_eval.version import __version__

console = Console()
error_console = Console(stderr=True)

# Global logger instance
_cli_logger: EvalLogger | None = None


def get_cli_logger() -> EvalLogger:
    """Get CLI logger (initializes if needed)."""
    global _cli_logger
    if _cli_logger is None:
        _cli_logger = get_logger("cli")
    return _cli_logger


# =============================================================================
# Model Discovery
# =============================================================================


def get_ollama_models(max_size_gb: float = 15.0) -> list[dict]:
    """
    Query Ollama for available models under size threshold.

    Args:
        max_size_gb: Maximum model size in GB

    Returns:
        List of model dictionaries with name, size_gb, and size_str
    """
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        error_console.print(f"[red]Error querying Ollama:[/red] {e}")
        return []
    except FileNotFoundError:
        error_console.print("[red]Ollama not found. Is it installed?[/red]")
        return []

    models = []
    lines = result.stdout.strip().split("\n")[1:]  # Skip header

    for line in lines:
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 3:
            name = parts[0]

            # Parse size (e.g., "5.0 GB", "986 MB")
            try:
                size_val = float(parts[2])
                size_unit = parts[3] if len(parts) > 3 else "GB"

                if size_unit == "MB":
                    size_gb = size_val / 1024
                elif size_unit == "GB":
                    size_gb = size_val
                else:
                    size_gb = size_val

                if size_gb <= max_size_gb:
                    models.append(
                        {
                            "name": name,
                            "size_gb": round(size_gb, 2),
                            "size_str": f"{size_val} {size_unit}",
                        }
                    )
            except (ValueError, IndexError):
                continue

    # Filter out embedding models by default
    return filter_models(models)


def filter_models(models: list[dict], exclude_patterns: list[str] | None = None) -> list[dict]:
    """
    Filter out embedding models and other non-chat models.

    Args:
        models: List of model dictionaries
        exclude_patterns: Patterns to exclude (defaults to common embedding models)

    Returns:
        Filtered list of models
    """
    exclude_patterns = exclude_patterns or [
        "embed",
        "snowflake",
        "nomic",
        "minilm",
        "mxbai",
    ]

    filtered = []
    for model in models:
        name_lower = model["name"].lower()
        if not any(pat in name_lower for pat in exclude_patterns):
            filtered.append(model)

    return filtered


# =============================================================================
# Benchmark Discovery
# =============================================================================


def get_available_benchmarks(with_descriptions: bool = False) -> list[str] | dict[str, str]:
    """
    Get list of available benchmarks from the task registry.

    Args:
        with_descriptions: If True, return dict mapping names to descriptions

    Returns:
        List of benchmark names or dict with descriptions
    """
    # Ensure all task modules are imported (triggers @register_benchmark decorators)
    import matric_eval.tasks  # noqa: F401
    from matric_eval.tasks.registry import get_registry

    registry = get_registry()
    benchmarks_info = registry.get_descriptions()
    for metadata in registry.list_metadata():
        if metadata.status.value != "stable":
            reason = f": {metadata.status_reason}" if metadata.status_reason else ""
            benchmarks_info[metadata.name] = (
                f"[{metadata.status.value}{reason}] {metadata.description}"
            )

    # Discover external datasets
    try:
        from matric_eval.discovery import get_external_datasets

        for name, dataset in get_external_datasets().items():
            if name not in benchmarks_info:  # Registered benchmarks take priority
                display_name = dataset.manifest.name or name
                desc = (
                    dataset.manifest.description
                    or f"{display_name} - External dataset ({dataset.total_samples:,} samples)"
                )
                benchmarks_info[name] = desc
    except Exception:
        pass  # Discovery failure shouldn't break CLI

    if with_descriptions:
        return benchmarks_info
    return list(benchmarks_info.keys())


# =============================================================================
# Evaluation Runner
# =============================================================================


@dataclass(frozen=True)
class EvaluationTarget:
    """A stable execution target used for checkpoint identity and resume."""

    checkpoint_model: str
    model: str
    thinking_mode: str | None = None

    def as_metadata(self) -> dict[str, str | None]:
        """Serialize the non-secret target configuration."""
        return {
            "checkpoint_model": self.checkpoint_model,
            "model": self.model,
            "thinking_mode": self.thinking_mode,
        }


def _resolve_benchmarks(tier: str, selected: tuple[str, ...] = ()) -> list[str]:
    """Resolve a concrete benchmark list for immutable run metadata."""
    if selected:
        return list(selected)

    tier_config = get_tier(tier)
    available = get_available_benchmarks()
    if not isinstance(available, list):
        raise TypeError("Benchmark discovery returned descriptions instead of names")
    return [name for name in available if getattr(tier_config, name, 0) > 0]


def _thinking_modes(model: str, thinking: str) -> list[str | None]:
    """Resolve configured thinking modes for one model."""
    if thinking == "auto":
        return ["off"] if has_thinking_capability(model) else [None]
    if thinking == "both":
        return ["on", "off"] if has_thinking_capability(model) else [None]
    if thinking in ("on", "off"):
        return [thinking]
    return [None]


def _build_targets(models: list[dict[str, Any]], thinking: str) -> list[EvaluationTarget]:
    """Build checkpoint-safe targets from discovered models."""
    targets: list[EvaluationTarget] = []
    for model_info in models:
        model = str(model_info["name"])
        for thinking_mode in _thinking_modes(model, thinking):
            checkpoint_model = model
            if thinking_mode is not None:
                checkpoint_model = f"{model}#thinking={thinking_mode}"
            targets.append(
                EvaluationTarget(
                    checkpoint_model=checkpoint_model,
                    model=model,
                    thinking_mode=thinking_mode,
                )
            )
    return targets


def _load_targets(metadata: dict[str, Any], models: list[str]) -> list[EvaluationTarget]:
    """Load target configuration, with compatibility for legacy checkpoints."""
    configuration = metadata.get("configuration", {})
    records = configuration.get("targets", []) if isinstance(configuration, dict) else []
    if not records:
        return [EvaluationTarget(checkpoint_model=model, model=model) for model in models]

    targets = [
        EvaluationTarget(
            checkpoint_model=str(record["checkpoint_model"]),
            model=str(record["model"]),
            thinking_mode=record.get("thinking_mode"),
        )
        for record in records
    ]
    if {target.checkpoint_model for target in targets} != set(models):
        raise ValueError("Checkpoint targets do not match run state models")
    return targets


def _result_path(output_dir: Path, target: EvaluationTarget) -> Path:
    """Return the stable result path for an execution target."""
    safe_name = target.checkpoint_model
    for character in (":", "/", "#", "="):
        safe_name = safe_name.replace(character, "_")
    return output_dir / f"{safe_name}.json"


def _create_provider(
    provider_name: str | None,
    provider_url: str | None,
    api_key: str | None,
) -> Any:
    """Create a provider without persisting credentials in run metadata."""
    if provider_name is None:
        return None

    config = ProviderConfig()
    if provider_url:
        config.base_url = provider_url
    if api_key:
        config.api_key = api_key
    try:
        return get_provider(provider_name, config)
    except ValueError as exc:
        choices = ", ".join(list_providers())
        raise click.ClickException(f"{exc}. Available providers: {choices}") from exc


def run_evaluation(
    model: str,
    tier: str = "smoke",
    benchmarks: Optional[list[str]] = None,
    output_dir: Optional[Path] = None,
    thinking_mode: Optional[str] = None,
    provider: Any = None,
    judge_spec: Optional[str] = None,
    state_manager: StateManager | None = None,
    checkpoint_model: str | None = None,
) -> dict[str, Any]:
    """
    Run evaluation using the synchronous engine.

    Args:
        model: Model name (e.g., 'llama3.2:3b')
        tier: Evaluation tier (smoke, quick, full)
        benchmarks: Specific benchmarks to run (None = all for tier)
        output_dir: Output directory for logs
        thinking_mode: Thinking mode ("on", "off", or None)
        provider: Provider instance. If None, defaults to Ollama behavior.
        judge_spec: Optional judge specification (e.g., "ollama:llama3.1:8b")
        state_manager: Optional persistent run checkpoint
        checkpoint_model: Stable target key used by the checkpoint

    Returns:
        Results dictionary
    """
    # If no provider given, use legacy ollama/ prefix behavior
    if provider is None:
        if not model.startswith("ollama/"):
            model = f"ollama/{model}"

    # Determine which benchmarks to run
    if benchmarks is None:
        # Run all benchmarks with samples > 0 in this tier
        tier_config = get_tier(tier)
        benchmarks = [
            name for name in get_available_benchmarks() if getattr(tier_config, name, 0) > 0
        ]

    # Create engine and run
    engine = EvaluationEngine(
        model=model,
        tier=tier,
        log_dir=output_dir / "logs" if output_dir else None,
        thinking_mode=thinking_mode,
        provider=provider,
        judge_spec=judge_spec,
    )

    return engine.run_all(
        benchmarks,
        checkpoint=state_manager is not None,
        state_manager=state_manager,
        checkpoint_model=checkpoint_model,
    )


def _execute_targets(
    targets: list[EvaluationTarget],
    benchmark_plan: dict[str, list[str]],
    tier: str,
    output_dir: Path,
    output_format: str,
    provider: Any,
    judge_spec: str | None,
    state_manager: StateManager,
) -> list[dict[str, Any]]:
    """Execute fresh or resumed targets through the same engine path."""
    logger = get_cli_logger()
    all_results: list[dict[str, Any]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console if output_format != "json" else None,
        disable=output_format == "json",
    ) as progress:
        task = progress.add_task(f"Evaluating {len(targets)} target(s)...", total=len(targets))

        for target in targets:
            set_context(model=target.model)
            benchmarks = benchmark_plan[target.checkpoint_model]
            logger.info(
                "Starting model evaluation",
                extra={
                    "model": target.model,
                    "checkpoint_model": target.checkpoint_model,
                    "tier": tier,
                    "benchmarks": benchmarks,
                },
            )
            if output_format != "json":
                progress.update(task, description=f"Evaluating {target.checkpoint_model}...")

            try:
                result = run_evaluation(
                    model=target.model,
                    tier=tier,
                    benchmarks=benchmarks,
                    output_dir=output_dir,
                    thinking_mode=target.thinking_mode,
                    provider=provider,
                    judge_spec=judge_spec,
                    state_manager=state_manager,
                    checkpoint_model=target.checkpoint_model,
                )
                result.setdefault("checkpoint_model", target.checkpoint_model)
                all_results.append(result)
                _result_path(output_dir, target).write_text(json.dumps(result, indent=2))

                logger.info(
                    "Model evaluation complete",
                    extra={
                        "model": target.model,
                        "checkpoint_model": target.checkpoint_model,
                        "overall_score": result.get("overall_score", 0),
                        "status": result.get("status"),
                        "thinking_mode": target.thinking_mode,
                    },
                )
            except Exception as exc:
                logger.error(
                    "Model evaluation failed",
                    extra={
                        "model": target.model,
                        "checkpoint_model": target.checkpoint_model,
                        "error": str(exc),
                    },
                    exc_info=True,
                )
                error_result = {
                    "model": target.model,
                    "checkpoint_model": target.checkpoint_model,
                    "tier": tier,
                    "status": "error",
                    "error": str(exc),
                }
                all_results.append(error_result)
                if output_format != "json":
                    raise click.ClickException(
                        f"Error evaluating {target.checkpoint_model}: {exc}"
                    ) from exc
            finally:
                progress.advance(task)

    return all_results


# =============================================================================
# CLI Commands
# =============================================================================


@click.group()
@click.version_option(version=__version__)
@click.option(
    "--log-level",
    type=click.Choice(["debug", "info", "warning", "error"], case_sensitive=False),
    default="info",
    help="Set logging level (default: info)",
)
@click.option(
    "--log-json",
    is_flag=True,
    help="Output logs in JSON format (useful for log aggregation)",
)
@click.option(
    "--log-file",
    type=click.Path(path_type=Path),
    help="Write logs to file in addition to console",
)
@click.pass_context
def cli(ctx: click.Context, log_level: str, log_json: bool, log_file: Path | None):
    """
    matric-eval - Consolidated model evaluation framework.

    Evaluate LLM models across multiple providers using standardized benchmarks.
    """
    # Store config in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["log_level"] = log_level
    ctx.obj["log_json"] = log_json
    ctx.obj["log_file"] = log_file

    # Configure logging
    configure_logging(
        level=log_level.upper(),
        console=True,
        file=str(log_file) if log_file else None,
        json_format=log_json,
        color=not log_json,
    )

    logger = get_cli_logger()
    logger.debug("CLI initialized", extra={"level": log_level, "json_mode": log_json})


@cli.command()
@click.option(
    "--tier",
    type=click.Choice(["smoke", "quick", "full"], case_sensitive=False),
    default="smoke",
    help="Evaluation tier (smoke=5 samples, quick=75, full=all)",
)
@click.option(
    "--model",
    type=str,
    help=(
        "Specific model to evaluate (e.g., llama3.2:3b). "
        "If omitted, evaluates all models under --max-size."
    ),
)
@click.option(
    "--benchmark",
    type=str,
    multiple=True,
    help=(
        "Specific benchmark(s) to run. May be repeated. "
        "If omitted, runs all benchmarks for the tier."
    ),
)
@click.option(
    "--max-size",
    type=float,
    default=15.0,
    help="Maximum model size in GB (default: 15.0)",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default="results",
    help="Output directory for results (default: ./results)",
)
@click.option(
    "--output-format",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    help="Output format (default: table)",
)
@click.option(
    "--thinking",
    type=click.Choice(["auto", "on", "off", "both"], case_sensitive=False),
    default="auto",
    help=("Thinking mode for capable models (auto=detect, on=enable, off=disable, both=run twice)"),
)
@click.option(
    "--provider",
    "provider_name",
    type=str,
    default=None,
    help="Inference provider (ollama, llama-cpp, vllm, openrouter, chutes). Default: ollama.",
)
@click.option(
    "--provider-url",
    type=str,
    default=None,
    help="Override the provider's base URL (e.g., http://localhost:8080)",
)
@click.option(
    "--api-key",
    type=str,
    default=None,
    help="API key for authenticated providers (openrouter, chutes). Can also use env vars.",
)
@click.option(
    "--matrix",
    "matrix_file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="YAML evaluation matrix config file for multi-provider runs.",
)
@click.option(
    "--judge",
    "judge_spec",
    type=str,
    default=None,
    help=(
        "LLM judge for subjective evaluation (e.g., ollama:llama3.1:8b). "
        "Adds judge scoring alongside deterministic scorers."
    ),
)
@click.option(
    "--resume",
    type=str,
    help="Resume from checkpoint (provide run-id or path to run directory)",
)
@click.option(
    "--fill-gaps",
    is_flag=True,
    help="When resuming, only fill gaps (incomplete/missing benchmarks)",
)
def run(
    tier: str,
    model: Optional[str],
    benchmark: tuple[str, ...],
    max_size: float,
    output: Path,
    output_format: str,
    thinking: str,
    provider_name: Optional[str],
    provider_url: Optional[str],
    api_key: Optional[str],
    matrix_file: Optional[Path],
    judge_spec: Optional[str],
    resume: Optional[str],
    fill_gaps: bool,
):
    """
    Run model evaluation.

    Examples:

        # Run smoke test on specific model
        matric-eval run --tier smoke --model llama3.2:3b

        # Run quick evaluation on all small models
        matric-eval run --tier quick --max-size 5.0

        # Run specific benchmark only
        matric-eval run --tier smoke --model llama3.2:3b --benchmark humaneval

        # Resume from checkpoint
        matric-eval run --resume run-2024-01-20T10-30-00

        # Fill gaps in incomplete run
        matric-eval run --resume run-2024-01-20T10-30-00 --fill-gaps

        # Output as JSON
        matric-eval run --tier smoke --model llama3.2:3b --output-format json
    """
    # Suppress console logging when JSON output is requested (clean stdout)
    if output_format == "json":
        configure_logging(level="ERROR", console=False)

    logger = get_cli_logger()

    # Handle matrix-based evaluation
    if matrix_file:
        if resume:
            raise click.UsageError("--matrix and --resume cannot be used together")
        from matric_eval.providers.matrix import EvaluationMatrix

        matrix = EvaluationMatrix.from_yaml(matrix_file)
        _run_matrix_evaluation(matrix, output, output_format, thinking, tier)
        return

    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")

    if resume:
        logger.info("Attempting to resume run", extra={"resume_path": resume})
        output_dir = Path(resume) if Path(resume).is_dir() else output / resume
        if not output_dir.exists():
            raise click.ClickException(f"Run directory not found: {output_dir}")

        state_manager = StateManager(output_dir)
        try:
            run_state = state_manager.load_run_state()
            metadata = state_manager.load_metadata()
        except Exception as exc:
            raise click.ClickException(f"Invalid checkpoint state at {output_dir}: {exc}") from exc

        if run_state.status == Status.COMPLETED:
            raise click.ClickException(f"Run is already complete: {run_state.run_id}")
        if state_manager.is_locked():
            raise click.ClickException(
                f"Run is locked: {state_manager.lock_file}. "
                "Use 'matric-eval validate <run> --force-unlock' only for a stale lock."
            )

        configuration = metadata.get("configuration", {})
        if not isinstance(configuration, dict):
            raise click.ClickException("Invalid checkpoint configuration")

        stored_provider = configuration.get("provider")
        if provider_name is not None and "provider" in configuration:
            if provider_name != stored_provider:
                raise click.ClickException("--provider does not match the checkpoint")
        effective_provider_name = provider_name or stored_provider

        stored_provider_url = configuration.get("provider_url")
        if provider_url is not None and stored_provider_url not in (None, provider_url):
            raise click.ClickException("--provider-url does not match the checkpoint")
        effective_provider_url = provider_url or stored_provider_url

        stored_judge = configuration.get("judge_spec")
        if judge_spec is not None and stored_judge not in (None, judge_spec):
            raise click.ClickException("--judge does not match the checkpoint")
        effective_judge = judge_spec or stored_judge

        active_provider = _create_provider(
            str(effective_provider_name) if effective_provider_name else None,
            str(effective_provider_url) if effective_provider_url else None,
            api_key,
        )
        try:
            targets = _load_targets(metadata, run_state.models)
        except (KeyError, TypeError, ValueError) as exc:
            raise click.ClickException(f"Invalid checkpoint configuration: {exc}") from exc
        resume_work = state_manager.get_resume_work()
        if not resume_work:
            state_manager.refresh_run_progress()
            console.print("[green]No gaps found - run is complete.[/green]")
            return

        heading = "RESUMING RUN - FILLING GAPS" if fill_gaps else "RESUMING RUN"
        if output_format != "json":
            console.print(f"\n[bold]{heading}[/bold]")
            console.print("Checkpoint granularity: benchmark")
            console.print(f"Run directory: {output_dir}\n")
            for checkpoint_model, benchmarks in resume_work.items():
                console.print(f"  {checkpoint_model}: {', '.join(benchmarks)}")
            console.print()

        targets_to_run = [target for target in targets if target.checkpoint_model in resume_work]
        benchmark_plan = {
            target.checkpoint_model: run_state.benchmarks for target in targets_to_run
        }
        try:
            state_manager.acquire_lock()
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from exc
        settings = get_settings()
        previous_seed = settings.seed
        settings.seed = run_state.seed
        try:
            _execute_targets(
                targets_to_run,
                benchmark_plan,
                run_state.tier,
                output_dir,
                output_format,
                active_provider,
                str(effective_judge) if effective_judge else None,
                state_manager,
            )
            state_manager.refresh_run_progress()
            all_results = [
                state_manager.build_model_result(target.checkpoint_model, target.model)
                for target in targets
            ]
            for target, result in zip(targets, all_results, strict=True):
                _result_path(output_dir, target).write_text(json.dumps(result, indent=2))
        finally:
            settings.seed = previous_seed
            state_manager.release_lock()
        tier = run_state.tier
    else:
        active_provider = _create_provider(provider_name, provider_url, api_key)
        logger.info("Discovering models", extra={"max_size_gb": max_size, "specific_model": model})

        if model:
            models_to_eval = [{"name": model, "size_gb": 0, "size_str": "unknown"}]
        elif active_provider:
            try:
                provider_models = active_provider.list_models(max_size_gb=max_size)
            except ProviderConnectionError as exc:
                raise click.ClickException(
                    f"Error querying {active_provider.display_name}: {exc}"
                ) from exc
            models_to_eval = [
                {"name": item.name, "size_gb": item.size_gb, "size_str": f"{item.size_gb} GB"}
                for item in provider_models
            ]
        else:
            models_to_eval = get_ollama_models(max_size)

        if not models_to_eval:
            raise click.ClickException("No models found to evaluate")

        benchmarks_to_run = _resolve_benchmarks(tier, benchmark)
        if not benchmarks_to_run:
            raise click.ClickException(f"No benchmarks are enabled for tier '{tier}'")
        targets = _build_targets(models_to_eval, thinking)
        output_dir = output / f"run-{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)

        state_manager = StateManager(output_dir)
        state_manager.initialize_run(
            run_id=output_dir.name,
            tier=tier,
            seed=get_seed(),
            models=[target.checkpoint_model for target in targets],
            benchmarks=benchmarks_to_run,
            metadata={
                "targets": [target.as_metadata() for target in targets],
                "provider": provider_name,
                "provider_url": provider_url,
                "judge_spec": judge_spec,
                "thinking": thinking,
            },
        )

        logger.info(
            "Starting evaluation run",
            extra={
                "tier": tier,
                "targets": len(targets),
                "benchmarks": benchmarks_to_run,
                "output_dir": str(output_dir),
            },
        )
        if output_format != "json":
            console.print(f"\n[bold]MATRIC-EVAL - {tier.upper()} tier[/bold]")
            console.print(f"Targets: {len(targets)}")
            console.print(f"Max size: {max_size}GB")
            console.print(f"Output: {output_dir}")
            console.print(f"Benchmarks: {', '.join(benchmarks_to_run)}")
            if judge_spec:
                console.print(f"Judge: {judge_spec}")
            console.print()

        benchmark_plan = {target.checkpoint_model: benchmarks_to_run for target in targets}
        try:
            all_results = _execute_targets(
                targets,
                benchmark_plan,
                tier,
                output_dir,
                output_format,
                active_provider,
                judge_spec,
                state_manager,
            )
        finally:
            state_manager.release_lock()

    # Save summary
    successful = len([r for r in all_results if r.get("status") == "success"])
    failed = len([r for r in all_results if r.get("status") == "error"])

    summary = {
        "timestamp": timestamp,
        "tier": tier,
        "models_evaluated": len(all_results),
        "successful": successful,
        "failed": failed,
        "output_dir": str(output_dir),
        "results": all_results,
    }

    summary_file = output_dir / "summary.json"
    summary_file.write_text(json.dumps(summary, indent=2))

    logger.info(
        "Evaluation run complete",
        extra={
            "models_evaluated": len(all_results),
            "successful": successful,
            "failed": failed,
            "output_dir": str(output_dir),
        },
    )

    # Output results
    if output_format == "json":
        # For single model, output just the result; for multiple, output summary
        if len(all_results) == 1:
            console.print(json.dumps({**all_results[0], "output_dir": str(output_dir)}, indent=2))
        else:
            console.print(json.dumps(summary, indent=2))
    else:
        # Table output
        console.print("\n[bold]RESULTS SUMMARY[/bold]")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Rank", style="dim", width=6)
        table.add_column("Model", style="cyan")
        table.add_column("Overall Score", justify="right")
        table.add_column("Status", justify="center")

        # Sort by overall score
        ranked = sorted(
            [r for r in all_results if r.get("status") == "success"],
            key=lambda x: x.get("overall_score", 0),
            reverse=True,
        )

        for i, result in enumerate(ranked[:10], 1):
            score = result.get("overall_score", 0)
            score_str = f"{score:.1%}"
            status = "[green]✓[/green]" if result.get("status") == "success" else "[red]✗[/red]"

            # Extract model name (remove ollama/ prefix if present)
            model_display = result["model"].replace("ollama/", "")

            table.add_row(
                f"#{i}",
                model_display,
                score_str,
                status,
            )

        console.print(table)
        console.print(f"\n[dim]Results saved to: {output_dir}[/dim]")


@cli.command()
@click.argument("run_id")
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default="results",
    help="Results directory (default: ./results)",
)
@click.option(
    "--force-unlock",
    is_flag=True,
    help="Force unlock if lock file exists",
)
@click.option(
    "--output-format",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    help="Output format (default: table)",
)
def validate(
    run_id: str,
    output: Path,
    force_unlock: bool,
    output_format: str,
):
    """
    Validate run completeness and check for gaps.

    Examples:

        # Check run completeness
        matric-eval validate run-2024-01-20T10-30-00

        # Force unlock stale lock
        matric-eval validate run-2024-01-20T10-30-00 --force-unlock

        # Output as JSON
        matric-eval validate run-2024-01-20T10-30-00 --output-format json
    """
    # Determine run directory
    if Path(run_id).is_dir():
        run_dir = Path(run_id)
    else:
        run_dir = output / run_id

    if not run_dir.exists():
        error_console.print(f"[red]Error:[/red] Run directory not found: {run_dir}")
        sys.exit(1)

    # Load state manager
    state_manager = StateManager(run_dir)

    # Handle force unlock
    if force_unlock:
        if state_manager.is_locked():
            state_manager.release_lock(force=True)
            console.print(f"[green]Lock released:[/green] {state_manager.lock_file}")
        else:
            console.print("[yellow]No lock file found[/yellow]")

    # Load run state
    try:
        run_state = state_manager.load_run_state()
    except FileNotFoundError:
        error_console.print(f"[red]Error:[/red] No state file found in {run_dir}")
        sys.exit(1)

    # Find gaps
    gaps = state_manager.find_gaps()

    validation_result = {
        "run_id": run_state.run_id,
        "tier": run_state.tier,
        "status": run_state.status.value,
        "started_at": run_state.started_at,
        "updated_at": run_state.updated_at,
        "total_models": len(run_state.models),
        "total_benchmarks": len(run_state.benchmarks),
        "is_complete": len(gaps) == 0,
        "gaps": gaps,
        "is_locked": state_manager.is_locked(),
    }

    if output_format == "json":
        console.print(json.dumps(validation_result, indent=2))
    else:
        # Table output
        console.print(f"\n[bold]RUN VALIDATION: {run_state.run_id}[/bold]\n")

        info_table = Table(show_header=False)
        info_table.add_column("Field", style="cyan")
        info_table.add_column("Value")

        info_table.add_row("Tier", run_state.tier)
        info_table.add_row("Status", run_state.status.value)
        info_table.add_row("Started", run_state.started_at)
        info_table.add_row("Updated", run_state.updated_at)
        info_table.add_row("Models", str(len(run_state.models)))
        info_table.add_row("Benchmarks", str(len(run_state.benchmarks)))
        info_table.add_row("Locked", "Yes" if state_manager.is_locked() else "No")

        console.print(info_table)
        console.print()

        if gaps:
            console.print("[yellow]GAPS FOUND:[/yellow]\n")

            gaps_table = Table(show_header=True, header_style="bold yellow")
            gaps_table.add_column("Model", style="cyan")
            gaps_table.add_column("Benchmark")
            gaps_table.add_column("Status")
            gaps_table.add_column("Progress", justify="right")

            for model, benchmarks in gaps.items():
                for benchmark, gap_info in benchmarks.items():
                    status = gap_info["status"]
                    if status == "not_started":
                        progress = "0/0"
                    else:
                        progress = f"{gap_info['completed']}/{gap_info['total']}"

                    gaps_table.add_row(model, benchmark, status, progress)

            console.print(gaps_table)
            console.print(
                "\n[yellow]Run is incomplete. Use --resume --fill-gaps to complete.[/yellow]"
            )
        else:
            console.print("[green]Run is complete - no gaps found![/green]")


@cli.command("list-models")
@click.option(
    "--max-size",
    type=float,
    default=15.0,
    help="Maximum model size in GB (default: 15.0)",
)
@click.option(
    "--output-format",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    help="Output format (default: table)",
)
def list_models(max_size: float, output_format: str):
    """
    List available Ollama models.

    Examples:

        # List all models under 15GB
        matric-eval list-models

        # List only small models
        matric-eval list-models --max-size 5.0

        # Output as JSON
        matric-eval list-models --output-format json
    """
    models = get_ollama_models(max_size)

    if not models:
        error_console.print("[red]No models found.[/red]")
        error_console.print("Try running: [bold]ollama pull llama3.2:3b[/bold]")
        sys.exit(1)

    if output_format == "json":
        console.print(json.dumps(models, indent=2))
    else:
        console.print(f"\n[bold]Available models under {max_size}GB:[/bold]\n")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Model", style="cyan")
        table.add_column("Size", justify="right")

        for model in sorted(models, key=lambda x: x["size_gb"]):
            table.add_row(model["name"], model["size_str"])

        console.print(table)
        console.print(f"\n[dim]Total: {len(models)} models[/dim]")


@cli.command("list-benchmarks")
@click.option(
    "--tier",
    type=click.Choice(["smoke", "quick", "full"], case_sensitive=False),
    help="Show sample counts for specific tier",
)
@click.option(
    "--output-format",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    help="Output format (default: table)",
)
def list_benchmarks(tier: Optional[str], output_format: str):
    """
    List registered and discovered benchmarks, including unavailable entries.

    Examples:

        # List all benchmarks
        matric-eval list-benchmarks

        # Show sample counts for smoke tier
        matric-eval list-benchmarks --tier smoke

        # Output as JSON
        matric-eval list-benchmarks --output-format json
    """
    benchmarks_info = get_available_benchmarks(with_descriptions=True)

    if output_format == "json":
        if tier:
            # Include tier info
            tier_config = get_tier(tier)
            output = {
                name: {
                    "description": desc,
                    "samples": getattr(tier_config, name, 0),
                }
                for name, desc in benchmarks_info.items()
            }
            click.echo(json.dumps(output, indent=2))
        else:
            click.echo(json.dumps(benchmarks_info, indent=2))
    else:
        console.print("\n[bold]Benchmarks:[/bold]\n")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Benchmark", style="cyan")
        table.add_column("Status")
        table.add_column("Description")

        from matric_eval.tasks.registry import get_registry

        registry = get_registry()

        def benchmark_status(name: str) -> str:
            metadata = registry.get(name)
            return metadata.status.value if metadata is not None else "external"

        if tier:
            tier_config = get_tier(tier)
            table.add_column(f"{tier.capitalize()} Samples", justify="right")

            for name, desc in benchmarks_info.items():
                samples = getattr(tier_config, name, 0)
                table.add_row(name, benchmark_status(name), desc, str(samples))
        else:
            for name, desc in benchmarks_info.items():
                table.add_row(name, benchmark_status(name), desc)

        console.print(table)
        console.print(f"\n[dim]Total: {len(benchmarks_info)} benchmarks[/dim]")


@cli.command("audit-benchmarks")
@click.option(
    "--live",
    is_flag=True,
    help="Probe public canonical sources without downloading benchmark payloads.",
)
@click.option(
    "--output-format",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    help="Output format (default: table).",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    help="Retain the machine-readable audit report at this path.",
)
@click.option(
    "--fail-on-error/--no-fail-on-error",
    default=True,
    help="Exit nonzero when audit errors are present.",
)
def audit_benchmarks(
    live: bool,
    output_format: str,
    output: Path | None,
    fail_on_error: bool,
) -> None:
    """Audit benchmark source health, revisions, protocols, and lifecycle state."""
    from matric_eval.freshness import audit_registry

    report = audit_registry(live=live)
    serialized = json.dumps(report, indent=2)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized + "\n", encoding="utf-8")

    if output_format == "json":
        click.echo(serialized)
    else:
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Benchmark", style="cyan")
        table.add_column("Classification")
        table.add_column("Errors", justify="right")
        table.add_column("Warnings", justify="right")
        for benchmark in report["benchmarks"]:
            findings = benchmark["findings"]
            errors = sum(item["severity"] == "error" for item in findings)
            warnings = sum(item["severity"] == "warning" for item in findings)
            table.add_row(
                benchmark["name"],
                benchmark["classification"],
                str(errors),
                str(warnings),
            )
        console.print(table)
        summary = report["summary"]
        console.print(
            f"\n[dim]{summary['benchmarks']} benchmarks; "
            f"{summary['error']} errors; {summary['warning']} warnings[/dim]"
        )

    if fail_on_error and report["summary"]["error"]:
        raise click.exceptions.Exit(1)


@cli.command("recommend")
@click.option(
    "--results-dir",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Directory containing evaluation results",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    help="Output file for recommendations (default: stdout)",
)
@click.option(
    "--output-format",
    type=click.Choice(["json", "model-categories"], case_sensitive=False),
    default="json",
    help="Output format (default: json)",
)
@click.option(
    "--min-score",
    type=float,
    default=0.3,
    help="Minimum score to recommend a model (default: 0.3)",
)
def recommend(
    results_dir: Path,
    output: Optional[Path],
    output_format: str,
    min_score: float,
):
    """
    Generate model recommendations from evaluation results.

    Analyzes evaluation results and generates recommendations for which
    models to use for different capabilities (code generation, math, etc.).

    Examples:

        # Generate recommendations from results directory
        matric-eval recommend --results-dir results/run-2024-01-20T10-30-00

        # Output to file
        matric-eval recommend --results-dir results/latest --output recommendations.json

        # Generate model-categories.json format for matric-cli
        matric-eval recommend --results-dir results/latest --output-format model-categories
    """
    from matric_eval.recommendation import RecommendationEngine

    logger = get_cli_logger()
    logger.info("Generating recommendations", extra={"results_dir": str(results_dir)})

    engine = RecommendationEngine(min_score_threshold=min_score)

    # Check for summary.json first
    summary_file = results_dir / "summary.json"
    if summary_file.exists():
        report = engine.from_summary_file(summary_file)
    else:
        report = engine.from_results_directory(results_dir)

    if not report.model_scores:
        error_console.print("[red]Error:[/red] No valid evaluation results found")
        error_console.print(f"Directory: {results_dir}")
        sys.exit(1)

    # Format output
    if output_format == "model-categories":
        output_data = report.to_model_categories()
    else:
        output_data = report.to_dict()

    json_output = json.dumps(output_data, indent=2)

    # Write output
    if output:
        output.write_text(json_output)
        console.print(f"[green]Recommendations written to:[/green] {output}")
    else:
        console.print(json_output)

    # Log summary
    logger.info(
        "Recommendations generated",
        extra={
            "models_analyzed": len(report.model_scores),
            "best_overall": report.best_overall,
            "best_balanced": report.best_balanced,
        },
    )


@cli.command("list-providers")
@click.option(
    "--check-availability",
    is_flag=True,
    help="Check if each provider is reachable",
)
@click.option(
    "--output-format",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    help="Output format (default: table)",
)
def list_providers_cmd(check_availability: bool, output_format: str):
    """
    List available inference providers.

    Examples:

        # List all providers
        matric-eval list-providers

        # Check which providers are reachable
        matric-eval list-providers --check-availability
    """
    provider_names = list_providers()

    if output_format == "json":
        providers_info = []
        for name in provider_names:
            info: dict[str, Any] = {"name": name}
            try:
                p = get_provider(name)
                info["display_name"] = p.display_name
                if check_availability:
                    info["available"] = p.is_available()
            except Exception:
                info["display_name"] = name
                if check_availability:
                    info["available"] = False
            providers_info.append(info)
        console.print(json.dumps(providers_info, indent=2))
    else:
        console.print("\n[bold]Available providers:[/bold]\n")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Provider", style="cyan")
        table.add_column("Display Name")
        if check_availability:
            table.add_column("Status", justify="center")

        for name in provider_names:
            try:
                p = get_provider(name)
                display = p.display_name
                if check_availability:
                    available = p.is_available()
                    status = "[green]available[/green]" if available else "[dim]unavailable[/dim]"
                    table.add_row(name, display, status)
                else:
                    table.add_row(name, display)
            except Exception:
                if check_availability:
                    table.add_row(name, name, "[red]error[/red]")
                else:
                    table.add_row(name, name)

        console.print(table)
        console.print(f"\n[dim]Total: {len(provider_names)} providers[/dim]")


def _run_matrix_evaluation(
    matrix: Any,
    output: Path,
    output_format: str,
    thinking: str,
    default_tier: str,
) -> None:
    """Run evaluation from a matrix configuration."""
    logger = get_cli_logger()
    runs = matrix.get_runs()
    tier = matrix.tier or default_tier

    if not runs:
        error_console.print("[red]Error:[/red] Evaluation matrix produced no runs.")
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    output_dir = output / f"run-{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    if output_format != "json":
        console.print(f"\n[bold]MATRIC-EVAL MATRIX RUN - {tier.upper()} tier[/bold]")
        console.print(f"Runs: {len(runs)}")
        console.print(f"Output: {output_dir}\n")

    all_results = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console if output_format != "json" else None,
        disable=output_format == "json",
    ) as progress:
        task = progress.add_task(f"Running {len(runs)} evaluations...", total=len(runs))

        for run_spec in runs:
            model_name = run_spec["model"]
            provider_name = run_spec["provider"]
            benchmark_name = run_spec.get("benchmark")

            set_context(model=model_name)

            if output_format != "json":
                progress.update(task, description=f"{model_name} on {provider_name}...")

            try:
                provider = get_provider(provider_name)
                benchmarks = [benchmark_name] if benchmark_name else None

                result = run_evaluation(
                    model=model_name,
                    tier=tier,
                    benchmarks=benchmarks,
                    output_dir=output_dir,
                    provider=provider,
                )
                result["provider"] = provider_name
                all_results.append(result)
            except Exception as e:
                logger.error(
                    "Matrix run failed",
                    extra={"model": model_name, "provider": provider_name, "error": str(e)},
                )
                all_results.append(
                    {
                        "model": model_name,
                        "provider": provider_name,
                        "tier": tier,
                        "status": "error",
                        "error": str(e),
                    }
                )

            progress.advance(task)

    # Save summary
    summary = {
        "timestamp": timestamp,
        "tier": tier,
        "matrix_runs": len(runs),
        "results": all_results,
    }
    summary_file = output_dir / "summary.json"
    summary_file.write_text(json.dumps(summary, indent=2))

    if output_format == "json":
        console.print(json.dumps(summary, indent=2))
    else:
        console.print("\n[bold]MATRIX RESULTS[/bold]\n")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Model", style="cyan")
        table.add_column("Provider")
        table.add_column("Score", justify="right")
        table.add_column("Status", justify="center")

        for result in sorted(all_results, key=lambda x: x.get("overall_score", 0), reverse=True):
            score = result.get("overall_score", 0)
            status = "[green]OK[/green]" if result.get("status") == "success" else "[red]ERR[/red]"
            model_display = result["model"].replace("ollama/", "").replace("openai/", "")
            table.add_row(model_display, result.get("provider", "?"), f"{score:.1%}", status)

        console.print(table)
        console.print(f"\n[dim]Results saved to: {output_dir}[/dim]")


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
