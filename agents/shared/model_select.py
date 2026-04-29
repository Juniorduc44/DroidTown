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
    # DeepSeek  (v4 series = paid subscription; v3 series = free)
    {"name": "deepseek-v4-flash:cloud",     "family": "DeepSeek",    "context": "1M",   "notes": "284B MoE preview, thinking",        "subscription": True},
    {"name": "deepseek-v4-pro:cloud",       "family": "DeepSeek",    "context": "1M",   "notes": "frontier MoE, 3 reasoning modes",   "subscription": True},
    {"name": "deepseek-v3.2:cloud",         "family": "DeepSeek",    "context": "128k", "notes": "tools + thinking"},
    {"name": "deepseek-v3.1:671b-cloud",    "family": "DeepSeek",    "context": "128k", "notes": "671B, strong reasoning"},
    # Moonshot (Kimi)  — k2.5/k2.6 = paid; k2-thinking/k2:1t = server errors (unavailable)
    {"name": "kimi-k2.6:cloud",            "family": "Moonshot",    "context": "128k", "notes": "vision, agentic, thinking",         "subscription": True},
    {"name": "kimi-k2.5:cloud",            "family": "Moonshot",    "context": "128k", "notes": "vision, long-horizon coding",       "subscription": True},
    # Z.ai (GLM)  — glm-5/5.1 = paid; glm-4.6/4.7 = free
    {"name": "glm-5.1:cloud",             "family": "Z.ai",        "context": "128k", "notes": "next-gen agentic, coding",          "subscription": True},
    {"name": "glm-5:cloud",               "family": "Z.ai",        "context": "128k", "notes": "744B total / 40B active",           "subscription": True},
    {"name": "glm-4.7:cloud",             "family": "Z.ai",        "context": "128k", "notes": "strong coding + tools"},
    {"name": "glm-4.6:cloud",             "family": "Z.ai",        "context": "128k", "notes": "tools + thinking"},
    # Google
    {"name": "gemma4:31b-cloud",          "family": "Google",      "context": "256k", "notes": "vision, audio, thinking"},
    {"name": "gemini-3-flash-preview:cloud","family": "Google",     "context": "128k", "notes": "vision, fast, frontier"},
    # Alibaba (Qwen)
    {"name": "qwen3.5:cloud",             "family": "Alibaba",     "context": "256k", "notes": "vision, thinking, multimodal"},
    {"name": "qwen3-coder-next:cloud",    "family": "Alibaba",     "context": "128k", "notes": "agentic coding"},
    {"name": "qwen3-next:80b-cloud",      "family": "Alibaba",     "context": "256k", "notes": "80B, efficient thinking"},
    {"name": "qwen3-vl:235b-cloud",       "family": "Alibaba",     "context": "256k", "notes": "235B vision-language"},
    {"name": "qwen3-coder:480b-cloud",    "family": "Alibaba",     "context": "256k", "notes": "480B coding MoE"},
    # NVIDIA
    {"name": "nemotron-3-super:cloud",    "family": "NVIDIA",      "context": "1M",   "notes": "120B MoE / 12B active"},
    {"name": "nemotron-3-nano:30b-cloud", "family": "NVIDIA",      "context": "1M",   "notes": "efficient, 30B, thinking"},
    # MiniMax
    {"name": "minimax-m2.7:cloud",        "family": "MiniMax",     "context": "128k", "notes": "agentic, productivity"},
    {"name": "minimax-m2.5:cloud",        "family": "MiniMax",     "context": "128k", "notes": "coding + agentic workflows"},
    {"name": "minimax-m2.1:cloud",        "family": "MiniMax",     "context": "128k", "notes": "tools"},
    {"name": "minimax-m2:cloud",          "family": "MiniMax",     "context": "128k", "notes": "tools + thinking"},
    # Mistral
    {"name": "mistral-large-3:675b-cloud","family": "Mistral",     "context": "128k", "notes": "vision, multilingual, 675B"},
    {"name": "devstral-2:123b-cloud",     "family": "Mistral",     "context": "128k", "notes": "123B codebase agent"},
    {"name": "devstral-small-2:24b-cloud","family": "Mistral",     "context": "128k", "notes": "24B vision + tools"},
    {"name": "ministral-3:3b-cloud",      "family": "Mistral",     "context": "128k", "notes": "3B vision, edge-class"},
    # OpenAI OSS
    {"name": "gpt-oss:20b-cloud",         "family": "OpenAI",      "context": "128k", "notes": "20B, thinking"},
    {"name": "gpt-oss:120b-cloud",        "family": "OpenAI",      "context": "128k", "notes": "120B, thinking"},
    # Essential AI
    {"name": "rnj-1:8b-cloud",            "family": "Essential AI","context": "128k", "notes": "8B dense, tool-optimized"},
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
            "capabilities": ["tools"],
            "has_tools": True,
            "source": "ollama-cloud",
            "family": m.get("family", ""),
            "context": m.get("context", ""),
            "notes": m.get("notes", ""),
            "subscription": m.get("subscription", False),
        }
        for m in OLLAMA_CLOUD_CATALOG
    ]


def check_cloud_access(model_name: str) -> str:
    """
    Check if a cloud model is accessible.
    Returns: "ok" | "unauth" | "subscription" | "unknown"
    """
    try:
        resp = httpx.post(
            "http://localhost:11434/api/chat",
            json={"model": model_name, "messages": [{"role": "user", "content": "hi"}], "stream": False},
            timeout=15,
        )
        txt = resp.text.lower()
        if resp.status_code == 403 or "subscription" in txt:
            return "subscription"
        if resp.status_code == 401 or "unauthorized" in txt:
            return "unauth"
        return "ok"
    except Exception:
        return "unknown"


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
    cloud_table.add_column("Access", width=6)
    cloud_table.add_column("Notes", style="dim")

    for i, m in enumerate(cloud_models, offset + 1):
        access_str = "[yellow]💳[/yellow]" if m.get("subscription") else "[green]✅[/green]"
        cloud_table.add_row(
            str(i), m["name"], m.get("family", ""), m.get("context", ""),
            access_str, m.get("notes", "")
        )

    console.print(cloud_table)
    console.print("[dim]☁ Cloud models: [green]✅[/green] free with [bold cyan]ollama signin[/bold cyan]  "
                  "[yellow]💳[/yellow] requires paid subscription (ollama.com/upgrade)[/dim]")
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

        if selected["cloud"]:
            access = check_cloud_access(selected["name"])
            if access == "subscription":
                console.print(Panel(
                    f"[bold yellow]{selected['name']}[/bold yellow] requires a paid Ollama subscription.\n\n"
                    "Upgrade at: [bold cyan]https://ollama.com/upgrade[/bold cyan]\n"
                    "Or pick a [green]✅[/green] free cloud model from the list.",
                    title="💳 Subscription Required", border_style="yellow"
                ))
                continue
            if access == "unauth":
                console.print(Panel(
                    "[bold red]Cloud model requires Ollama authentication.[/bold red]\n\n"
                    "Run: [bold cyan]ollama signin[/bold cyan]  then retry.",
                    title="❌ Unauthorized", border_style="red"
                ))
                continue

        console.print(f"\n[bold green]Using model:[/bold green] {selected['name']}\n")
        return selected["name"]
