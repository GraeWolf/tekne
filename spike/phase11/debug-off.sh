#!/bin/bash
# Phase 11 spike: undo debug-on.sh without rebooting. Run with sudo.
set -euo pipefail

[ "$(id -u)" = 0 ] || { echo "Run this with sudo." >&2; exit 1; }
state=/run/tekne-nvidia-spike-debug

pidfile=/run/tekne-nvidia-spike-logger.pid
if [ -e "${pidfile}" ]; then
	pkill -P "$(cat "${pidfile}")" || true   # the logger's dmesg and loop
	kill "$(cat "${pidfile}")" 2>/dev/null || true
	rm -f "${pidfile}"
fi
echo 0 > /sys/power/pm_debug_messages
echo 0 > /sys/power/pm_print_times
if [ -e "${state}" ]; then
	while IFS='=' read -r k v; do sysctl -q -w "kernel.${k}=${v}"; done < "${state}"
	rm -f "${state}"
fi
echo "debug off"
