"""
DroidTown model selector — GPU-aware, cloud-aware.

Shows local Ollama models + the full Ollama cloud catalog.
Configures GPU env vars before returning the selected model name.
"""

import sys
import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.rule import Rule

console = Console()

# ---------------------------------------------------------------------------
# Ollama cloud model catalog
# All models accessible via Ollama cloud (appended after local models).
# Ollama routes these to hosted inference — no local VRAM required.
# ---------------------------------------------------------------------------
OLLAMA_CLOUD_CATALOG: list[dict] = [
    # Meta Llama
    {"name": "llama4:scout",        "family": "Meta",       "context": "10M", "notes": "128-expert MoE, multimodal"},
    {"name": "llama4:maverick",     "family": "Meta",       "context": "1M",  "notes": "17B active params, multimodal"},
    {"name": "llama3.3:70b",        "family": "Meta",       "context": "128k", "notes": "top open-weight 70B"},
    {"name": "llama3.1:405b",       "family": "Meta",       "context": "128k", "notes": "flagship, tool-capable"},
    # Qwen
    {"name": "qwen3:235b-a22b",     "family": "Alibaba",    "context": "128k", "notes": "235B MoE, thinking mode"},
    {"name": "qwen3:32b",           "family": "Alibaba",    "context": "128k", "notes": "dense 32B, strong coder"},
    {"name": "qwen2.5-coder:32b",   "family": "Alibaba",    "context": "128k", "notes": "best open coding model"},
    # DeepSeek
    {"name": "deepseek-r1:671b",    "family": "DeepSeek",   "context": "128k", "notes": "o1-level reasoning"},
    {"name": "deepseek-r1:70b",     "family": "DeepSeek",   "context": "128k", "notes": "reasoning, tool-capable"},
    {"name": "deepseek-v3:685b",    "family": "DeepSeek",   "context": "128k", "notes": "frontier MoE"},
    # Mistral
    {"name": "mistral-large:123b",  "family": "Mistral",    "context": "128k", "notes": "top Mistral, multilingual"},
    {"name": "mistral-small:24b",   "family": "Mistral",    "context": "128k", "notes": "efficient, fast"},
    {"name": "codestral:22b",       "family": "Mistral",    "context": "256k", "notes": "code specialist"},
    # Google
    {"name": "gemma3:27b",          "family": "Google",     "context": "128k", "notes": "multimodal, top Gemma"},
    {"name": "gemma3:9b",           "family": "Google",     "context": "128k", "notes": "fast, multilingual"},
    # Microsoft
    {"name": "phi4:14b",            "family": "Microsoft",  "context": "16k",  "notes": "small but capable"},
    {"name": "phi4-reasoning:14b",  "family": "Microsoft",  "context": "16k",  "notes": "reasoning-optimized"},
    # Cohere
    {"name": "command-r-plus:104b", "family": "Cohere",     "context": "128k", "notes": "RAG champion"},
    {"name": "command-r:35b",       "family": "Cohere",     "context": "128k", "notes": "fast RAG"},
    # xAI
    {"name": "granite3.3:8b",       "family": "IBM",        "context": "128k", "notes": "thinking + tools"},
    # Other notable
    {"name": "falcon3:10b",         "family": "TII",        "context": "32k",  "notes": "open, multilingual"},
    {"name": "solar-pro:22b",       "family": "Upstage",    "context": "4k",   "notes": "Korean + English"},
]


# ---------------------------------------------------------------------------
# Local Ollama helpers
# ---------------------------------------------------------------------------

def _get_model_capabilities(model_name: str) -> list[str]:
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


def get_local_models() -> list[dict]:
    """Fetch models from the running Ollama instance."""
    try:
        resp = httpx.get("http://localhost:11434/api/tags", timeout=10)
        resp.raise_for_status()
        models = []
        for m in resp.json().get("models", []):
            name = m.get("name", "")
            size = m.get("size", 0)
            size_str = f"{size / 1e9:.1f} GB" if size else "—"
            caps = _get_model_capabilities(name)
            models.append({
                "name": name,
                "size": size_str,
                "cloud": False,
                "capabilities": caps,
                "has_tools": "tools" in caps,
                "source": "local",
            })
        return models
    except httpx.ConnectError:
        console.print(Panel(
            "[bold red]Cannot connect to Ollama.[/bold red]\n\n"
            "Start it with:  [bold cyan]ollama serve[/bold cyan]",
            title="❌ Ollama not running", border_style="red"
        ))
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error fetching local models: {e}[/red]")
        sys.exit(1)


def get_cloud_models() -> list[dict]:
    """Return the static Ollama cloud catalog as selectable entries."""
    return [
        {
            "name": m["name"],
            "size": "cloud",
            "cloud": True,
            "capabilities": ["tools"],   # all cloud models support tools
            "has_tools": True,
            "source": "ollama-cloud",
            "family": m.get("family", ""),
            "context": m.get("context", ""),
            "notes": m.get("notes", ""),
        }
        for m in OLLAMA_CLOUD_CATALOG
    ]


def check_cloud_auth(model_name: str) -> bool:
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


# ---------------------------------------------------------------------------
# Main selector
# ---------------------------------------------------------------------------

def select_model(require_tools: bool = True, show_gpu: bool = True) -> str:
    """
    Interactive model selection menu.

    Shows:
    - GPU status header (VRAM, recommended models)
    - Section 1: locally pulled Ollama models
    - Section 2: full Ollama cloud catalog

    Returns the chosen model name string.
    """
    # GPU detection — import here to avoid circular deps
    gpu = None
    if show_gpu:
        try:
            from gpu_detect import setup as gpu_setup
            gpu = gpu_setup(silent=False)
        except ImportError:
            try:
                import importlib.util, pathlib
                spec = importlib.util.spec_from_file_location(
                    "gpu_detect",
                    pathlib.Path(__file__).parent / "gpu_detect.py"
                )
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                gpu = mod.setup(silent=False)
            except Exception:
                pass

    local_models = get_local_models()
    cloud_models = get_cloud_models()
    all_models = local_models + cloud_models

    # --- Local models table ---
    console.print(Rule("[bold cyan]Local Models[/bold cyan]"))
    local_table = Table(border_style="cyan", show_lines=True)
    local_table.add_column("#", style="bold yellow", width=4)
    local_table.add_column("Model", style="bold white")
    local_table.add_column("Size", style="dim", width=10)
    local_table.add_column("Tools", width=7)
    local_table.add_column("Capabilities", style="dim")

    if not local_models:
        local_table.add_row("—", "[dim]No local models pulled[/dim]", "—", "—", "—")
    else:
        for i, m in enumerate(local_models, 1):
            tools_str = "[green]✓[/green]" if m["has_tools"] else "[red]✗[/red]"
            caps_str = ", ".join(m["capabilities"]) if m["capabilities"] else "completion"
            if require_tools and not m["has_tools"]:
                local_table.add_row(
                    f"[dim]{i}[/dim]", f"[dim]{m['name']}[/dim]",
                    f"[dim]{m['size']}[/dim]", tools_str, f"[dim]{caps_str}[/dim]"
                )
            else:
                local_table.add_row(str(i), m["name"], m["size"], tools_str, caps_str)

    console.print(local_table)

    if gpu and gpu.has_gpu:
        recs = []
        try:
            from gpu_detect import recommended_model
            recs = recommended_model(gpu)
        except Exception:
            pass
        if recs:
            console.print(f"[dim]GPU fit recommendations: [bold]{', '.join(recs[:3])}[/bold][/dim]")

    # --- Cloud models table ---
    offset = len(local_models)
    console.print()
    console.print(Rule("[bold magenta]☁  Ollama Cloud Models[/bold magenta]"))
    cloud_table = Table(border_style="magenta", show_lines=True)
    cloud_table.add_column("#", style="bold yellow", width=5)
    cloud_table.add_column("Model", style="bold white")
    cloud_table.add_column("Family", style="dim", width=12)
    cloud_table.add_column("Context", style="dim", width=9)
    cloud_table.add_column("Notes", style="dim")

    for i, m in enumerate(cloud_models, offset + 1):
        cloud_table.add_row(
            str(i), m["name"], m.get("family", ""), m.get("context", ""), m.get("notes", "")
        )

    console.print(cloud_table)
    console.print("[dim]Cloud models run on Ollama's hosted infrastructure — no local VRAM required.[/dim]")
    console.print()

    if require_tools:
        compatible_local = [m for m in local_models if m["has_tools"]]
        if not compatible_local and not cloud_models:
            console.print(Panel(
                "[bold red]No tool-capable models available.[/bold red]\n\n"
                "Pull a local model:  [bold cyan]ollama pull qwen3:8b[/bold cyan]\n"
                "Or pick a cloud model from the list above.",
                title="❌ No Compatible Models", border_style="red"
            ))
            sys.exit(1)
        console.print("[dim]Models marked [red]✗[/red] Tools cannot be used with tool-calling agents.[/dim]\n")

    # --- Selection loop ---
    while True:
        try:
            choice = console.input("[bold yellow]Select model (number): [/bold yellow]").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)

        if not choice.isdigit() or int(choice) < 1 or int(choice) > len(all_models):
            console.print(f"[red]Enter a number between 1 and {len(all_models)}[/red]")
            continue

        selected = all_models[int(choice) - 1]

        if require_tools and not selected["has_tools"]:
            console.print(f"[red]{selected['name']} doesn't support tools. Pick a model with ✓.[/red]")
            continue

        if selected["cloud"] and not check_cloud_auth(selected["name"]):
            console.print(Panel(
                "[bold red]Cloud model requires Ollama authentication.[/bold red]\n\n"
                "Run: [bold cyan]ollama signin[/bold cyan]  then retry.",
                title="❌ Unauthorized", border_style="red"
            ))
            continue

        console.print(f"\n[bold green]Using model:[/bold green] {selected['name']}\n")
        return selected["name"]
