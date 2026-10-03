#!/bin/bash
# Phase 11 spike, option 3 (SPEC §9, DEC-041): NVIDIA's current driver (615)
# from NVIDIA's own Debian 13 repository, held to DEC-026's rules: a pinned
# key, Signed-By, and a pin that admits only the display driver.
# Run with sudo on the development laptop, then reboot. rollback.sh undoes it.
set -euo pipefail

[ "$(id -u)" = 0 ] || { echo "Run this with sudo." >&2; exit 1; }
here=$(dirname "$(readlink -f "$0")")
files="${here}/files/nvidia"
log=/var/log/tekne-nvidia-spike.log
note() { echo "$(date -Is) install-nvidia-repo: $*" | tee -a "${log}"; }

# --- Preflight -------------------------------------------------------------
lspci -d 10de: | grep -qE 'VGA|3D' || { echo "No NVIDIA GPU found." >&2; exit 1; }
sb=$(od -An -tu1 /sys/firmware/efi/efivars/SecureBoot-* 2>/dev/null | awk '{print $NF}')
[ "${sb:-0}" = 0 ] || { echo "Secure Boot is on; the DKMS module would be unsigned (DEC-016)." >&2; exit 1; }
if [ -n "$(dpkg --audit)" ] || dpkg-query -W -f='${Version}\n' nvidia-driver-bin 2>/dev/null | grep -q '^550'; then
	echo "The first attempt isn't fully rolled back; run rollback.sh first." >&2
	exit 1
fi

touch "${log}"; chmod 0644 "${log}"
note "start on $(uname -r)"

# --- NVIDIA's repository, DEC-026 style ------------------------------------
(cd "${files}" && sha256sum --quiet -c SHA256SUMS) \
	|| { echo "NVIDIA's key doesn't match its recorded checksum." >&2; exit 1; }
gpg --dearmor < "${files}/nvidia.pub" > /usr/share/keyrings/tekne-nvidia-spike.gpg
chmod 0644 /usr/share/keyrings/tekne-nvidia-spike.gpg
install -m 0644 "${files}/tekne-nvidia-spike.sources" /etc/apt/sources.list.d/tekne-nvidia-spike.sources
install -m 0644 "${files}/tekne-nvidia-spike.pref" /etc/apt/preferences.d/tekne-nvidia-spike.pref
install -m 0644 "${files}/tekne-nvidia-spike.conf" /etc/modprobe.d/tekne-nvidia-spike.conf
install -m 0644 "${files}/80-tekne-nvidia-spike-pm.rules" /etc/udev/rules.d/80-tekne-nvidia-spike-pm.rules
note "installed key, source, pin, modprobe options and udev rule (no sleep hook: 615 uses kernel suspend notifiers)"

# --- Packages --------------------------------------------------------------
# No recommends: they would add nvidia-persistenced (keeps the GPU awake),
# nvidia-settings, and nvidia-driver-pinning-615, which the pin blocks anyway.
apt-get update
apt-get install --no-install-recommends nvidia-driver linux-headers-amd64 mesa-utils vulkan-tools
note "packages installed: $(dpkg-query -W -f='${Version}' nvidia-driver)"

# --- Did DKMS build the module for this kernel? ----------------------------
dkms status | tee -a "${log}"
if ! dkms status | grep -q "^nvidia/.*$(uname -r).*installed"; then
	note "FAILED: no DKMS module for $(uname -r)"
	echo "DKMS didn't build the module. See /var/lib/dkms/nvidia/*/build/make.log" >&2
	echo "Don't reboot into this; run rollback.sh instead." >&2
	exit 1
fi

update-initramfs -u
note "done; reboot next"
echo
echo "Done. Reboot, log in, then run: spike/phase11/check.sh after-install"
