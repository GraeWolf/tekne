# Tekne (DEC-014): logging in on tty1 starts the X session.
# To keep a plain console on tty1, create ~/.config/tekne/no-startx.
#
# DEC-042: no restart loop. With autologin, a broken X would otherwise loop:
# startx fails, the shell logs out, getty respawns and logs in again. If the
# session ends within a few seconds, whatever startx returns (xinit reports
# success when the session client fails), this stays on a console shell and
# leaves a marker holding the boot ID, so tty1 doesn't start X again until the
# next boot. tty2-6 keep normal logins.
if [ -z "${DISPLAY:-}" ] && [ "$(tty)" = /dev/tty1 ] \
	&& [ ! -e "${XDG_CONFIG_HOME:-$HOME/.config}/tekne/no-startx" ] \
	&& command -v startx >/dev/null 2>&1; then
	# DEC-045: X takes its seat from elogind, not seatd. Under seatd, X sometimes
	# never got its seat back after a suspend's VT switch.
	export LIBSEAT_BACKEND="${LIBSEAT_BACKEND:-logind}"
	_tekne_marker="${XDG_CACHE_HOME:-$HOME/.cache}/tekne/startx-failed"
	_tekne_boot="$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)"
	if [ -n "${_tekne_boot}" ] && [ "$(cat "${_tekne_marker}" 2>/dev/null)" = "${_tekne_boot}" ]; then
		echo "tekne: X failed earlier in this boot, so it isn't started again. Log:"
		echo "  ~/.local/state/xorg/Xorg.0.log"
		echo "To try again: rm ${_tekne_marker} && startx"
	else
		_tekne_start="$(date +%s)"
		startx
		_tekne_status=$?
		if [ $(( $(date +%s) - _tekne_start )) -ge 15 ]; then
			exit "${_tekne_status}"
		fi
		mkdir -p "${_tekne_marker%/*}" && echo "${_tekne_boot}" > "${_tekne_marker}"
		echo "tekne: X exited after less than 15 seconds (status ${_tekne_status})."
		echo "tty1 stays on this console until the next boot. X's log:"
		echo "  ~/.local/state/xorg/Xorg.0.log"
		echo "To try again: rm ${_tekne_marker} && startx"
	fi
	unset _tekne_marker _tekne_boot _tekne_start _tekne_status
fi
