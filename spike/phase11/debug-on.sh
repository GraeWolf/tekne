#!/bin/bash
# Phase 11 spike: make a suspend/resume freeze leave evidence. Run with sudo.
# Until the next reboot (or debug-off.sh):
#  - lockups and stuck tasks panic, so the EFI pstore keeps the kernel log,
#    and the laptop reboots itself 20 s after a panic;
#  - suspend/resume prints each device as it's handled (dmesg only; the
#    console stays quiet at loglevel=3);
#  - every kernel message is appended to /var/log/tekne-nvidia-spike-kmsg.log
#    and fsynced, so whatever happened before a freeze is on disk.
set -euo pipefail

[ "$(id -u)" = 0 ] || { echo "Run this with sudo." >&2; exit 1; }
log=/var/log/tekne-nvidia-spike-kmsg.log
state=/run/tekne-nvidia-spike-debug

# Remember the current values for debug-off.sh.
if [ ! -e "${state}" ]; then
	for k in nmi_watchdog softlockup_panic hardlockup_panic hung_task_panic \
		hung_task_timeout_secs panic panic_on_oops; do
		echo "${k}=$(cat /proc/sys/kernel/${k})"
	done > "${state}"
fi

sysctl -q -w kernel.nmi_watchdog=1 \
	kernel.softlockup_panic=1 kernel.hardlockup_panic=1 \
	kernel.hung_task_panic=1 kernel.hung_task_timeout_secs=30 \
	kernel.panic_on_oops=1 kernel.panic=20
echo 1 > /sys/power/pm_debug_messages
echo 1 > /sys/power/pm_print_times

here=$(dirname "$(readlink -f "$0")")
pidfile=/run/tekne-nvidia-spike-logger.pid
# A PID file, not pgrep -f: any command line mentioning the logger would match.
if ! { [ -e "${pidfile}" ] && kill -0 "$(cat "${pidfile}")" 2>/dev/null; }; then
	touch "${log}"; chmod 0644 "${log}"
	echo "=== $(date -Is) logger start, boot $(cat /proc/sys/kernel/random/boot_id)" >> "${log}"
	setsid "${here}/kmsg-logger.sh" "${log}" </dev/null >/dev/null 2>&1 &
	echo $! > "${pidfile}"
fi

sleep 1
echo "nmi_watchdog=$(cat /proc/sys/kernel/nmi_watchdog) hung_task_panic=$(cat /proc/sys/kernel/hung_task_panic) panic=$(cat /proc/sys/kernel/panic)"
echo "pm_debug_messages=$(cat /sys/power/pm_debug_messages) pm_print_times=$(cat /sys/power/pm_print_times)"
kill -0 "$(cat "${pidfile}")" 2>/dev/null && echo "logger running (pid $(cat "${pidfile}")): ${log}" || echo "logger NOT running" >&2
