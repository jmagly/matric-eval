"""
matric-eval CLI - Model evaluation runner.

Click-based CLI with rich progress reporting and JSON output support.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import click
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from matric_eval.config import TIERS, get_tier
from matric_eval.core.engine import EvaluationEngine
from matric_eval.logging import (
    EvalLogger,
    configure_logging,
    get_logger,
    set_context,
)
from matric_eval.state import StateManager
from matric_eval.models.detection import has_thinking_capability
from matric_eval.providers import get_provider, list_providers
from matric_eval.providers.base import ProviderConfig, ProviderConnectionError

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
                    models.append({
                        "name": name,
                        "size_gb": round(size_gb, 2),
                        "size_str": f"{size_val} {size_unit}",
                    })
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
    Get list of available benchmarks.

    Args:
        with_descriptions: If True, return dict mapping names to descriptions

    Returns:
        List of benchmark names or dict with descriptions
    """
    benchmarks_info = {
        "humaneval": "HumanEval - Python code generation (164 problems)",
        "mbpp": "MBPP - Mostly Basic Python Problems (974 problems)",
        "gsm8k": "GSM8K - Grade school math problems (1,319 problems)",
        "arc": "ARC - AI2 Reasoning Challenge (1,172 problems)",
        "ifeval": "IFEval - Instruction following (541 problems)",
        "ds1000": "DS-1000 - Data science tasks (1,000 problems)",
        "livecodebench": "LiveCodeBench - Competitive programming (880 problems)",
        "mtbench": "MT-Bench - Multi-turn conversation (80 problems)",
        "tool_calling": "Tool Calling - Function invocation (6 scenarios)",
        "matric_cli": "Matric-CLI - Code generation & tool calling (12 scenarios)",
        "matric_memory": "Matric-Memory - Title generation & semantics (30 cases)",
    }

    if with_descriptions:
        return benchmarks_info
    return list(benchmarks_info.keys())


# =============================================================================
# Evaluation Runner
# =============================================================================


def run_evaluation(
    model: str,
    tier: str = "smoke",
    benchmarks: Optional[list[str]] = None,
    output_dir: Optional[Path] = None,
    thinking_mode: Optional[str] = None,
    provider: Any = None,
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
            name for name in get_available_benchmarks()
            if getattr(tier_config, name, 0) > 0
        ]

    # Create engine and run
    engine = EvaluationEngine(
        model=model,
        tier=tier,
        log_dir=output_dir / "logs" if output_dir else None,
        thinking_mode=thinking_mode,
        provider=provider,
    )

    return engine.run_all(benchmarks)


# =============================================================================
# CLI Commands
# =============================================================================


@click.group()
@click.version_option(version="0.1.0")
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

    Evaluate Ollama models using standardized benchmarks (HumanEval, MBPP, GSM8K).
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
    help="Specific model to evaluate (e.g., llama3.2:3b). If not specified, evaluates all models under --max-size.",
)
@click.option(
    "--benchmark",
    type=str,
    multiple=True,
    help="Specific benchmark(s) to run. Can be specified multiple times. If not specified, runs all benchmarks for the tier.",
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
    help="Thinking mode for thinking-capable models (auto=detect, on=enable, off=disable, both=run twice)",
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

    # Handle resume
    if resume:
        logger.info("Attempting to resume run", extra={"resume_path": resume})

        # Determine run directory
        if Path(resume).is_dir():
            run_dir = Path(resume)
        else:
            run_dir = output / resume

        if not run_dir.exists():
            logger.error("Run directory not found", extra={"path": str(run_dir)})
            error_console.print(f"[red]Error:[/red] Run directory not found: {run_dir}")
            sys.exit(1)

        # Load state manager
        state_manager = StateManager(run_dir)

        if not state_manager.can_resume():
            error_console.print(f"[red]Error:[/red] Cannot resume run at {run_dir}")
            error_console.print("Run may already be complete or state file is corrupted.")
            sys.exit(1)

        # Check lock
        if state_manager.is_locked():
            error_console.print(f"[red]Error:[/red] Run is locked (already running)")
            error_console.print(f"Lock file: {state_manager.lock_file}")
            error_console.print("If process has died, use: matric-eval validate --force-unlock")
            sys.exit(1)

        # Get work to resume
        if fill_gaps:
            resume_work = state_manager.get_resume_work()
            if not resume_work:
                console.print("[green]No gaps found - run is complete![/green]")
                return

            console.print(f"\n[bold]RESUMING RUN - FILLING GAPS[/bold]")
            console.print(f"Run directory: {run_dir}\n")

            for model_name, benchmarks in resume_work.items():
                console.print(f"  {model_name}: {', '.join(benchmarks)}")

            console.print()
        else:
            console.print(f"\n[bold]RESUMING RUN[/bold]")
            console.print(f"Run directory: {run_dir}\n")

        # TODO: Implement resume execution
        error_console.print("[yellow]Warning:[/yellow] Resume execution not yet implemented")
        return

    # Handle matrix-based evaluation
    if matrix_file:
        from matric_eval.providers.matrix import EvaluationMatrix
        matrix = EvaluationMatrix.from_yaml(matrix_file)
        _run_matrix_evaluation(matrix, output, output_format, thinking, tier)
        return

    # Resolve provider
    active_provider = None
    if provider_name:
        config = ProviderConfig()
        if provider_url:
            config.base_url = provider_url
        if api_key:
            config.api_key = api_key
        try:
            active_provider = get_provider(provider_name, config)
        except ValueError as e:
            error_console.print(f"[red]Error:[/red] {e}")
            error_console.print(f"Available providers: {', '.join(list_providers())}")
            sys.exit(1)

    # Get models to evaluate
    logger.info("Discovering models", extra={"max_size_gb": max_size, "specific_model": model})

    if model:
        # User specified a model - use it even if not in Ollama list
        models_to_eval = [{"name": model, "size_gb": 0, "size_str": "unknown"}]
        logger.debug("Using user-specified model", extra={"model": model})
    elif active_provider:
        # Discover models from the active provider
        try:
            provider_models = active_provider.list_models(max_size_gb=max_size)
            models_to_eval = [
                {"name": m.name, "size_gb": m.size_gb, "size_str": f"{m.size_gb} GB"}
                for m in provider_models
            ]
        except ProviderConnectionError as e:
            error_console.print(f"[red]Error querying {active_provider.display_name}:[/red] {e}")
            sys.exit(1)
        logger.debug(f"Discovered models from {active_provider.display_name}", extra={"count": len(models_to_eval)})
    else:
        models_to_eval = get_ollama_models(max_size)
        logger.debug("Discovered models from Ollama", extra={"count": len(models_to_eval)})

    if not models_to_eval:
        logger.error("No models found to evaluate")
        error_console.print("[red]Error:[/red] No models found to evaluate.")
        error_console.print("Try running: [bold]ollama list[/bold] to see available models")
        sys.exit(1)

    # Prepare benchmarks list
    benchmarks_to_run = list(benchmark) if benchmark else None

    # Setup output directory
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    output_dir = output / f"run-{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Starting evaluation run",
        extra={
            "tier": tier,
            "models": len(models_to_eval),
            "benchmarks": benchmarks_to_run,
            "output_dir": str(output_dir),
        },
    )

    # Show evaluation info (unless JSON output)
    if output_format != "json":
        console.print(f"\n[bold]MATRIC-EVAL - {tier.upper()} tier[/bold]")
        console.print(f"Models: {len(models_to_eval)}")
        console.print(f"Max size: {max_size}GB")
        console.print(f"Output: {output_dir}")
        if benchmarks_to_run:
            console.print(f"Benchmarks: {', '.join(benchmarks_to_run)}")
        console.print()

    all_results = []

    # Progress tracking
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console if output_format != "json" else None,
        disable=output_format == "json",
    ) as progress:
        task = progress.add_task(
            f"Evaluating {len(models_to_eval)} model(s)...",
            total=len(models_to_eval),
        )

        for model_info in models_to_eval:
            model_name = model_info["name"]

            # Set logging context for this model
            set_context(model=model_name)
            logger.info("Starting model evaluation", extra={"model": model_name, "tier": tier})

            if output_format != "json":
                progress.update(task, description=f"Evaluating {model_name}...")

            try:
                # Handle thinking mode
                is_thinking_model = False
                modes_to_run = []

                if thinking == "auto":
                    # Auto-detect thinking capability
                    is_thinking_model = has_thinking_capability(model_name)
                    modes_to_run = ["off"] if is_thinking_model else [None]
                elif thinking == "both":
                    # Run both modes (only makes sense for thinking models)
                    is_thinking_model = has_thinking_capability(model_name)
                    modes_to_run = ["on", "off"] if is_thinking_model else [None]
                elif thinking in ("on", "off"):
                    # Explicit mode
                    modes_to_run = [thinking]
                else:
                    modes_to_run = [None]

                # Run evaluation for each mode
                for thinking_mode in modes_to_run:
                    result = run_evaluation(
                        model=model_name,
                        tier=tier,
                        benchmarks=benchmarks_to_run,
                        output_dir=output_dir,
                        thinking_mode=thinking_mode,
                        provider=active_provider,
                    )
                    all_results.append(result)

                    # Log result
                    overall_score = result.get("overall_score", 0)
                    thinking_suffix = f" (thinking={thinking_mode})" if thinking_mode else ""
                    logger.info(
                        f"Model evaluation complete{thinking_suffix}",
                        extra={
                            "model": model_name,
                            "overall_score": overall_score,
                            "status": result.get("status"),
                            "thinking_mode": thinking_mode,
                        },
                    )

                    # Save individual result
                    safe_name = model_name.replace(":", "_").replace("/", "_")
                    if thinking_mode:
                        safe_name = f"{safe_name}_thinking_{thinking_mode}"
                    result_file = output_dir / f"{safe_name}.json"
                    result_file.write_text(json.dumps(result, indent=2))

            except Exception as e:
                logger.error(
                    "Model evaluation failed",
                    extra={"model": model_name, "error": str(e)},
                    exc_info=True,
                )
                error_console.print(f"\n[red]Error evaluating {model_name}:[/red] {e}")
                all_results.append({
                    "model": f"ollama/{model_name}" if not model_name.startswith("ollama/") else model_name,
                    "tier": tier,
                    "status": "error",
                    "error": str(e),
                })
                # In table mode, re-raise to stop execution
                # In JSON mode, continue to collect all errors
                if output_format != "json":
                    sys.exit(1)

            progress.advance(task)

    # Save summary
    successful = len([r for r in all_results if r.get("status") == "success"])
    failed = len([r for r in all_results if r.get("status") == "error"])

    summary = {
        "timestamp": timestamp,
        "tier": tier,
        "models_evaluated": len(all_results),
        "successful": successful,
        "failed": failed,
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
            console.print(json.dumps(all_results[0], indent=2))
        else:
            console.print(json.dumps(summary, indent=2))
    else:
        # Table output
        console.print(f"\n[bold]RESULTS SUMMARY[/bold]")

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
            console.print(f"\n[yellow]Run is incomplete. Use --resume --fill-gaps to complete.[/yellow]")
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
    List available benchmarks.

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
            console.print(json.dumps(output, indent=2))
        else:
            console.print(json.dumps(benchmarks_info, indent=2))
    else:
        console.print("\n[bold]Available benchmarks:[/bold]\n")

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Benchmark", style="cyan")
        table.add_column("Description")

        if tier:
            tier_config = get_tier(tier)
            table.add_column(f"{tier.capitalize()} Samples", justify="right")

            for name, desc in benchmarks_info.items():
                samples = getattr(tier_config, name, 0)
                table.add_row(name, desc, str(samples))
        else:
            for name, desc in benchmarks_info.items():
                table.add_row(name, desc)

        console.print(table)
        console.print(f"\n[dim]Total: {len(benchmarks_info)} benchmarks[/dim]")


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
                all_results.append({
                    "model": model_name,
                    "provider": provider_name,
                    "tier": tier,
                    "status": "error",
                    "error": str(e),
                })

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
        console.print(f"\n[bold]MATRIX RESULTS[/bold]\n")

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
