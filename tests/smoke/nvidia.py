#!/usr/bin/env python3
"""NVIDIA packages smoke test: tekne-nvidia-repo and tekne-nvidia (DEC-041).

    tests/smoke/nvidia.py [--keep] [ISO]

SPEC §9 Phase 13. The VM has no NVIDIA GPU, so this checks that the opt-in
packages install, leave a working system and purge cleanly. The driver itself
is checked on real hardware (docs/testing.md).

  1. Install the ISO (default: the newest out/tekne-*-amd64.iso) unattended,
     with UEFI and LUKS, as install.py does.
  2. Boot, log in over serial, and point Tekne's repository source at this
     build's test repository (out/test-repo/, served by the host), as
     upgrade.py does. Install tekne-nvidia-repo, run apt-get update, which
     reaches NVIDIA's repository over the network, and install tekne-nvidia
     the way docs/customizing.md says. Check that the driver came from NVIDIA's
     repository, that DKMS built the module for the running kernel, that
     nvidia-persistenced wasn't installed, and that no systemd package was.
  3. Reboot and run install.py's checks: installed-checks.sh (which also
     checks there's no systemd package), hibernate and resume.
  4. Remove it the documented way (tekne-nvidia-remove) and check nothing of
     the driver is left: no NVIDIA package, no NVIDIA source, no nouveau
     blacklist. A plain "apt purge --autoremove" isn't enough (see the script).
  5. Reboot and run install.py's checks again.

Needs network access, like the build. Work files go to out/nvidia-test/ and
are deleted after a pass unless --keep is given. Exits non-zero on failure.
"""
import glob
import os
import shutil
import sys
import time

import install
from qemu_serial import OUT, Serial, newest_iso, qemu_command, serve, start, stop

WORK = os.path.join(OUT, "nvidia-test")
TEST_REPO = os.path.join(OUT, "test-repo")
GUEST_TIMEOUT = 2700   # downloads about 400 MB and builds the module in the VM
BEGIN, END = install.BEGIN, install.END

# Run as root in the installed VM (delivered through fw_cfg).
INSTALL_GUEST = r"""
set -u
fw=/sys/firmware/qemu_fw_cfg/by_name/opt/tekne
mkdir -p /tmp/nv /etc/apt/keyrings
for i in $(seq 60); do ip route | grep -q '^default' && break; sleep 1; done
# This build's test repository instead of the published one: only URL and key
# change. (fw_cfg files are root-only; apt checks signatures as its _apt user.)
cp $fw/test-key/raw /etc/apt/keyrings/tekne-test.gpg
chmod 644 /etc/apt/keyrings/tekne-test.gpg
sed -i -e 's|^URIs:.*|URIs: http://10.0.2.2:@PORT@/repo/|' \
	-e 's|^Signed-By:.*|Signed-By: /etc/apt/keyrings/tekne-test.gpg|' /etc/apt/sources.list.d/tekne.sources
export DEBIAN_FRONTEND=noninteractive
dpkg-query -W -f '${Package}\n' | sort > /tmp/nv/before
apt-get update >/tmp/nv/update1.log 2>&1 && echo APT_UPDATE=ok || { echo APT_UPDATE=failed; tail -n 20 /tmp/nv/update1.log; }
apt-get install -y tekne-nvidia-repo >/tmp/nv/repo.log 2>&1 \
	&& echo REPO_INSTALL=ok || { echo REPO_INSTALL=failed; tail -n 20 /tmp/nv/repo.log; }
apt-get update >/tmp/nv/update2.log 2>&1 && echo NVIDIA_UPDATE=ok || { echo NVIDIA_UPDATE=failed; tail -n 20 /tmp/nv/update2.log; }
apt-get install -y tekne-nvidia >/tmp/nv/install.log 2>&1 \
	&& echo NVIDIA_INSTALL=ok || { echo NVIDIA_INSTALL=failed; tail -n 40 /tmp/nv/install.log; }
dpkg-query -W -f '${Package}\n' | sort > /tmp/nv/after
echo "NEW_PACKAGES=$(comm -13 /tmp/nv/before /tmp/nv/after | wc -l)"
echo "NEW_SYSTEMD=$(comm -13 /tmp/nv/before /tmp/nv/after | grep -c systemd)"
echo "DRIVER_ORIGIN=$(apt-cache policy nvidia-driver | grep -A1 '^ \*\*\*' | grep -c developer.download.nvidia.com)"
echo "DRIVER_VERSION=$(dpkg-query -W -f '${Version}' nvidia-driver 2>/dev/null)"
echo "DKMS=$(dkms status 2>/dev/null | grep -c "$(uname -r).*installed")"
echo "PERSISTENCED=$(dpkg-query -W -f '${db:Status-Status}' nvidia-persistenced 2>/dev/null || echo absent)"
echo "PRIME_RUN=$([ -x /usr/bin/tekne-prime-run ] && echo present || echo missing)"
"""

PURGE_GUEST = r"""
set -u
export DEBIAN_FRONTEND=noninteractive
# The documented way back to nouveau (docs/customizing.md).
tekne-nvidia-remove -y >/tmp/purge.log 2>&1 \
	&& echo PURGE=ok || { echo PURGE=failed; tail -n 30 /tmp/purge.log; }
# firmware-nvidia-graphics is Devuan's firmware (DEC-013), not the driver's.
echo "LEFT=$(dpkg-query -W -f '${Package} ${db:Status-Status}\n' '*nvidia*' 2>/dev/null \
	| awk '$2 == "installed" && $1 != "firmware-nvidia-graphics"' | tr '\n' ' ')"
echo "NVIDIA_SOURCE=$([ -e /etc/apt/sources.list.d/tekne-nvidia.sources ] && echo present || echo gone)"
echo "BLACKLIST=$(grep -ls 'blacklist nouveau' /etc/modprobe.d/*.conf | tr '\n' ' ')"
# If anything is left, say why: manual marks, and what apt's autoremover
# follows to reach nvidia-driver.
if dpkg-query -W -f '${db:Status-Status}' nvidia-driver 2>/dev/null | grep -qx installed; then
	echo "--- manual: $(apt-mark showmanual | grep -iE 'nvidia|cuda|egl|vulkan|glx' | tr '\n' ' ')"
	apt-get -s -o Debug::pkgAutoRemove=1 autoremove 2>&1 \
		| grep -E 'Following dep: .*(nvidia|egl|vulkan|glx|vdpau)|Marking: .*nvidia' | head -40 | sed 's/^/--- /'
fi
"""


def run_guest(mode, luks, disk, vars_path, workdir, name, script_text, extra_fw_cfg=()):
    """Boot the installed disk, run a script as root over serial, power off."""
    script = os.path.join(workdir, f"{name}.sh")
    with open(script, "w") as f:
        f.write(script_text)
    cmd = qemu_command(mode, vars_path, install.MEMORY_MIB, cpus=4) + [
        "-boot", "c", "-drive", f"file={disk},if=virtio,format=qcow2",
        "-fw_cfg", f"name=opt/tekne/{name},file={script}",
    ] + list(extra_fw_cfg)
    user, password = install.ANSWERS["USERNAME"], install.ANSWERS["PASSWORD"]
    run = ("sh -c 'modprobe qemu_fw_cfg; echo __TEKNE\"\"_BEGIN__; "
           f"sh /sys/firmware/qemu_fw_cfg/by_name/opt/tekne/{name}/raw; echo __TEKNE\"\"_END__'")
    with open(os.path.join(workdir, f"serial-{name}.log"), "w") as log:
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
            output = con.expect(END, GUEST_TIMEOUT)
            con.expect("$ ", install.CMD_TIMEOUT)
            con.send(f"echo {password} | sudo -S -p '' poweroff\n")
            stop(proc, install.CMD_TIMEOUT)
        finally:
            if proc.poll() is None:
                proc.kill()
    return output, dict(line.strip().split("=", 1) for line in output.splitlines()
                        if "=" in line and line.strip()[:1].isupper())


def check(mode, luks, disk, vars_path, workdir, label):
    """install.py's checks; keeps each run's serial log under its own name."""
    try:
        got = install.boot_and_check(mode, luks, disk, vars_path, workdir)
    except (TimeoutError, RuntimeError) as err:
        return [f"{label}: {err}"]
    finally:
        log = os.path.join(workdir, "serial-boot.log")
        if os.path.exists(log):
            os.replace(log, os.path.join(workdir, f"serial-boot-{label}.log"))
    want = install.expected(mode, luks)
    return [f"{label}: {k}: got {got.get(k)!r}, want {v!r}" for k, v in want.items() if got.get(k) != v]


def main():
    args = sys.argv[1:]
    keep = "--keep" in args
    args = [a for a in args if a != "--keep"]
    if len(args) > 1 or (args and args[0].startswith("-")):
        sys.exit(__doc__)
    iso = os.path.abspath(args[0]) if args else newest_iso()
    if not iso or not os.path.exists(iso):
        sys.exit("error: no out/tekne-*-amd64.iso; run sudo scripts/build.sh first")
    repo_debs = [glob.glob(os.path.join(TEST_REPO, "repo", "**", f"{p}_*_all.deb"), recursive=True)
                 for p in ("tekne-nvidia-repo", "tekne-nvidia")]
    if not all(repo_debs) or not os.path.isdir(os.path.join(TEST_REPO, "repo")):
        sys.exit("error: needs this build's out/test-repo/ with the NVIDIA packages; run sudo scripts/build.sh first")

    mode, luks, name = "uefi", True, "uefi-luks"
    workdir = os.path.join(WORK, name)
    disk, vars_path, answers_path = install.new_case(workdir, mode, luks)
    started = time.monotonic()
    print(f"[nvidia] installing {os.path.basename(iso)} ({name})")
    try:
        install.install(mode, luks, iso, disk, vars_path, answers_path, workdir)
    except (TimeoutError, RuntimeError) as err:
        print(f"FAIL [nvidia]: installing: {err}. Logs in {workdir}")
        return 1

    problems = []
    server = serve(TEST_REPO)
    try:
        port = server.server_address[1]
        output, r = run_guest(mode, luks, disk, vars_path, workdir, "install",
                              INSTALL_GUEST.replace("@PORT@", str(port)),
                              ["-fw_cfg", f"name=opt/tekne/test-key,file={os.path.join(TEST_REPO, 'test-key.gpg')}"])
    except (TimeoutError, RuntimeError) as err:
        print(f"FAIL [nvidia]: installing the packages: {err}. Logs in {workdir}")
        return 1
    finally:
        server.shutdown()
    print(f"[nvidia] installed {r.get('NEW_PACKAGES')} packages: driver {r.get('DRIVER_VERSION')}, "
          f"DKMS modules for the running kernel: {r.get('DKMS')}")
    for key, want in [("APT_UPDATE", "ok"), ("REPO_INSTALL", "ok"), ("NVIDIA_UPDATE", "ok"),
                      ("NVIDIA_INSTALL", "ok"), ("NEW_SYSTEMD", "0"), ("DRIVER_ORIGIN", "1"),
                      ("DKMS", "1"), ("PERSISTENCED", "absent"), ("PRIME_RUN", "present")]:
        got = r.get(key)
        if key == "PERSISTENCED" and got == "not-installed":
            got = "absent"
        if got != want:
            problems.append(f"install: {key}: got {got!r}, want {want!r}")
    if problems:
        print(output)
    else:
        problems += check(mode, luks, disk, vars_path, workdir, "installed")

    if not problems:
        try:
            output, r = run_guest(mode, luks, disk, vars_path, workdir, "purge", PURGE_GUEST)
        except (TimeoutError, RuntimeError) as err:
            problems.append(f"purge: {err}")
            r = {}
        for key, want in [("PURGE", "ok"), ("LEFT", ""), ("NVIDIA_SOURCE", "gone"), ("BLACKLIST", "")]:
            if r and r.get(key, "").strip() != want:
                problems.append(f"purge: {key}: got {r.get(key)!r}, want {want!r}")
        if problems and r:
            print(output)
        if not problems:
            problems += check(mode, luks, disk, vars_path, workdir, "purged")

    for problem in problems:
        print(f"[nvidia]   {problem}")
    ok = not problems
    print(f"[nvidia] done in {time.monotonic() - started:.0f}s")
    print(f"{'PASS' if ok else 'FAIL'} [nvidia] (logs: {workdir})")
    if ok and not keep:
        shutil.rmtree(workdir, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
