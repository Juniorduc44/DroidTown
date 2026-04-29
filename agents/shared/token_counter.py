"""
DroidTown session token counter.

Tracks tokens in (prompt) and tokens out (completion) across all agent
calls in a single CLI session. Works with Ollama local and Ollama cloud.

Ollama returns eval_count (tokens generated) and prompt_eval_count
(prompt tokens) on every /api/chat response. We capture these via a
LangChain callback handler and accumulate them into a SessionCounter.

Usage:
    from token_counter import SessionCounter, OllamaTokenCallback, print_token_summary

    counter  = SessionCounter()
    callback = OllamaTokenCallback(counter)

    llm = ChatOllama(model=..., callbacks=[callback])
    # ... run agent normally ...

    print_token_summary(counter)   # print at end of session
"""

import time
from dataclasses import dataclass, field
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live

console = Console()


@dataclass
class SessionCounter:
    tokens_in: int = 0
    tokens_out: int = 0
    calls: int = 0
    session_start: float = field(default_factory=time.time)

    @property
    def total_tokens(self) -> int:
        return self.tokens_in + self.tokens_out

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.session_start

    @property
    def tokens_per_second(self) -> float:
        elapsed = self.elapsed_seconds
        return round(self.tokens_out / elapsed, 1) if elapsed > 0 else 0.0


class OllamaTokenCallback(BaseCallbackHandler):
    """
    LangChain callback that reads Ollama token usage from LLMResult metadata.

    Ollama populates usage_metadata on each generation with:
      - input_tokens  (prompt_eval_count)
      - output_tokens (eval_count)
    """

    def __init__(self, counter: SessionCounter):
        super().__init__()
        self.counter = counter

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        for generations in response.generations:
            for gen in generations:
                # LangChain >= 0.3 stores usage in generation_info
                info = getattr(gen, "generation_info", None) or {}

                # Ollama puts it in response metadata
                usage = (
                    info.get("usage_metadata")
                    or info.get("usage")
                    or {}
                )

                tokens_in  = (
                    usage.get("input_tokens")
                    or usage.get("prompt_eval_count")
                    or info.get("prompt_eval_count", 0)
                )
                tokens_out = (
                    usage.get("output_tokens")
                    or usage.get("eval_count")
                    or info.get("eval_count", 0)
                )

                self.counter.tokens_in  += int(tokens_in  or 0)
                self.counter.tokens_out += int(tokens_out or 0)
                self.counter.calls      += 1

        # Also check usage_metadata at the top-level response level
        if hasattr(response, "llm_output") and response.llm_output:
            meta = response.llm_output.get("usage_metadata") or {}
            if meta:
                self.counter.tokens_in  += int(meta.get("input_tokens",  0))
                self.counter.tokens_out += int(meta.get("output_tokens", 0))


def _make_counter_table(counter: SessionCounter, model: str = "") -> Table:
    table = Table(border_style="dim", show_header=False, padding=(0, 2), box=None)
    table.add_column("Label", style="dim")
    table.add_column("Value", style="bold white")

    if model:
        table.add_row("Model", f"[cyan]{model}[/cyan]")
    table.add_row("Tokens in",    f"[green]{counter.tokens_in:,}[/green]")
    table.add_row("Tokens out",   f"[yellow]{counter.tokens_out:,}[/yellow]")
    table.add_row("Total tokens", f"[bold]{counter.total_tokens:,}[/bold]")
    table.add_row("LLM calls",    str(counter.calls))
    table.add_row("Speed",        f"{counter.tokens_per_second} tok/s")
    elapsed = counter.elapsed_seconds
    table.add_row("Session time", f"{int(elapsed // 60)}m {int(elapsed % 60)}s")
    return table


def print_token_bar(counter: SessionCounter, model: str = "") -> None:
    """Print a compact one-line token bar (used after each agent call)."""
    console.print(
        f"[dim]┤ tokens: [green]↑{counter.tokens_in:,}[/green] in  "
        f"[yellow]↓{counter.tokens_out:,}[/yellow] out  "
        f"[bold]{counter.total_tokens:,}[/bold] total  "
        f"[dim]{counter.tokens_per_second} tok/s[/dim]  "
        f"calls={counter.calls} ├[/dim]"
    )


def print_token_summary(counter: SessionCounter, model: str = "") -> None:
    """Print a full token summary panel at end of session."""
    table = _make_counter_table(counter, model)
    console.print()
    console.print(Panel(
        table,
        title="[bold]📊 Session Token Usage[/bold]",
        border_style="cyan",
        padding=(0, 1),
    ))
