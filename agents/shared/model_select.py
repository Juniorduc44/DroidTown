import sys
import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def _get_model_capabilities(model_name: str) -> list:
    """Fetch capabilities for a specific model via /api/show."""
    try:
        resp = httpx.post(
            "http://localhost:11434/api/show",
            json={"name": model_name},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("capabilities", [])
    except Exception:
        pass
    return []


def get_available_models():
    """Fetch all models from the local Ollama instance with capabilities."""
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
            caps = _get_model_capabilities(name)
            models.append({
                "name": name,
                "size": size_str,
                "cloud": is_cloud,
                "capabilities": caps,
                "has_tools": "tools" in caps,
            })
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


def select_model(require_tools: bool = True) -> str:
    """Display a model selection menu and return the chosen model name.

    Args:
        require_tools: If True, only models with tool-calling support are selectable.
                       Models without tools are shown but marked as incompatible.
    """
    models = get_available_models()

    if not models:
        console.print("[red]No models found. Install one with: ollama pull <model>[/red]")
        sys.exit(1)

    table = Table(title="Available Models", border_style="cyan", show_lines=True)
    table.add_column("#", style="bold yellow", width=4)
    table.add_column("Model", style="bold white")
    table.add_column("Size", style="dim")
    table.add_column("Type", style="dim")
    table.add_column("Tools", width=8)
    table.add_column("Capabilities", style="dim")

    for i, m in enumerate(models, 1):
        model_type = "[magenta]☁ cloud[/magenta]" if m["cloud"] else "[green]💻 local[/green]"
        tools_str = "[green]✓[/green]" if m["has_tools"] else "[red]✗[/red]"
        caps_str = ", ".join(m["capabilities"]) if m["capabilities"] else "completion"

        if require_tools and not m["has_tools"]:
            table.add_row(f"[dim]{i}[/dim]", f"[dim]{m['name']}[/dim]", f"[dim]{m['size']}[/dim]", model_type, tools_str, f"[dim]{caps_str}[/dim]")
        else:
            table.add_row(str(i), m["name"], m["size"], model_type, tools_str, caps_str)

    console.print(table)

    if require_tools:
        compatible = [m for m in models if m["has_tools"]]
        if not compatible:
            console.print(Panel(
                "[bold red]No models with tool-calling support found.[/bold red]\n\n"
                "DroidTown agents require models that support tools.\n"
                "Install a compatible model, for example:\n\n"
                "  [bold cyan]ollama pull qwen3:8b[/bold cyan]\n"
                "  [bold cyan]ollama pull glm-5.1:cloud[/bold cyan]",
                title="❌ No Compatible Models", border_style="red"
            ))
            sys.exit(1)
        console.print("[dim]Models marked with [red]✗[/red] Tools do not support tool-calling and cannot be used.[/dim]")

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

        if require_tools and not selected["has_tools"]:
            console.print(f"[red]{selected['name']} does not support tools. Pick a model marked with ✓.[/red]")
            continue

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
