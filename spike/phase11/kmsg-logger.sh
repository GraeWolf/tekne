#!/bin/bash
# Phase 11 spike: append every kernel message to LOG and fsync it after each
# line, so whatever the kernel said before a freeze is on disk. Started by
# debug-on.sh, stopped by debug-off.sh.
log=${1:?usage: kmsg-logger.sh LOG}
dmesg --follow --time-format iso | while IFS= read -r line; do
	printf '%s\n' "${line}" >> "${log}"
	sync "${log}"
done
