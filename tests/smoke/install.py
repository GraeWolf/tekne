#!/usr/bin/env python3
"""Install smoke test: unattended installs in QEMU, then boot and check each one.

    tests/smoke/install.py [bios|uefi|all] [plain|luks|all] [--keep] [ISO]

Defaults to the full matrix, {BIOS, UEFI} x {plain, LUKS}, and the newest
out/tekne-*-amd64.iso (SPEC.md §5.2, docs/installer.md §6). For each case:

  1. Boot the ISO with a blank virtual disk. Press "s" for the serial-console
     GRUB entry and pass an answers file through QEMU fw_cfg: together these
     make the live system run tekne-install unattended, then power off.
  2. Boot the installed disk, type the LUKS passphrase if needed, log in over
     serial, and run installed-checks.sh (also passed via fw_cfg) as root.
     The LUKS cases ask the installer for autologin (DEC-042): tty1 must then
     start the X session with no login, while the serial console, which never
     logs in automatically, still asks for the password. They also lock the
     X session and type a wrong, then the right password on the VM's keyboard
     (QEMU's monitor): the lock screen must still ask for the password.
  3. Hibernate (DEC-017): write a random token to /dev/shm (RAM only), run
     "loginctl hibernate", start the VM again from the same disk, and check
     the same shell session still has the token. A cold boot would lose both.
     In the LUKS cases, X is running on tty1 while it hibernates.
  4. uefi-luks only: break X on purpose (a missing driver) and reboot. tty1
     must try X at most twice, then stay on a console shell, and logging that
     shell out mustn't start X again. tty2 must still offer a normal login.
  5. Compare the results with what the answers file asked for.

Everything runs in virtual machines; nothing touches the host's disks. Work
files go to out/install-test/<case>/ and are deleted after a pass unless
--keep is given. Exits non-zero if any case fails.
"""
import os
import secrets
import shutil
import subprocess
import sys
import time

from qemu_serial import (OUT, SERIAL_ENTRY_HOTKEY, SERIAL_ENTRY_TITLE, Serial,
                         newest_iso, qemu_command, sendkeys, start, stop, uefi_vars)

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKS = os.path.join(HERE, "installed-checks.sh")
WORK = os.path.join(OUT, "install-test")

MEMORY_MIB = 2048          # the swapfile is sized to RAM: 2 GiB
DISK_SIZE = "24G"          # installer minimum: 20 GiB + swapfile
INSTALL_TIMEOUT = 2400
HIBERNATE_TIMEOUT = 180
BOOT_TIMEOUT = 300
CMD_TIMEOUT = 120
X_TIMEOUT = 180            # tty1's autologin to a running X session

ANSWERS = {
    "DISK": "/dev/vda",
    "CONFIRM_DISK": "vda",
    "HOSTNAME": "tekne-test",
    "TZ": "Europe/Berlin",
    "LOCALE": "en_GB.UTF-8",
    "KEYMAP": "gb",
    "FULLNAME": "Test User",
    "USERNAME": "tester",
    "PASSWORD": "tester-pw-123",
    "LUKS_PASSPHRASE": "tekne-test-luks",
    "SERIAL_CONSOLE": "yes",
}

BEGIN, END = "__TEKNE" + "_BEGIN__", "__TEKNE" + "_END__"


def expected(mode, luks, upgraded=False, autologin=False):
    # upgrade.py's user was made by the previous release, before /etc/skel had
    # .bash_aliases and before the installer made XDG directories. With
    # autologin, tekne-session's first X login creates the directories.
    per_user = ({"XDG_DIRS": "present" if autologin else "missing", "CAT_ALIAS": "none", "FASTFETCH_LOGO": "none"}
                if upgraded else {"XDG_DIRS": "present", "CAT_ALIAS": "batcat", "FASTFETCH_LOGO": "tekne"})
    # DEC-042. The login keyring must exist before the boot's password login:
    # the installer made it (or, after an upgrade, the system's earlier use did).
    auto = ({"TTY1_X": "running", "SEAT_LOG": "logind", "LOCK_SCREEN": "asks for the password",
             "KEYRING_CREATED": "before-boot"} if autologin
            else {"TTY1_X": "none", "SEAT_LOG": "none"})
    return per_user | auto | {
        "PID1": "init", "RUN_SYSTEMD": "absent", "SYSTEMD_PKGS": "0",
        "LIVE_PKGS": "0", "LIVE_FILES": "0",
        "AUTOLOGIN": f"on {ANSWERS['USERNAME']}" if autologin else "off", "AUTOLOGIN_OTHER_TTYS": "0",
        "AUTOLOGIN_CMD": "roundtrip" if luks else "refused",
        "ROOT_FS": "ext4", "BOOT_FS": "ext4", "EFI_FS": "vfat" if mode == "uefi" else "none",
        "CRYPT": "1" if luks else "0",
        "SWAP_ACTIVE": "1", "SWAP_GIB": str(MEMORY_MIB // 1024),
        "HOSTNAME": ANSWERS["HOSTNAME"], "TIMEZONE": ANSWERS["TZ"],
        "LANG": ANSWERS["LOCALE"], "KEYMAP": ANSWERS["KEYMAP"],
        "ROOT_PASSWORD": "L", "FIREWALL": "loaded",
        "OS_ID": "tekne", "GRUB_THEME": "present", "KERNEL": "backports", "TEKNE_REPO": "configured",
        "GRUB_PKG": "grub-efi-amd64" if mode == "uefi" else "grub-pc",
        "HIBERNATE": "resumed",
        "KEYRING_DAEMON": "running", "LOGIN_KEYRING": "unlocked", "PAM_ORDER": "ok",
        "SEAT_BACKEND": "logind", "ASUS_KBD_HOOK": "idle", "TLP_SLEEP_HOOK": "linked",
    }


def install(mode, luks, iso, disk, vars_path, answers_path, workdir):
    log_path = os.path.join(workdir, "serial-install.log")
    cmd = qemu_command(mode, vars_path, MEMORY_MIB, cpus=4) + [
        "-cdrom", iso, "-boot", "d",
        "-drive", f"file={disk},if=virtio,format=qcow2",
        "-fw_cfg", f"name=opt/tekne/answers,file={answers_path}",
    ]
    with open(log_path, "w") as log:
        proc = start(cmd)
        con = Serial(proc, log)
        try:
            con.expect(SERIAL_ENTRY_TITLE, 60)
            con.send(SERIAL_ENTRY_HOTKEY)
            result = con.expect_any(["TEKNE-INSTALL: SUCCESS", "TEKNE-INSTALL: FAILED"], INSTALL_TIMEOUT)
            stop(proc, 120)
        finally:
            if proc.poll() is None:
                proc.kill()
    if result.endswith("FAILED"):
        raise RuntimeError(f"installer reported failure; see {log_path}")


def serial_login(con, luks):
    """Unlock the disk if needed and log in on the serial console's getty,
    which never logs in automatically, so PAM gets the password (DEC-030)."""
    if luks:
        con.expect("unlock disk", BOOT_TIMEOUT)
        con.send(ANSWERS["LUKS_PASSPHRASE"] + "\n")
    con.expect("login:", BOOT_TIMEOUT)
    con.send(ANSWERS["USERNAME"] + "\n")
    con.expect("assword:", CMD_TIMEOUT)
    con.send(ANSWERS["PASSWORD"] + "\n")
    con.expect("$ ", CMD_TIMEOUT)


def run_as_root(con, name, timeout=CMD_TIMEOUT):
    """Run the script passed through fw_cfg as opt/tekne/NAME as root (the
    user can sudo with their password); return its KEY=VALUE lines."""
    password = ANSWERS["PASSWORD"]
    script = (f"sh -c 'modprobe qemu_fw_cfg; echo __TEKNE\"\"_BEGIN__; "
              f"sh /sys/firmware/qemu_fw_cfg/by_name/opt/tekne/{name}/raw; echo __TEKNE\"\"_END__'")
    con.send(f"echo {password} | sudo -S -p '' {script}\n")
    con.expect(BEGIN, CMD_TIMEOUT)
    output = con.expect(END, timeout)
    con.expect("$ ", CMD_TIMEOUT)
    return dict(line.strip().split("=", 1) for line in output.splitlines() if "=" in line)


def shell_flag(con, command, name, timeout=CMD_TIMEOUT):
    """Run a shell test on the serial console; True if it succeeded."""
    con.send(f"if {command}; then echo {name}\"\"=yes; else echo {name}\"\"=no; fi\n")
    seen = con.expect_any([f"{name}=yes", f"{name}=no"], timeout)
    con.expect("$ ", CMD_TIMEOUT)
    return seen.endswith("yes")


def lock_screen(con, monitor):
    """DEC-042: autologin skips only the first login. Lock tty1's X session the
    way suspend does (xss-lock runs i3lock), type a wrong password on the VM's
    keyboard, then the right one; only the right one may unlock it."""
    password = ANSWERS["PASSWORD"]
    locked = "pgrep -u tester -x i3lock >/dev/null"
    # xss-lock's process appears before it has subscribed to elogind's signals.
    con.send(f"sleep 5; echo {password} | sudo -S -p '' loginctl lock-sessions\n")
    con.expect("$ ", CMD_TIMEOUT)
    if not shell_flag(con, f"for i in $(seq 20); do {locked} && break; sleep 1; done; {locked}", "LOCKED"):
        return "didn't lock"
    sendkeys(monitor, "wrong-password\n")
    # login's PAM stack, which i3lock uses, waits 3 s after a failure.
    if not shell_flag(con, f"sleep 6; {locked}", "STILL_LOCKED"):
        return "a wrong password unlocked it"
    sendkeys(monitor, password + "\n")
    if not shell_flag(con, f"for i in $(seq 15); do {locked} || break; sleep 1; done; ! {locked}", "UNLOCKED"):
        return "the right password didn't unlock it"
    return "asks for the password"


def start_vm(cmd, monitor=None):
    """Start QEMU, first removing the monitor socket a previous run left."""
    if monitor and os.path.exists(monitor):
        os.remove(monitor)
    return start(cmd)


def boot_and_check(mode, luks, disk, vars_path, workdir, autologin=False):
    log_path = os.path.join(workdir, "serial-boot.log")
    monitor = os.path.join(workdir, "monitor.sock") if autologin else None
    cmd = qemu_command(mode, vars_path, MEMORY_MIB, monitor=monitor) + [
        "-boot", "c",
        "-drive", f"file={disk},if=virtio,format=qcow2",
        "-fw_cfg", f"name=opt/tekne/check,file={CHECKS}",
    ]
    password = ANSWERS["PASSWORD"]
    with open(log_path, "w") as log:
        proc = start_vm(cmd, monitor)
        con = Serial(proc, log)
        try:
            serial_login(con, luks)
            if autologin and not shell_flag(
                    con, f"for i in $(seq {X_TIMEOUT}); do pgrep -u tester -x xss-lock >/dev/null && break; "
                         f"sleep 1; done; pgrep -u tester -x xss-lock >/dev/null", "X_READY", X_TIMEOUT + 30):
                raise TimeoutError(f"tty1's autologin didn't start the X session within {X_TIMEOUT}s")
            results = run_as_root(con, "check")
            if autologin:
                results["LOCK_SCREEN"] = lock_screen(con, monitor)

            # Hibernate: the VM powers itself off once the image is written.
            token = secrets.token_hex(8)
            con.send(f"echo {token} > /dev/shm/tekne-hibernate-test; "
                     f"echo {password} | sudo -S -p '' loginctl hibernate\n")
            try:
                proc.wait(timeout=HIBERNATE_TIMEOUT)
            except subprocess.TimeoutExpired:
                results["HIBERNATE"] = "didn't power off"
                con.send(f"echo {password} | sudo -S -p '' poweroff\n")
                stop(proc, CMD_TIMEOUT)
                return results
        finally:
            if proc.poll() is None:
                proc.kill()

    # Resume: same disk and UEFI variables; the LUKS prompt comes first.
    with open(os.path.join(workdir, "serial-resume.log"), "w") as log:
        proc = start_vm(cmd, monitor)
        con = Serial(proc, log)
        try:
            if luks:
                con.expect("unlock disk", BOOT_TIMEOUT)
                con.send(ANSWERS["LUKS_PASSPHRASE"] + "\n")
            # Resuming restores the logged-in shell; a cold boot shows "login:".
            # Keystrokes typed while the console is still being restored get
            # lost, so press Enter until a prompt answers before typing.
            deadline = time.monotonic() + BOOT_TIMEOUT
            seen = None
            while seen is None:
                if time.monotonic() > deadline:
                    raise TimeoutError(f"no shell or login prompt {BOOT_TIMEOUT}s after resume started")
                con.send("\n")
                try:
                    seen = con.expect_any(["$ ", "login:"], 5)
                except TimeoutError:
                    pass
            if seen == "$ ":
                con.expect("$ ", CMD_TIMEOUT)
                con.send("cat /dev/shm/tekne-hibernate-test\n")
                seen = con.expect_any([token, "login:", "No such file"], CMD_TIMEOUT)
            results["HIBERNATE"] = "resumed" if seen == token else "cold boot (resume failed)"
            if seen == token:
                con.send(f"echo {password} | sudo -S -p '' poweroff\n")
            stop(proc, CMD_TIMEOUT)
        finally:
            if proc.poll() is None:
                proc.kill()
    return results


# Test only: count tty1's X starts, and break X with a driver that doesn't
# exist. The ~/.xserverrc starts X the way startx otherwise would.
BROKEN_X_SETUP = r"""
set -u
cat > /home/tester/.xserverrc <<'EOF'
#!/bin/sh
date +%s >> "$HOME/.xstarts"
exec /usr/bin/X -nolisten tcp "$@"
EOF
chown tester: /home/tester/.xserverrc
chmod 755 /home/tester/.xserverrc
rm -f /home/tester/.xstarts
mkdir -p /etc/X11/xorg.conf.d
cat > /etc/X11/xorg.conf.d/99-tekne-test-broken.conf <<'EOF'
Section "Device"
	Identifier "tekne-test-broken"
	Driver "tekne-test-nonexistent"
EndSection
EOF
echo BROKEN_X=set
"""

# After a reboot with X broken: tty1 gave up on X, logging it out doesn't
# start X again, and tty2 still offers a normal login (DEC-042).
BROKEN_X_CHECK = r"""
set -u
boot="$(cat /proc/sys/kernel/random/boot_id)"
marker=/home/tester/.cache/tekne/startx-failed
for i in $(seq 120); do [ "$(cat "${marker}" 2>/dev/null)" = "${boot}" ] && break; sleep 1; done
echo "MARKER=$([ "$(cat "${marker}" 2>/dev/null)" = "${boot}" ] && echo this-boot || echo missing)"
sleep 5
echo "X_STARTS=$(cat /home/tester/.xstarts 2>/dev/null | wc -l)"
shell="$(pgrep -u tester -t tty1 -x bash | head -n 1)"
echo "TTY1=$([ -n "${shell}" ] && ! pgrep -u tester -x Xorg >/dev/null && echo console || echo other)"
# Log tty1 out: getty respawns, autologin logs in again, and the marker must
# keep X from starting.
[ -n "${shell}" ] && kill -KILL "${shell}"
new=""
for i in $(seq 30); do
	new="$(pgrep -u tester -t tty1 -x bash | head -n 1)"
	[ -n "${new}" ] && [ "${new}" != "${shell}" ] && break
	sleep 1
done
sleep 10
echo "RELOGIN=$([ -n "${new}" ] && [ "${new}" != "${shell}" ] && echo yes || echo no)"
echo "X_STARTS_AFTER=$(cat /home/tester/.xstarts 2>/dev/null | wc -l)"
echo "TTY2=$(ps -o args= -t tty2 | grep getty | grep -qv -- --autologin && echo login || echo other)"
"""


def broken_x(mode, disk, vars_path, workdir):
    """Step 4: set up a broken X, reboot, and check tty1 doesn't loop. Returns
    a list of problems."""
    setup = os.path.join(workdir, "broken-x-setup.sh")
    check = os.path.join(workdir, "broken-x-check.sh")
    with open(setup, "w") as f:
        f.write(BROKEN_X_SETUP)
    with open(check, "w") as f:
        f.write(BROKEN_X_CHECK)
    cmd = qemu_command(mode, vars_path, MEMORY_MIB) + [
        "-boot", "c", "-drive", f"file={disk},if=virtio,format=qcow2",
        "-fw_cfg", f"name=opt/tekne/broken-x-setup,file={setup}",
        "-fw_cfg", f"name=opt/tekne/broken-x-check,file={check}",
    ]
    password = ANSWERS["PASSWORD"]
    results = {}
    for step, name in [("setup", "broken-x-setup"), ("check", "broken-x-check")]:
        with open(os.path.join(workdir, f"serial-broken-x-{step}.log"), "w") as log:
            proc = start(cmd)
            con = Serial(proc, log)
            try:
                serial_login(con, luks=True)
                results |= run_as_root(con, name, timeout=BOOT_TIMEOUT)
                con.send(f"echo {password} | sudo -S -p '' poweroff\n")
                stop(proc, CMD_TIMEOUT)
            finally:
                if proc.poll() is None:
                    proc.kill()

    problems = []
    if results.get("BROKEN_X") != "set":
        problems.append(f"broken X: setup failed ({results.get('BROKEN_X')!r})")
    starts = results.get("X_STARTS", "")
    if not starts.isdigit() or not 1 <= int(starts) <= 2:
        problems.append(f"broken X: tty1 started X {starts!r} times, want 1 or 2")
    for key, want in [("MARKER", "this-boot"), ("TTY1", "console"), ("RELOGIN", "yes"),
                      ("X_STARTS_AFTER", starts), ("TTY2", "login")]:
        if results.get(key) != want:
            problems.append(f"broken X: {key}: got {results.get(key)!r}, want {want!r}")
    print(f"[{mode}-luks] broken X: tty1 started X {starts} time(s), then stayed on a console shell"
          if not problems else f"[{mode}-luks] broken X: {results}")
    return problems


def new_case(workdir, mode, luks, autologin=False):
    """A fresh work directory with a blank disk, UEFI variables (UEFI only)
    and the answers file. Returns (disk, vars_path, answers_path). AUTOLOGIN
    is written only when asked for: previous releases' installers, which
    upgrade.py uses, reject keys they don't know."""
    shutil.rmtree(workdir, ignore_errors=True)
    os.makedirs(workdir)
    disk = os.path.join(workdir, "disk.qcow2")
    subprocess.run(["qemu-img", "create", "-q", "-f", "qcow2", disk, DISK_SIZE], check=True)
    vars_path = uefi_vars(os.path.join(workdir, "OVMF_VARS.fd")) if mode == "uefi" else None
    answers_path = os.path.join(workdir, "answers")
    with open(answers_path, "w") as f:
        for key, value in ANSWERS.items():
            f.write(f"{key}={value}\n")
        f.write(f"ENCRYPT={'yes' if luks else 'no'}\n")
        if autologin:
            f.write("AUTOLOGIN=yes\n")
    return disk, vars_path, answers_path


def run_case(mode, luks, iso, keep):
    name = f"{mode}-{'luks' if luks else 'plain'}"
    workdir = os.path.join(WORK, name)
    # The LUKS cases ask for autologin (DEC-042); plain installs can't have it.
    autologin = luks
    disk, vars_path, answers_path = new_case(workdir, mode, luks, autologin)

    started = time.monotonic()
    try:
        install(mode, luks, iso, disk, vars_path, answers_path, workdir)
        installed = time.monotonic()
        results = boot_and_check(mode, luks, disk, vars_path, workdir, autologin)
        checked = time.monotonic()
        # Firmware doesn't matter to the restart-loop guard, so one case is enough.
        broken = broken_x(mode, disk, vars_path, workdir) if name == "uefi-luks" else []
    except (TimeoutError, RuntimeError) as err:
        print(f"FAIL [{name}]: {err}. Logs in {workdir}")
        return False

    want = expected(mode, luks, autologin=autologin)
    problems = [f"{k}: got {results.get(k)!r}, want {v!r}" for k, v in want.items() if results.get(k) != v]
    if not results.get("SWAP_OFFSET") or results.get("SWAP_OFFSET") != results.get("CMDLINE_OFFSET"):
        problems.append(f"resume_offset on the kernel command line ({results.get('CMDLINE_OFFSET')}) "
                        f"doesn't match the swapfile ({results.get('SWAP_OFFSET')})")
    if results.get("CMDLINE_RESUME") != results.get("ROOT_UUID"):
        problems.append(f"resume=UUID={results.get('CMDLINE_RESUME')} isn't the root filesystem ({results.get('ROOT_UUID')})")
    if "sudo" not in results.get("USER_GROUPS", "").split(","):
        problems.append(f"user isn't in the sudo group ({results.get('USER_GROUPS')})")
    problems += broken

    print(f"[{name}] installed in {installed - started:.0f}s; booted, checked, hibernated and resumed in {checked - installed:.0f}s"
          + (f"; broken X checked in {time.monotonic() - checked:.0f}s" if name == "uefi-luks" else ""))
    for problem in problems:
        print(f"[{name}]   {problem}")
    ok = not problems
    print(f"{'PASS' if ok else 'FAIL'} [{name}] (logs: {workdir})")
    if ok and not keep:
        shutil.rmtree(workdir, ignore_errors=True)
    return ok


def main():
    args = sys.argv[1:]
    keep = "--keep" in args
    args = [a for a in args if a != "--keep"]
    mode = args.pop(0) if args and args[0] in ("bios", "uefi", "all") else "all"
    enc = args.pop(0) if args and args[0] in ("plain", "luks", "all") else "all"
    if len(args) > 1:
        sys.exit(__doc__)
    iso = os.path.abspath(args[0]) if args else newest_iso()
    if not iso or not os.path.exists(iso):
        sys.exit("error: no ISO found; run sudo scripts/build.sh first")

    modes = ["bios", "uefi"] if mode == "all" else [mode]
    encs = [False, True] if enc == "all" else [enc == "luks"]
    print(f"Testing {iso}")
    results = [run_case(m, e, iso, keep) for m in modes for e in encs]
    print(f"{sum(results)}/{len(results)} install cases passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
