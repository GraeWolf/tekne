#!/usr/bin/env python3
"""Repository smoke test: Tekne's APT repository, its key and its pin (DEC-040).

    tests/smoke/repo.py [ISO]

Boots the newest out/tekne-*-amd64.iso (BIOS) and checks, in the live system,
how apt treats the test repository that scripts/build.sh writes to
out/test-repo/. That repository is built by scripts/build-repo.sh, like the
published one, but signed with a throwaway key; it holds the build's Tekne
packages and a decoy "base-files 99:0". The host serves it over HTTP, and the
VM reaches it through QEMU's user network (host = 10.0.2.2).

The live system's own /etc/apt/sources.list.d/tekne.sources and
/etc/apt/preferences.d/tekne.pref are used, with only the URL and the key
swapped for the test repository's. Then, with only that source enabled:

  1. Right key: apt-get update succeeds, tekne-config is offered at
     priority 500, and the decoy base-files at -1, so Devuan's stays the
     candidate (DEC-026 rule 3).
  2. Wrong key: apt refuses the repository ("is not signed") and offers
     nothing from it.
  3. Tampered .deb (one byte changed, same size): apt-get update succeeds,
     but downloading the package fails with a hash mismatch.

Nothing is installed from the test repository. Exits non-zero on failure.
"""
import os
import shutil
import sys
import tempfile
import time

from qemu_serial import (OUT, SERIAL_ENTRY_HOTKEY, SERIAL_ENTRY_TITLE, Serial,
                         newest_iso, parse_results, qemu_command, serve, start, stop)

TEST_REPO = os.path.join(OUT, "test-repo")
LIVE_USER, LIVE_PASSWORD = "user", "live"
MENU_TIMEOUT, BOOT_TIMEOUT, CMD_TIMEOUT = 60, 300, 180
BEGIN, END = "__TEKNE" + "_BEGIN__", "__TEKNE" + "_END__"
HOST = "10.0.2.2"


def guest_script(port):
    """Shell run as root in the live VM; prints KEY=VALUE lines."""
    base = f"http://{HOST}:{port}"
    return f"""
set -u
src=/etc/apt/sources.list.d/tekne.sources
[ -f "$src" ] && [ -f /etc/apt/preferences.d/tekne.pref ] && echo SHIPPED=present || echo SHIPPED=missing
mkdir -p /tmp/rt/src /tmp/rt/lists/partial /tmp/rt/archives/partial /tmp/rt/keys
fw=/sys/firmware/qemu_fw_cfg/by_name/opt/tekne
# fw_cfg files are root-only; apt checks signatures as its _apt user.
for k in test wrong; do cp $fw/$k-key/raw /tmp/rt/keys/$k.gpg; chmod 644 /tmp/rt/keys/$k.gpg; done
# Only the test source: the shipped file with its URL and key swapped.
use() {{  # use REPO_PATH KEY
	sed -e "s|^URIs:.*|URIs: {base}/$1/|" -e "s|^Signed-By:.*|Signed-By: /tmp/rt/keys/$2.gpg|" "$src" > /tmp/rt/src/tekne.sources
	rm -rf /tmp/rt/lists/* && mkdir -p /tmp/rt/lists/partial
}}
A="-o Dir::Etc::SourceList=/dev/null -o Dir::Etc::SourceParts=/tmp/rt/src -o Dir::State::Lists=/tmp/rt/lists -o Dir::Cache::Archives=/tmp/rt/archives"
cd /tmp/rt

use repo test
apt-get $A update >/tmp/rt/update1.log 2>&1 && echo GOOD_UPDATE=ok || {{ echo GOOD_UPDATE=failed; tail -5 /tmp/rt/update1.log; }}
apt-cache $A policy tekne-config base-files > /tmp/rt/policy1.log 2>&1
# Version lines start " *** " (installed) or five spaces; the priority is last.
echo "GOOD_TEKNE_PRIO=$(awk '/^tekne-config:/ {{p=1}} /^base-files:/ {{p=0}} p && /^( \\*\\*\\* |     )[^ ]/ {{print $NF; exit}}' /tmp/rt/policy1.log)"
echo "GOOD_TEKNE_FROM_REPO=$(grep -c '{HOST}' /tmp/rt/policy1.log)"
echo "DECOY_PRIO=$(awk '/^base-files:/ {{p=1}} p && $1 == "99:0" {{print $2; exit}}' /tmp/rt/policy1.log)"
echo "DECOY_CANDIDATE=$(apt-cache $A policy base-files | awk '/Candidate:/ {{print $2}}')"

use repo wrong
apt-get $A update >/tmp/rt/update2.log 2>&1 && echo WRONG_UPDATE=ok || echo WRONG_UPDATE=failed
grep -q 'is not signed' /tmp/rt/update2.log && echo WRONG_REFUSED=yes || {{ echo WRONG_REFUSED=no; tail -5 /tmp/rt/update2.log; }}
echo "WRONG_OFFERED=$(apt-cache $A policy tekne-config | grep -c '{HOST}')"

use tampered test
apt-get $A update >/tmp/rt/update3.log 2>&1 && echo TAMPER_UPDATE=ok || echo TAMPER_UPDATE=failed
v=$(apt-cache $A policy tekne-config | awk '/Candidate:/ {{print $2}}')
apt-get $A download "tekne-config=$v" >/tmp/rt/download3.log 2>&1 && echo TAMPER_DOWNLOAD=succeeded || echo TAMPER_DOWNLOAD=failed
grep -qi 'hash sum mismatch' /tmp/rt/download3.log && echo TAMPER_REFUSED=yes || {{ echo TAMPER_REFUSED=no; tail -5 /tmp/rt/download3.log; }}
"""


def main():
    args = sys.argv[1:]
    if len(args) > 1:
        sys.exit(__doc__)
    iso = os.path.abspath(args[0]) if args else newest_iso()
    if not iso or not os.path.exists(iso):
        sys.exit("error: no ISO found; run sudo scripts/build.sh first")
    if not os.path.isdir(os.path.join(TEST_REPO, "repo")):
        sys.exit(f"error: {TEST_REPO} missing; it's made by a full sudo scripts/build.sh")

    with tempfile.TemporaryDirectory() as tmp:
        # The served tree: the test repository and a tampered copy of it.
        shutil.copytree(os.path.join(TEST_REPO, "repo"), os.path.join(tmp, "repo"))
        shutil.copytree(os.path.join(TEST_REPO, "repo"), os.path.join(tmp, "tampered"))
        pool = os.path.join(tmp, "tampered", "pool", "main")
        target = os.path.join(pool, next(f for f in os.listdir(pool) if f.startswith("tekne-config_")))
        with open(target, "r+b") as f:  # flip one byte; the size stays the same
            f.seek(200)
            byte = f.read(1)
            f.seek(200)
            f.write(bytes([byte[0] ^ 0xFF]))

        server = serve(tmp)
        port = server.server_address[1]
        script_path = os.path.join(tmp, "check.sh")
        with open(script_path, "w") as f:
            f.write(guest_script(port))

        log_path = os.path.join(OUT, "serial-repo.log")
        cmd = qemu_command("bios") + ["-cdrom", iso, "-boot", "d",
                                       "-fw_cfg", f"name=opt/tekne/check,file={script_path}"]
        for key in ("test", "wrong"):
            cmd += ["-fw_cfg", f"name=opt/tekne/{key}-key,file={os.path.join(TEST_REPO, key + '-key.gpg')}"]
        print(f"Testing {iso} against {TEST_REPO} (served on port {port})")
        started = time.monotonic()
        with open(log_path, "w") as log:
            proc = start(cmd)
            con = Serial(proc, log)
            try:
                con.expect(SERIAL_ENTRY_TITLE, MENU_TIMEOUT)
                con.send(SERIAL_ENTRY_HOTKEY)
                con.expect("login:", BOOT_TIMEOUT)
                con.send(LIVE_USER + "\n")
                con.expect("assword:", CMD_TIMEOUT)
                con.send(LIVE_PASSWORD + "\n")
                con.expect("$ ", CMD_TIMEOUT)
                # Wait for the network (NetworkManager, DHCP from QEMU), then run the checks.
                con.send("for i in $(seq 60); do ip route | grep -q '^default' && break; sleep 1; done; "
                         "sudo sh -c 'modprobe qemu_fw_cfg; echo __TEKNE\"\"_BEGIN__; "
                         "sh /sys/firmware/qemu_fw_cfg/by_name/opt/tekne/check/raw; echo __TEKNE\"\"_END__'\n")
                con.expect(BEGIN, CMD_TIMEOUT)
                output = con.expect(END, CMD_TIMEOUT)
                con.send("sudo poweroff\n")
                stop(proc, CMD_TIMEOUT)
            except (TimeoutError, RuntimeError) as err:
                print(f"FAIL [repo]: {err}. Serial log: {log_path}")
                return 1
            finally:
                if proc.poll() is None:
                    proc.kill()
                server.shutdown()

    results = parse_results(output)
    want = {
        "SHIPPED": "present",
        "GOOD_UPDATE": "ok", "GOOD_TEKNE_PRIO": "500", "DECOY_PRIO": "-1",
        "WRONG_REFUSED": "yes", "WRONG_OFFERED": "0",
        "TAMPER_UPDATE": "ok", "TAMPER_DOWNLOAD": "failed", "TAMPER_REFUSED": "yes",
    }
    problems = [f"{k}: got {results.get(k)!r}, want {v!r}" for k, v in want.items() if results.get(k) != v]
    if results.get("GOOD_TEKNE_FROM_REPO", "0") == "0":
        problems.append("tekne-config isn't offered by the test repository")
    if results.get("DECOY_CANDIDATE", "").startswith("99:"):
        problems.append(f"the decoy base-files is the candidate ({results.get('DECOY_CANDIDATE')})")

    for key in want:
        print(f"[repo] {key}: {results.get(key)}")
    print(f"[repo] base-files candidate: {results.get('DECOY_CANDIDATE')}")
    for problem in problems:
        print(f"[repo]   {problem}")
    ok = not problems
    print(f"{'PASS' if ok else 'FAIL'} [repo] in {time.monotonic() - started:.0f}s (serial log: {log_path})")
    if not ok:
        print(output)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
