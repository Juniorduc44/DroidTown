"""
DroidTown unified runtime shim.

Detects whether to use:
  1. Claude API  — CLAUDE_API_KEY is set
  2. Gemini API  — GEMINI_API_KEY is set (free tier supported)
  3. Ollama local — Ollama is reachable at localhost:11434
  4. Claude Code  — detected via CLAUDE_CODE env var (no Python process needed;
                    this module is a no-op and just reports the runtime)

Usage in any agent:
    from runtime import get_llm, RUNTIME
    llm = get_llm()   # returns the right LLM object for the current environment
"""

import os
import sys
import pathlib
from enum import Enum

import httpx
from rich.console import Console
from rich.panel import Panel

# Load .env from the project root (DroidTown/) without overwriting shell vars
try:
    from dotenv import load_dotenv
    _proj_root = pathlib.Path(__file__).resolve().parent.parent.parent
    load_dotenv(_proj_root / ".env", override=False)
except ImportError:
    pass  # dotenv not installed yet — keys must be set in the shell

console = Console()


class Runtime(str, Enum):
    CLAUDE_CODE = "claude-code"   # running inside Claude Code — no LLM object needed
    CLAUDE_API  = "claude-api"    # Anthropic API via CLAUDE_API_KEY
    GEMINI      = "gemini"        # Google Gemini API via GEMINI_API_KEY
    OLLAMA      = "ollama"        # local or cloud Ollama


def detect_runtime() -> Runtime:
    """Determine the active runtime environment."""
    # Claude Code sets this env var when invoking tools
    if os.environ.get("CLAUDE_CODE") or os.environ.get("ANTHROPIC_TOOL_USE"):
        return Runtime.CLAUDE_CODE

    if os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"):
        return Runtime.CLAUDE_API

    if os.environ.get("GEMINI_API_KEY"):
        return Runtime.GEMINI

    # Try Ollama
    try:
        resp = httpx.get("http://localhost:11434/api/tags", timeout=4)
        if resp.status_code == 200:
            return Runtime.OLLAMA
    except Exception:
        pass

    # Default to Ollama and let model_select handle the error
    return Runtime.OLLAMA


RUNTIME: Runtime = detect_runtime()


def get_llm(droid: str = "default", require_tools: bool = True):
    """
    Return the appropriate LLM object for the detected runtime.

    - CLAUDE_CODE  → returns None (Claude Code IS the agent; no LLM object needed)
    - CLAUDE_API   → returns a ChatAnthropic LangChain object
    - GEMINI       → returns a ChatGoogleGenerativeAI LangChain object
    - OLLAMA       → runs GPU setup then returns a ChatOllama object via model_select
    """
    if RUNTIME == Runtime.CLAUDE_CODE:
        console.print(Panel(
            "[bold cyan]Running inside Claude Code.[/bold cyan]\n"
            "Droids are loaded from [bold].factory/droids/[/bold] via CLAUDE.md.\n"
            "No Ollama process is needed.",
            title="🤖 DroidTown — Claude Code Runtime", border_style="cyan"
        ))
        return None

    if RUNTIME == Runtime.CLAUDE_API:
        return _build_claude_llm(droid)

    if RUNTIME == Runtime.GEMINI:
        return _build_gemini_llm(droid)

    # Ollama — default path
    return _build_ollama_llm(require_tools)


def _build_ollama_llm(require_tools: bool):
    """GPU setup → model selection → ChatOllama."""
    # GPU env vars must be set BEFORE the LLM is constructed
    try:
        import importlib.util, pathlib
        spec = importlib.util.spec_from_file_location(
            "gpu_detect", pathlib.Path(__file__).parent / "gpu_detect.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.setup(silent=False)
    except Exception as e:
        console.print(f"[dim yellow]GPU detection skipped: {e}[/dim yellow]")

    try:
        import importlib.util, pathlib
        spec = importlib.util.spec_from_file_location(
            "model_select", pathlib.Path(__file__).parent / "model_select.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        model_name = mod.select_model(require_tools=require_tools, show_gpu=False)
    except Exception as e:
        console.print(f"[red]Model selection failed: {e}[/red]")
        sys.exit(1)

    os.environ["DROIDTOWN_MODEL"] = model_name

    from langchain_ollama import ChatOllama
    return ChatOllama(model=model_name, temperature=0.0)


def _build_gemini_llm(droid: str):
    """Build a LangChain ChatGoogleGenerativeAI object for the Gemini API."""
    api_key = os.environ.get("GEMINI_API_KEY", "")

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError:
        console.print(Panel(
            "[bold red]langchain-google-genai not installed.[/bold red]\n\n"
            "Run: [bold cyan]pip install langchain-google-genai[/bold cyan]\n"
            "Or:  [bold cyan]pip install -r agents/requirements.txt[/bold cyan]",
            title="❌ Missing dependency", border_style="red"
        ))
        sys.exit(1)

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "model_select", pathlib.Path(__file__).parent / "model_select.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Honour a pinned model from env or let user pick
    model_name = os.environ.get("GEMINI_MODEL") or mod.select_gemini_model()
    os.environ["DROIDTOWN_MODEL"] = model_name

    console.print(Panel(
        f"[bold blue]Gemini runtime[/bold blue]\n"
        f"Model: [cyan]{model_name}[/cyan]  Droid: [cyan]{droid}[/cyan]",
        title="🤖 DroidTown — Gemini Runtime", border_style="blue"
    ))
    return ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key, temperature=0.0)


def _build_claude_llm(droid: str):
    """Build a LangChain ChatAnthropic object for direct API use."""
    api_key = os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        console.print(Panel(
            "[bold red]langchain-anthropic not installed.[/bold red]\n\n"
            "Run: [bold cyan]pip install langchain-anthropic[/bold cyan]",
            title="❌ Missing dependency", border_style="red"
        ))
        sys.exit(1)

    console.print(Panel(
        f"[bold green]Claude API runtime[/bold green]\n"
        f"Model: [cyan]{model}[/cyan]  Droid: [cyan]{droid}[/cyan]",
        title="🤖 DroidTown — Claude API Runtime", border_style="green"
    ))
    return ChatAnthropic(model=model, api_key=api_key, temperature=0.0)


def print_runtime_banner() -> None:
    """Print a one-line runtime banner at agent startup."""
    badges = {
        Runtime.CLAUDE_CODE: "[bold cyan]Claude Code[/bold cyan]",
        Runtime.CLAUDE_API:  "[bold green]Claude API[/bold green]",
        Runtime.GEMINI:      "[bold blue]Gemini[/bold blue]",
        Runtime.OLLAMA:      "[bold magenta]Ollama[/bold magenta]",
    }
    console.print(f"[dim]DroidTown runtime:[/dim] {badges[RUNTIME]}")
