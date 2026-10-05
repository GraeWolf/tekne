# Tekne's interactive bash defaults (SPEC §9.2), sourced from ~/.bash_aliases.
# New users get that line from /etc/skel; existing users can add it, or delete
# it to opt out of everything here.

case $- in
	*i*) ;;
	*) return ;;
esac

# bat instead of cat: Debian installs it as batcat. --paging=never keeps cat's
# behaviour in a terminal; piped or redirected, batcat prints plain text.
if command -v batcat >/dev/null 2>&1; then
	alias cat='batcat --paging=never'
	alias bat='batcat'
fi

# fastfetch when tekne-terminal opens a terminal, once: not in nested shells,
# on ttys or over SSH. Opt out with ~/.config/tekne/no-fastfetch. A user's own
# fastfetch config wins over Tekne's.
if [ -n "${TEKNE_FASTFETCH:-}" ]; then
	unset TEKNE_FASTFETCH
	if command -v fastfetch >/dev/null 2>&1 \
		&& [ ! -e "${XDG_CONFIG_HOME:-$HOME/.config}/tekne/no-fastfetch" ]; then
		if [ -e "${XDG_CONFIG_HOME:-$HOME/.config}/fastfetch/config.jsonc" ]; then
			fastfetch
		else
			fastfetch --config /usr/share/tekne/fastfetch/config.jsonc
		fi
	fi
fi
