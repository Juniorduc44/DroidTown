# GPU Agent — Setup & Usage Guide

The GPU Agent is an AI-powered assistant that detects, diagnoses, installs, and monitors GPU hardware. It specializes in NVIDIA GPUs for AI/ML workloads with Ollama.

## What It Does

```
  START
    │
    ▼
  Detect GPUs (lspci scan)
    │
    ├─ No GPU found → STOP
    │
    ▼
  Check Driver (kernel modules, nvidia-smi)
    │
    ├─ Driver NOT loaded          ├─ Driver loaded
    │   │                         │   │
    │   ▼                         │   ▼
    │  Diagnose issues            │  GPU status (VRAM, temp, power)
    │   │                         │   │
    │   ▼                         │   ▼
    │  Install guide (per distro) │  CUDA check
    │   │                         │   │
    │   ▼                         │   ▼
    │  Verify install             │  Ollama GPU offload check
    │   │                         │   │
    │   ▼                         │   ▼
    │  Benchmark                  │  Benchmark
    │                             │
    └──────────┬──────────────────┘
               ▼
          Full Report
```

## Available Tools

| Tool | What It Does |
|------|-------------|
| `detect_gpus` | Scans PCI bus for NVIDIA/AMD/Intel GPUs |
| `check_driver` | Checks kernel modules and nvidia-smi |
| `diagnose_driver` | Finds why drivers aren't working (headers, Secure Boot, nouveau, DKMS) |
| `get_install_guide` | Generates distro-specific driver installation steps |
| `get_gpu_status` | Full nvidia-smi stats: VRAM, temp, power, utilization, processes |
| `check_cuda` | Checks CUDA toolkit, nvcc, and library installation |
| `check_ollama_gpu` | Verifies Ollama is using GPU (not CPU) for inference |
| `verify_install` | Post-install verification checklist (6 checks) |
| `run_gpu_benchmark` | Stress test and performance check |
| `full_report` | Runs all checks and generates a complete health report |
| `run_shell` | Run any shell command for manual troubleshooting |

## Setup

### Step 1: Clone the Repository (skip if already cloned)

```bash
git clone git@github.com:cbman0/DroidTown.git
cd DroidTown
```

### Step 2: Set Up the Virtual Environment

```bash
cd agents
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
cd ..
```

## Usage

### Interactive Mode

```bash
cd agents/gpu
source ../venv/bin/activate
python agent.py
```

### Example Prompts

```
> run a full gpu health check
> do I have a GPU and is it working?
> help me install nvidia drivers
> check if ollama is using my GPU
> what is my GPU temperature and VRAM usage?
> verify my driver installation
> run a benchmark on my GPU
```

### Single Command Mode

```bash
python agent.py "run a full gpu health check"
```

Or from the repo root:

```bash
cd agents/gpu && source ../venv/bin/activate && python agent.py "run a full gpu health check"
```

## Common Scenarios

### Scenario 1: Fresh install, no drivers

The agent will:
1. Detect your GPU model
2. Identify that drivers are missing
3. Check for blockers (Secure Boot, nouveau, missing kernel headers)
4. Generate step-by-step install instructions for your distro
5. After you install and reboot, verify everything works

### Scenario 2: Drivers installed, Ollama on CPU

The agent will:
1. Confirm GPU and driver are working
2. Show that Ollama is running on CPU
3. Recommend restarting Ollama to pick up the GPU
4. Verify GPU offload is working after restart

### Scenario 3: Routine monitoring

The agent will:
1. Show GPU utilization, temperature, VRAM, power draw
2. List processes using the GPU
3. Check CUDA version
4. Run a benchmark if requested

## Troubleshooting

### Agent can't detect GPU
Make sure `lspci` is available: `sudo apt install pciutils`

### nvidia-smi not found after driver install
Reboot first. If still missing, check: `dkms status | grep nvidia`

### Ollama still on CPU after driver install
Restart Ollama: `systemctl restart ollama` or kill and relaunch `ollama serve`
