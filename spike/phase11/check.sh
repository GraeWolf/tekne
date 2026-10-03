#!/bin/bash
# Phase 11 spike: collect the evidence for SPEC §9 Phase 11's criteria.
# Runs as the desktop user (no sudo), inside the X session.
#   spike/phase11/check.sh LABEL     e.g. after-install, battery, after-suspend
# Writes spike/phase11/results/LABEL.txt and prints a summary.
set -uo pipefail

label=${1:?usage: check.sh LABEL}
here=$(dirname "$(readlink -f "$0")")
mkdir -p "${here}/results"
out="${here}/results/${label}.txt"
exec 3>"${out}"
section() { printf '\n=== %s\n' "$*" >&3; }
run() { section "$*"; "$@" >&3 2>&1; }
summary=()
verdict() { summary+=("$1  $2"); }

gpu=$(for d in /sys/bus/pci/devices/*; do
	[ "$(cat "$d/vendor")" = 0x10de ] && [ "$(cat "$d/class")" = 0x030000 ] && echo "$d"
done | head -1)
audio="${gpu%.0}.1"
rt() { cat "$1/power/runtime_status" 2>/dev/null || echo "?"; }
ctl() { cat "$1/power/control" 2>/dev/null || echo "?"; }
ac=$(cat /sys/class/power_supply/ACAD/online 2>/dev/null || echo "?")

section "context"
{ date -Is; uname -r; echo "AC online: ${ac}"; echo "GPU: ${gpu}"; } >&3

# Runtime power first, before anything below wakes the GPU.
section "runtime PM before any GPU use (sampled for 20 s)"
for i in 1 2 3 4 5; do
	echo "t=$((i * 4))s gpu=$(rt "$gpu")/$(ctl "$gpu") audio=$(rt "$audio")/$(ctl "$audio")" >&3
	sleep 4
done
idle_status=$(rt "$gpu")
cat /proc/driver/nvidia/gpus/*/power >&3 2>/dev/null
[ -r /sys/class/power_supply/BAT1/power_now ] && \
	echo "battery power_now: $(( $(cat /sys/class/power_supply/BAT1/power_now) / 1000 )) mW" >&3

run /usr/sbin/dkms status
section "modules"; lsmod | grep -E '^(nvidia|nouveau|amdgpu)' >&3
run lspci -k -s "${gpu##*/}"
section "driver parameters"
grep -E 'PreserveVideoMemoryAllocations|TemporaryFilePath|DynamicPowerManagement|UseKernelSuspendNotifiers|EnableS0ix' \
	/proc/driver/nvidia/params >&3 2>&1
echo "nvidia_drm modeset: $(cat /sys/module/nvidia_drm/parameters/modeset 2>/dev/null)" >&3

xlog="${HOME}/.local/state/xorg/Xorg.0.log"
section "X log: NVIDIA, ABI and errors (${xlog})"
grep -nE 'NVIDIA|nvidia|ABI|\(EE\)' "${xlog}" >&3 2>&1
run xrandr --listproviders
run xrandr --query

section "OpenGL: default and offloaded"
default_gl=$(glxinfo -B 2>&1 | grep -E 'OpenGL (vendor|renderer) string')
offload_gl=$("${here}/prime-run" glxinfo -B 2>&1 | grep -E 'OpenGL (vendor|renderer) string')
printf 'default:\n%s\noffload:\n%s\n' "${default_gl}" "${offload_gl}" >&3
section "Vulkan devices, offloaded"
"${here}/prime-run" vulkaninfo --summary 2>&1 | grep -E 'deviceName|driverName' >&3

section "runtime PM 30 s after offload"
sleep 30
after_status=$(rt "$gpu")
echo "gpu=${after_status}/$(ctl "$gpu") audio=$(rt "$audio")/$(ctl "$audio")" >&3

run nvidia-smi
section "spike log (sleep hook)"
tail -n 30 /var/log/tekne-nvidia-spike.log >&3 2>&1

# Summary
/usr/sbin/dkms status 2>/dev/null | grep "$(uname -r).*installed" >/dev/null \
	&& verdict PASS "DKMS module built for $(uname -r)" || verdict FAIL "no DKMS module for $(uname -r)"
mods=$(lsmod | awk '{print $1}')
grep -qx nvidia <<<"${mods}" && ! grep -qx nouveau <<<"${mods}" \
	&& verdict PASS "nvidia loaded, nouveau not" || verdict FAIL "modules: $(grep -xE 'nvidia|nouveau' <<<"${mods}" | tr '\n' ' ')"
grep -qi 'AMD' <<<"${default_gl}" \
	&& verdict PASS "desktop renders on the AMD GPU" || verdict FAIL "default OpenGL isn't AMD"
grep -qi 'NVIDIA' <<<"${offload_gl}" \
	&& verdict PASS "offloaded OpenGL runs on NVIDIA" || verdict FAIL "offload OpenGL isn't NVIDIA"
grep -q 'PreserveVideoMemoryAllocations: 1' /proc/driver/nvidia/params 2>/dev/null \
	&& verdict PASS "PreserveVideoMemoryAllocations=1" || verdict FAIL "PreserveVideoMemoryAllocations not set"
[ "${idle_status}" = suspended ] && [ "${after_status}" = suspended ] \
	&& verdict PASS "GPU suspended when idle (AC=${ac})" \
	|| verdict WARN "GPU idle status: before=${idle_status} after=${after_status} (AC=${ac}; TLP forces 'on' on AC)"

grep -q 'NVIDIA(G0): Failing initialization' "${xlog}" 2>/dev/null \
	&& verdict FAIL "X has no NVIDIA GPU screen (outputs on the NVIDIA GPU unusable)" \
	|| verdict PASS "X initialised the NVIDIA GPU screen"

section "summary"
printf '%s\n' "${summary[@]}" >&3
printf '%s\n' "${summary[@]}"
echo "Report: ${out}"
