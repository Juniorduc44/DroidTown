# How DroidTown Works

This document explains DroidTown's architecture, runtime flow, and what each agent can do today.

## Table of Contents

- [Project Goals](#project-goals)
- [High-Level Architecture](#high-level-architecture)
- [Repository Structure](#repository-structure)
- [Runtime Flow](#runtime-flow)
- [Agent Capabilities](#agent-capabilities)
- [Model Selection and Execution](#model-selection-and-execution)
- [Outputs and Reports](#outputs-and-reports)
- [Global vs Local Usage](#global-vs-local-usage)
- [Current Limitations](#current-limitations)
- [Planned Direction](#planned-direction)

## Project Goals

DroidTown is designed as a local-first, agent-driven toolkit for developer workflows.

Current focus areas:

- Security scanning of source code.
- Local filesystem and shell assistance.
- GPU diagnostics and setup support.

The project is organized so each agent can evolve independently while sharing common model selection logic.

## High-Level Architecture

DroidTown consists of:

1. A root command entrypoint (`scan`) for security workflows.
2. A shared Python virtual environment under `agents/venv`.
3. Agent implementations in separate folders:
   - `agents/security`
   - `agents/cli`
   - `agents/gpu`
4. Shared runtime utilities in `agents/shared`.

At the moment, only the security workflow is exposed as a top-level command.

## Repository Structure

```text
DroidTown/
├── scan                         # Bash command entrypoint for security scanning
├── agents/
│   ├── requirements.txt         # Shared Python dependencies
│   ├── shared/
│   │   └── model_select.py      # Local/cloud model discovery and selection
│   ├── security/
│   │   ├── agent.py             # Single-file security review agent
│   │   ├── scan.py              # Folder scan orchestrator
│   │   └── reporter.py          # Report generation and formatting
│   ├── cli/
│   │   └── agent.py             # CLI/filesystem assistant agent
│   └── gpu/
│       └── agent.py             # GPU diagnostics and install guidance agent
└── howTo/
    ├── global-scan-setup.md
    ├── cli-agent-setup.md
    ├── gpu-agent-setup.md
    └── how-droidtown-works.md   # This document
```

## Runtime Flow

### 1) User invokes `scan`

Example:

```bash
./scan src/
```

The `scan` script:

- Resolves symlinks so it can run correctly when installed globally.
- Locates `agents/venv/bin/python`.
- Validates the target path.
- Exports scan metadata:
  - `SCAN_OUTPUT_DIR`
  - `SCAN_TARGET_NAME`
- Routes execution:
  - file target -> `agents/security/agent.py`
  - directory target -> `agents/security/scan.py`

### 2) Security agent model is selected

`agents/security/agent.py` calls `select_model()` from `agents/shared/model_select.py`.

The selector:

- Queries local Ollama models (`/api/tags`).
- Reads model capabilities (`/api/show`).
- Ensures tool-calling support for compatible agent execution.
- Lets the user choose a model interactively.

### 3) Code is analyzed

Depending on mode:

- **Single file:** the security agent reviews one file.
- **Folder scan:** `scan.py` walks files and invokes the security agent repeatedly, aggregating findings.

### 4) Professional report is generated

`agents/security/reporter.py` formats findings into a markdown report in the output directory.

## Agent Capabilities

## 1) Security Agent (`agents/security`)

Primary purpose: strict code security auditing.

Current capabilities:

- Reads file content via tool-enabled agent flow.
- Searches for:
  - hardcoded secrets and credentials
  - unsafe execution patterns (`eval`, `exec`, risky shell usage)
  - injection risks
  - weak/insecure security practices
- Returns findings with severity labels.
- Produces markdown reports for single-file and multi-file scans.

How to use:

- Single file/folder via root command: `./scan <file_or_folder>`
- Direct file-mode run: `cd agents/security && python agent.py <file>`

## 2) CLI Agent (`agents/cli`)

Primary purpose: natural-language local shell/filesystem assistance.

Current capabilities:

- File and directory inspection.
- File editing/creation operations.
- Shell command assistance for local tasks.

How to use:

- `cd agents/cli && python agent.py`

For setup details, see `howTo/cli-agent-setup.md`.

## 3) GPU Agent (`agents/gpu`)

Primary purpose: GPU environment diagnostics and install guidance.

Current capabilities:

- Detecting GPU context and tooling state.
- Guiding driver/toolkit checks.
- Assisting with GPU readiness and troubleshooting flows.

How to use:

- `cd agents/gpu && python agent.py`

For setup details, see `howTo/gpu-agent-setup.md`.

## Model Selection and Execution

All agents share model discovery through `agents/shared/model_select.py`.

Behavior highlights:

- Works with local and cloud Ollama models.
- Displays model size/type/capabilities.
- Enforces tool-calling compatibility when required.
- Performs cloud auth checks where needed.

This gives a consistent user experience across agent types.

## Outputs and Reports

Security scans write markdown reports to:

- Current working directory where `scan` was invoked (`SCAN_OUTPUT_DIR`).

Report naming uses a target-based convention, and folder scans aggregate findings from multiple files.

## Global vs Local Usage

Current state:

- **Local-first by default:** run `./scan` inside a clone.
- **Optional global command:** create a symlink to `scan` in your `PATH` (documented in `howTo/global-scan-setup.md`).

Important clarification:

- Global installation currently exposes the same security scan workflow.
- There is not yet a generalized global agent registry or per-agent global command router.

## Current Limitations

- Top-level command surface is currently security-only (`scan`).
- Agent routing is hardcoded in the `scan` script.
- No centralized user config file for selecting agent routing behavior yet.
- Test suite is minimal and should be expanded as additional agents are exposed.

## Planned Direction

As DroidTown evolves, the intended direction is:

- Keep agent capabilities modular.
- Support optional routing for local/global behavior.
- Allow forks to opt in to only the agents/commands they want.
- Add explicit config-driven command-to-agent mapping instead of hardcoded routing.

This approach enables a clean path for extending the platform one agent at a time without forcing one default operating model on all forks.
