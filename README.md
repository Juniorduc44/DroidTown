# DroidTown

A collection of AI-powered agents for security scanning, CLI file management, and GPU diagnostics.

## Documentation

Start here for a detailed architecture and capability guide:

- [How DroidTown Works](howTo/how-droidtown-works.md)

That document explains:

- End-to-end runtime flow (`scan` -> security agent -> report generation)
- What each agent can and cannot do today
- Local vs global command behavior and current limitations
- How the project is structured for future optional agent routing

## Quick Start

```bash
git clone git@github.com:cbman0/DroidTown.git
cd DroidTown
cd agents && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt && deactivate && cd ..
chmod +x scan
```

## Agents

All agents live in the `agents/` folder with a shared virtual environment.

| Agent | Description | Usage |
|-------|-------------|-------|
| **Security** | Scans code for vulnerabilities, secrets, and insecure patterns | `./scan <file_or_folder>` or `cd agents/security && python agent.py` |
| **CLI** | Filesystem and shell assistant — reads, writes, moves files via natural language | `./cli` (interactive) or `./cli "your task"` |
| **GPU** | GPU diagnostics, driver install guidance, and monitoring | `cd agents/gpu && python agent.py` |

## Guides

- [Global `scan` command setup](howTo/global-scan-setup.md)
- [CLI Agent usage](howTo/cli-agent-setup.md)
- [GPU Agent usage](howTo/gpu-agent-setup.md)
- [Global `cli` command setup](howTo/global-cli-setup.md)
- [How DroidTown Works (detailed)](howTo/how-droidtown-works.md)
