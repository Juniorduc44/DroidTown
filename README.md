# DroidTown

A local-first, GPU-accelerated town of AI droids. Runs on **Ollama** (local or cloud) and **Claude Code** interchangeably — no vendor lock-in, minimal token waste.

Built on the **ICM (Interpretable Context Methodology)** pattern: each droid owns exactly one context slice, keeping token usage low and agent behavior predictable.

---

## Quick Start

```bash
git clone git@github.com:Juniorduc44/DroidTown.git
cd DroidTown
git checkout claude

# Install shared environment
cd agents && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt && deactivate && cd ..

# Make entrypoints executable
chmod +x scan cli browser gpu-optimize
```

---

## Droid Roster

| Droid | Entrypoint | Capability |
|-------|-----------|------------|
| **reviewer** | `./scan <file_or_dir>` | Security audit — secrets, injection, weak crypto |
| **cli** | `./cli` or `./cli "task"` | Filesystem + shell via natural language |
| **browser** | `./browser` or `./browser "task"` | Web automation (CDP local or Browser Use Cloud) |
| **gpu** | `./gpu-optimize` | GPU detection, driver advice, Ollama tuning |
| **planner** | Claude Code only | Multi-droid orchestration and task routing |
| **researcher** | Claude Code only | Web research, CVE lookup, doc summarization |

---

## GPU Optimization

DroidTown auto-detects your GPU at startup and configures Ollama for maximum local LLM performance.

```bash
./gpu-optimize          # standalone GPU status + tuning
./scan src/             # GPU auto-configured before model loads
./cli "list my files"   # same for all agents
```

What it does:
- Detects NVIDIA (CUDA), AMD (ROCm), and Intel GPUs
- Reads free VRAM and recommends models that fit
- Sets `OLLAMA_NUM_GPU=-1`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`
- On multi-GPU: sets `CUDA_VISIBLE_DEVICES=0,1,...`
- CPU-only fallback: recommends quantized models + thread tuning

**VRAM fit guide:**

| Free VRAM | Recommended models |
|-----------|-------------------|
| 24 GB+ | `qwen3:32b`, `llama3.3:70b-q4_K_M`, `deepseek-r1:32b` |
| 16 GB | `qwen3:14b`, `llama3.1:13b`, `mistral:12b` |
| 8 GB | `qwen3:8b`, `llama3.2:8b`, `phi4:8b`, `gemma3:9b` |
| 4 GB | `phi3.5:mini`, `qwen3:4b`, `gemma3:4b` |
| <4 GB | `qwen3:1.7b`, `llama3.2:1b` |

---

## Model Selection — Local + Cloud

When any Ollama agent starts it shows:

1. **GPU status** — name, VRAM free/total, temperature, VRAM-fit recommendations
2. **Local models** — everything pulled to your machine via `ollama pull`
3. **Ollama Cloud catalog** — 22 hosted models, no local VRAM needed

**Ollama Cloud models available (no local GPU required):**

| Model | Family | Context | Notes |
|-------|--------|---------|-------|
| `llama4:scout` | Meta | 10M | 128-expert MoE, multimodal |
| `llama4:maverick` | Meta | 1M | 17B active params |
| `llama3.3:70b` | Meta | 128k | Top open-weight 70B |
| `qwen3:235b-a22b` | Alibaba | 128k | 235B MoE, thinking mode |
| `qwen3:32b` | Alibaba | 128k | Dense 32B, strong coder |
| `qwen2.5-coder:32b` | Alibaba | 128k | Best open coding model |
| `deepseek-r1:671b` | DeepSeek | 128k | o1-level reasoning |
| `deepseek-r1:70b` | DeepSeek | 128k | Reasoning + tools |
| `deepseek-v3:685b` | DeepSeek | 128k | Frontier MoE |
| `mistral-large:123b` | Mistral | 128k | Top Mistral, multilingual |
| `codestral:22b` | Mistral | 256k | Code specialist |
| `gemma3:27b` | Google | 128k | Multimodal |
| `phi4-reasoning:14b` | Microsoft | 16k | Reasoning-optimized |
| `command-r-plus:104b` | Cohere | 128k | RAG champion |
| + 8 more | — | — | See `model_select.py` |

Cloud models require `ollama signin`. Local models work offline.

---

## Token Counter

Every Ollama agent session tracks **tokens in** (prompt) and **tokens out** (completion) live.

After each response:
```
┤ tokens: ↑1,024 in  ↓312 out  1,336 total  18.4 tok/s  calls=3 ├
```

At session end:
```
╭─────────────── 📊 Session Token Usage ────────────────╮
│  Model       claude-sonnet-4-6 / qwen3:8b             │
│  Tokens in   4,218                                     │
│  Tokens out  1,047                                     │
│  Total       5,265                                     │
│  LLM calls   7                                         │
│  Speed       21.3 tok/s                                │
│  Session     2m 14s                                    │
╰───────────────────────────────────────────────────────╯
```

Works for all Ollama local and cloud models. Not applicable in Claude Code mode (Claude Code tracks its own usage natively).

---

## Dual Runtime — Ollama ↔ Claude Code

| Env / Condition | Runtime used |
|----------------|-------------|
| Claude Code active | Native — droids load from `.factory/droids/` via `CLAUDE.md` |
| `CLAUDE_API_KEY` set | Anthropic API (`claude-sonnet-4-6` default) |
| Ollama running | Interactive model picker (GPU-aware, cloud-aware) |

Switch at any time — no code changes needed.

---

## ICM Architecture — One Droid, One Slice

Each droid in `.factory/droids/` is a self-contained context file:

```
.factory/
├── droids/
│   ├── reviewer.md    ← security auditor
│   ├── cli.md         ← filesystem + shell
│   ├── browser.md     ← web automation
│   ├── gpu.md         ← GPU diagnostics
│   ├── planner.md     ← orchestrator
│   └── researcher.md  ← research + CVE lookup
└── registry.md        ← capability map + tool index
```

**Why this keeps token usage low:** each droid loads only its own slice. No agent reads another agent's context. The planner coordinates by naming the next droid and passing a one-line handoff, not by loading all context into one call.

---

## Agent Workspace

`agent-workspace/` mirrors the browser-harness pattern — droids write back here:

```
agent-workspace/
├── agent_helpers.py      ← shared helpers (report writing, skill I/O, shell utils)
└── domain-skills/        ← droid-learned skills, one folder per domain
```

When a droid discovers a reusable pattern (a stable selector, a private API, a useful command), it writes a skill file to `domain-skills/<domain>/`. The next run loads that skill instead of rediscovering.

---

## Full Project Structure

```
DroidTown/
├── CLAUDE.md                        ← Claude Code entry point
├── context.md                       ← live town bulletin board
├── .factory/
│   ├── droids/                      ← ICM context slices
│   └── registry.md                  ← droid capability map
├── agent-workspace/
│   ├── agent_helpers.py
│   └── domain-skills/
├── agents/
│   ├── shared/
│   │   ├── model_select.py          ← GPU-aware, cloud-aware model picker
│   │   ├── gpu_detect.py            ← NVIDIA/AMD/Intel detection + Ollama tuning
│   │   ├── runtime.py               ← unified Ollama/Claude runner
│   │   └── token_counter.py         ← session token tracking
│   ├── security/                    ← security audit agent
│   ├── cli/                         ← filesystem/shell agent
│   ├── gpu/                         ← GPU diagnostics agent
│   └── browser/                     ← browser automation agent
├── howTo/                           ← setup and usage guides
├── scan                             ← entrypoint: security scan
├── cli                              ← entrypoint: CLI agent
├── browser                          ← entrypoint: browser agent
└── gpu-optimize                     ← entrypoint: GPU tuning
```

---

## Guides

- [How DroidTown Works](howTo/how-droidtown-works.md)
- [Global `scan` setup](howTo/global-scan-setup.md)
- [CLI Agent usage](howTo/cli-agent-setup.md)
- [GPU Agent usage](howTo/gpu-agent-setup.md)
- [Global `cli` setup](howTo/global-cli-setup.md)

---

## Fork of [cbman0/DroidTown](https://github.com/cbman0/DroidTown) — `claude` branch
ICM upgrade by Juniorduc44: GPU optimization, full droid roster, agent-workspace, token counter, dual-runtime shim.
