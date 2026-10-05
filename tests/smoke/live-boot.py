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
seat from elogind (DEC-045). Serial logs are
written to out/serial-<mode>.log. Exits non-zero if any mode fails.
"""
import os
import sys
import tempfile
import time

from qemu_serial import (OUT, SERIAL_ENTRY_HOTKEY, SERIAL_ENTRY_TITLE, Serial,
                         newest_iso, qemu_command, start, stop, uefi_vars)

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
    'sudo nft list chain inet tekne input 2>/dev/null | grep -q "policy drop" && echo FIREWALL=loaded || echo FIREWALL=missing; '
    "sudo ss -H -tuln | awk '{print $5}' | grep -v -E '^(127\\.|\\[::1\\]|\\[::ffff:127\\.)' | sed 's/^/LISTEN=/'; "
    'echo __TEKNE""_END__\n'
)


def run(mode, iso):
    log_path = os.path.join(OUT, f"serial-{mode}.log")
    with tempfile.TemporaryDirectory() as tmp, open(log_path, "w") as log:
        vars_path = uefi_vars(os.path.join(tmp, "OVMF_VARS.fd")) if mode == "uefi" else None
        proc = start(qemu_command(mode, vars_path) + ["-cdrom", iso, "-boot", "d"])
        con = Serial(proc, log)
        started = time.monotonic()
        try:
            con.expect(SERIAL_ENTRY_TITLE, MENU_TIMEOUT)
            con.send(SERIAL_ENTRY_HOTKEY)
            con.expect("login:", BOOT_TIMEOUT)
            boot_secs = time.monotonic() - started
            con.send(LIVE_USER + "\n")
            con.expect("assword:", CMD_TIMEOUT)
            con.send(LIVE_PASSWORD + "\n")
            con.expect("$ ", CMD_TIMEOUT)
            con.send(CHECK_CMD)
            con.expect(BEGIN, CMD_TIMEOUT)
            output = con.expect(END, DESKTOP_TIMEOUT + CMD_TIMEOUT)
            con.send("sudo poweroff\n")
            stop(proc, CMD_TIMEOUT)
        except (TimeoutError, RuntimeError) as err:
            print(f"FAIL [{mode}]: {err}. Serial log: {log_path}")
            return False
        finally:
            if proc.poll() is None:
                proc.kill()

    lines = [line.strip() for line in output.splitlines()]
    results = dict(line.split("=", 1) for line in lines
                   if "=" in line and not line.startswith(("PKG=", "LISTEN=")))
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
    print(f"[{mode}] listening beyond loopback: {', '.join(listening) or 'none'}")
    ok = (results.get("PID1") == "init" and results.get("RUN_SYSTEMD") == "absent" and not down
          and results.get("FIREWALL") == "loaded" and not listening
          and results.get("OS_ID") == "tekne" and results.get("SEAT") == "logind")
    print(f"{'PASS' if ok else 'FAIL'} [{mode}] (serial log: {log_path})")
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
    results = [run(m, iso) for m in modes]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
