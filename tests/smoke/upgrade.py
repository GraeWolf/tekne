#!/usr/bin/env python3
"""Upgrade smoke test: move an installed Tekne to this build through apt.

    tests/smoke/upgrade.py [--keep] [CASE_DIR]

This is how installed systems get Tekne updates (DEC-040, SPEC §8 Phase 9).

With no CASE_DIR, as in CI, it starts from the previous release: the ISO named
in tests/smoke/previous-release is downloaded from GitHub Releases (cached in
out/previous-release/) and must match the SHA-256 pinned there. It's
installed unattended with UEFI and LUKS, as install.py does. With CASE_DIR, it
starts from a case kept by "install.py --keep" instead (any mode).

Then:
  1. Boot the installed system, unlock it and log in over serial.
  2. If it has no Tekne repository source yet (systems installed from 0.1), do
     DEC-040's one-time step: install this build's tekne-apt-sources .deb.
  3. Point /etc/apt/sources.list.d/tekne.sources at out/test-repo/repo, which
     the host serves over HTTP (the VM reaches it at 10.0.2.2), and at the
     build's throwaway test key. Only the URL and the key differ from what
     installed systems use: the pin and the rest of the source are shipped.
  4. apt-get update, then upgrade the way "apt upgrade" does (new
     dependencies allowed), from every source the system has: Devuan,
     backports, Brave and XLibre too.
  5. Check every Tekne package moved to this build's version, that the
     index came from the test repository, and that its decoy base-files
     wasn't installed. Then turn on autologin the way an existing encrypted
     install does (DEC-042): "tekne-autologin on". Power off.
  6. Boot again, since a kernel upgrade takes effect only after a reboot,
     then run install.py's checks with autologin: tty1 starts X with no
     login, the lock screen asks for the password, installed-checks.sh,
     hibernate and resume.

install.py's answers file must stay acceptable to the previous release's
installer, which rejects unknown keys. Needs network access, like the build.
Work files go to out/upgrade-test/ and are deleted after a pass unless --keep
is given (a CASE_DIR is never deleted). Exits non-zero on failure.
"""
import glob
import hashlib
import os
import shutil
import subprocess
import sys
import time
import urllib.request

import install
from qemu_serial import OUT, Serial, qemu_command, serve, start, stop

HERE = os.path.dirname(os.path.abspath(__file__))
PREVIOUS = os.path.join(HERE, "previous-release")
RELEASES_URL = "https://github.com/GraeWolf/tekne/releases/download"
WORK = os.path.join(OUT, "upgrade-test")
TEST_REPO = os.path.join(OUT, "test-repo")
PACKAGES = ["tekne-apt-sources", "tekne-branding", "tekne-config", "tekne-desktop"]
UPGRADE_TIMEOUT = 1800
BEGIN, END = install.BEGIN, install.END

# Run as root in the installed VM (delivered through fw_cfg). @PORT@ and
# @PKGS@ are filled in by guest_script().
GUEST = r"""
set -u
fw=/sys/firmware/qemu_fw_cfg/by_name/opt/tekne
mkdir -p /tmp/up /etc/apt/keyrings
for i in $(seq 60); do ip route | grep -q '^default' && break; sleep 1; done
dpkg-query -W -f 'BEFORE_${Package}=${Version}\n' @PKGS@ 2>/dev/null
# DEC-040's one-time step for systems installed before Tekne's repository.
if [ -f /etc/apt/sources.list.d/tekne.sources ]; then
	echo ONE_TIME=not-needed
else
	cp $fw/apt-sources/raw /tmp/up/tekne-apt-sources.deb
	chmod 644 /tmp/up/tekne-apt-sources.deb
	DEBIAN_FRONTEND=noninteractive apt-get install -y /tmp/up/tekne-apt-sources.deb >/tmp/up/one-time.log 2>&1 \
		&& echo ONE_TIME=done || { echo ONE_TIME=failed; tail -n 20 /tmp/up/one-time.log; }
fi
# The test repository instead of the published one: only URL and key change.
# (fw_cfg files are root-only; apt checks signatures as its _apt user.)
cp $fw/test-key/raw /etc/apt/keyrings/tekne-test.gpg
chmod 644 /etc/apt/keyrings/tekne-test.gpg
sed -i -e 's|^URIs:.*|URIs: http://10.0.2.2:@PORT@/repo/|' \
	-e 's|^Signed-By:.*|Signed-By: /etc/apt/keyrings/tekne-test.gpg|' /etc/apt/sources.list.d/tekne.sources
apt-get update >/tmp/up/update.log 2>&1 && echo APT_UPDATE=ok || { echo APT_UPDATE=failed; tail -n 20 /tmp/up/update.log; }
# apt names list files after the URL: "10.0.2.2:PORT_repo_dists_excalibur_...".
echo "TEKNE_INDEX=$(ls /var/lib/apt/lists/ | grep -cE '^10\.0\.2\.2(:|%3a)[0-9]+_repo_dists_excalibur_')"
DEBIAN_FRONTEND=noninteractive apt-get -y --with-new-pkgs \
	-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold upgrade >/tmp/up/upgrade.log 2>&1 \
	&& echo APT_UPGRADE=ok || { echo APT_UPGRADE=failed; tail -n 30 /tmp/up/upgrade.log; dmesg | tail -n 20; free -m; }
echo "UPGRADED_PACKAGES=$(grep -c '^Setting up ' /tmp/up/upgrade.log)"
dpkg-query -W -f 'AFTER_${Package}=${Version}\n' @PKGS@
echo "BASE_FILES=$(dpkg-query -W -f '${Version}' base-files)"
# DEC-042's step for existing encrypted installs, like the laptop. (A kept
# plain case can't have autologin.) First use the keyring once, as a system in
# daily use has: the password login over serial started its daemon, which
# creates the login keyring from that password on first use (DEC-030).
uid="$(id -u tester)"
sudo -u tester env HOME=/home/tester XDG_RUNTIME_DIR="/run/user/${uid}" dbus-run-session -- sh -c \
	"gnome-keyring-daemon --start --components=secrets >/dev/null 2>&1; dbus-send --session --print-reply \
	--dest=org.freedesktop.secrets /org/freedesktop/secrets/collection/login \
	org.freedesktop.DBus.Properties.Get string:org.freedesktop.Secret.Collection string:Locked" >/dev/null 2>&1
echo "KEYRING_BEFORE=$([ -s /home/tester/.local/share/keyrings/login.keyring ] && echo present || echo missing)"
if lsblk -rno TYPE | grep -q crypt; then
	tekne-autologin on tester >/tmp/up/autologin.log 2>&1 \
		&& echo AUTOLOGIN_ON=ok || { echo AUTOLOGIN_ON=failed; cat /tmp/up/autologin.log; }
else
	echo AUTOLOGIN_ON=plain
fi
"""


def guest_script(port):
    return GUEST.replace("@PORT@", str(port)).replace("@PKGS@", " ".join(PACKAGES))


def deb_field(path, field):
    return subprocess.run(["dpkg-deb", "-f", path, field], capture_output=True,
                          text=True, check=True).stdout.strip()


def version_lt(a, b):
    return subprocess.run(["dpkg", "--compare-versions", a, "lt", b]).returncode == 0


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def previous_release_iso():
    """The previous release's ISO, downloaded once and checked against its pin."""
    pin = {}
    with open(PREVIOUS) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, value = line.strip().split("=", 1)
                pin[key] = value
    tag, name, want = pin["TAG"], pin["ISO"], pin["SHA256"]
    cache = os.path.join(OUT, "previous-release")
    path = os.path.join(cache, name)
    if os.path.exists(path) and sha256(path) == want:
        return tag, path
    os.makedirs(cache, exist_ok=True)
    url = f"{RELEASES_URL}/{tag}/{name}"
    print(f"Downloading {url}")
    with urllib.request.urlopen(url) as response, open(path + ".part", "wb") as f:
        shutil.copyfileobj(response, f, 1 << 20)
    got = sha256(path + ".part")
    if got != want:
        os.remove(path + ".part")
        sys.exit(f"error: {name} has SHA-256 {got}, but {PREVIOUS} pins {want}")
    os.replace(path + ".part", path)
    return tag, path


def upgrade(mode, luks, disk, vars_path, workdir, port):
    """Boot the installed disk, upgrade it through apt, power off; return results."""
    script = os.path.join(workdir, "upgrade.sh")
    with open(script, "w") as f:
        f.write(guest_script(port))
    apt_sources = glob.glob(os.path.join(OUT, "packages", "tekne-apt-sources_*.deb"))[0]
    cmd = qemu_command(mode, vars_path, install.MEMORY_MIB) + [
        "-boot", "c", "-drive", f"file={disk},if=virtio,format=qcow2",
        "-fw_cfg", f"name=opt/tekne/upgrade,file={script}",
        "-fw_cfg", f"name=opt/tekne/test-key,file={os.path.join(TEST_REPO, 'test-key.gpg')}",
        "-fw_cfg", f"name=opt/tekne/apt-sources,file={apt_sources}",
    ]
    user, password = install.ANSWERS["USERNAME"], install.ANSWERS["PASSWORD"]
    run = ("sh -c 'modprobe qemu_fw_cfg; echo __TEKNE\"\"_BEGIN__; "
           "sh /sys/firmware/qemu_fw_cfg/by_name/opt/tekne/upgrade/raw; echo __TEKNE\"\"_END__'")
    with open(os.path.join(workdir, "serial-upgrade.log"), "w") as log:
        proc = start(cmd)
        con = Serial(proc, log)
        try:
            if luks:
                con.expect("unlock disk", install.BOOT_TIMEOUT)
                con.send(install.ANSWERS["LUKS_PASSPHRASE"] + "\n")
            con.expect("login:", install.BOOT_TIMEOUT)
            con.send(user + "\n")
            con.expect("assword:", install.CMD_TIMEOUT)
            con.send(password + "\n")
            con.expect("$ ", install.CMD_TIMEOUT)
            con.send(f"echo {password} | sudo -S -p '' {run}\n")
            con.expect(BEGIN, install.CMD_TIMEOUT)
            output = con.expect(END, UPGRADE_TIMEOUT)
            con.expect("$ ", install.CMD_TIMEOUT)
            con.send(f"echo {password} | sudo -S -p '' poweroff\n")
            stop(proc, install.CMD_TIMEOUT)
        finally:
            if proc.poll() is None:
                proc.kill()
    return output, dict(line.strip().split("=", 1) for line in output.splitlines()
                        if "=" in line and line.strip()[:1].isupper())


def main():
    args = sys.argv[1:]
    keep = "--keep" in args
    args = [a for a in args if a != "--keep"]
    if len(args) > 1 or (args and args[0].startswith("-")):
        sys.exit(__doc__)

    debs = {p: glob.glob(os.path.join(OUT, "packages", f"{p}_*_all.deb")) for p in PACKAGES}
    if not all(len(d) == 1 for d in debs.values()) or not os.path.isdir(os.path.join(TEST_REPO, "repo")):
        sys.exit("error: needs this build's out/packages/ and out/test-repo/; run sudo scripts/build.sh first")
    new = {p: deb_field(d[0], "Version") for p, d in debs.items()}

    started = time.monotonic()
    if args:
        workdir = os.path.abspath(args[0])
        name = os.path.basename(workdir)
        mode, _, enc = name.partition("-")
        luks = enc == "luks"
        disk = os.path.join(workdir, "disk.qcow2")
        vars_path = os.path.join(workdir, "OVMF_VARS.fd") if mode == "uefi" else None
        if mode not in ("bios", "uefi") or not os.path.exists(disk):
            sys.exit(f"error: {workdir} isn't a kept install.py case (e.g. out/install-test/uefi-luks)")
        print(f"Upgrading the kept case {workdir} to {new['tekne-config']}")
    else:
        tag, iso = previous_release_iso()
        mode, luks = "uefi", True
        name = f"from-{tag}-{mode}-luks"
        workdir = os.path.join(WORK, name)
        disk, vars_path, answers_path = install.new_case(workdir, mode, luks)
        print(f"Installing {os.path.basename(iso)} ({tag}), then upgrading it to {new['tekne-config']}")
        try:
            install.install(mode, luks, iso, disk, vars_path, answers_path, workdir)
        except (TimeoutError, RuntimeError) as err:
            print(f"FAIL [upgrade {name}]: installing {tag}: {err}. Logs in {workdir}")
            return 1
    installed = time.monotonic()

    server = serve(TEST_REPO)
    try:
        output, results = upgrade(mode, luks, disk, vars_path, workdir, server.server_address[1])
    except (TimeoutError, RuntimeError) as err:
        print(f"FAIL [upgrade {name}]: {err}. Logs in {workdir}")
        return 1
    finally:
        server.shutdown()
    upgraded = time.monotonic()

    problems = []
    for key, want in [("APT_UPDATE", "ok"), ("APT_UPGRADE", "ok"), ("KEYRING_BEFORE", "present"),
                      ("AUTOLOGIN_ON", "ok" if luks else "plain")]:
        if results.get(key) != want:
            problems.append(f"{key}: {results.get(key)!r}")
    if results.get("ONE_TIME") not in ("done", "not-needed"):
        problems.append(f"the one-time step failed: {results.get('ONE_TIME')!r}")
    if results.get("TEKNE_INDEX", "0") == "0":
        problems.append("no index was fetched from the test repository")
    if results.get("BASE_FILES", "").startswith("99:"):
        problems.append("the test repository's decoy base-files was installed")
    for pkg, version in new.items():
        before, after = results.get(f"BEFORE_{pkg}"), results.get(f"AFTER_{pkg}")
        print(f"[upgrade {name}] {pkg}: {before} -> {after}")
        if after != version:
            problems.append(f"{pkg} is {after}, want {version}")
        elif before and not version_lt(before, after):
            problems.append(f"{pkg} didn't move to a higher version ({before} -> {after})")
    print(f"[upgrade {name}] one-time step: {results.get('ONE_TIME')}; "
          f"packages set up by the upgrade: {results.get('UPGRADED_PACKAGES')}")

    # Reboot into the upgraded system, then the full installed-system checks.
    if not problems:
        try:
            checks = install.boot_and_check(mode, luks, disk, vars_path, workdir, autologin=luks)
        except (TimeoutError, RuntimeError) as err:
            problems.append(f"after the upgrade: {err}")
            checks = {}
        want = install.expected(mode, luks, upgraded=True, autologin=luks)
        problems += [f"{k}: got {checks.get(k)!r}, want {v!r}" for k, v in want.items()
                     if checks and checks.get(k) != v]

    for problem in problems:
        print(f"[upgrade {name}]   {problem}")
    ok = not problems
    print(f"[upgrade {name}] installed in {installed - started:.0f}s, upgraded in {upgraded - installed:.0f}s, "
          f"rebooted, checked, hibernated and resumed in {time.monotonic() - upgraded:.0f}s")
    print(f"{'PASS' if ok else 'FAIL'} [upgrade {name}] (logs: {workdir})")
    if not ok and problems and "APT" in " ".join(problems):
        print(output)
    if ok and not keep and not args:
        shutil.rmtree(workdir, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
