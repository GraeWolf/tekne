#!/usr/bin/env python3
"""Live boot smoke test: boot the ISO headless in QEMU and check it over serial.

    tests/smoke/live-boot.py [bios|uefi|all] [ISO]

Defaults to "all" and the newest out/tekne-*-amd64.iso. For each firmware
mode it boots the ISO, presses "s" at the GRUB menu to pick the serial-console
entry, logs in as the live user, and checks SPEC.md §4 rule 1: PID 1 is
sysvinit's init and /run/systemd/system doesn't exist. It then waits for the
autologin desktop on tty1 and checks that the X server and every session
component in DESKTOP_PROCESSES is running (Phase 2), that Tekne's firewall is
loaded, that nothing listens beyond loopback (DEC-023), and that X took its
seat from elogind (DEC-045).

It then boots two more entries, reached with GRUB's menu keys and edited to
add the serial console:
- "safe graphics" (nomodeset), UEFI only: the same desktop checks, with X on
  the firmware's framebuffer through the fbdev driver. BIOS has no
  framebuffer for X there (docs/testing.md).
- "console, no desktop" (tekne.console): tty1's autologin stays on a
  console, with no X, and the login message points to the installer.
Serial logs are written to out/serial-<mode>[-safe|-console].log. Exits
non-zero if any check fails.
"""
import functools
import os
import sys
import tempfile
import time

from qemu_serial import (OUT, SERIAL_ENTRY_HOTKEY, SERIAL_ENTRY_TITLE, Serial,
                         newest_iso, parse_results, qemu_command, start, stop, uefi_vars)

LIVE_USER, LIVE_PASSWORD = "user", "live"

MENU_TIMEOUT = 60
BOOT_TIMEOUT = 300
CMD_TIMEOUT = 60
DESKTOP_TIMEOUT = 120

# Started on tty1 by autologin -> startx -> tekne-session -> herbstluftwm autostart.
DESKTOP_PROCESSES = [
    "Xorg", "herbstluftwm", "polybar", "dunst", "picom", "lxpolkit", "copyq",
    "xss-lock", "pipewire", "wireplumber", "pipewire-pulse",
]

# Assembled at runtime so the echoed command line never matches the markers.
BEGIN, END = "__TEKNE" + "_BEGIN__", "__TEKNE" + "_END__"
CHECK_CMD = (
    'echo __TEKNE""_BEGIN__; '
    'echo "PID1=$(cat /proc/1/comm)"; '
    '[ -d /run/systemd/system ] && echo RUN_SYSTEMD=present || echo RUN_SYSTEMD=absent; '
    "dpkg-query -W -f='${Package}\\n' | grep systemd | sed 's/^/PKG=/'; "
    # Poll until every desktop process is up, or DESKTOP_TIMEOUT seconds pass.
    f'i=0; while [ $i -lt {DESKTOP_TIMEOUT} ]; do n=0; '
    f'for p in {" ".join(DESKTOP_PROCESSES)}; do pgrep -x $p >/dev/null || n=1; done; '
    '[ $n = 0 ] && break; sleep 1; i=$((i+1)); done; '
    f'for p in {" ".join(DESKTOP_PROCESSES)}; do pgrep -x $p >/dev/null && echo PROC_$p=up || echo PROC_$p=down; done; '
    # DEC-023: Tekne's firewall is loaded, and nothing listens beyond loopback.
    # DEC-034: the live system identifies as Tekne.
    'echo "OS_ID=$(. /etc/os-release && echo $ID)"; '
    # DEC-045: X took its seat from elogind (libseat's logind backend).
    'grep -q "Seat opened with backend .logind." ~/.local/state/xorg/Xorg.0.log && echo SEAT=logind || echo SEAT=other; '
    # Phase 12: the bar's symbols font (DEC-043) and the floating, centred
    # windows for nmtui, Blueman and Pavucontrol.
    'fc-match -f "%{family[0]}\\n" "Symbols Nerd Font" | grep -qx "Symbols Nerd Font" && echo SYMBOLS_FONT=present || echo SYMBOLS_FONT=missing; '
    'echo "FLOAT_RULES=$(DISPLAY=:0 herbstclient list_rules | grep -c floatplacement=center)"; '
    # ssh-agent keeps a key after its first use (/etc/ssh/ssh_config.d/tekne.conf).
    'ssh -G localhost </dev/null 2>/dev/null | grep -qx "addkeystoagent true" && echo SSH_ADDKEYS=yes || echo SSH_ADDKEYS=no; '
    'sudo nft list chain inet tekne input 2>/dev/null | grep -q "policy drop" && echo FIREWALL=loaded || echo FIREWALL=missing; '
    "sudo ss -H -tuln | awk '{print $5}' | grep -v -E '^(127\\.|\\[::1\\]|\\[::ffff:127\\.)' | sed 's/^/LISTEN=/'; "
    'echo __TEKNE""_END__\n'
)

# GRUB entries the test edits: their place in the menu, counting from 0, and
# their titles.
SAFE_ENTRY = (1, "Tekne live (safe graphics)")
CONSOLE_ENTRY = (2, "Tekne live (console, no desktop)")
CONSOLE_TTY1_TIMEOUT = 60
# How long tty1's autologin shell runs with no X before the check passes;
# startx would have started X within a few seconds.
CONSOLE_NO_X_SECS = 15

CONSOLE_CHECK_CMD = (
    'echo __TEKNE""_BEGIN__; '
    'grep -qw tekne.console /proc/cmdline && echo CMDLINE_CONSOLE=yes || echo CMDLINE_CONSOLE=no; '
    'grep -qw nomodeset /proc/cmdline && echo NOMODESET=yes || echo NOMODESET=no; '
    # tty1's autologin shell, which would otherwise start X.
    f'i=0; while [ $i -lt {CONSOLE_TTY1_TIMEOUT} ] && ! pgrep -t tty1 -x bash >/dev/null; do sleep 1; i=$((i+1)); done; '
    'pgrep -t tty1 -x bash >/dev/null && echo TTY1_SHELL=up || echo TTY1_SHELL=down; '
    f'sleep {CONSOLE_NO_X_SECS}; '
    'pgrep -x Xorg >/dev/null && echo XORG=running || echo XORG=absent; '
    '[ -e ~/.config/tekne/no-startx ] && echo NO_STARTX=yes || echo NO_STARTX=no; '
    # live-config's xinit component (disabled by nocomponents=xinit) would loop startx.
    '[ -e /etc/profile.d/zz-live-config_xinit.sh ] && echo XINIT_LOOP=present || echo XINIT_LOOP=absent; '
    'grep -q "sudo tekne-install" /etc/motd && echo MOTD_HINT=yes || echo MOTD_HINT=no; '
    'sudo -n test -x /usr/sbin/tekne-install && echo INSTALLER=yes || echo INSTALLER=no; '
    'echo __TEKNE""_END__\n'
)
CONSOLE_EXPECTED = {
    "CMDLINE_CONSOLE": "yes", "NOMODESET": "yes", "TTY1_SHELL": "up", "XORG": "absent",
    "NO_STARTX": "yes", "XINIT_LOOP": "absent", "MOTD_HINT": "yes", "INSTALLER": "yes",
}


def boot_and_check(mode, iso, log_path, pick_entry, check_cmd, check_timeout):
    """Boot the ISO, pick a GRUB entry with pick_entry(con), log in over
    serial, and run check_cmd. Returns (seconds to the login prompt, the
    command's output), or None after printing the failure."""
    with tempfile.TemporaryDirectory() as tmp, open(log_path, "w") as log:
        vars_path = uefi_vars(os.path.join(tmp, "OVMF_VARS.fd")) if mode == "uefi" else None
        proc = start(qemu_command(mode, vars_path) + ["-cdrom", iso, "-boot", "d"])
        con = Serial(proc, log)
        started = time.monotonic()
        try:
            # The serial entry is the menu's last, so the whole menu is drawn.
            con.expect(SERIAL_ENTRY_TITLE, MENU_TIMEOUT)
            pick_entry(con)
            con.expect("login:", BOOT_TIMEOUT)
            boot_secs = time.monotonic() - started
            con.send(LIVE_USER + "\n")
            con.expect("assword:", CMD_TIMEOUT)
            con.send(LIVE_PASSWORD + "\n")
            con.expect("$ ", CMD_TIMEOUT)
            con.send(check_cmd)
            con.expect(BEGIN, CMD_TIMEOUT)
            output = con.expect(END, check_timeout)
            con.send("sudo poweroff\n")
            stop(proc, CMD_TIMEOUT)
        except (TimeoutError, RuntimeError) as err:
            print(f"FAIL [{mode}]: {err}. Serial log: {log_path}")
            return None
        finally:
            if proc.poll() is None:
                proc.kill()
    return boot_secs, output


def pick_serial_entry(con):
    con.send(SERIAL_ENTRY_HOTKEY)


def pick_edited_entry(entry, con):
    """Open entry, (index, title), in GRUB's editor and add the serial console
    to its linux line: Ctrl+N moves down (the menu, then the editor's lines:
    "setparams", the empty line after the entry's "{", then linux), Ctrl+E
    goes to the end of the line, and Ctrl+X boots. A hotkey would boot the
    entry before it can be edited."""
    index, title = entry
    for key in "\x0e" * index + "e":
        con.send(key)
        time.sleep(0.3)
    con.expect(f"setparams '{title}'", CMD_TIMEOUT)
    for key in "\x0e\x0e\x05":
        con.send(key)
        time.sleep(0.3)
    # One key at a time: UEFI GRUB redraws the line after each one, and on a
    # slow runner it fell behind a single write, so the serial port dropped
    # the end ("tekne.se").
    for key in " console=tty0 console=ttyS0,115200n8 tekne.serial":
        con.send(key)
        time.sleep(0.1)
    time.sleep(0.5)
    con.send("\x18")


def run(mode, iso, safe=False):
    """The desktop checks, from the serial entry or, with safe, the "safe
    graphics" entry."""
    label = f"{mode} safe" if safe else mode
    log_path = os.path.join(OUT, f"serial-{mode}{'-safe' if safe else ''}.log")
    pick = functools.partial(pick_edited_entry, SAFE_ENTRY) if safe else pick_serial_entry
    result = boot_and_check(mode, iso, log_path, pick, CHECK_CMD, DESKTOP_TIMEOUT + CMD_TIMEOUT)
    if result is None:
        return False
    boot_secs, output = result
    mode = label

    lines = [line.strip() for line in output.splitlines()]
    results = parse_results(output, skip=("PKG", "LISTEN"))
    packages = [line[4:] for line in lines if line.startswith("PKG=")]
    down = [p for p in DESKTOP_PROCESSES if results.get(f"PROC_{p}") != "up"]
    listening = [line[7:] for line in lines if line.startswith("LISTEN=")]

    print(f"[{mode}] reached login prompt in {boot_secs:.0f}s")
    print(f"[{mode}] PID 1: {results.get('PID1')}")
    print(f"[{mode}] /run/systemd/system: {results.get('RUN_SYSTEMD')}")
    print(f"[{mode}] systemd-named packages: {', '.join(packages) or 'none'}")
    print(f"[{mode}] desktop processes not running: {', '.join(down) or 'none'}")
    print(f"[{mode}] firewall: {results.get('FIREWALL')}")
    print(f"[{mode}] os-release ID: {results.get('OS_ID')}")
    print(f"[{mode}] X seat backend: {results.get('SEAT')}")
    print(f"[{mode}] symbols font: {results.get('SYMBOLS_FONT')}, centred float rules: {results.get('FLOAT_RULES')}, "
          f"ssh AddKeysToAgent: {results.get('SSH_ADDKEYS')}")
    print(f"[{mode}] listening beyond loopback: {', '.join(listening) or 'none'}")
    ok = (results.get("PID1") == "init" and results.get("RUN_SYSTEMD") == "absent" and not down
          and results.get("FIREWALL") == "loaded" and not listening
          and results.get("OS_ID") == "tekne" and results.get("SEAT") == "logind"
          and results.get("SYMBOLS_FONT") == "present" and results.get("FLOAT_RULES") == "3"
          and results.get("SSH_ADDKEYS") == "yes")
    print(f"{'PASS' if ok else 'FAIL'} [{mode}] (serial log: {log_path})")
    return ok


def run_console(mode, iso):
    log_path = os.path.join(OUT, f"serial-{mode}-console.log")
    result = boot_and_check(mode, iso, log_path, functools.partial(pick_edited_entry, CONSOLE_ENTRY),
                            CONSOLE_CHECK_CMD,
                            CONSOLE_TTY1_TIMEOUT + CONSOLE_NO_X_SECS + CMD_TIMEOUT)
    if result is None:
        return False
    results = parse_results(result[1])
    for key in CONSOLE_EXPECTED:
        print(f"[{mode} console] {key}: {results.get(key)}")
    ok = all(results.get(key) == value for key, value in CONSOLE_EXPECTED.items())
    print(f"{'PASS' if ok else 'FAIL'} [{mode} console] (serial log: {log_path})")
    return ok


def main():
    args = sys.argv[1:]
    mode = args.pop(0) if args and args[0] in ("bios", "uefi", "all") else "all"
    if len(args) > 1:
        sys.exit(__doc__)
    iso = os.path.abspath(args[0]) if args else newest_iso()
    if not iso:
        sys.exit("error: no out/tekne-*-amd64.iso; run sudo scripts/build.sh first")
    if not os.path.exists(iso):
        sys.exit(f"error: {iso} not found")

    print(f"Testing {iso}")
    modes = ["bios", "uefi"] if mode == "all" else [mode]
    results = [check(m, iso) for m in modes for check in (run, run_console)]
    # BIOS: nomodeset leaves no framebuffer for X (docs/testing.md).
    if "uefi" in modes:
        results.append(run("uefi", iso, safe=True))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
