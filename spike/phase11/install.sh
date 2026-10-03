#!/bin/bash
# Phase 11 spike (SPEC §9, DEC-041): install Devuan's NVIDIA driver from
# excalibur-backports by hand, plus the pieces tekne-nvidia would ship.
# Run with sudo on the development laptop, then reboot. rollback.sh undoes it.
set -euo pipefail

[ "$(id -u)" = 0 ] || { echo "Run this with sudo." >&2; exit 1; }
here=$(dirname "$(readlink -f "$0")")
log=/var/log/tekne-nvidia-spike.log
note() { echo "$(date -Is) install: $*" | tee -a "${log}"; }

# --- Preflight -------------------------------------------------------------
lspci -d 10de: | grep -qE 'VGA|3D' || { echo "No NVIDIA GPU found." >&2; exit 1; }
sb=$(od -An -tu1 /sys/firmware/efi/efivars/SecureBoot-* 2>/dev/null | awk '{print $NF}')
[ "${sb:-0}" = 0 ] || { echo "Secure Boot is on; the DKMS module would be unsigned (DEC-016)." >&2; exit 1; }
case "$(uname -r)" in
	*bpo*|7.*) ;;
	*) echo "Not running the backports kernel (DEC-036): $(uname -r)" >&2; exit 1 ;;
esac

touch "${log}"; chmod 0644 "${log}"
note "start on $(uname -r)"

# --- Files tekne-nvidia would ship (spike names, so rollback finds them) ---
install -m 0644 "${here}/files/tekne-nvidia-spike.pref" /etc/apt/preferences.d/tekne-nvidia-spike.pref
install -m 0644 "${here}/files/tekne-nvidia-spike.conf" /etc/modprobe.d/tekne-nvidia-spike.conf
install -m 0644 "${here}/files/80-tekne-nvidia-spike-pm.rules" /etc/udev/rules.d/80-tekne-nvidia-spike-pm.rules
install -m 0755 "${here}/files/tekne-nvidia-spike-sleep" /usr/lib/elogind/system-sleep/tekne-nvidia-spike
note "installed pin, modprobe options, udev rule and elogind sleep hook"

# --- Packages --------------------------------------------------------------
# nvidia-persistenced (recommended by nvidia-driver) starts at boot and keeps
# the GPU initialised, which stops it powering down; leave it out.
apt-get update
apt-get install nvidia-driver nvidia-kernel-dkms firmware-nvidia-gsp \
	linux-headers-amd64 mesa-utils vulkan-tools nvidia-persistenced-
note "packages installed"

# --- Did DKMS build the module for this kernel? ----------------------------
dkms status | tee -a "${log}"
if ! dkms status | grep -q "$(uname -r).*installed"; then
	note "FAILED: no DKMS module for $(uname -r)"
	echo "DKMS didn't build the module for $(uname -r). See /var/lib/dkms/nvidia-current/*/build/make.log" >&2
	echo "Don't reboot into this; run rollback.sh instead." >&2
	exit 1
fi

# Debian's nouveau blacklist must reach the initramfs.
update-initramfs -u
note "done; reboot next"
echo
echo "Done. Reboot, log in, then run: spike/phase11/check.sh after-install"
