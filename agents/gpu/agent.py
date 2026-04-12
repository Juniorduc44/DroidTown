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
#  ┌──────────────────────┐  ┌─────────────────────┐
#  │ diagnose_driver()    │  │ get_gpu_status()     │
#  │ (DKMS logs, kernel   │  └────────┬────────────┘
#  │  compat, Secure Boot,│          │
#  │  nouveau, packages)  │          ▼
#  └────────┬─────────────┘  ┌─────────────────────┐
#           │                │ check_cuda()         │
#     Mismatch found?       └────────┬────────────┘
#     ┌─────┴──────┐                │
#     Yes          No               ▼
#     │            │         ┌──────────────────────┐
#     ▼            ▼         │ check_ollama_gpu()   │
#  ┌──────────────────┐     └────────┬─────────────┘
#  │check_dkms_build  │             │
#  │  _log()          │             ▼
#  │check_available   │     ┌──────────────────────┐
#  │  _kernels()      │     │ run_gpu_benchmark()  │
#  └────────┬─────────┘     └──────────────────────┘
#           │
#           ▼
#  ┌──────────────────────┐
#  │ get_install_guide()  │  ← auto-detects scenario:
#  │                      │     • kernel/driver mismatch
#  │  Option A: boot      │       → .run installer + fallback kernel
#  │    older kernel      │     • DKMS failed (other)
#  │  Option B: install   │       → fix headers + rebuild
#  │    newer .run driver │     • fresh install
#  └────────┬─────────────┘       → repo driver + fallback to .run
#           │
#           ▼
#  ┌─────────────────────┐
#  │ verify_install()    │  ← 6-point post-install check
#  └─────────────────────┘
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
    """Diagnose why the GPU driver isn't working. Checks kernel/driver compat, DKMS, Secure Boot, nouveau, and more."""
    checks = []

    distro = _run("cat /etc/os-release | grep -E '^(PRETTY_NAME|ID|VERSION_ID)'")
    checks.append(f"Distribution:\n{distro}")

    kernel = _run("uname -r").strip()
    checks.append(f"Running kernel: {kernel}")

    # Check all available kernels for fallback
    available_kernels = _run("ls /boot/vmlinuz-* 2>/dev/null")
    if available_kernels and available_kernels != "(no output)":
        checks.append(f"Available kernels on this system:\n{available_kernels}")

    headers = _run(f"dpkg -l 2>/dev/null | grep 'linux-headers-{kernel}' | head -3")
    if headers and headers != "(no output)":
        checks.append(f"Kernel headers for running kernel: INSTALLED\n{headers}")
    else:
        rpm_headers = _run(f"rpm -qa 2>/dev/null | grep kernel-devel | head -3")
        if rpm_headers and rpm_headers != "(no output)":
            checks.append(f"Kernel headers: {rpm_headers}")
        else:
            checks.append(f"PROBLEM: Kernel headers for {kernel} are NOT installed. Required for driver compilation.\n  Fix: sudo apt install -y linux-headers-{kernel}")

    secure_boot = _run("mokutil --sb-state 2>/dev/null")
    if "enabled" in secure_boot.lower():
        checks.append("WARNING: Secure Boot is ENABLED — this can block NVIDIA driver loading. Disable in BIOS or run: sudo mokutil --disable-validation")
    elif "not found" in secure_boot.lower() or "command not found" in secure_boot.lower():
        checks.append("Secure Boot: Cannot check (mokutil not installed). Install with: sudo apt install mokutil")
    else:
        checks.append(f"Secure Boot: {secure_boot}")

    blacklist = _run("grep -r nouveau /etc/modprobe.d/ 2>/dev/null")
    if blacklist and blacklist != "(no output)":
        checks.append(f"Nouveau blacklist config found:\n{blacklist}")
    else:
        checks.append("WARNING: Nouveau is NOT blacklisted — it will conflict with the NVIDIA driver.")

    nouveau_loaded = _run("lsmod | grep nouveau")
    if nouveau_loaded and nouveau_loaded != "(no output)":
        checks.append(f"PROBLEM: Nouveau kernel module is actively loaded. It must be blacklisted and system rebooted before NVIDIA driver can work.\n{nouveau_loaded}")

    # DKMS status — critical for detecting build failures
    dkms = _run("dkms status 2>/dev/null | grep -i nvidia")
    if dkms and dkms != "(no output)":
        checks.append(f"DKMS NVIDIA status:\n{dkms}")
        # Check if DKMS built for the RUNNING kernel
        if kernel in dkms and "installed" in dkms.lower():
            checks.append(f"DKMS module IS built for running kernel {kernel}.")
        elif kernel not in dkms:
            # Find which kernels it IS built for
            built_kernels = [line.strip() for line in dkms.split("\n") if "installed" in line.lower()]
            checks.append(f"PROBLEM: DKMS NVIDIA module is NOT built for running kernel {kernel}.")
            if built_kernels:
                checks.append(f"  It IS built for: {', '.join(built_kernels)}")
                checks.append(f"  QUICK FIX: Boot into one of those kernels via GRUB > Advanced options.")
            checks.append(f"  PROPER FIX: The installed driver version may be too old for kernel {kernel}. Check the build log below.")
    else:
        checks.append("No NVIDIA DKMS modules found — driver may not be installed yet.")

    # Check DKMS build log for compilation errors
    nvidia_ver = _run("dpkg -l 2>/dev/null | grep nvidia-kernel-dkms | awk '{print $3}' | head -1").strip()
    if nvidia_ver:
        dkms_module = _run(f"ls -d /var/lib/dkms/nvidia-current/ /var/lib/dkms/nvidia/ 2>/dev/null | head -1").strip()
        if dkms_module:
            build_log = _run(f"cat {dkms_module}{nvidia_ver}/build/make.log 2>/dev/null | tail -40")
            if build_log and build_log != "(no output)" and "Error" in build_log:
                checks.append(f"DKMS BUILD LOG (last 40 lines) — shows why compilation failed:\n{build_log}")
                # Detect specific known incompatibilities
                if "__vm_flags" in build_log or "in_irq" in build_log or "implicit declaration" in build_log:
                    checks.append(
                        f"DIAGNOSIS: Driver version {nvidia_ver} is TOO OLD for kernel {kernel}. "
                        f"The kernel API has changed and this driver cannot compile against it.\n"
                        f"  SOLUTION: Install a newer driver version. The repository driver ({nvidia_ver}) is incompatible.\n"
                        f"  Use get_install_guide() which will detect this and recommend the correct approach."
                    )

    # Check for broken dpkg state — apt stuck in retry loop
    broken_pkgs = _run("dpkg -l 2>/dev/null | grep -iE 'nvidia' | grep -E '^(iF|iU|iHR|rc)' | head -10")
    dpkg_audit = _run("dpkg --audit 2>/dev/null | head -10")
    apt_broken = _run("apt-get check 2>&1 | head -5")

    has_broken_state = False
    if broken_pkgs and broken_pkgs != "(no output)":
        has_broken_state = True
        checks.append(f"PROBLEM: NVIDIA packages are in a BROKEN dpkg state:\n{broken_pkgs}")
    if dpkg_audit and dpkg_audit != "(no output)" and "nvidia" in dpkg_audit.lower():
        has_broken_state = True
        checks.append(f"dpkg --audit:\n{dpkg_audit}")
    if apt_broken and "not fully installed" in apt_broken.lower():
        has_broken_state = True
        checks.append(f"apt reports broken packages:\n{apt_broken}")

    if has_broken_state:
        checks.append(
            "CRITICAL: The system is in a broken package state. Every time apt runs, it will retry the "
            "failed DKMS build, which DESTROYS the working module for the older kernel before failing again.\n"
            "  YOU MUST FIX THIS FIRST before any other steps.\n"
            "\n"
            "  IMPORTANT: The order matters. nvidia-driver depends on nvidia-kernel-dkms, so you must\n"
            "  remove nvidia-driver FIRST, then nvidia-kernel-dkms. Use --force-depends to break the chain.\n"
            "  Do NOT run 'apt --fix-broken install' while nvidia-kernel-dkms is still installed — it will\n"
            "  re-trigger the failed DKMS build and destroy working modules again.\n"
            "\n"
            "  Step 1 — Remove nvidia-driver (has dependency on nvidia-kernel-dkms):\n"
            "    sudo dpkg --force-remove-reinstreq --remove nvidia-driver\n"
            "\n"
            "  Step 2 — Remove nvidia-kernel-dkms (the broken package causing the loop):\n"
            "    sudo dpkg --force-remove-reinstreq --force-depends --remove nvidia-kernel-dkms\n"
            "\n"
            "  Step 3 — NOW it is safe to fix apt (no DKMS rebuild will be triggered):\n"
            "    sudo apt --fix-broken install\n"
            "\n"
            "  Step 4 — Clean up leftover nvidia packages:\n"
            "    sudo apt remove --purge -y nvidia-kernel-common nvidia-kernel-support nvidia-driver-libs 2>/dev/null\n"
            "    sudo apt autoremove -y\n"
            "\n"
            "  Step 5 — Verify clean state:\n"
            "    dpkg -l | grep -i nvidia\n"
            "    (Should show no nvidia packages, or only 'rc' status meaning configs remain)\n"
            "\n"
            "  After cleaning up, use get_install_guide() for the correct driver installation method."
        )

    # Package status — general listing
    existing_pkgs = _run("dpkg -l 2>/dev/null | grep -iE 'nvidia-(driver|kernel|utils)' | head -10")
    if not existing_pkgs or existing_pkgs == "(no output)":
        existing_pkgs = _run("rpm -qa 2>/dev/null | grep -i nvidia | head -10")
    if existing_pkgs and existing_pkgs != "(no output)":
        checks.append(f"Installed NVIDIA packages:\n{existing_pkgs}")
    else:
        checks.append("No NVIDIA driver packages found installed.")

    # Check if fallback kernel's module was destroyed by retries
    if fallback_kernels_raw := _run("ls /boot/vmlinuz-* 2>/dev/null"):
        other_kernels = [k.replace("/boot/vmlinuz-", "").strip() for k in fallback_kernels_raw.strip().split("\n") if kernel not in k]
        dkms_full = _run("dkms status 2>/dev/null")
        for ok in other_kernels:
            if ok in (dkms_full or "") and "installed" in (dkms_full or "").lower():
                checks.append(f"Fallback kernel {ok} still has a working NVIDIA module.")
            elif dkms_full and ok not in dkms_full:
                checks.append(
                    f"WARNING: Fallback kernel {ok} may NO LONGER have a working NVIDIA module. "
                    f"The broken dpkg retry loop may have deleted it during rebuild attempts. "
                    f"If you boot into {ok} and nvidia-smi fails, you will need to rebuild: "
                    f"sudo dkms install nvidia-current/<version> -k {ok}"
                )

    return "\n\n".join(checks)


@tool
def check_dkms_build_log() -> str:
    """Read the DKMS build log to understand why the NVIDIA kernel module failed to compile."""
    kernel = _run("uname -r").strip()
    sections = []

    # Find the DKMS module directory
    dkms_dirs = _run("ls -d /var/lib/dkms/nvidia-current/*/build/make.log /var/lib/dkms/nvidia/*/build/make.log 2>/dev/null")
    if not dkms_dirs or dkms_dirs == "(no output)":
        return "No DKMS build logs found. The NVIDIA driver may not have been installed via DKMS."

    for log_path in dkms_dirs.strip().split("\n"):
        log_path = log_path.strip()
        if not log_path:
            continue
        version = log_path.split("/")[5] if len(log_path.split("/")) > 5 else "unknown"
        sections.append(f"Build log for driver version {version}:")

        log = _run(f"cat {log_path} 2>/dev/null | tail -50")
        sections.append(log)

        if "Error" in log:
            sections.append(f"\nBUILD FAILED for version {version}")
            if "__vm_flags" in log or "in_irq" in log or "implicit declaration" in log:
                sections.append(f"CAUSE: Driver {version} uses kernel APIs removed/changed in kernel {kernel}. Driver is too old for this kernel.")
            elif "No such file" in log and "headers" in log.lower():
                sections.append(f"CAUSE: Kernel headers for {kernel} are missing.")
            elif "Permission denied" in log or "Operation not permitted" in log:
                sections.append("CAUSE: Permission issue — possibly Secure Boot blocking module signing.")
        else:
            sections.append(f"Build appears successful for version {version}.")

    # Also show which kernels have working builds
    dkms_status = _run("dkms status 2>/dev/null | grep -i nvidia")
    if dkms_status and dkms_status != "(no output)":
        sections.append(f"\nDKMS status overview:\n{dkms_status}")
        if kernel not in dkms_status:
            sections.append(f"\nNo working build for running kernel {kernel}.")
        working = [l.strip() for l in dkms_status.split("\n") if "installed" in l.lower() and kernel not in l]
        if working:
            sections.append(f"Working builds exist for other kernels. User can boot into one of those as a quick fix.")

    return "\n\n".join(sections)


@tool
def check_available_kernels() -> str:
    """List all installed kernels and identify which ones have working NVIDIA drivers."""
    sections = []

    running = _run("uname -r").strip()
    sections.append(f"Currently running kernel: {running}")

    kernels = _run("ls /boot/vmlinuz-* 2>/dev/null")
    if not kernels or kernels == "(no output)":
        return "Cannot find kernel images in /boot/."

    kernel_list = [k.replace("/boot/vmlinuz-", "").strip() for k in kernels.strip().split("\n")]
    sections.append(f"\nInstalled kernels ({len(kernel_list)}):")

    dkms_status = _run("dkms status 2>/dev/null | grep -i nvidia")

    for k in kernel_list:
        is_running = " (RUNNING)" if k == running else ""
        has_nvidia = "NO"
        if dkms_status and k in dkms_status and "installed" in dkms_status.lower():
            has_nvidia = "YES"
        sections.append(f"  • {k}{is_running} — NVIDIA module built: {has_nvidia}")

    sections.append(f"\nTo boot a different kernel: reboot and select it from GRUB > Advanced options.")
    sections.append("Hold Shift (BIOS) or Escape (UEFI) during boot to access the GRUB menu.")

    return "\n\n".join(sections)


@tool
def get_install_guide() -> str:
    """Generate step-by-step GPU driver installation instructions. Detects kernel/driver version mismatches and recommends the correct approach."""
    distro_id = _run("grep '^ID=' /etc/os-release | cut -d= -f2 | tr -d '\"'").strip()
    distro_like = _run("grep '^ID_LIKE=' /etc/os-release | cut -d= -f2 | tr -d '\"'").strip()
    distro_pretty = _run("grep '^PRETTY_NAME=' /etc/os-release | cut -d= -f2 | tr -d '\"'").strip()
    gpu_info = _run("lspci -nn | grep -iE 'VGA|3D' | grep -i nvidia")
    kernel = _run("uname -r").strip()

    if "nvidia" not in gpu_info.lower():
        return "No NVIDIA GPU detected. This guide currently supports NVIDIA GPUs only."

    base = distro_like if distro_like else distro_id

    # Check for broken dpkg state first — must be resolved before anything else
    broken_pkgs = _run("dpkg -l 2>/dev/null | grep -iE 'nvidia' | grep -E '^(iF|iU|iHR)' | head -5")
    has_broken_dpkg = bool(broken_pkgs and broken_pkgs != "(no output)")

    # Detect kernel/driver version mismatch
    repo_version = _run("apt-cache policy nvidia-driver 2>/dev/null | grep Candidate | awk '{print $2}'").strip()
    if not repo_version:
        repo_version = _run("dpkg -l 2>/dev/null | grep nvidia-kernel-dkms | awk '{print $3}' | head -1").strip()

    dkms_build_failed = False
    driver_too_old = False
    if repo_version:
        dkms_log_paths = _run("ls /var/lib/dkms/nvidia-current/*/build/make.log /var/lib/dkms/nvidia/*/build/make.log 2>/dev/null").strip()
        if dkms_log_paths and dkms_log_paths != "(no output)":
            for log_path in dkms_log_paths.split("\n"):
                log_tail = _run(f"cat {log_path.strip()} 2>/dev/null | tail -20")
                if "Error" in log_tail:
                    dkms_build_failed = True
                    if "__vm_flags" in log_tail or "in_irq" in log_tail or "implicit declaration" in log_tail:
                        driver_too_old = True

    # Check if there's a working kernel available as fallback
    dkms_status = _run("dkms status 2>/dev/null | grep -i nvidia")
    fallback_kernels = []
    if dkms_status and dkms_status != "(no output)":
        for line in dkms_status.split("\n"):
            if "installed" in line.lower():
                # Extract kernel version from dkms status line
                parts = line.split(",")
                for p in parts:
                    p = p.strip()
                    if p and p != kernel and "." in p and not p[0].isalpha():
                        fallback_kernels.append(p)

    guide_parts = []
    guide_parts.append(f"NVIDIA Driver Installation Guide")
    guide_parts.append(f"Distribution: {distro_pretty}")
    guide_parts.append(f"GPU: {gpu_info.strip()}")
    guide_parts.append(f"Running kernel: {kernel}")
    if repo_version:
        guide_parts.append(f"Repository driver version: {repo_version}")

    # PREREQUISITE: Fix broken dpkg state if detected
    if has_broken_dpkg:
        guide_parts.append(f"\n{'='*60}")
        guide_parts.append(f"URGENT: BROKEN PACKAGE STATE DETECTED")
        guide_parts.append(f"{'='*60}")
        guide_parts.append(f"NVIDIA packages are in a broken dpkg state. This causes apt to retry the failed")
        guide_parts.append(f"DKMS build every time it runs, which DESTROYS any working modules for other kernels.")
        guide_parts.append(f"You MUST fix this before doing anything else.")
        guide_parts.append(f"")
        guide_parts.append(f"IMPORTANT: Remove nvidia-driver FIRST (it depends on nvidia-kernel-dkms).")
        guide_parts.append(f"Do NOT run 'apt --fix-broken install' until nvidia-kernel-dkms is fully removed,")
        guide_parts.append(f"or it will re-trigger the broken DKMS build.")
        guide_parts.append(f"")
        guide_parts.append(f"  Step 1: sudo dpkg --force-remove-reinstreq --remove nvidia-driver")
        guide_parts.append(f"  Step 2: sudo dpkg --force-remove-reinstreq --force-depends --remove nvidia-kernel-dkms")
        guide_parts.append(f"  Step 3: sudo apt --fix-broken install")
        guide_parts.append(f"  Step 4: sudo apt remove --purge -y nvidia-kernel-common nvidia-kernel-support nvidia-driver-libs 2>/dev/null")
        guide_parts.append(f"  Step 5: sudo apt autoremove -y")
        guide_parts.append(f"  Step 6: dpkg -l | grep -i nvidia   (verify clean state)")
        guide_parts.append(f"")
        guide_parts.append(f"After that, continue with the installation steps below.")

    # SCENARIO: Driver version incompatible with kernel
    if driver_too_old:
        guide_parts.append(f"\n{'='*60}")
        guide_parts.append(f"DETECTED: KERNEL/DRIVER VERSION MISMATCH")
        guide_parts.append(f"{'='*60}")
        guide_parts.append(f"The repository driver ({repo_version}) cannot compile against kernel {kernel}.")
        guide_parts.append(f"The kernel has newer APIs that this driver version does not support.")

        if fallback_kernels:
            guide_parts.append(f"\n--- OPTION A: Quick fix — boot an older kernel (fastest) ---")
            guide_parts.append(f"The NVIDIA module is already compiled for: {', '.join(fallback_kernels)}")
            guide_parts.append(f"  1. Reboot your system")
            guide_parts.append(f"  2. At the GRUB boot menu, select 'Advanced options'")
            guide_parts.append(f"     (Hold Shift during BIOS boot, or Escape during UEFI boot to see GRUB)")
            guide_parts.append(f"  3. Select kernel {fallback_kernels[0]}")
            guide_parts.append(f"  4. After boot, verify: nvidia-smi")

        guide_parts.append(f"\n--- OPTION B: Install a newer driver from NVIDIA (recommended long-term) ---")
        guide_parts.append(f"  Step 1: Remove the broken DKMS module")
        nvidia_dkms_name = "nvidia-current" if "nvidia-current" in (dkms_status or "") else "nvidia"
        guide_parts.append(f"    sudo dkms remove {nvidia_dkms_name}/{repo_version} -k {kernel} 2>/dev/null")
        guide_parts.append(f"")
        guide_parts.append(f"  Step 2: Remove conflicting repo packages")
        guide_parts.append(f"    sudo apt remove --purge -y nvidia-driver nvidia-kernel-dkms nvidia-kernel-source 2>/dev/null")
        guide_parts.append(f"    sudo apt autoremove -y")
        guide_parts.append(f"")
        guide_parts.append(f"  Step 3: Make sure kernel headers and build tools are installed")
        guide_parts.append(f"    sudo apt install -y linux-headers-$(uname -r) build-essential dkms")
        guide_parts.append(f"")
        guide_parts.append(f"  Step 4: Blacklist nouveau (if not already done)")
        guide_parts.append(f'    echo -e "blacklist nouveau\\noptions nouveau modeset=0" | sudo tee /etc/modprobe.d/blacklist-nouveau.conf')
        guide_parts.append(f"    sudo update-initramfs -u")
        guide_parts.append(f"")
        guide_parts.append(f"  Step 5: Download the latest NVIDIA driver")
        guide_parts.append(f"    Go to: https://www.nvidia.com/Download/index.aspx")
        guide_parts.append(f"    Select your GPU, Linux 64-bit, and download the .run file.")
        guide_parts.append(f"    Or download directly (check for latest version):")
        guide_parts.append(f"    wget https://us.download.nvidia.com/XFree86/Linux-x86_64/570.133.07/NVIDIA-Linux-x86_64-570.133.07.run")
        guide_parts.append(f"")
        guide_parts.append(f"  Step 6: Install the driver")
        guide_parts.append(f"    sudo systemctl stop gdm 2>/dev/null; sudo systemctl stop sddm 2>/dev/null; sudo systemctl stop lightdm 2>/dev/null")
        guide_parts.append(f"    chmod +x NVIDIA-Linux-x86_64-*.run")
        guide_parts.append(f"    sudo bash NVIDIA-Linux-x86_64-*.run --dkms")
        guide_parts.append(f"    (Accept the license, say Yes to DKMS, Yes to 32-bit libraries if asked)")
        guide_parts.append(f"")
        guide_parts.append(f"  Step 7: Reboot")
        guide_parts.append(f"    sudo reboot")
        guide_parts.append(f"")
        guide_parts.append(f"  Step 8: Verify after reboot")
        guide_parts.append(f"    nvidia-smi")
        guide_parts.append(f"    lsmod | grep nvidia")

        guide_parts.append(f"\nTROUBLESHOOTING:")
        guide_parts.append(f"  - If .run installer fails, make sure you stopped your display manager (step 6)")
        guide_parts.append(f"  - If Secure Boot blocks it: mokutil --sb-state  (disable in BIOS if enabled)")
        guide_parts.append(f"  - If nouveau is still loaded after reboot: check blacklist and run update-initramfs -u")
        guide_parts.append(f"  - Check DKMS: dkms status | grep nvidia")
        guide_parts.append(f"  - Check logs: journalctl -b | grep -i nvidia | tail -20")

        return "\n".join(guide_parts)

    # SCENARIO: DKMS failed for other reasons
    if dkms_build_failed:
        guide_parts.append(f"\nDKMS build failed. Run check_dkms_build_log() for details on the failure.")
        guide_parts.append(f"Common causes: missing kernel headers, Secure Boot, or driver/kernel incompatibility.")
        guide_parts.append(f"Fix missing headers: sudo apt install -y linux-headers-$(uname -r) build-essential dkms")
        guide_parts.append(f"Then rebuild: sudo dkms autoinstall")
        guide_parts.append(f"Then reboot: sudo reboot")
        return "\n".join(guide_parts)

    # SCENARIO: Fresh install — no driver at all
    if "debian" in base or distro_id in ("debian", "ubuntu", "parrot", "kali", "mint", "pop"):
        guide_parts.append(f"\n--- Fresh Install Steps ---")
        guide_parts.append(f"")
        guide_parts.append(f"Step 1: Update system")
        guide_parts.append(f"  sudo apt update && sudo apt upgrade -y")
        guide_parts.append(f"")
        guide_parts.append(f"Step 2: Install kernel headers and build tools")
        guide_parts.append(f"  sudo apt install -y linux-headers-$(uname -r) build-essential dkms")
        guide_parts.append(f"")
        guide_parts.append(f"Step 3: Blacklist nouveau driver")
        guide_parts.append(f'  echo -e "blacklist nouveau\\noptions nouveau modeset=0" | sudo tee /etc/modprobe.d/blacklist-nouveau.conf')
        guide_parts.append(f"  sudo update-initramfs -u")
        guide_parts.append(f"")
        guide_parts.append(f"Step 4: Install NVIDIA driver")
        guide_parts.append(f"  Try the repository version first:")
        guide_parts.append(f"    sudo apt install -y nvidia-driver")
        guide_parts.append(f"")
        guide_parts.append(f"  If that fails (DKMS build error), remove it and use NVIDIA's .run installer:")
        guide_parts.append(f"    sudo apt remove --purge -y nvidia-driver nvidia-kernel-dkms")
        guide_parts.append(f"    wget https://us.download.nvidia.com/XFree86/Linux-x86_64/570.133.07/NVIDIA-Linux-x86_64-570.133.07.run")
        guide_parts.append(f"    sudo systemctl stop gdm 2>/dev/null; sudo systemctl stop sddm 2>/dev/null; sudo systemctl stop lightdm 2>/dev/null")
        guide_parts.append(f"    sudo bash NVIDIA-Linux-x86_64-570.133.07.run --dkms")
        guide_parts.append(f"")
        guide_parts.append(f"Step 5: Reboot")
        guide_parts.append(f"  sudo reboot")
        guide_parts.append(f"")
        guide_parts.append(f"Step 6: Verify after reboot")
        guide_parts.append(f"  nvidia-smi")
        guide_parts.append(f"  lsmod | grep nvidia")
        guide_parts.append(f"")
        guide_parts.append(f"Step 7 (optional): Install CUDA toolkit")
        guide_parts.append(f"  sudo apt install -y nvidia-cuda-toolkit")
        guide_parts.append(f"  nvcc --version")
        guide_parts.append(f"")
        guide_parts.append(f"TROUBLESHOOTING:")
        guide_parts.append(f"  - nvidia-smi fails after reboot? Check: dkms status | grep nvidia")
        guide_parts.append(f"  - Secure Boot blocking? Check: mokutil --sb-state")
        guide_parts.append(f"  - Nouveau still loaded? Verify blacklist and run: sudo update-initramfs -u")
        guide_parts.append(f"  - Check logs: journalctl -b | grep -i nvidia | tail -20")

    elif "rhel" in base or "fedora" in base or distro_id in ("fedora", "centos", "rocky", "alma"):
        guide_parts.append(f"\n--- Fresh Install Steps (RHEL/Fedora) ---")
        guide_parts.append(f"  sudo dnf update -y")
        guide_parts.append(f"  sudo dnf install -y kernel-devel kernel-headers gcc make dkms")
        guide_parts.append(f"  sudo dnf install -y https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm")
        guide_parts.append(f"  sudo dnf install -y https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm")
        guide_parts.append(f"  sudo dnf install -y akmod-nvidia xorg-x11-drv-nvidia-cuda")
        guide_parts.append(f"  sudo reboot")
        guide_parts.append(f"  nvidia-smi")

    elif "arch" in base or distro_id in ("arch", "manjaro"):
        guide_parts.append(f"\n--- Fresh Install Steps (Arch) ---")
        guide_parts.append(f"  sudo pacman -S nvidia nvidia-utils nvidia-settings")
        guide_parts.append(f"  sudo reboot")
        guide_parts.append(f"  nvidia-smi")

    else:
        guide_parts.append(f"\n--- Manual Install from NVIDIA ---")
        guide_parts.append(f"  1. Go to https://www.nvidia.com/Download/index.aspx")
        guide_parts.append(f"  2. Select your GPU and Linux 64-bit")
        guide_parts.append(f"  3. Download the .run installer")
        guide_parts.append(f"  4. sudo systemctl stop gdm (or sddm/lightdm)")
        guide_parts.append(f"  5. sudo bash NVIDIA-Linux-x86_64-*.run --dkms")
        guide_parts.append(f"  6. sudo reboot")
        guide_parts.append(f"  7. nvidia-smi")

    return "\n".join(guide_parts)


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


SYSTEM_PROMPT = """You are a GPU diagnostics and setup assistant for NVIDIA GPUs on Linux, focused on AI/ML workloads with Ollama.

YOU MUST USE YOUR TOOLS. Do NOT write your own install steps or diagnosis from memory. Your tools contain real-time system checks and battle-tested instructions. Always call the tools and present their output to the user.

MANDATORY WORKFLOW — you MUST follow this exact order:
1. Call detect_gpus() to find hardware
2. Call check_driver() to check if drivers are loaded
3. If drivers are NOT working (modules not loaded, nvidia-smi fails, or nvidia-smi not installed):
   a. Call diagnose_driver() — this is MANDATORY, do not skip it
   b. Call get_install_guide() — this auto-detects the exact problem and generates the correct fix. ALWAYS use its output as your recommendation. Do NOT write your own install steps.
   c. Present the output of get_install_guide() to the user as the solution
4. If drivers ARE working:
   a. Call get_gpu_status()
   b. Call check_cuda()
   c. Call check_ollama_gpu()
5. For a complete report, call full_report()
6. After user completes install, call verify_install()

ABSOLUTE RULES — NEVER VIOLATE THESE:
- NEVER suggest installing the Nouveau driver. It has no CUDA support and is useless for AI/ML workloads.
- NEVER suggest "wait for distro updates" as a primary solution. The user needs a working GPU now.
- NEVER suggest "manual driver patching" of DKMS source. This is impractical.
- NEVER make up install commands from memory. ALWAYS call get_install_guide() and use its output.
- NEVER suggest 'apt --fix-broken install' while nvidia-kernel-dkms is still installed in a broken state — it re-triggers the failed DKMS build and destroys working modules.
- When a kernel/driver mismatch exists, the ONLY two valid solutions are:
  (A) Boot an older kernel where the driver works (quick fix)
  (B) Install a newer driver from NVIDIA's .run installer (proper fix)
- When broken dpkg state is detected, the cleanup order MUST be:
  (1) sudo dpkg --force-remove-reinstreq --remove nvidia-driver
  (2) sudo dpkg --force-remove-reinstreq --force-depends --remove nvidia-kernel-dkms
  (3) THEN sudo apt --fix-broken install
  (4) sudo apt remove --purge leftover nvidia packages
  (5) sudo apt autoremove -y
- After ANY install steps, always tell the user to reboot and then ask them to run verify_install()
- Be specific to the user's distro — the tools detect it automatically"""


TOOLS = [
    detect_gpus,
    check_driver,
    diagnose_driver,
    check_dkms_build_log,
    check_available_kernels,
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
