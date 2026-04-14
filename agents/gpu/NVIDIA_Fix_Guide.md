# 🖥️ NVIDIA RTX 4090 Laptop GPU — Driver Fix Guide

**System:** Parrot Security 7.1 (echo)  
**GPU:** NVIDIA AD103M / GN21-X11 [GeForce RTX 4090 Laptop GPU]  
**Running Kernel:** 6.19.6+parrot7-amd64  
**Fallback Kernel:** 6.17.13+2-amd64 (has a working NVIDIA module)  
**Date Generated:** $(date)

---

## ⚠️ The Problem

Your system has a **broken dpkg state** from a previous failed NVIDIA driver installation. The DKMS (Dynamic Kernel Module Support) build for the NVIDIA kernel module failed on your current kernel (6.19.6), and the packages are stuck in a broken state. This means:

- `nvidia-smi` is not installed / not working
- NVIDIA kernel modules are **NOT loaded**
- Every time `apt` runs, it retries the failed DKMS build, which can **destroy** the working module on the older kernel before failing again

---

## 🔧 The Fix — Two-Phase Approach

### Phase 1: Clean Up the Broken Packages

> **CRITICAL:** The order matters! `nvidia-driver` depends on `nvidia-kernel-dkms`, so you must remove `nvidia-driver` FIRST. Do **NOT** run `apt --fix-broken install` while `nvidia-kernel-dkms` is still installed — it will re-trigger the failed DKMS build.

```bash
# Step 1 — Remove nvidia-driver (depends on nvidia-kernel-dkms)
sudo dpkg --force-remove-reinstreq --remove nvidia-driver

# Step 2 — Remove nvidia-kernel-dkms (the broken package causing the loop)
sudo dpkg --force-remove-reinstreq --force-depends --remove nvidia-kernel-dkms

# Step 3 — NOW it is safe to fix apt (no DKMS rebuild will be triggered)
sudo apt --fix-broken install

# Step 4 — Clean up leftover nvidia packages
sudo apt remove --purge -y nvidia-kernel-common nvidia-kernel-support nvidia-driver-libs 2>/dev/null
sudo apt autoremove -y

# Step 5 — Verify clean state (should show no nvidia packages, or only 'rc' status)
dpkg -l | grep -i nvidia
```

---

### Phase 2: Reinstall the NVIDIA Driver

#### Option A — Quick Fix: Boot the Older Kernel

Your fallback kernel **6.17.13+2-amd64** still has a working NVIDIA module. You can boot into it to get your GPU working immediately:

1. Reboot your machine
2. At the GRUB menu, select **"Advanced options"**
3. Choose the **6.17.13+2-amd64** kernel
4. Once booted, verify with: `nvidia-smi`

> This is a temporary workaround. The older kernel may not receive security updates.

#### Option B — Proper Fix: Fresh Driver Install on Current Kernel

After completing **Phase 1** (cleanup), do the following:

```bash
# Step 1 — Update system
sudo apt update && sudo apt upgrade -y

# Step 2 — Install kernel headers and build tools
sudo apt install -y linux-headers-$(uname -r) build-essential dkms

# Step 3 — Blacklist nouveau driver (already done on your system, but verify)
echo -e "blacklist nouveau\noptions nouveau modeset=0" | sudo tee /etc/modprobe.d/blacklist-nouveau.conf
sudo update-initramfs -u

# Step 4 — Install NVIDIA driver from repository
sudo apt install -y nvidia-driver
```

**If the repository driver fails (DKMS build error again):**

```bash
# Remove the broken install
sudo apt remove --purge -y nvidia-driver nvidia-kernel-dkms

# Download NVIDIA's official .run installer (v570.133.07 for RTX 4090)
wget https://us.download.nvidia.com/XFree86/Linux-x86_64/570.133.07/NVIDIA-Linux-x86_64-570.133.07.run

# Stop display manager
sudo systemctl stop gdm 2>/dev/null; sudo systemctl stop sddm 2>/dev/null; sudo systemctl stop lightdm 2>/dev/null

# Run the installer with DKMS flag
sudo bash NVIDIA-Linux-x86_64-570.133.07.run --dkms
```

```bash
# Step 5 — Reboot
sudo reboot
```

---

## ✅ Post-Install Verification

After rebooting, run these commands to confirm everything is working:

```bash
# Check driver is loaded
nvidia-smi

# Check kernel module
lsmod | grep nvidia

# Check DKMS status
dkms status | grep nvidia
```

Then come back and ask me to run **`verify_install()`** for a full verification.

---

## 🧰 Optional: Install CUDA Toolkit

Once the driver is working:

```bash
sudo apt install -y nvidia-cuda-toolkit
nvcc --version
```

---

## 🐛 Troubleshooting

| Problem | Solution |
|---|---|
| `nvidia-smi` fails after reboot | Check: `dkms status \| grep nvidia` |
| Secure Boot blocking module | Check: `mokutil --sb-state` |
| Nouveau still loaded | Verify blacklist: `cat /etc/modprobe.d/blacklist-nouveau.conf` then `sudo update-initramfs -u` |
| Check logs | `journalctl -b \| grep -i nvidia \| tail -20` |

---

## 📋 TL;DR — Quick Copy-Paste Sequence

```bash
# === PHASE 1: CLEANUP ===
sudo dpkg --force-remove-reinstreq --remove nvidia-driver
sudo dpkg --force-remove-reinstreq --force-depends --remove nvidia-kernel-dkms
sudo apt --fix-broken install
sudo apt remove --purge -y nvidia-kernel-common nvidia-kernel-support nvidia-driver-libs 2>/dev/null
sudo apt autoremove -y

# === PHASE 2: REINSTALL ===
sudo apt update && sudo apt upgrade -y
sudo apt install -y linux-headers-$(uname -r) build-essential dkms
sudo apt install -y nvidia-driver

# === REBOOT ===
sudo reboot
```

If `apt install nvidia-driver` fails, use the `.run` installer method described in Option B above.

---

*Generated by GPU Diagnostics Assistant*
