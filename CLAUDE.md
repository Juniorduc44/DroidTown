# DroidTown

A local-first, GPU-accelerated town of AI droids — runs on Ollama (local or cloud) and Claude Code interchangeably.

## How to invoke a droid

```
Do a security review of agents/cli/agent.py
Plan and coordinate a multi-droid task
Run GPU diagnostics and optimize for local LLMs
```

Claude Code reads this file on every session. Each droid below is a context slice — load only the one you need.

## Droid roster

@.factory/droids/reviewer.md
@.factory/droids/cli.md
@.factory/droids/browser.md
@.factory/droids/gpu.md
@.factory/droids/planner.md
@.factory/droids/researcher.md

## Shared state

@context.md

## Agent workspace

Task-specific helpers and learned domain skills live in `agent-workspace/`.
Droids write back to `agent-workspace/domain-skills/<domain>/` when they discover something reusable.
Core helpers are in `agent-workspace/agent_helpers.py`.

## Runtime rules

- **Claude Code active** → you are the droid. Load the relevant droid slice, follow its system prompt and rules. No Python process needed.
- **Ollama local** → `agents/shared/runtime.py` auto-detects GPU and routes to the right model. Run `./scan`, `./cli`, or `./browser`.
- **Claude API** → set `CLAUDE_API_KEY` and `runtime.py` switches backends automatically.
- **GPU** → `agents/shared/gpu_detect.py` configures Ollama for maximum GPU utilization on startup. Run `./gpu-optimize` to tune manually.

## ICM file tree — one droid, one slice

Each droid definition in `.factory/droids/` is the *complete* context for that droid:
- Its identity and system prompt
- Its tool list
- Its rules and output format
- Nothing else

Never load another droid's slice during a task. If a task needs multiple droids, use the **planner** to coordinate and hand off.

## Project structure

```
DroidTown/
├── CLAUDE.md                        ← you are here
├── context.md                       ← live town state board
├── .factory/
│   ├── droids/                      ← ICM context slices, one per droid
│   └── registry.md                  ← droid capability map
├── agent-workspace/
│   ├── agent_helpers.py             ← shared helpers (agent-editable)
│   └── domain-skills/              ← learned per-domain skills
├── agents/
│   ├── shared/
│   │   ├── model_select.py          ← Ollama model picker (GPU-aware, cloud-aware)
│   │   ├── gpu_detect.py            ← GPU detection + Ollama tuning
│   │   └── runtime.py               ← unified Ollama/Claude runner
│   ├── security/                    ← security audit agent
│   ├── cli/                         ← filesystem/shell agent
│   ├── gpu/                         ← GPU diagnostics agent
│   └── browser/                     ← browser automation agent
├── howTo/                           ← setup and usage guides
├── scan                             ← entrypoint: security scan
├── cli                              ← entrypoint: CLI agent
└── browser                          ← entrypoint: browser agent
```
