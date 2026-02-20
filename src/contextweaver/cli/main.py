"""
ContextWeaver CLI - Decision Archaeology at your fingertips.

Usage examples:

  # Index a GitHub repository
  contextweaver mine github --repo owner/repo

  # Index a local git repository
  contextweaver mine local --path ./my-project

  # Ask WHY a decision was made
  contextweaver why "why do we use PostgreSQL instead of MongoDB?"

  # Generate an onboarding briefing
  contextweaver brief "authentication system" --for "new backend engineer"

  # Check if a proposed approach conflicts with historical decisions
  contextweaver check "We should switch from REST to GraphQL for all endpoints"

  # Show system statistics
  contextweaver stats

  # Start the REST API server
  contextweaver serve
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
import uvicorn
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

app = typer.Typer(
    name="contextweaver",
    help="Decision Archaeology & Living Project Intelligence",
    rich_markup_mode="rich",
    add_completion=False,
)
console = Console()

mine_app = typer.Typer(help="Mine project artifacts for decisions")
app.add_typer(mine_app, name="mine")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_orchestrator():
    """Lazy import to avoid slow startup when just running --help."""
    from contextweaver.agents.orchestrator import Orchestrator

    return Orchestrator()


def _print_decision_table(decisions: list) -> None:
    table = Table(
        title=f"Extracted {len(decisions)} Decisions",
        box=box.ROUNDED,
        show_lines=True,
    )
    table.add_column("Title", style="bold cyan", max_width=50)
    table.add_column("Confidence", justify="center")
    table.add_column("Debt", justify="center")
    table.add_column("Date", justify="right")

    debt_colors = {(0.0, 0.3): "green", (0.3, 0.6): "yellow", (0.6, 1.1): "red"}

    for d in decisions:
        debt = d.debt_score
        debt_color = "green"
        for (lo, hi), color in debt_colors.items():
            if lo <= debt < hi:
                debt_color = color
                break
        table.add_row(
            d.title,
            d.confidence.value,
            f"[{debt_color}]{debt:.2f}[/{debt_color}]",
            d.made_at.strftime("%Y-%m-%d"),
        )
    console.print(table)


# ---------------------------------------------------------------------------
# mine subcommands
# ---------------------------------------------------------------------------


@mine_app.command("github")
def mine_github(
    repo: Annotated[str, typer.Option("--repo", "-r", help="owner/repo")] = "",
    days: Annotated[int, typer.Option("--days", "-d", help="Lookback days")] = 365,
) -> None:
    """Mine a GitHub repository for decisions."""
    console.print(Panel("[bold cyan]ContextWeaver[/] - Mining GitHub repository..."))
    orc = _get_orchestrator()

    with console.status("[bold green]Mining artifacts and running Decision Archaeology...[/]"):
        decisions, status = orc.mine_github(repo_name=repo or None, lookback_days=days)

    console.print(
        f"[green]Mining complete.[/] Processed [bold]{status.artifacts_processed}[/] artifacts, "
        f"extracted [bold]{len(decisions)}[/] decisions."
    )
    if decisions:
        _print_decision_table(decisions[:20])


@mine_app.command("local")
def mine_local(
    path: Annotated[str, typer.Argument(help="Path to local git repository")],
    docs: Annotated[Optional[str], typer.Option("--docs", help="Docs directory")] = None,
    since: Annotated[Optional[str], typer.Option("--since", help="Start date (YYYY-MM-DD or ISO format)")] = None,
    until: Annotated[Optional[str], typer.Option("--until", help="End date (YYYY-MM-DD or ISO format)")] = None,
) -> None:
    """Mine a local git repository for decisions."""
    console.print(Panel(f"[bold cyan]ContextWeaver[/] - Mining local repo: {path}"))
    orc = _get_orchestrator()

    with console.status("[bold green]Mining artifacts and running Decision Archaeology...[/]"):
        decisions = orc.mine_local(path, docs_dir=docs, since=since, until=until)

    console.print(f"[green]Mining complete.[/] Extracted [bold]{len(decisions)}[/] decisions.")
    if decisions:
        _print_decision_table(decisions[:20])


# ---------------------------------------------------------------------------
# Top-level commands
# ---------------------------------------------------------------------------


@app.command()
def why(
    question: Annotated[str, typer.Argument(help="Your 'why?' question")],
) -> None:
    """Answer a 'why?' question about the project's historical decisions."""
    console.print(Panel(f"[bold]Q:[/] {question}", title="Decision Archaeology", border_style="cyan"))
    orc = _get_orchestrator()

    with console.status("[bold green]Consulting the decision archive...[/]"):
        answer = orc.why(question)

    console.print(Panel(answer, title="[green]Answer[/]", border_style="green"))


@app.command()
def brief(
    topic: Annotated[str, typer.Argument(help="Topic or area to brief on")],
    for_: Annotated[
        str, typer.Option("--for", "-f", help="Who this briefing is for")
    ] = "developer",
    scope: Annotated[str, typer.Option("--scope", "-s", help="Scope")] = "project",
) -> None:
    """Generate a context briefing for a developer or task."""
    console.print(
        Panel(f"Generating briefing on: [bold]{topic}[/]", title="Context Briefing", border_style="cyan")
    )
    orc = _get_orchestrator()

    with console.status("[bold green]Synthesizing decision history...[/]"):
        briefing = orc.brief(topic, subject=for_, scope=scope)

    # Narrative
    console.print(Panel(briefing.narrative, title="[bold]Narrative[/]", border_style="white"))

    # Critical constraints
    if briefing.critical_constraints:
        t = Table(title="Critical Constraints", box=box.SIMPLE)
        t.add_column("Constraint", style="red bold")
        for c in briefing.critical_constraints:
            t.add_row(c)
        console.print(t)

    # Decision debt
    if briefing.active_debt:
        t = Table(title="Active Decision Debt", box=box.SIMPLE)
        t.add_column("Debt Item", style="yellow")
        for d in briefing.active_debt:
            t.add_row(d)
        console.print(t)

    # Questions
    if briefing.suggested_questions:
        t = Table(title="Questions to Investigate", box=box.SIMPLE)
        t.add_column("Question", style="cyan")
        for q in briefing.suggested_questions:
            t.add_row(q)
        console.print(t)


@app.command()
def check(
    text: Annotated[str, typer.Argument(help="Proposed approach or PR description to check")],
    label: Annotated[str, typer.Option("--label", "-l")] = "check",
) -> None:
    """Check if a proposed approach conflicts with historical decisions."""
    console.print(Panel("[bold cyan]Conflict Detection[/] - Checking against decision archive"))
    orc = _get_orchestrator()

    with console.status("[bold green]Scanning for decision conflicts...[/]"):
        conflicts = orc.check_text_conflicts(text, label=label)

    if not conflicts:
        console.print("[bold green]No conflicts detected.[/] Your approach aligns with historical decisions.")
        return

    console.print(f"[bold red]{len(conflicts)} conflict(s) detected![/]")
    for i, conflict in enumerate(conflicts, 1):
        severity_colors = {"low": "yellow", "medium": "orange3", "high": "red", "critical": "red bold"}
        color = severity_colors.get(conflict.severity, "white")
        console.print(
            Panel(
                f"[bold]Explanation:[/] {conflict.explanation}\n\n"
                f"[bold]Suggested action:[/] {conflict.suggested_action}",
                title=f"[{color}]Conflict #{i} - {conflict.severity.upper()}[/{color}]",
                border_style=color,
            )
        )


@app.command()
def stats() -> None:
    """Show system statistics and most critical decisions."""
    console.print(Panel("[bold cyan]ContextWeaver Statistics[/]"))
    orc = _get_orchestrator()
    s = orc.stats()

    # Summary table
    t = Table(box=box.ROUNDED)
    t.add_column("Metric", style="bold")
    t.add_column("Value", justify="right", style="cyan")
    t.add_row("Decisions Indexed", str(s["decisions_indexed"]))
    t.add_row("Graph Nodes", str(s["graph_nodes"]))
    t.add_row("Graph Edges", str(s["graph_edges"]))
    t.add_row("High-Debt Decisions", str(len(s["high_debt_decisions"])))
    console.print(t)

    # Critical decisions
    critical = s["critical_decisions"]
    if critical:
        ct = Table(title="Most Architecturally Critical Decisions", box=box.SIMPLE)
        ct.add_column("Title", style="bold")
        ct.add_column("Date")
        ct.add_column("Debt", justify="center")
        for d in critical:
            ct.add_row(
                d.get("title", "?"),
                str(d.get("made_at", "?"))[:10],
                f"{d.get('debt_score', 0):.2f}",
            )
        console.print(ct)


@app.command()
def serve(
    host: str = "0.0.0.0",
    port: int = 8765,
    reload: bool = False,
) -> None:
    """Start the ContextWeaver REST API server."""
    console.print(
        Panel(
            f"Starting ContextWeaver API on [bold]http://{host}:{port}[/]\n"
            f"Docs: [bold]http://{host}:{port}/docs[/]",
            title="[bold cyan]ContextWeaver Server[/]",
        )
    )
    uvicorn.run(
        "contextweaver.api.routes:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    app()
