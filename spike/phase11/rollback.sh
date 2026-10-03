#!/bin/bash
# Phase 11 spike: undo install.sh (Devuan's driver) or install-nvidia-repo.sh
# (NVIDIA's) and go back to nouveau. Run with sudo, then reboot.
set -euo pipefail

[ "$(id -u)" = 0 ] || { echo "Run this with sudo." >&2; exit 1; }
log=/var/log/tekne-nvidia-spike.log
echo "$(date -Is) rollback: start" >> "${log}"

# xserver-xorg-video-nvidia's postrm warns about X config that mentions
# nvidia, and XLibre's own xserver-xlibre-common ships two such files
# (/etc/X11/xorg.conf.d/10-nvidia-*.conf), so the warning always fires; its
# debconf prompt then fails (exit 20) and stops dpkg. The postrm allows
# switching the check off by preseeding.
echo 'nvidia-support nvidia-support/check-xorg-conf-on-removal boolean false' \
	| debconf-set-selections

# Everything built from the driver's source packages (Devuan's or NVIDIA's),
# plus the test tools and headers the install scripts asked for. apt shows
# the list and asks first. firmware-nvidia-graphics (DEC-013) is built from
# firmware-nonfree, so it stays.
apt-get purge \
	'?source-package("^(nvidia-graphics-drivers|nvidia-kmod-open|nvidia-modprobe|egl-wayland2|egl-x11|nvidia-egl-gbm)$")' \
	mesa-utils vulkan-tools linux-headers-amd64
rm -f /etc/apt/preferences.d/tekne-nvidia-spike.pref \
	/etc/apt/sources.list.d/tekne-nvidia-spike.sources \
	/usr/share/keyrings/tekne-nvidia-spike.gpg \
	/etc/modprobe.d/tekne-nvidia-spike.conf \
	/etc/udev/rules.d/80-tekne-nvidia-spike-pm.rules \
	/usr/lib/elogind/system-sleep/tekne-nvidia-spike \
	/usr/lib/elogind/system-sleep/tekne-asus-kbd-spike \
	/usr/libexec/system-sleep/tekne-asus-kbd-spike \
	/usr/libexec/system-sleep/tekne-vt-restore-spike \
	/etc/X11/xorg.conf.d/90-tekne-nvidia-spike-ignoreabi.conf
# dkms, gcc and the rest were pulled in automatically; apt lists them first.
apt-get autoremove --purge
apt-get update
update-initramfs -u
echo "$(date -Is) rollback: done" >> "${log}"
echo "Done. Reboot to get nouveau back."
