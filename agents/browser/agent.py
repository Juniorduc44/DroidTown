import sys
import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "shared"))

from browser_use_sdk import BrowserUse, SupportedLLMs
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table

console = Console()

DEFAULT_MODEL = SupportedLLMs.claude_sonnet_4_6.value
API_KEY = os.environ.get("BROWSER_USE_API_KEY", "")


def select_model() -> str:
    """Present a model menu and return the chosen model ID string."""
    models = list(SupportedLLMs)

    table = Table(title="Browser Use Models", border_style="cyan", show_lines=True)
    table.add_column("#", style="bold yellow", width=4)
    table.add_column("Model ID", style="bold white")

    for i, m in enumerate(models, 1):
        if m.value == DEFAULT_MODEL:
            table.add_row(str(i), f"[bold green]{m.value}[/bold green] [dim](recommended)[/dim]")
        else:
            table.add_row(str(i), m.value)

    console.print(table)
    console.print(f"[dim]Press Enter to use the recommended model: {DEFAULT_MODEL}[/dim]\n")

    while True:
        try:
            choice = console.input("[bold yellow]Select a model (number or Enter for default): [/bold yellow]").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)

        if choice == "":
            console.print(f"\n[bold green]Using model:[/bold green] {DEFAULT_MODEL}\n")
            return DEFAULT_MODEL

        if not choice.isdigit() or not (1 <= int(choice) <= len(models)):
            console.print(f"[red]Enter a number between 1 and {len(models)}, or press Enter for default.[/red]")
            continue

        selected = models[int(choice) - 1]
        console.print(f"\n[bold green]Using model:[/bold green] {selected.value}\n")
        return selected.value


def run_task(client: BrowserUse, task: str, model: str):
    """Run a browser task with live step-by-step streaming."""
    console.print(Panel(f"[bold]{task}[/bold]", title="Browser Task", border_style="cyan"))

    try:
        stream = client.stream(task, llm=model)

        for step in stream:
            lines = [f"[bold cyan]Step {step.number}[/bold cyan]"]
            if step.url:
                lines.append(f"[dim]URL:[/dim]  {step.url}")
            lines.append(f"[dim]Goal:[/dim] {step.next_goal}")
            if step.evaluation_previous_goal and step.number > 1:
                lines.append(f"[dim]Eval:[/dim] {step.evaluation_previous_goal}")

            console.print(Panel("\n".join(lines), border_style="blue", padding=(0, 1)))

        result = stream.result
        if result and result.output:
            console.print(Panel(
                Markdown(result.output),
                title="Result",
                border_style="green",
                padding=(1, 2),
            ))
        else:
            console.print(Panel("[dim]Task completed — no text output returned.[/dim]", title="Done", border_style="green"))

    except KeyboardInterrupt:
        console.print("\n[yellow]Task cancelled.[/yellow]")
    except Exception as e:
        err = str(e)
        if "401" in err or "unauthorized" in err.lower() or "api key" in err.lower() or "api_key" in err.lower():
            console.print(Panel(
                "[bold red]Invalid or missing API key.[/bold red]\n\n"
                "Set your key:\n\n  [bold cyan]export BROWSER_USE_API_KEY=bu_...[/bold cyan]",
                title="Auth Error",
                border_style="red",
            ))
        else:
            console.print(Panel(f"[bold red]{err}[/bold red]", title="Error", border_style="red"))


if __name__ == "__main__":
    if not API_KEY:
        console.print(Panel(
            "[bold red]No API key found.[/bold red]\n\n"
            "Set it with:\n\n  [bold cyan]export BROWSER_USE_API_KEY=bu_...[/bold cyan]",
            title="Missing API Key",
            border_style="red",
        ))
        sys.exit(1)

    client = BrowserUse(api_key=API_KEY)
    model = select_model()

    if len(sys.argv) > 1:
        run_task(client, " ".join(sys.argv[1:]), model)
    else:
        console.print(Panel(
            "[bold cyan]DroidTown Browser Agent[/bold cyan]\n"
            "Powered by Browser Use Cloud\n\n"
            "Type a web task and press Enter. Type 'exit' to quit.",
            border_style="blue",
        ))
        while True:
            try:
                task = console.input("[bold yellow]> [/bold yellow]")
            except (EOFError, KeyboardInterrupt):
                break
            if task.strip().lower() in ("exit", "quit", "q"):
                console.print("[dim]Goodbye.[/dim]")
                break
            if not task.strip():
                continue
            run_task(client, task, model)
