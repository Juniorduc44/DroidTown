# Installing NVIDIA Driver via .run Installer

Use this when the repository driver is too old for your kernel.

## Prerequisites

- NVIDIA `.run` installer downloaded (e.g., `NVIDIA-Linux-x86_64-570.133.07.run`)
- Broken repo packages already removed (no `iF`/`iU` nvidia packages in `dpkg -l`)

If you still have broken packages, clean them first:
```bash
sudo dpkg --force-remove-reinstreq --remove nvidia-driver
sudo dpkg --force-remove-reinstreq --force-depends --remove nvidia-kernel-dkms
sudo apt --fix-broken install
sudo apt autoremove -y
```

## Step 1: Install Build Dependencies

```bash
sudo apt install -y linux-headers-$(uname -r) build-essential dkms
```

## Step 2: Switch to a TTY

The installer needs exclusive GPU access. Press **Ctrl+Alt+F2** to switch to a text console and log in there.

## Step 3: Stop the Display Manager

```bash
sudo systemctl stop gdm 2>/dev/null
sudo systemctl stop sddm 2>/dev/null
sudo systemctl stop lightdm 2>/dev/null
```

## Step 4: Run the Installer

```bash
cd ~/Desktop/projects/factoryAI/DroidTown/agents/gpu
sudo bash NVIDIA-Linux-x86_64-570.133.07.run --dkms
```

When prompted:
- **Accept** the license
- **Yes** to register with DKMS
- **Yes** to 32-bit compatibility libraries (if asked)
- **Yes** to update the X configuration file (if asked)

## Step 5: Reboot

```bash
sudo reboot
```

## Step 6: Verify

```bash
nvidia-smi
lsmod | grep nvidia
```

You should see your GPU listed with driver version, temperature, and VRAM.

## Step 7: Restart Ollama

```bash
ollama serve &
# or
sudo systemctl restart ollama

# Verify GPU offload
ollama ps
```

The `PROCESSOR` column should show `GPU` instead of `CPU`.

## Troubleshooting

### "nvidia-smi: command not found" after reboot
The installer didn't complete. Re-run from Step 2.

### "NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver"
The kernel module didn't load. Check:
```bash
dkms status | grep nvidia
journalctl -b | grep -i nvidia | tail -20
```

### Installer says "ERROR: The Nouveau kernel driver is currently in use"
Blacklist nouveau and reboot before running the installer:
```bash
echo -e "blacklist nouveau\noptions nouveau modeset=0" | sudo tee /etc/modprobe.d/blacklist-nouveau.conf
sudo update-initramfs -u
sudo reboot
```
Then start from Step 2 again.

### Installer says "ERROR: Unable to find the kernel source tree"
Install kernel headers:
```bash
sudo apt install -y linux-headers-$(uname -r)
```

### Secure Boot blocking module load
```bash
mokutil --sb-state
```
If enabled, disable in BIOS or run `sudo mokutil --disable-validation` and reboot.
