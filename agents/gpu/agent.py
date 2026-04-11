import sys
import os
import subprocess
import json
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "shared"))

from langchain_ollama import ChatOllama
from langchain.agents import create_agent
from langchain_core.tools import tool
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from model_select import select_model

console = Console()

# ============================================================
#  FLOW CHART — GPU Agent Decision Tree
# ============================================================
#
#  START
#    │
#    ▼
#  ┌─────────────────────┐
#  │  detect_gpus()       │  ← lspci scan for NVIDIA/AMD/Intel
#  └────────┬────────────┘
#           │
#      GPU found?
#      ┌────┴────┐
#      No        Yes
#      │         │
#      ▼         ▼
#   [STOP:    ┌──────────────────┐
#    No GPU]  │ check_driver()   │  ← kernel module + nvidia-smi
#             └────────┬─────────┘
#                      │
#               Driver loaded?
#               ┌──────┴──────┐
#               No            Yes
#               │             │
#               ▼             ▼
#  ┌────────────────────┐  ┌─────────────────────┐
#  │ diagnose_driver()  │  │ get_gpu_status()     │  ← nvidia-smi full stats
#  └────────┬───────────┘  └────────┬────────────┘
#           │                       │
#           ▼                       ▼
#  ┌─────────────────────┐  ┌─────────────────────┐
#  │ get_install_guide() │  │ check_cuda()         │  ← CUDA version + libs
#  └────────┬────────────┘  └────────┬────────────┘
#           │                       │
#           ▼                       ▼
#  ┌─────────────────────┐  ┌──────────────────────┐
#  │ verify_install()    │  │ check_ollama_gpu()    │  ← ollama ps GPU offload
#  └────────┬────────────┘  └────────┬─────────────┘
#           │                       │
#           ▼                       ▼
#  ┌─────────────────────┐  ┌──────────────────────┐
#  │ run_gpu_benchmark() │  │ run_gpu_benchmark()   │  ← stress test + VRAM
#  └────────┬────────────┘  └────────┬─────────────┘
#           │                       │
#           ▼                       ▼
#        [REPORT]              [REPORT]
#           │                       │
#           └───────────┬───────────┘
#                       ▼
#              ┌────────────────┐
#              │  full_report() │  ← aggregate all findings
#              └────────────────┘
#
# ============================================================


def _run(cmd: str, timeout: int = 15) -> str:
    """Run a shell command and return combined output."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        out = ""
        if r.stdout:
            out += r.stdout
        if r.stderr:
            out += r.stderr
        return out.strip() if out.strip() else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: command timed out"
    except Exception as e:
        return f"Error: {e}"


@tool
def detect_gpus() -> str:
    """Detect all GPUs on the system using lspci. Returns GPU model, vendor, and bus ID."""
    pci = _run("lspci -nn | grep -iE 'VGA|3D|Display'")
    if not pci or "Error" in pci:
        return "No GPUs detected via lspci."

    lines = pci.strip().split("\n")
    results = []
    for line in lines:
        results.append(f"  • {line.strip()}")

    usb_gpu = _run("lsusb 2>/dev/null | grep -iE 'nvidia|amd|radeon'")
    if usb_gpu and "Error" not in usb_gpu:
        results.append(f"\nUSB GPUs:\n  • {usb_gpu}")

    return f"Detected GPUs ({len(lines)}):\n" + "\n".join(results)


@tool
def check_driver() -> str:
    """Check if GPU drivers are loaded (kernel modules, nvidia-smi availability)."""
    sections = []

    nvidia_mod = _run("lsmod | grep -i nvidia")
    if nvidia_mod and "Error" not in nvidia_mod and nvidia_mod != "(no output)":
        sections.append(f"NVIDIA kernel modules loaded:\n{nvidia_mod}")
    else:
        sections.append("NVIDIA kernel modules: NOT LOADED")

    smi = _run("which nvidia-smi 2>/dev/null")
    if smi and "/" in smi:
        sections.append(f"nvidia-smi found at: {smi}")
        ver = _run("nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null")
        if ver and "Error" not in ver and "Failed" not in ver:
            sections.append(f"Driver version: {ver}")
        else:
            sections.append("nvidia-smi exists but cannot query GPU — driver may not be loaded.")
    else:
        sections.append("nvidia-smi: NOT INSTALLED")

    nouveau = _run("lsmod | grep nouveau")
    if nouveau and nouveau != "(no output)":
        sections.append(f"WARNING: Nouveau (open-source) driver is loaded — this blocks NVIDIA proprietary driver.\n{nouveau}")

    return "\n\n".join(sections)


@tool
def diagnose_driver() -> str:
    """Diagnose why the GPU driver isn't working. Checks common issues."""
    checks = []

    distro = _run("cat /etc/os-release | grep -E '^(PRETTY_NAME|ID|VERSION_ID)'")
    checks.append(f"Distribution:\n{distro}")

    kernel = _run("uname -r")
    checks.append(f"Kernel: {kernel}")

    headers = _run("dpkg -l 2>/dev/null | grep linux-headers | head -3")
    if headers and headers != "(no output)":
        checks.append(f"Kernel headers installed:\n{headers}")
    else:
        rpm_headers = _run("rpm -qa 2>/dev/null | grep kernel-devel | head -3")
        if rpm_headers and rpm_headers != "(no output)":
            checks.append(f"Kernel headers installed:\n{rpm_headers}")
        else:
            checks.append("WARNING: Kernel headers may not be installed. Required for driver compilation.")

    secure_boot = _run("mokutil --sb-state 2>/dev/null")
    if "enabled" in secure_boot.lower():
        checks.append("WARNING: Secure Boot is ENABLED — this can block NVIDIA driver loading. You may need to disable it in BIOS or sign the kernel module.")
    else:
        checks.append(f"Secure Boot: {secure_boot}")

    blacklist = _run("grep -r nouveau /etc/modprobe.d/ 2>/dev/null")
    if blacklist and blacklist != "(no output)":
        checks.append(f"Nouveau blacklist config found:\n{blacklist}")
    else:
        checks.append("Nouveau is NOT blacklisted — it may conflict with the NVIDIA driver.")

    dkms = _run("dkms status 2>/dev/null | grep -i nvidia")
    if dkms and dkms != "(no output)":
        checks.append(f"DKMS NVIDIA status:\n{dkms}")
    else:
        checks.append("No NVIDIA DKMS modules found.")

    existing_pkgs = _run("dpkg -l 2>/dev/null | grep -iE 'nvidia-(driver|kernel|utils)' | head -10")
    if not existing_pkgs or existing_pkgs == "(no output)":
        existing_pkgs = _run("rpm -qa 2>/dev/null | grep -i nvidia | head -10")
    if existing_pkgs and existing_pkgs != "(no output)":
        checks.append(f"Installed NVIDIA packages:\n{existing_pkgs}")
    else:
        checks.append("No NVIDIA driver packages found installed.")

    return "\n\n".join(checks)


@tool
def get_install_guide() -> str:
    """Generate step-by-step GPU driver installation instructions for the detected OS."""
    distro_id = _run("grep '^ID=' /etc/os-release | cut -d= -f2 | tr -d '\"'").strip()
    distro_like = _run("grep '^ID_LIKE=' /etc/os-release | cut -d= -f2 | tr -d '\"'").strip()
    gpu_info = _run("lspci -nn | grep -iE 'VGA|3D' | grep -i nvidia")

    if "nvidia" not in gpu_info.lower():
        return "No NVIDIA GPU detected. This guide currently supports NVIDIA GPUs only."

    base = distro_like if distro_like else distro_id

    if "debian" in base or distro_id in ("debian", "ubuntu", "parrot", "kali", "mint", "pop"):
        return f"""NVIDIA Driver Installation — Debian/Ubuntu-based ({distro_id})

GPU: {gpu_info.strip()}

Step 1: Update system
  sudo apt update && sudo apt upgrade -y

Step 2: Install kernel headers (required for driver compilation)
  sudo apt install -y linux-headers-$(uname -r) build-essential dkms

Step 3: Blacklist nouveau driver
  echo -e "blacklist nouveau\\noptions nouveau modeset=0" | sudo tee /etc/modprobe.d/blacklist-nouveau.conf
  sudo update-initramfs -u

Step 4: Install NVIDIA driver
  Option A — Repository (recommended):
    sudo apt install -y nvidia-driver

  Option B — Auto-detect best driver (Ubuntu/Pop):
    sudo ubuntu-drivers install

  Option C — Specific version:
    apt search nvidia-driver
    sudo apt install -y nvidia-driver-560

Step 5: Reboot
  sudo reboot

Step 6: Verify after reboot
  nvidia-smi
  lsmod | grep nvidia

Step 7 (optional): Install CUDA toolkit
  sudo apt install -y nvidia-cuda-toolkit
  nvcc --version

TROUBLESHOOTING:
  - If nvidia-smi fails after reboot, check Secure Boot: mokutil --sb-state
  - If Secure Boot is enabled, disable it in BIOS or use: sudo mokutil --disable-validation
  - Check dkms status: dkms status | grep nvidia
  - Check logs: journalctl -b | grep -i nvidia | tail -20"""

    elif "rhel" in base or "fedora" in base or distro_id in ("fedora", "centos", "rocky", "alma"):
        return f"""NVIDIA Driver Installation — RHEL/Fedora-based ({distro_id})

GPU: {gpu_info.strip()}

Step 1: Update system
  sudo dnf update -y

Step 2: Install kernel headers
  sudo dnf install -y kernel-devel kernel-headers gcc make dkms

Step 3: Enable RPM Fusion (Fedora)
  sudo dnf install -y https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm
  sudo dnf install -y https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm

Step 4: Install NVIDIA driver
  sudo dnf install -y akmod-nvidia xorg-x11-drv-nvidia-cuda

Step 5: Reboot
  sudo reboot

Step 6: Verify
  nvidia-smi"""

    elif "arch" in base or distro_id == "arch" or distro_id == "manjaro":
        return f"""NVIDIA Driver Installation — Arch-based ({distro_id})

GPU: {gpu_info.strip()}

Step 1: Install NVIDIA driver
  sudo pacman -S nvidia nvidia-utils nvidia-settings

Step 2: Reboot
  sudo reboot

Step 3: Verify
  nvidia-smi"""

    else:
        return f"""NVIDIA Driver Installation — Generic ({distro_id})

GPU: {gpu_info.strip()}

Your distribution ({distro_id}) doesn't match a known package manager pattern.

Option 1: Check if your distro has an nvidia-driver package
  Search your package manager for 'nvidia-driver' or 'nvidia'

Option 2: Install from NVIDIA directly
  1. Go to https://www.nvidia.com/Download/index.aspx
  2. Select your GPU and OS
  3. Download the .run installer
  4. Stop display manager: sudo systemctl stop gdm (or sddm/lightdm)
  5. Run: sudo bash NVIDIA-Linux-x86_64-*.run
  6. Reboot

After install, verify with: nvidia-smi"""


@tool
def get_gpu_status() -> str:
    """Get detailed GPU status: utilization, VRAM, temperature, power, processes."""
    smi_check = _run("which nvidia-smi 2>/dev/null")
    if "/" not in str(smi_check):
        return "nvidia-smi not available. Install NVIDIA drivers first."

    full = _run("nvidia-smi")
    if "Failed" in full or "NVIDIA-SMI has failed" in full:
        return f"nvidia-smi exists but failed to communicate with the driver:\n{full}"

    query = _run(
        "nvidia-smi --query-gpu=index,name,driver_version,temperature.gpu,"
        "utilization.gpu,utilization.memory,memory.total,memory.used,memory.free,"
        "power.draw,power.limit,fan.speed,pstate "
        "--format=csv,noheader,nounits 2>/dev/null"
    )

    procs = _run("nvidia-smi --query-compute-apps=pid,name,used_memory --format=csv,noheader 2>/dev/null")

    result = f"nvidia-smi output:\n{full}\n\nParsed metrics:\n{query}"
    if procs and procs != "(no output)":
        result += f"\n\nGPU Processes:\n{procs}"
    else:
        result += "\n\nNo compute processes running on GPU."

    return result


@tool
def check_cuda() -> str:
    """Check CUDA installation: version, libraries, nvcc compiler."""
    sections = []

    nvcc = _run("nvcc --version 2>/dev/null")
    if nvcc and "release" in nvcc.lower():
        sections.append(f"CUDA Compiler (nvcc):\n{nvcc}")
    else:
        sections.append("nvcc not found — CUDA toolkit may not be installed.")

    cuda_ver = _run("cat /usr/local/cuda/version.txt 2>/dev/null || cat /usr/local/cuda/version.json 2>/dev/null")
    if cuda_ver and cuda_ver != "(no output)":
        sections.append(f"CUDA version file:\n{cuda_ver}")

    libcuda = _run("ldconfig -p 2>/dev/null | grep -i libcuda | head -5")
    if libcuda and libcuda != "(no output)":
        sections.append(f"CUDA libraries:\n{libcuda}")
    else:
        sections.append("No CUDA libraries found in ldconfig.")

    cudnn = _run("ldconfig -p 2>/dev/null | grep -i cudnn | head -3")
    if cudnn and cudnn != "(no output)":
        sections.append(f"cuDNN libraries:\n{cudnn}")

    return "\n\n".join(sections)


@tool
def check_ollama_gpu() -> str:
    """Check if Ollama is using the GPU for inference."""
    ps = _run("ollama ps 2>/dev/null")
    if not ps or "Error" in ps or ps == "(no output)":
        return "Ollama is not running or not installed."

    result = f"Ollama running models:\n{ps}\n\n"

    if "GPU" in ps.upper():
        result += "Ollama IS using GPU for inference."
    elif "CPU" in ps.upper():
        result += "WARNING: Ollama is running on CPU only. GPU is not being utilized.\n"
        result += "This usually means:\n"
        result += "  1. NVIDIA driver is not installed/loaded\n"
        result += "  2. Ollama was installed before the driver — restart ollama after driver install\n"
        result += "  3. Insufficient VRAM for the model\n"
        result += "\nTry: systemctl restart ollama (or kill and restart ollama serve)"
    else:
        result += "Could not determine GPU/CPU status from ollama ps output."

    return result


@tool
def verify_install() -> str:
    """Run post-installation verification checks to confirm GPU is working."""
    checks = []

    mod = _run("lsmod | grep nvidia | head -5")
    checks.append(f"[1/6] Kernel modules:\n{mod if mod and mod != '(no output)' else 'FAIL — no nvidia modules loaded'}")

    smi = _run("nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>/dev/null")
    checks.append(f"[2/6] nvidia-smi:\n{smi if smi and 'Error' not in smi and 'Failed' not in smi else 'FAIL — nvidia-smi not working'}")

    dev = _run("ls -la /dev/nvidia* 2>/dev/null")
    checks.append(f"[3/6] Device nodes:\n{dev if dev and dev != '(no output)' else 'FAIL — no /dev/nvidia* devices'}")

    gl = _run("glxinfo 2>/dev/null | grep 'OpenGL renderer' | head -1")
    checks.append(f"[4/6] OpenGL:\n{gl if gl and gl != '(no output)' else 'SKIP — glxinfo not available'}")

    ollama = _run("ollama ps 2>/dev/null")
    if ollama and "GPU" in ollama.upper():
        checks.append(f"[5/6] Ollama GPU:\nPASS — models running on GPU")
    elif ollama and "CPU" in ollama.upper():
        checks.append(f"[5/6] Ollama GPU:\nWARN — models still on CPU. Restart ollama.")
    else:
        checks.append(f"[5/6] Ollama GPU:\nSKIP — no models running")

    nouveau = _run("lsmod | grep nouveau")
    if nouveau and nouveau != "(no output)":
        checks.append(f"[6/6] Nouveau conflict:\nFAIL — nouveau is loaded, will block nvidia driver")
    else:
        checks.append(f"[6/6] Nouveau conflict:\nPASS — nouveau not loaded")

    return "\n\n".join(checks)


@tool
def run_gpu_benchmark() -> str:
    """Run a quick GPU benchmark to test functionality and measure performance."""
    sections = []

    smi = _run("nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader 2>/dev/null")
    if not smi or "Error" in smi or "Failed" in smi:
        sections.append("Cannot benchmark — nvidia-smi not working. Install drivers first.")
        return "\n\n".join(sections)

    sections.append(f"GPU: {smi}")

    bandwidthTest = _run("which bandwidthTest 2>/dev/null || which cuda-bandwidthTest 2>/dev/null")
    if "/" in str(bandwidthTest):
        bw = _run(f"{bandwidthTest.strip()} --device=0 2>/dev/null", timeout=30)
        sections.append(f"Bandwidth test:\n{bw}")

    sections.append("Running Ollama inference benchmark...")
    ollama_bench = _run(
        "time ollama run glm-5.1:cloud 'Say exactly: GPU benchmark complete' --verbose 2>&1",
        timeout=30
    )
    sections.append(f"Ollama test:\n{ollama_bench}")

    stress = _run("nvidia-smi --query-gpu=utilization.gpu,temperature.gpu,power.draw --format=csv,noheader 2>/dev/null")
    sections.append(f"Post-test GPU state:\n{stress}")

    return "\n\n".join(sections)


@tool
def full_report() -> str:
    """Generate a complete GPU health report covering all checks."""
    sections = []
    sections.append("=" * 60)
    sections.append("  DROIDTOWN GPU HEALTH REPORT")
    sections.append("=" * 60)

    sections.append("\n[1] GPU DETECTION")
    sections.append(detect_gpus.invoke(""))

    sections.append("\n[2] DRIVER STATUS")
    sections.append(check_driver.invoke(""))

    smi_works = "NOT INSTALLED" not in sections[-1] and "NOT LOADED" not in sections[-1]

    if smi_works:
        sections.append("\n[3] GPU STATUS")
        sections.append(get_gpu_status.invoke(""))

        sections.append("\n[4] CUDA")
        sections.append(check_cuda.invoke(""))

        sections.append("\n[5] OLLAMA GPU")
        sections.append(check_ollama_gpu.invoke(""))
    else:
        sections.append("\n[3] DRIVER DIAGNOSIS")
        sections.append(diagnose_driver.invoke(""))

        sections.append("\n[4] INSTALLATION GUIDE")
        sections.append(get_install_guide.invoke(""))

    sections.append("\n[VERIFICATION]")
    sections.append(verify_install.invoke(""))

    return "\n".join(sections)


@tool
def run_shell(command: str) -> str:
    """Run a shell command for manual troubleshooting. Use for specific checks not covered by other tools."""
    return _run(command, timeout=30)


SYSTEM_PROMPT = """You are a GPU diagnostics and setup assistant. Your job is to help users detect, install, configure, and monitor GPU hardware — especially NVIDIA GPUs for AI/ML workloads with Ollama.

WORKFLOW — Follow this order:
1. Start with detect_gpus() to find what hardware exists
2. Use check_driver() to see if drivers are loaded
3. If drivers are missing:
   - Run diagnose_driver() to find the root cause
   - Run get_install_guide() for step-by-step install instructions
   - After user installs, run verify_install() to confirm it worked
4. If drivers are working:
   - Run get_gpu_status() for current utilization/temps/VRAM
   - Run check_cuda() for CUDA toolkit status
   - Run check_ollama_gpu() to verify Ollama is using GPU
5. Use run_gpu_benchmark() to stress-test after setup
6. Use full_report() to generate a complete health check

RULES:
- Always start by detecting the GPU before suggesting anything
- Give clear, numbered steps the user can follow
- Warn about destructive operations (blacklisting, driver removal)
- If Secure Boot is on, always mention it as a potential blocker
- After install steps, always remind user to reboot and run verify_install()
- Be specific to the user's distro — don't give Ubuntu commands on Fedora"""


TOOLS = [
    detect_gpus,
    check_driver,
    diagnose_driver,
    get_install_guide,
    get_gpu_status,
    check_cuda,
    check_ollama_gpu,
    verify_install,
    run_gpu_benchmark,
    full_report,
    run_shell,
]


def build_agent(model_name: str):
    """Create the agent with the selected model."""
    llm = ChatOllama(model=model_name, temperature=0.0)
    return create_agent(
        model=llm,
        tools=TOOLS,
        system_prompt=SYSTEM_PROMPT
    )


def run_task(agent, task: str):
    """Run a single task through the agent with error handling."""
    console.print(Panel(f"[bold]{task}[/bold]", title="📋 Task", border_style="cyan"))
    try:
        result = agent.invoke({
            "messages": [{"role": "user", "content": task}]
        })
        output = result["messages"][-1].content if isinstance(result, dict) and "messages" in result else str(result)
        console.print(Panel(Markdown(output), title="✅ Result", border_style="green", padding=(1, 2)))
    except Exception as e:
        err = str(e)
        if "unauthorized" in err.lower() or "401" in err:
            console.print(Panel(
                "[bold red]Authentication expired or invalid.[/bold red]\n\n"
                "Run: [bold cyan]ollama signin[/bold cyan]",
                title="❌ Unauthorized", border_style="red"
            ))
        else:
            console.print(Panel(f"[bold red]{err}[/bold red]", title="❌ Error", border_style="red"))


if __name__ == "__main__":
    model_name = select_model()
    agent = build_agent(model_name)

    if len(sys.argv) > 1:
        run_task(agent, " ".join(sys.argv[1:]))
    else:
        console.print(Panel(
            "[bold cyan]DroidTown GPU Agent[/bold cyan]\n"
            "GPU diagnostics, driver setup, and monitoring assistant.\n"
            "Type a task and press Enter. Type 'exit' to quit.\n\n"
            "[dim]Try: 'run a full gpu health check' or 'help me install nvidia drivers'[/dim]",
            border_style="blue"
        ))
        while True:
            try:
                task = console.input("[bold yellow]> [/bold yellow]")
            except (EOFError, KeyboardInterrupt):
                break
            if task.strip().lower() in ("exit", "quit", "q"):
                console.print("[dim]Goodbye.[/dim]")
                break
            if not task.strip():
                continue
            run_task(agent, task)
