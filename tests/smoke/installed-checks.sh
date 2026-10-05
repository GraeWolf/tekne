#!/bin/sh
# Runs as root inside an installed Tekne system booted by tests/smoke/install.py
# (delivered through QEMU fw_cfg). Prints KEY=VALUE lines; install.py compares
# them with what the answers file asked for (docs/installer.md §6).

echo "PID1=$(cat /proc/1/comm)"
[ -d /run/systemd/system ] && echo RUN_SYSTEMD=present || echo RUN_SYSTEMD=absent
echo "SYSTEMD_PKGS=$(dpkg-query -W -f '${Package}\n' | grep -c systemd)"
echo "LIVE_PKGS=$(dpkg-query -W -f '${Package} ${db:Status-Status}\n' 'live-*' tekne-installer 2>/dev/null | awk '$2 == "installed"' | wc -l)"
echo "LIVE_FILES=$(ls /usr/lib/live/config/0161-tekne-autologin /usr/local/sbin/tekne-serial-getty /usr/share/tekne-installer 2>/dev/null | wc -l)"
echo "AUTOLOGIN=$(grep -c -- '--autologin' /etc/inittab)"

echo "ROOT_FS=$(findmnt -no FSTYPE /)"
echo "BOOT_FS=$(findmnt -no FSTYPE /boot)"
echo "EFI_FS=$(findmnt -no FSTYPE /boot/efi 2>/dev/null || echo none)"
echo "CRYPT=$(lsblk -rno TYPE | grep -c crypt)"

echo "SWAP_ACTIVE=$(swapon --show=NAME --noheadings | grep -cx /swapfile)"
echo "SWAP_GIB=$(( $(stat -c %s /swapfile) / 1073741824 ))"
echo "SWAP_OFFSET=$(filefrag -v /swapfile | awk '$1 == "0:" { sub(/\.\.$/, "", $4); print $4; exit }')"
echo "CMDLINE_OFFSET=$(sed -n 's/.*resume_offset=\([0-9]*\).*/\1/p' /proc/cmdline)"
echo "CMDLINE_RESUME=$(sed -n 's/.*resume=UUID=\([^ ]*\).*/\1/p' /proc/cmdline)"
echo "ROOT_UUID=$(findmnt -no UUID /)"

echo "OS_ID=$(. /etc/os-release && echo "${ID}")"
# DEC-036: the kernel comes from excalibur-backports.
case "$(uname -r) $(dpkg-query -W -f '${Version}' linux-image-amd64)" in
	*bpo*) echo "KERNEL=backports" ;;
	*)     echo "KERNEL=stable" ;;
esac
# DEC-040: Tekne's own repository is configured: its source, pin and key.
echo "TEKNE_REPO=$([ -f /etc/apt/sources.list.d/tekne.sources ] && [ -f /etc/apt/preferences.d/tekne.pref ] \
	&& [ -f /usr/share/tekne/keyrings/tekne.gpg ] && echo configured || echo missing)"
echo "GRUB_THEME=$([ -f /boot/grub/themes/tekne/theme.txt ] && echo present || echo missing)"
echo "HOSTNAME=$(cat /etc/hostname)"
echo "TIMEZONE=$(cat /etc/timezone)"
echo "LANG=$(sed -n 's/^LANG=//p' /etc/default/locale | tr -d '"')"
echo "KEYMAP=$(sed -n 's/^XKBLAYOUT=//p' /etc/default/keyboard | tr -d '"')"
echo "ROOT_PASSWORD=$(passwd -S root | awk '{print $2}')"
echo "USER_GROUPS=$(id -nG tester | tr ' ' ',')"
# DEC-030: logging in with a password (install.py logs in on the serial
# console, PAM service "login") starts the keyring daemon with that password.
echo "KEYRING_DAEMON=$(pgrep -u tester -x gnome-keyring-d >/dev/null && echo running || echo missing)"
# pam_gnome_keyring needs XDG_RUNTIME_DIR, which pam_elogind sets up.
echo "PAM_ORDER=$(awk '/pam_elogind/ { e = NR } /pam_gnome_keyring/ { g = NR } END { print (e && g && e < g) ? "ok" : "wrong" }' /etc/pam.d/common-session)"
# Then do what tekne-session does in the X session (start the secrets
# component on a session bus) and ask over D-Bus whether the login keyring is
# unlocked. The daemon creates it on first use, from the login password.
uid="$(id -u tester)"
locked="$(sudo -u tester env HOME=/home/tester XDG_RUNTIME_DIR="/run/user/${uid}" dbus-run-session -- sh -c \
	'gnome-keyring-daemon --start --components=secrets >/dev/null 2>&1
	 dbus-send --session --print-reply --dest=org.freedesktop.secrets /org/freedesktop/secrets/collection/login \
		org.freedesktop.DBus.Properties.Get string:org.freedesktop.Secret.Collection string:Locked' 2>/dev/null \
	| awk '/boolean/ { print $3 }')"
case "${locked}" in
	false) echo "LOGIN_KEYRING=unlocked" ;;
	true)  echo "LOGIN_KEYRING=locked" ;;
	*)     echo "LOGIN_KEYRING=missing" ;;
esac
echo "FIREWALL=$(nft list chain inet tekne input 2>/dev/null | grep -q 'policy drop' && echo loaded || echo missing)"
# Resume fixes (SPEC §9.4). DEC-045: tty1's startx gets libseat's logind
# backend. DEC-044: the ASUS keyboard hook does nothing without that keyboard.
# DEC-025: TLP's sleep hook runs from the directory Devuan's elogind reads.
echo "SEAT_BACKEND=$(sed -n 's/.*export LIBSEAT_BACKEND="\${LIBSEAT_BACKEND:-\([a-z]*\)}".*/\1/p' /etc/profile.d/tekne-startx.sh)"
kmsg_before="$(dmesg | grep -c tekne-asus-keyboard)"
/usr/libexec/system-sleep/tekne-asus-keyboard post suspend
hook_rc=$?
echo "ASUS_KBD_HOOK=$([ "${hook_rc}" = 0 ] && [ "$(dmesg | grep -c tekne-asus-keyboard)" = "${kmsg_before}" ] && echo idle || echo acted)"
echo "TLP_SLEEP_HOOK=$([ -x /usr/libexec/system-sleep/49-tekne-tlp ] && [ -x /usr/lib/elogind/system-sleep/49-tlp-sleep ] && echo linked || echo missing)"
echo "GRUB_PKG=$(dpkg-query -W -f '${Package} ${db:Status-Status}\n' grub-pc grub-efi-amd64 2>/dev/null | awk '$2 == "installed" { print $1 }')"
