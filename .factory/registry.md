# Droid Registry

Maps every droid to its context slice, capabilities, tools, and entry point.
The planner droid reads this to route tasks. Claude Code reads this via CLAUDE.md.

## Roster

| Droid | File | Runtime | Primary capability |
|-------|------|---------|-------------------|
| reviewer | `.factory/droids/reviewer.md` | Ollama / Claude | Security audit — credentials, injection, weak crypto |
| cli | `.factory/droids/cli.md` | Ollama / Claude | Filesystem + shell — read, write, move, run commands |
| browser | `.factory/droids/browser.md` | Ollama / Claude Code / Cloud SDK | Browser automation via CDP or Browser Use Cloud |
| gpu | `.factory/droids/gpu.md` | Ollama / Claude | GPU diagnostics, driver advice, Ollama tuning |
| planner | `.factory/droids/planner.md` | Claude Code preferred | Multi-droid orchestration — routes, sequences, hands off |
| researcher | `.factory/droids/researcher.md` | Ollama / Claude | Web research, CVE lookup, doc summarization |

## Tool index

| Tool | Droids that use it |
|------|--------------------|
| `run_command` | cli, gpu, reviewer |
| `read_file` | cli, reviewer, planner, researcher, gpu |
| `write_file` | cli, planner, researcher |
| `http_get` | researcher |
| `goto_url` / `new_tab` | browser |
| `click_at_xy` / `capture_screenshot` | browser |
| `js` | browser |
| `list_directory` | cli |

## Model routing

| Condition | Model used |
|-----------|-----------|
| `CLAUDE_API_KEY` set | Claude API (claude-sonnet-4-6 default) |
| Claude Code active | Claude Code native (no Python process) |
| Ollama running locally | Interactive picker via `model_select.py` |
| GPU detected | GPU-accelerated Ollama layers (auto-configured) |
| No GPU | Ollama CPU mode with quantized model recommendation |

## Adding a new droid

1. Create `.factory/droids/<name>.md` with YAML frontmatter + system prompt.
2. Add a row to this registry.
3. Add `@.factory/droids/<name>.md` to `CLAUDE.md`.
4. Optionally add a Python agent in `agents/<name>/agent.py` for Ollama CLI use.
