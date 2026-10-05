# Tekne (DEC-014): logging in on tty1 starts the X session.
# To keep a plain console on tty1, create ~/.config/tekne/no-startx.
if [ -z "${DISPLAY:-}" ] && [ "$(tty)" = /dev/tty1 ] \
	&& [ ! -e "${XDG_CONFIG_HOME:-$HOME/.config}/tekne/no-startx" ] \
	&& command -v startx >/dev/null 2>&1; then
	# DEC-045: X takes its seat from elogind, not seatd. Under seatd, X sometimes
	# never got its seat back after a suspend's VT switch.
	export LIBSEAT_BACKEND="${LIBSEAT_BACKEND:-logind}"
	exec startx
fi
