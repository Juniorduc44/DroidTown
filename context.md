# DroidTown — Town Context Board

Shared state visible to all droids and Claude Code. Updated by droids after completing tasks.

## Active tasks

_None in progress._

## Last droid activity

| Droid | Last task | Status | Output location |
|-------|-----------|--------|-----------------|
| reviewer | — | idle | — |
| cli | — | idle | — |
| browser | — | idle | — |
| gpu | — | idle | — |
| planner | — | idle | — |
| researcher | — | idle | — |

## Environment snapshot

| Property | Value |
|----------|-------|
| Runtime | _detect on startup_ |
| GPU | _detect on startup — see `agents/shared/gpu_detect.py`_ |
| Ollama | `http://localhost:11434` |
| Agent workspace | `agent-workspace/` |
| Reports out | cwd where command was invoked |

## Droid handoff log

_Droids append here when passing work to another droid._

---

## How to update this file

After completing a task, update the relevant row in **Last droid activity** and append to **Droid handoff log** if passing work on. Keep entries brief — one line each. This file is loaded into every session context so token weight matters.
