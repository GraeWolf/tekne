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
  3. Hibernate (DEC-017): write a random token to /dev/shm (RAM only), run
     "loginctl hibernate", start the VM again from the same disk, and check
     the same shell session still has the token. A cold boot would lose both.
  4. Compare the results with what the answers file asked for.

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
                         newest_iso, qemu_command, start, stop, uefi_vars)

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKS = os.path.join(HERE, "installed-checks.sh")
WORK = os.path.join(OUT, "install-test")

MEMORY_MIB = 2048          # the swapfile is sized to RAM: 2 GiB
DISK_SIZE = "24G"          # installer minimum: 20 GiB + swapfile
INSTALL_TIMEOUT = 2400
HIBERNATE_TIMEOUT = 180
BOOT_TIMEOUT = 300
CMD_TIMEOUT = 120

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


def expected(mode, luks, upgraded=False):
    # upgrade.py's user was made by the previous release, before /etc/skel had
    # .bash_aliases and before the installer made XDG directories.
    per_user = ({"XDG_DIRS": "missing", "CAT_ALIAS": "none", "FASTFETCH_LOGO": "none"} if upgraded
                else {"XDG_DIRS": "present", "CAT_ALIAS": "batcat", "FASTFETCH_LOGO": "tekne"})
    return per_user | {
        "PID1": "init", "RUN_SYSTEMD": "absent", "SYSTEMD_PKGS": "0",
        "LIVE_PKGS": "0", "LIVE_FILES": "0", "AUTOLOGIN": "0",
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


def boot_and_check(mode, luks, disk, vars_path, workdir):
    log_path = os.path.join(workdir, "serial-boot.log")
    cmd = qemu_command(mode, vars_path, MEMORY_MIB) + [
        "-boot", "c",
        "-drive", f"file={disk},if=virtio,format=qcow2",
        "-fw_cfg", f"name=opt/tekne/check,file={CHECKS}",
    ]
    user, password = ANSWERS["USERNAME"], ANSWERS["PASSWORD"]
    check = ("sh -c 'modprobe qemu_fw_cfg; echo __TEKNE\"\"_BEGIN__; "
             "sh /sys/firmware/qemu_fw_cfg/by_name/opt/tekne/check/raw; echo __TEKNE\"\"_END__'")
    with open(log_path, "w") as log:
        proc = start(cmd)
        con = Serial(proc, log)
        try:
            if luks:
                con.expect("unlock disk", BOOT_TIMEOUT)
                con.send(ANSWERS["LUKS_PASSPHRASE"] + "\n")
            con.expect("login:", BOOT_TIMEOUT)
            con.send(user + "\n")
            con.expect("assword:", CMD_TIMEOUT)
            con.send(password + "\n")
            con.expect("$ ", CMD_TIMEOUT)
            # The user can sudo (with their password) and the checks run as root.
            con.send(f"echo {password} | sudo -S -p '' {check}\n")
            con.expect(BEGIN, CMD_TIMEOUT)
            output = con.expect(END, CMD_TIMEOUT)
            con.expect("$ ", CMD_TIMEOUT)
            results = dict(line.strip().split("=", 1) for line in output.splitlines() if "=" in line)

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
        proc = start(cmd)
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


def new_case(workdir, mode, luks):
    """A fresh work directory with a blank disk, UEFI variables (UEFI only)
    and the answers file. Returns (disk, vars_path, answers_path)."""
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
    return disk, vars_path, answers_path


def run_case(mode, luks, iso, keep):
    name = f"{mode}-{'luks' if luks else 'plain'}"
    workdir = os.path.join(WORK, name)
    disk, vars_path, answers_path = new_case(workdir, mode, luks)

    started = time.monotonic()
    try:
        install(mode, luks, iso, disk, vars_path, answers_path, workdir)
        installed = time.monotonic()
        results = boot_and_check(mode, luks, disk, vars_path, workdir)
    except (TimeoutError, RuntimeError) as err:
        print(f"FAIL [{name}]: {err}. Logs in {workdir}")
        return False

    want = expected(mode, luks)
    problems = [f"{k}: got {results.get(k)!r}, want {v!r}" for k, v in want.items() if results.get(k) != v]
    if not results.get("SWAP_OFFSET") or results.get("SWAP_OFFSET") != results.get("CMDLINE_OFFSET"):
        problems.append(f"resume_offset on the kernel command line ({results.get('CMDLINE_OFFSET')}) "
                        f"doesn't match the swapfile ({results.get('SWAP_OFFSET')})")
    if results.get("CMDLINE_RESUME") != results.get("ROOT_UUID"):
        problems.append(f"resume=UUID={results.get('CMDLINE_RESUME')} isn't the root filesystem ({results.get('ROOT_UUID')})")
    if "sudo" not in results.get("USER_GROUPS", "").split(","):
        problems.append(f"user isn't in the sudo group ({results.get('USER_GROUPS')})")

    print(f"[{name}] installed in {installed - started:.0f}s; booted, checked, hibernated and resumed in {time.monotonic() - installed:.0f}s")
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
