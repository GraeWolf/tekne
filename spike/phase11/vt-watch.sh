#!/bin/sh
# Phase 11 spike: every 2 s, record which VT is active and what X, seatd and
# i3lock are doing, so a frozen resume can be read afterwards. Runs as the
# user, no root needed; it's frozen and restored along with the session.
#   vt-watch.sh OUT
out=${1:?usage: vt-watch.sh OUT}
while :; do
	x=$(ps -o stat=,wchan:24= -C Xorg | head -1)
	s=$(ps -o stat=,wchan:24= -C seatd | head -1)
	l=$(pgrep -x i3lock >/dev/null && echo yes || echo no)
	echo "$(date +%T) vt=$(cat /sys/class/tty/tty0/active) X=[${x}] seatd=[${s}] i3lock=${l} xlog=$(stat -c %Y "${HOME}/.local/state/xorg/Xorg.0.log")" >> "${out}"
	sleep 2
done
