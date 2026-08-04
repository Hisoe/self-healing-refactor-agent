"""
src/cli.py
----------
Interactive Command Line Interface for the Self-Healing Refactor Agent.
Provides rich terminal formatting, live state spinners, and side-by-side code visualizers.
"""

import argparse
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from src.agent.graph import build_graph

console = Console()


def display_banner():
    """Renders application header."""
    console.print(
        Panel.fit(
            "[bold cyan]Self-Healing Code Refactor & Sandbox Agent[/bold cyan]\n"
            "[dim]LangGraph • Ephemeral Docker Sandbox • Closed-Loop Self-Healing[/dim]",
            border_style="cyan",
        )
    )


def run_cli():
    parser = argparse.ArgumentParser(
        description="Autonomous Self-Healing Code Refactoring Agent"
    )
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        required=True,
        help="Path to the Python file requiring refactoring.",
    )
    parser.add_argument(
        "--max-iterations",
        "-m",
        type=int,
        default=3,
        help="Maximum self-healing attempt loops (default: 3).",
    )

    args = parser.parse_args()
    file_path = Path(args.file)

    if not file_path.exists():
        console.print(f"[bold red]Error:[/bold red] File not found: {file_path}")
        sys.exit(1)

    original_code = file_path.read_text(encoding="utf-8")

    display_banner()

    console.print(
        Panel(
            Syntax(original_code, "python", theme="monokai", line_numbers=True),
            title="[bold yellow]Target Code Input[/bold yellow]",
            border_style="yellow",
        )
    )

    app = build_graph()

    initial_state = {
        "original_code": original_code,
        "refactored_code": None,
        "refactor_explanation": None,
        "test_code": None,
        "execution_result": None,
        "iteration_count": 0,
        "max_iterations": args.max_iterations,
        "failure_history": [],
        "status": "INITIALIZED",
    }

    console.print("\n[bold green]► Starting Self-Healing Control Loop...[/bold green]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(
            description="Executing LangGraph Workflow & Docker Sandbox...", total=None
        )

        final_state = app.invoke(initial_state)
        progress.update(task, completed=True, description="Workflow Execution Finished.")

    exec_res = final_state.get("execution_result")

    # Render Results Summary Table
    table = Table(title="Execution Summary", border_style="blue")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold white")

    table.add_row("Final Status", final_state.get("status", "UNKNOWN"))
    table.add_row("Total Iterations", str(final_state.get("iteration_count", 0)))
    table.add_row(
        "Sandbox Tests Passed",
        "[bold green]YES[/bold green]"
        if exec_res and exec_res.passed
        else "[bold red]NO[/bold red]",
    )

    console.print(table)

    # Output Refactored Solution Panel
    if final_state.get("refactored_code"):
        console.print(
            Panel(
                Syntax(
                    final_state["refactored_code"],
                    "python",
                    theme="monokai",
                    line_numbers=True,
                ),
                title="[bold green]Refactored Solution (Validated in Docker Sandbox)[/bold green]",
                border_style="green",
            )
        )

    # Output Explanation Panel
    if final_state.get("refactor_explanation"):
        console.print(
            Panel(
                final_state["refactor_explanation"],
                title="[bold cyan]Technical Explanation[/bold cyan]",
                border_style="cyan",
            )
        )

    # Output Test Suite Panel
    if final_state.get("test_code"):
        console.print(
            Panel(
                Syntax(
                    final_state["test_code"],
                    "python",
                    theme="monokai",
                    line_numbers=True,
                ),
                title="[bold magenta]Generated Pytest Suite[/bold magenta]",
                border_style="magenta",
            )
        )


if __name__ == "__main__":
    run_cli() 