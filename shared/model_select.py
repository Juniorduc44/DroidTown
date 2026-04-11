import sys
import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def get_available_models():
    """Fetch all models from the local Ollama instance."""
    try:
        resp = httpx.get("http://localhost:11434/api/tags", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        models = []
        for m in data.get("models", []):
            name = m.get("name", "")
            size = m.get("size", 0)
            size_str = f"{size / 1e9:.1f} GB" if size else "cloud"
            is_cloud = name.endswith(":cloud")
            models.append({"name": name, "size": size_str, "cloud": is_cloud})
        return models
    except httpx.ConnectError:
        console.print(Panel(
            "[bold red]Cannot connect to Ollama.[/bold red]\n\n"
            "Make sure Ollama is running:\n\n"
            "  [bold cyan]ollama serve[/bold cyan]",
            title="❌ Connection Error", border_style="red"
        ))
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error fetching models: {e}[/red]")
        sys.exit(1)


def check_cloud_auth(model_name: str) -> bool:
    """Check if a cloud model is authorized. Returns True if auth is ok."""
    try:
        resp = httpx.post(
            "http://localhost:11434/api/chat",
            json={"model": model_name, "messages": [{"role": "user", "content": "hi"}], "stream": False},
            timeout=15,
        )
        if resp.status_code == 401 or "unauthorized" in resp.text.lower():
            return False
        return True
    except Exception:
        return True


def select_model() -> str:
    """Display a model selection menu and return the chosen model name."""
    models = get_available_models()

    if not models:
        console.print("[red]No models found. Install one with: ollama pull <model>[/red]")
        sys.exit(1)

    table = Table(title="Available Models", border_style="cyan", show_lines=True)
    table.add_column("#", style="bold yellow", width=4)
    table.add_column("Model", style="bold white")
    table.add_column("Size", style="dim")
    table.add_column("Type", style="dim")

    for i, m in enumerate(models, 1):
        model_type = "[magenta]☁ cloud[/magenta]" if m["cloud"] else "[green]💻 local[/green]"
        table.add_row(str(i), m["name"], m["size"], model_type)

    console.print(table)
    console.print()

    while True:
        try:
            choice = console.input("[bold yellow]Select a model (number): [/bold yellow]").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)

        if not choice.isdigit() or int(choice) < 1 or int(choice) > len(models):
            console.print(f"[red]Enter a number between 1 and {len(models)}[/red]")
            continue

        selected = models[int(choice) - 1]

        if selected["cloud"] and not check_cloud_auth(selected["name"]):
            console.print(Panel(
                "[bold red]Cloud model requires authentication.[/bold red]\n\n"
                "Run: [bold cyan]ollama signin[/bold cyan]\n\n"
                "Then try again or pick a local model.",
                title="❌ Unauthorized", border_style="red"
            ))
            continue

        console.print(f"\n[bold green]Using model:[/bold green] {selected['name']}\n")
        return selected["name"]
