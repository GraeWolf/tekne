#!/bin/sh
# Phase 11 spike: set runtime power management for the NVIDIA GPU and its audio
# function, overriding TLP until it next applies its settings (a power-source
# change or boot). Run with sudo.
#   gpu-pm.sh auto   let the idle GPU power off (what TLP does on battery)
#   gpu-pm.sh on     keep it powered (what TLP does on AC)
set -eu
mode=${1:?usage: gpu-pm.sh auto|on}
for f in /sys/bus/pci/devices/*; do
	[ "$(cat "$f/vendor")" = 0x10de ] || continue
	echo "${mode}" > "$f/power/control"
	echo "$(basename "$f"): $(cat "$f/power/control")"
done
