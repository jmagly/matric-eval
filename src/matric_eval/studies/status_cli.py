"""Status and bounded supervision for external study adapters."""

import json
from pathlib import Path

import click

from matric_eval.studies.run_status import RunStatus, supervise


@click.group()
def study_run() -> None:
    """Inspect correlated task progress or supervise an external adapter."""


@study_run.command("status")
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--json-output", is_flag=True)
@click.option("--stale-seconds", type=float, default=15.0)
def status_command(directory: Path, json_output: bool, stale_seconds: float) -> None:
    """Read atomic status and reconcile a missing supervisor terminal receipt."""
    try:
        data = RunStatus(directory).read(stale_seconds=stale_seconds)
    except (ValueError, OSError, KeyError) as error:
        raise click.ClickException(str(error)) from None
    if json_output:
        click.echo(json.dumps(data, allow_nan=False))
        return
    counts = data["counts"]
    click.echo(f"{data['run_id']} / {data['attempt_id']}: {data['phase']}")
    click.echo(
        f"Attempted {counts['attempted']}/{counts['planned']}; scored-valid {counts['valid']}/{counts['planned']}; invalid {counts['invalid']}; not-started {counts['not_started']}"
    )
    click.echo(
        f"Supervisor alive: {data['liveness']['supervisor_alive']}; heartbeat fresh: {data['liveness']['heartbeat_fresh']}; cleanup: {data['cleanup']}"
    )
    if data.get("resources"):
        resource = data["resources"]
        click.echo(
            f"Resources: {resource['state']}; cleanup: {resource['cleanup']}; record: {resource['record']}"
        )
    for row in data["tasks"]:
        click.echo(
            f"{row['model_id']}/{row['suite_id']}/{row['task_id']}: {row['state']}"
            + (f" ({row['reason']})" if row["reason"] else "")
        )
    for item in data["diagnostics"]:
        click.echo(
            f"{item['actor']}/{item['stage']}: {item['reason']}; exit={item['exit_code']}; signal={item['signal']}"
        )
        for exception in item["exception_chain"]:
            click.echo(f"{exception['type']}: {exception.get('message', '')}")
        if item["stdout"]:
            click.echo(item["stdout"])
        if item["stderr"]:
            click.echo(item["stderr"])


@study_run.command("supervise", context_settings={"ignore_unknown_options": True})
@click.argument("plan", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("directory", type=click.Path(path_type=Path))
@click.option("--timeout", type=float, required=True)
@click.argument("command", nargs=-1, type=click.UNPROCESSED, required=True)
def supervise_command(
    plan: Path, directory: Path, timeout: float, command: tuple[str, ...]
) -> None:
    """Supervise COMMAND using a JSON run_id, attempt_id, tasks plan."""
    try:
        payload = json.loads(plan.read_text())
        status = RunStatus.create(
            directory,
            run_id=payload["run_id"],
            attempt_id=payload["attempt_id"],
            tasks=payload["tasks"],
        )
        code = supervise(status, command, timeout=timeout)
    except (ValueError, OSError, KeyError) as error:
        raise click.ClickException(str(error)) from None
    click.echo(json.dumps(status.read()["terminal_event"]))
    raise click.exceptions.Exit(code)


@study_run.command("preflight")
@click.argument("plan", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("receipt", type=click.Path(path_type=Path))
@click.option(
    "--launch", is_flag=True, help="Acquire target and invoke adapter only after admission."
)
def preflight_command(plan: Path, receipt: Path, launch: bool) -> None:
    """Validate a staged execution PLAN in the actual caller service context."""
    from matric_eval.studies.preflight import execute_plan

    try:
        result = execute_plan(json.loads(plan.read_text()), receipt, launch=launch)
    except (ValueError, OSError) as error:
        raise click.ClickException(str(error)) from None
    click.echo(json.dumps(result, allow_nan=False))
    raise click.exceptions.Exit(0 if result["completed"] else 1)
