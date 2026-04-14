# Companion Guide for `run.sh` (NVIDIA Driver Install)

This guide is the operator playbook for `howTo/run.sh`.

Use it when you want one repeatable command to recover/install NVIDIA drivers on your Parrot/Debian laptop, with clear validation and rollback steps.

## What This Script Does

`run.sh` performs the following in a safe order:

1. Validates OS family and NVIDIA GPU presence.
2. Stops display manager services (non-GUI install safety).
3. Detects/cleans broken NVIDIA package states (`iF`/`iU`).
4. Installs build prerequisites and kernel headers.
5. Blacklists `nouveau` and updates initramfs.
6. Attempts repo driver install first (`apt install nvidia-driver`).
7. Falls back to NVIDIA `.run` installer if repo method fails.
8. Outputs post-install diagnostics (`dkms`, `lsmod`, `nvidia-smi`).
9. Writes a full timestamped log file in `howTo/`.

## Before You Run

- Save your work and close applications.
- Prefer running from a local TTY (`Ctrl+Alt+F2`) if possible.
- Ensure network access is available.
- Confirm you can use `sudo`.

Optional sanity check:

```bash
cd /home/cbman0/Desktop/projects/factoryAI/DroidTown
RUN_SELF_TEST=1 bash howTo/run.sh
```

If self-test reports blocking failures, fix those first.

## Standard Install (Recommended)

```bash
cd /home/cbman0/Desktop/projects/factoryAI/DroidTown/howTo
bash run.sh
```

This uses the safest default strategy:

- repo driver first
- `.run` installer only as fallback

## Advanced Run Modes

Force `.run` method immediately:

```bash
cd /home/cbman0/Desktop/projects/factoryAI/DroidTown/howTo
SKIP_REPO_INSTALL=1 bash run.sh
```

Use a specific `.run` file:

```bash
cd /home/cbman0/Desktop/projects/factoryAI/DroidTown/howTo
NVIDIA_RUN_FILE=/absolute/path/NVIDIA-Linux-x86_64-570.133.07.run bash run.sh
```

Auto reboot after completion:

```bash
cd /home/cbman0/Desktop/projects/factoryAI/DroidTown/howTo
AUTO_REBOOT=1 bash run.sh
```

Run preflight tests only (no install changes):

```bash
cd /home/cbman0/Desktop/projects/factoryAI/DroidTown
RUN_SELF_TEST=1 bash howTo/run.sh
```

## Where Logs Go

Each run writes:

- `howTo/nvidia-install-YYYYMMDD-HHMMSS.log`

If anything fails, start with that file. The script logs:

- exact command executed
- line number on failure
- exit code

## Post-Install Verification

After reboot, run:

```bash
nvidia-smi
lsmod | grep nvidia
dkms status | grep nvidia
```

Success looks like:

- `nvidia-smi` shows your RTX GPU and driver version
- `lsmod` includes `nvidia`
- `dkms status` shows an installed/built nvidia module for your kernel

## Troubleshooting Quick Map

### 1) apt/dpkg lock errors

Script already waits/retries. If still blocked:

```bash
sudo fuser /var/lib/dpkg/lock-frontend
sudo fuser /var/lib/dpkg/lock
```

Wait for the owning process to finish, then rerun.

### 2) Repo install fails repeatedly

Use forced fallback:

```bash
SKIP_REPO_INSTALL=1 bash run.sh
```

### 3) Secure Boot blocks module load

Check:

```bash
mokutil --sb-state
```

If enabled, disable Secure Boot or complete MOK enrollment workflow.

### 4) Nouveau conflict

The script writes:

- `/etc/modprobe.d/blacklist-nouveau.conf`

Then runs:

- `update-initramfs -u`

Reboot and rerun if conflict persists.

### 5) Driver installed but `nvidia-smi` still fails

Run:

```bash
journalctl -b | grep -i nvidia | tail -50
dkms status
```

Check for module build/load errors for your current kernel.

## Rollback / Recovery

If you need to remove NVIDIA packages and reset:

```bash
sudo apt remove --purge -y nvidia-driver nvidia-kernel-dkms 'nvidia-*' 'libnvidia-*'
sudo apt -f install
sudo apt autoremove -y
sudo update-initramfs -u
sudo reboot
```

Then rerun:

```bash
cd /home/cbman0/Desktop/projects/factoryAI/DroidTown/howTo
bash run.sh
```

## Recommended Sequence for Your System

1. `RUN_SELF_TEST=1 bash howTo/run.sh`
2. `bash howTo/run.sh`
3. Reboot
4. Verify with `nvidia-smi` and `dkms status`

This gives the highest chance of success while preserving a full audit trail in logs for any failure path.
