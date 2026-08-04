"""
run_phase3_test.py
------------------
Direct validation script for testing the Phase 3 LangGraph self-healing loop.
"""

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from src.agent.graph import build_graph

console = Console()

def test_phase3_graph():
    console.print("\n[bold cyan]1. Reading Target Input Code...[/bold cyan]")
    with open("sample_input.py", "r", encoding="utf-8") as f:
        original_code = f.read()

    console.print(
        Panel(
            Syntax(original_code, "python", theme="monokai", line_numbers=True),
            title="[yellow]Original Input Code[/yellow]",
            border_style="yellow"
        )
    )

    console.print("\n[bold cyan]2. Initializing LangGraph Engine...[/bold cyan]")
    app = build_graph()

    initial_state = {
        "original_code": original_code,
        "refactored_code": None,
        "refactor_explanation": None,
        "test_code": None,
        "execution_result": None,
        "iteration_count": 0,
        "max_iterations": 3,
        "failure_history": [],
        "status": "INITIALIZED"
    }

    console.print("[bold green]► Executing State Graph...[/bold green]\n")
    final_state = app.invoke(initial_state)

    exec_res = final_state.get("execution_result")

    # Render Results
    table = Table(title="Phase 3 Graph Execution Results", border_style="blue")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="bold white")

    table.add_row("Status", final_state.get("status", "UNKNOWN"))
    table.add_row("Total Iterations", str(final_state.get("iteration_count", 0)))
    table.add_row("Tests Passed", "[bold green]YES[/bold green]" if exec_res and exec_res.passed else "[bold red]NO[/bold red]")
    table.add_row("Container Exit Code", str(exec_res.exit_code) if exec_res else "N/A")

    console.print(table)

    if final_state.get("refactored_code"):
        console.print(
            Panel(
                Syntax(final_state["refactored_code"], "python", theme="monokai", line_numbers=True),
                title="[bold green]Validated Refactored Code (Docker Passed)[/bold green]",
                border_style="green"
            )
        )

    if final_state.get("test_code"):
        console.print(
            Panel(
                Syntax(final_state["test_code"], "python", theme="monokai", line_numbers=True),
                title="[bold magenta]Generated Pytest Suite[/bold magenta]",
                border_style="magenta"
            )
        )

if __name__ == "__main__":
    test_phase3_graph()