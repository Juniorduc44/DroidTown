#!/usr/bin/env bash
set -Eeuo pipefail

# DroidTown NVIDIA driver installer (Parrot/Debian-family)
# Usage:
#   bash run.sh
# Optional environment variables:
#   NVIDIA_DRIVER_VERSION=570.133.07
#   NVIDIA_RUN_FILE=/absolute/path/to/NVIDIA-Linux-x86_64-<ver>.run
#   AUTO_REBOOT=1
#   RUN_SELF_TEST=1            # run checks only, no install changes
#   SKIP_REPO_INSTALL=1        # skip apt nvidia-driver and force .run path

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_FILE="${SCRIPT_DIR}/nvidia-install-$(date +%Y%m%d-%H%M%S).log"

NVIDIA_DRIVER_VERSION="${NVIDIA_DRIVER_VERSION:-570.133.07}"
NVIDIA_RUN_FILE="${NVIDIA_RUN_FILE:-}"
NVIDIA_RUN_NAME="NVIDIA-Linux-x86_64-${NVIDIA_DRIVER_VERSION}.run"
NVIDIA_RUN_URL="https://us.download.nvidia.com/XFree86/Linux-x86_64/${NVIDIA_DRIVER_VERSION}/${NVIDIA_RUN_NAME}"

cleanup_needed=0

log() { printf '[%s] %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG_FILE"; }
warn() { printf '[%s] WARN: %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG_FILE"; }
die() { printf '[%s] ERROR: %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG_FILE"; exit 1; }

on_error() {
  local exit_code="$?"
  local line_no="$1"
  local cmd="${2:-unknown}"
  printf '[%s] ERROR: command failed (exit=%s) at line %s: %s\n' \
    "$(date '+%F %T')" "$exit_code" "$line_no" "$cmd" | tee -a "$LOG_FILE"
  printf '[%s] ERROR: full log: %s\n' "$(date '+%F %T')" "$LOG_FILE" | tee -a "$LOG_FILE"
  exit "$exit_code"
}
trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR

run_cmd() {
  log "RUN: $*"
  "$@" 2>&1 | tee -a "$LOG_FILE"
}

run_cmd_retry() {
  local retries="$1"
  shift
  local delay=2
  local attempt
  for attempt in $(seq 1 "$retries"); do
    if run_cmd "$@"; then
      return 0
    fi
    if [[ "$attempt" -lt "$retries" ]]; then
      warn "Attempt ${attempt}/${retries} failed. Retrying in ${delay}s..."
      sleep "$delay"
      delay=$((delay * 2))
    fi
  done
  return 1
}

ensure_root() {
  if [[ "${RUN_SELF_TEST:-0}" == "1" ]]; then
    return 0
  fi
  if [[ "${EUID}" -ne 0 ]]; then
    log "Re-running as root with sudo..."
    exec sudo -E bash "$0" "$@"
  fi
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || die "Required command not found: ${cmd}"
}

apt_wait_for_locks() {
  local lock_files=(
    /var/lib/dpkg/lock-frontend
    /var/lib/dpkg/lock
    /var/cache/apt/archives/lock
  )
  local waited=0
  local max_wait=300
  while :; do
    local busy=0
    local f
    for f in "${lock_files[@]}"; do
      if command -v fuser >/dev/null 2>&1 && fuser "$f" >/dev/null 2>&1; then
        busy=1
        break
      fi
    done
    if [[ "$busy" -eq 0 ]]; then
      break
    fi
    if [[ "$waited" -ge "$max_wait" ]]; then
      die "Timed out waiting for apt/dpkg locks."
    fi
    warn "apt/dpkg lock detected; waiting..."
    sleep 5
    waited=$((waited + 5))
  done
}

require_debian_family() {
  if [[ ! -f /etc/os-release ]]; then
    die "Cannot detect OS (missing /etc/os-release)."
  fi
  . /etc/os-release
  case "${ID_LIKE:-}:${ID:-}" in
    *debian*|*:debian|*:parrot|*ubuntu*)
      ;;
    *)
      die "This script supports Debian-family systems. Detected ID=${ID:-unknown}, ID_LIKE=${ID_LIKE:-unknown}."
      ;;
  esac
}

require_nvidia_gpu() {
  if ! command -v lspci >/dev/null 2>&1; then
    apt_wait_for_locks
    run_cmd_retry 3 apt-get update
    run_cmd_retry 3 apt-get install -y pciutils
  fi
  if ! lspci | grep -qi nvidia; then
    die "No NVIDIA GPU detected via lspci. Aborting."
  fi
}

stop_display_manager() {
  if ! command -v systemctl >/dev/null 2>&1; then
    warn "systemctl not found; skipping display-manager stop."
    return 0
  fi
  log "Stopping display manager(s) for safe driver operations..."
  local units=(display-manager gdm gdm3 sddm lightdm)
  local unit
  for unit in "${units[@]}"; do
    if systemctl list-unit-files | awk '{print $1}' | grep -qx "${unit}.service"; then
      run_cmd systemctl stop "${unit}" || true
    fi
  done
}

fix_broken_packages_if_needed() {
  log "Checking for broken NVIDIA package state..."
  if dpkg -l | awk '/^iF|^iU/ {print $2}' | grep -qi '^nvidia'; then
    cleanup_needed=1
  fi

  if [[ "$cleanup_needed" -eq 1 ]]; then
    warn "Broken NVIDIA package state detected. Running ordered cleanup."
    run_cmd dpkg --force-remove-reinstreq --remove nvidia-driver || true
    run_cmd dpkg --force-remove-reinstreq --force-depends --remove nvidia-kernel-dkms || true
    run_cmd apt-get -f install -y || true
    run_cmd apt-get remove --purge -y \
      nvidia-kernel-common nvidia-kernel-support nvidia-driver-libs \
      nvidia-dkms-* nvidia-driver-* libnvidia-* || true
    run_cmd apt-get autoremove -y || true
  else
    log "No broken NVIDIA package state detected."
  fi
}

prepare_build_environment() {
  log "Preparing build and kernel prerequisites..."
  apt_wait_for_locks
  run_cmd_retry 3 apt-get update
  run_cmd_retry 3 apt-get install -y \
    build-essential dkms curl wget \
    linux-headers-"$(uname -r)" \
    mokutil
}

configure_nouveau_blacklist() {
  log "Ensuring nouveau is blacklisted..."
  cat >/etc/modprobe.d/blacklist-nouveau.conf <<'EOF'
blacklist nouveau
options nouveau modeset=0
EOF
  run_cmd update-initramfs -u
}

verify_driver_loaded() {
  if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    log "nvidia-smi is working."
    return 0
  fi
  if modprobe nvidia >/dev/null 2>&1 && command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi >/dev/null 2>&1 && return 0
  fi
  return 1
}

try_repo_driver() {
  if [[ "${SKIP_REPO_INSTALL:-0}" == "1" ]]; then
    warn "SKIP_REPO_INSTALL=1 set; skipping repository driver method."
    return 1
  fi
  log "Attempting repository installation first (recommended path)..."
  apt_wait_for_locks
  if run_cmd_retry 2 apt-get install -y nvidia-driver; then
    log "Repository driver installation finished."
    return 0
  fi
  warn "Repository install failed; fallback to NVIDIA .run installer path."
  return 1
}

resolve_run_installer() {
  if [[ -n "$NVIDIA_RUN_FILE" && -f "$NVIDIA_RUN_FILE" ]]; then
    log "Using provided NVIDIA_RUN_FILE: $NVIDIA_RUN_FILE"
    return 0
  fi

  local candidates=(
    "${REPO_ROOT}/agents/gpu/${NVIDIA_RUN_NAME}"
    "${SCRIPT_DIR}/${NVIDIA_RUN_NAME}"
    "/tmp/${NVIDIA_RUN_NAME}"
  )
  local c
  for c in "${candidates[@]}"; do
    if [[ -f "$c" ]]; then
      NVIDIA_RUN_FILE="$c"
      log "Using discovered .run installer: $NVIDIA_RUN_FILE"
      return 0
    fi
  done

  log "Downloading NVIDIA installer: ${NVIDIA_RUN_URL}"
  NVIDIA_RUN_FILE="/tmp/${NVIDIA_RUN_NAME}"
  run_cmd_retry 3 wget -O "$NVIDIA_RUN_FILE" "$NVIDIA_RUN_URL"
}

run_nvidia_installer() {
  resolve_run_installer
  run_cmd chmod +x "$NVIDIA_RUN_FILE"

  # Run in non-GUI mode. The silent flags keep this one-file automation unattended.
  # If the installer exits non-zero, logs are preserved for diagnostics.
  run_cmd bash "$NVIDIA_RUN_FILE" --dkms --silent --no-cc-version-check
}

post_install_summary() {
  log "Collecting post-install diagnostics..."
  run_cmd uname -r
  run_cmd dkms status || true
  run_cmd lsmod || true
  if command -v nvidia-smi >/dev/null 2>&1; then
    run_cmd nvidia-smi || true
  fi

  if verify_driver_loaded; then
    log "SUCCESS: NVIDIA driver appears operational."
  else
    warn "Driver installed but not active yet. Reboot is likely required."
  fi

  log "Log file: $LOG_FILE"
  if [[ "${AUTO_REBOOT:-0}" == "1" ]]; then
    warn "AUTO_REBOOT=1 set. Rebooting now."
    reboot
  else
    warn "Please reboot now: sudo reboot"
  fi
}

report_secure_boot_state() {
  if command -v mokutil >/dev/null 2>&1; then
    if mokutil --sb-state 2>/dev/null | grep -qi "enabled"; then
      warn "Secure Boot appears enabled. NVIDIA module load may fail unless MOK enrollment is completed."
    fi
  fi
}

print_context_warnings() {
  if [[ "$(tty || true)" != /dev/tty* ]]; then
    warn "Not running from a local TTY. If .run fallback is needed, run from Ctrl+Alt+F2 text console."
  fi
}

self_test() {
  local failures=0
  log "Running self-test mode (no installation changes)."

  if [[ -f /etc/os-release ]]; then
    log "PASS: /etc/os-release present."
  else
    warn "FAIL: /etc/os-release missing."
    failures=$((failures + 1))
  fi

  if command -v bash >/dev/null 2>&1; then
    log "PASS: bash available."
  else
    warn "FAIL: bash unavailable."
    failures=$((failures + 1))
  fi

  if command -v apt-get >/dev/null 2>&1; then
    log "PASS: apt-get available."
  else
    warn "FAIL: apt-get unavailable."
    failures=$((failures + 1))
  fi

  if command -v systemctl >/dev/null 2>&1; then
    log "PASS: systemctl available."
  else
    warn "WARN: systemctl unavailable (non-systemd environment)."
  fi

  if command -v lspci >/dev/null 2>&1 && lspci | grep -qi nvidia; then
    log "PASS: NVIDIA GPU detected."
  else
    warn "FAIL: NVIDIA GPU not detected (or lspci missing)."
    failures=$((failures + 1))
  fi

  if [[ -d "/lib/modules/$(uname -r)" ]]; then
    log "PASS: kernel modules dir exists for $(uname -r)."
  else
    warn "FAIL: missing /lib/modules/$(uname -r)."
    failures=$((failures + 1))
  fi

  if [[ "$failures" -gt 0 ]]; then
    die "Self-test found ${failures} blocking issue(s). Review log before install."
  fi

  log "Self-test complete: no blocking issues found."
}

main() {
  ensure_root "$@"
  export DEBIAN_FRONTEND=noninteractive
  log "Starting NVIDIA driver installer workflow..."
  log "Driver target version: ${NVIDIA_DRIVER_VERSION}"
  log "Kernel: $(uname -r)"
  log "Log file: ${LOG_FILE}"

  require_cmd awk
  require_cmd grep
  require_cmd dpkg
  require_cmd apt-get
  require_debian_family
  if [[ "${RUN_SELF_TEST:-0}" == "1" ]]; then
    self_test
    exit 0
  fi

  require_nvidia_gpu
  print_context_warnings
  stop_display_manager
  fix_broken_packages_if_needed
  prepare_build_environment
  report_secure_boot_state
  configure_nouveau_blacklist

  if try_repo_driver; then
    log "Repository method completed."
  else
    warn "Switching to NVIDIA .run fallback installer."
    # Ensure failed repo attempt does not keep broken state.
    apt_wait_for_locks
    run_cmd apt-get remove --purge -y nvidia-driver nvidia-kernel-dkms || true
    run_nvidia_installer
  fi

  post_install_summary
}

main "$@"
