"""
GPU detection and Ollama tuning for DroidTown.

Detects NVIDIA / AMD / Intel GPUs, reads available VRAM, and configures
the environment for maximum Ollama GPU utilization before agents start.
"""

import os
import subprocess
import re
from dataclasses import dataclass, field
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


@dataclass
class GPUInfo:
    vendor: str                      # "nvidia" | "amd" | "intel" | "none"
    name: str = "Unknown"
    driver_version: str = "Unknown"
    vram_total_mb: int = 0
    vram_free_mb: int = 0
    temperature_c: Optional[int] = None
    cuda_available: bool = False
    rocm_available: bool = False
    indices: list[int] = field(default_factory=lambda: [0])

    @property
    def vram_total_gb(self) -> float:
        return round(self.vram_total_mb / 1024, 1)

    @property
    def vram_free_gb(self) -> float:
        return round(self.vram_free_mb / 1024, 1)

    @property
    def has_gpu(self) -> bool:
        return self.vendor != "none"


def _run(cmd: str) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=8)
        return r.returncode, r.stdout.strip()
    except Exception:
        return 1, ""


def _detect_nvidia() -> Optional[GPUInfo]:
    code, out = _run(
        "nvidia-smi --query-gpu=index,name,memory.total,memory.free,driver_version,temperature.gpu "
        "--format=csv,noheader,nounits"
    )
    if code != 0 or not out.strip():
        return None

    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        try:
            gpus.append({
                "index": int(parts[0]),
                "name": parts[1],
                "vram_total": int(parts[2]),
                "vram_free": int(parts[3]),
                "driver": parts[4],
                "temp": int(parts[5]) if parts[5].isdigit() else None,
            })
        except (ValueError, IndexError):
            continue

    if not gpus:
        return None

    # Aggregate across all GPUs (sum VRAM for multi-GPU)
    total = sum(g["vram_total"] for g in gpus)
    free = sum(g["vram_free"] for g in gpus)
    primary = gpus[0]

    return GPUInfo(
        vendor="nvidia",
        name=primary["name"] if len(gpus) == 1 else f"{len(gpus)}x {primary['name']}",
        driver_version=primary["driver"],
        vram_total_mb=total,
        vram_free_mb=free,
        temperature_c=primary["temp"],
        cuda_available=True,
        indices=[g["index"] for g in gpus],
    )


def _detect_amd() -> Optional[GPUInfo]:
    code, out = _run("rocm-smi --showmeminfo vram --csv 2>/dev/null")
    if code != 0 or not out.strip():
        # Fallback: check lspci
        _, lspci = _run("lspci | grep -i 'amd\\|radeon\\|advanced micro'")
        if not lspci:
            return None
        return GPUInfo(vendor="amd", name="AMD GPU (ROCm not detected)", rocm_available=False)

    # Parse rocm-smi CSV output
    total_mb, free_mb = 0, 0
    for line in out.splitlines():
        if "vram total" in line.lower():
            m = re.search(r"(\d+)", line)
            if m:
                total_mb = int(m.group(1))
        if "vram used" in line.lower():
            m = re.search(r"(\d+)", line)
            if m:
                used = int(m.group(1))
                free_mb = total_mb - used

    _, name_out = _run("rocm-smi --showproductname 2>/dev/null | head -2 | tail -1")
    name = name_out.strip() or "AMD GPU"

    return GPUInfo(
        vendor="amd",
        name=name,
        vram_total_mb=total_mb,
        vram_free_mb=free_mb,
        rocm_available=True,
    )


def _detect_intel() -> Optional[GPUInfo]:
    _, out = _run("lspci | grep -Ei 'intel.*graphics|intel.*display|intel.*vga'")
    if not out:
        return None
    name_line = out.splitlines()[0] if out else "Intel GPU"
    return GPUInfo(vendor="intel", name=name_line.split(":")[-1].strip())


def detect_gpu() -> GPUInfo:
    """Detect the best available GPU. Tries NVIDIA → AMD → Intel → CPU."""
    gpu = _detect_nvidia() or _detect_amd() or _detect_intel()
    return gpu or GPUInfo(vendor="none", name="No GPU detected (CPU mode)")


def recommended_model(gpu: GPUInfo) -> list[str]:
    """Return recommended local Ollama models based on available VRAM."""
    vram = gpu.vram_free_gb
    if vram >= 20:
        return ["qwen3:32b", "llama3.3:70b-q4_K_M", "deepseek-r1:32b"]
    if vram >= 14:
        return ["qwen3:14b", "llama3.1:13b", "mistral:12b"]
    if vram >= 7:
        return ["qwen3:8b", "llama3.2:8b", "phi4:8b", "gemma3:9b"]
    if vram >= 3.5:
        return ["phi3.5:mini", "llama3.2:3b", "qwen3:4b", "gemma3:4b"]
    return ["qwen3:1.7b", "llama3.2:1b"]


def configure_ollama_env(gpu: GPUInfo) -> dict[str, str]:
    """
    Set environment variables to maximize GPU utilization for Ollama.
    Returns the dict of vars set (also mutates os.environ).
    """
    env: dict[str, str] = {}

    if gpu.vendor == "nvidia" and gpu.cuda_available:
        env["CUDA_VISIBLE_DEVICES"] = ",".join(str(i) for i in gpu.indices)
        env["OLLAMA_NUM_GPU"] = "-1"               # all layers to GPU
        env["OLLAMA_FLASH_ATTENTION"] = "1"        # faster attention (Ampere+)
        env["OLLAMA_KV_CACHE_TYPE"] = "q8_0"       # compressed KV cache

    elif gpu.vendor == "amd" and gpu.rocm_available:
        env["OLLAMA_NUM_GPU"] = "-1"
        # HSA_OVERRIDE needed for some non-officially-supported AMD cards
        _, gfx = _run("rocminfo 2>/dev/null | grep 'gfx' | head -1")
        if gfx:
            gfx_ver = gfx.strip().split()[-1] if gfx.strip() else ""
            if gfx_ver:
                env["HSA_OVERRIDE_GFX_VERSION"] = gfx_ver

    elif gpu.vendor == "intel":
        env["OLLAMA_NUM_GPU"] = "1"

    # CPU-only: recommend threads = physical cores
    if gpu.vendor == "none":
        _, cores = _run("nproc --all")
        if cores.isdigit():
            env["OLLAMA_NUM_PARALLEL"] = str(max(1, int(cores) // 2))

    for k, v in env.items():
        os.environ[k] = v

    return env


def print_gpu_status(gpu: GPUInfo, env_set: dict[str, str]) -> None:
    """Print a rich GPU status panel."""
    table = Table(border_style="cyan", show_header=False, padding=(0, 1))
    table.add_column("Key", style="bold dim")
    table.add_column("Value", style="bold white")

    table.add_row("GPU", gpu.name)
    table.add_row("Vendor", gpu.vendor.upper())
    table.add_row("Driver", gpu.driver_version)

    if gpu.has_gpu and gpu.vram_total_mb:
        bar_len = 20
        used = gpu.vram_total_mb - gpu.vram_free_mb
        filled = int(bar_len * used / max(gpu.vram_total_mb, 1))
        bar = "█" * filled + "░" * (bar_len - filled)
        table.add_row(
            "VRAM",
            f"{gpu.vram_free_gb} GB free / {gpu.vram_total_gb} GB total  [{bar}]"
        )

    if gpu.temperature_c is not None:
        temp_color = "red" if gpu.temperature_c > 80 else "yellow" if gpu.temperature_c > 65 else "green"
        table.add_row("Temp", f"[{temp_color}]{gpu.temperature_c}°C[/{temp_color}]")

    if gpu.has_gpu:
        recs = recommended_model(gpu)
        table.add_row("Recommended", ", ".join(recs[:3]))

    if env_set:
        table.add_row("Ollama env", "  ".join(f"{k}={v}" for k, v in env_set.items()))
    else:
        table.add_row("Ollama env", "[dim]no GPU tuning applied[/dim]")

    title = "🖥️  GPU Ready" if gpu.has_gpu else "💻  CPU Mode"
    console.print(Panel(table, title=title, border_style="green" if gpu.has_gpu else "yellow"))


def setup(silent: bool = False) -> GPUInfo:
    """
    Full GPU setup: detect → configure → print status.
    Call this at agent startup. Returns GPUInfo for downstream use.
    """
    gpu = detect_gpu()
    env_set = configure_ollama_env(gpu)
    if not silent:
        print_gpu_status(gpu, env_set)
    return gpu


if __name__ == "__main__":
    setup()
