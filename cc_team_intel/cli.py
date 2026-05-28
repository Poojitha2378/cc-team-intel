"""CLI entry point for cc-team-intel."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import track
from rich.table import Table

from .aggregator import build_team_report
from .brief import generate_brief
from .models import TeamReport
from .parser import iter_records_from_claude_home, iter_records_from_upload_dir
from .storage import get_upload_dir, save_upload

console = Console()


def _fmt_usd(value: float) -> str:
    return f"${value:.4f}" if value < 0.01 else f"${value:.2f}"


def _print_report(report: TeamReport, show_brief: bool = False) -> None:
    period = "all time"
    if report.period_start and report.period_end:
        period = f"{report.period_start.date()} – {report.period_end.date()}"

    console.print(
        Panel(
            f"[bold red]cc-team-intel[/bold red]  |  {period}\n"
            f"Total spend: [bold green]{_fmt_usd(report.total_cost_usd)}[/bold green]  "
            f"Engineers: [cyan]{report.engineer_count}[/cyan]  "
            f"Sessions: [cyan]{report.total_sessions}[/cyan]  "
            f"Cache efficiency: [yellow]{report.cache_efficiency_pct:.1f}%[/yellow]",
            expand=False,
        )
    )

    if report.engineers:
        table = Table(title="Per-Engineer Breakdown", show_lines=True)
        table.add_column("Engineer", style="cyan", no_wrap=True)
        table.add_column("Spend", justify="right", style="green")
        table.add_column("Sessions", justify="right")
        table.add_column("Turns", justify="right")
        table.add_column("Cache eff.", justify="right", style="yellow")
        table.add_column("Top model", style="dim")

        for e in report.engineers:
            top_model = max(e.model_mix, key=e.model_mix.get) if e.model_mix else "—"
            table.add_row(
                e.engineer,
                _fmt_usd(e.total_cost_usd),
                str(e.session_count),
                str(e.total_turns),
                f"{e.cache_efficiency:.0%}",
                top_model,
            )
        console.print(table)

    if report.projects:
        proj_table = Table(title="Top Projects by Spend", show_lines=True)
        proj_table.add_column("Project", style="cyan")
        proj_table.add_column("Spend", justify="right", style="green")
        proj_table.add_column("Sessions", justify="right")
        for p in report.projects[:10]:
            proj_table.add_row(p.project_path or "—", _fmt_usd(p.total_cost_usd), str(p.session_count))
        console.print(proj_table)

    if report.model_breakdown:
        model_table = Table(title="Model Breakdown")
        model_table.add_column("Model", style="cyan")
        model_table.add_column("Spend", justify="right", style="green")
        model_table.add_column("Share", justify="right", style="dim")
        total = report.total_cost_usd or 1
        for model, cost in sorted(report.model_breakdown.items(), key=lambda x: x[1], reverse=True):
            model_table.add_row(model, _fmt_usd(cost), f"{cost/total:.0%}")
        console.print(model_table)

    if show_brief and report.cost_brief:
        console.print(Panel(report.cost_brief, title="[bold]AI Cost Brief[/bold]", expand=True))


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


@click.group()
@click.version_option()
def cli():
    """cc-team-intel — Team cost intelligence for Claude Code."""


@cli.command("report")
@click.option("--since", default=None, help="Start date filter (YYYY-MM-DD)")
@click.option("--until", default=None, help="End date filter (YYYY-MM-DD)")
@click.option("--brief", is_flag=True, default=False, help="Generate AI cost brief (needs ANTHROPIC_API_KEY)")
@click.option("--json-out", is_flag=True, default=False, help="Output raw JSON instead of tables")
@click.option("--data-dir", default=None, help="Path to upload directory (default: ~/.cc-team-intel/uploads)")
def report_cmd(since, until, brief, json_out, data_dir):
    """Show the team cost report from uploaded data."""
    upload_dir = Path(data_dir) if data_dir else get_upload_dir()
    if not upload_dir.exists() or not any(upload_dir.iterdir()):
        console.print("[red]No data found.[/red] Run [bold]ccti submit[/bold] first.")
        sys.exit(1)

    records = list(iter_records_from_upload_dir(upload_dir))
    if not records:
        console.print("[yellow]No usage records found in uploaded files.[/yellow]")
        sys.exit(0)

    period_start = datetime.fromisoformat(since).replace(tzinfo=timezone.utc) if since else None
    period_end = datetime.fromisoformat(until).replace(tzinfo=timezone.utc) if until else None

    report = build_team_report(records, period_start=period_start, period_end=period_end)

    if brief:
        with console.status("Generating AI cost brief…"):
            report.cost_brief = generate_brief(report)

    if json_out:
        click.echo(report.model_dump_json(indent=2))
    else:
        _print_report(report, show_brief=brief)


@cli.command("self")
@click.option("--since", default=None, help="Start date filter (YYYY-MM-DD)")
@click.option("--until", default=None, help="End date filter (YYYY-MM-DD)")
@click.option("--brief", is_flag=True, default=False, help="Generate AI cost brief")
@click.option("--engineer", default=None, help="Override engineer name (default: $USER)")
@click.option("--claude-home", default=None, help="Override ~/.claude path")
def self_cmd(since, until, brief, engineer, claude_home):
    """Analyze your own ~/.claude usage (single-user mode)."""
    name = engineer or os.environ.get("USER", "me")
    home = Path(claude_home) if claude_home else None

    records = list(iter_records_from_claude_home(claude_home=home, engineer=name))
    if not records:
        console.print("[yellow]No usage records found in ~/.claude/projects/[/yellow]")
        sys.exit(0)

    period_start = datetime.fromisoformat(since).replace(tzinfo=timezone.utc) if since else None
    period_end = datetime.fromisoformat(until).replace(tzinfo=timezone.utc) if until else None

    report = build_team_report(records, period_start=period_start, period_end=period_end)

    if brief:
        with console.status("Generating AI cost brief…"):
            report.cost_brief = generate_brief(report)

    _print_report(report, show_brief=brief)


@cli.command("submit")
@click.option("--engineer", default=None, help="Engineer name (default: $USER)")
@click.option("--server", default="http://localhost:8000", help="cc-team-intel server URL")
@click.option("--local", is_flag=True, default=False, help="Write to local upload dir instead of HTTP")
@click.option("--claude-home", default=None, help="Override ~/.claude path")
@click.option("--data-dir", default=None, help="Local upload directory (with --local)")
def submit_cmd(engineer, server, local, claude_home, data_dir):
    """
    Upload your JSONL session files to the team server (or local dir).

    By default, submits all files from ~/.claude/projects/ to the HTTP server.
    Use --local to write to a shared filesystem instead.
    """
    import glob as _glob
    import requests

    name = engineer or os.environ.get("USER", "unknown")
    home = Path(claude_home) if claude_home else Path.home() / ".claude"
    projects_dir = home / "projects"

    if not projects_dir.exists():
        console.print(f"[red]Directory not found:[/red] {projects_dir}")
        sys.exit(1)

    jsonl_files = list(projects_dir.rglob("*.jsonl"))
    if not jsonl_files:
        console.print("[yellow]No JSONL files found.[/yellow]")
        sys.exit(0)

    upload_dir = Path(data_dir) if data_dir else get_upload_dir()
    uploaded = 0

    for path in track(jsonl_files, description=f"Submitting as [cyan]{name}[/cyan]"):
        if local:
            save_upload(name, path, upload_dir)
            uploaded += 1
        else:
            try:
                resp = requests.post(
                    f"{server}/upload/{name}",
                    files={"file": (path.name, open(path, "rb"), "application/json")},
                    timeout=30,
                )
                resp.raise_for_status()
                uploaded += 1
            except Exception as exc:
                console.print(f"[red]Failed[/red] {path.name}: {exc}")

    console.print(f"[green]Submitted {uploaded}/{len(jsonl_files)} files.[/green]")


@cli.command("serve")
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8000, type=int, help="Bind port")
@click.option("--reload", is_flag=True, default=False, help="Auto-reload on code changes")
def serve_cmd(host, port, reload):
    """Start the cc-team-intel HTTP server."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]uvicorn not installed.[/red] Run: pip install cc-team-intel[server]")
        sys.exit(1)
    uvicorn.run("cc_team_intel.server:app", host=host, port=port, reload=reload)


def main():
    cli()
