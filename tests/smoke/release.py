#!/usr/bin/env python3
"""Release check: a fresh install from a published release is current.

    tests/smoke/release.py [--keep] [TAG]

Run by hand after publishing a release and approving its repository publish
(docs/building.md, "Release"). CI can't run it: it checks what's live on
GitHub, which a build's own tests come before. TAG defaults to the newest
published release, pre-releases included.

  1. Read the release's assets from GitHub's API. Download its ISO (cached in
     out/release-check/) and check it against the release's own .sha256.
  2. Install it unattended with UEFI and LUKS, as install.py does.
  3. Boot, log in over serial, and update from Tekne's live repository, with
     the shipped source, key and pin unchanged. A pre-release is checked on
     excalibur-rc, the suite release candidates are published to (testers
     switch to it the same way). Then check:
       - every installed tekne-* package is at the release's version
       - apt offers no tekne-* upgrade
       - every .deb the release carries, the opt-in ones included, is the
         suite's candidate at that version
     A mismatch means the published repository and the release differ, for
     example a publish that wasn't approved, or a stale GitHub Pages deploy.

Needs network access. Work files go to out/release-check/<tag>/ and are
deleted after a pass unless --keep is given. Exits non-zero on failure.
"""
import json
import os
import shutil
import subprocess
import sys
import time

import install
from qemu_serial import OUT, Serial, qemu_command, start, stop
from upgrade import deb_field, sha256

API = "https://api.github.com/repos/GraeWolf/tekne/releases"
WORK = os.path.join(OUT, "release-check")
GUEST_TIMEOUT = 600

# Run as root in the installed VM (delivered through fw_cfg). @SUITE@ and
# @DEBS@ ("package=version" for each .deb the release carries) are filled in
# by guest_script().
GUEST = r"""
set -u
for i in $(seq 60); do ip route | grep -q '^default' && break; sleep 1; done
sed -i 's/^Suites:.*/Suites: @SUITE@/' /etc/apt/sources.list.d/tekne.sources
apt-get update >/tmp/update.log 2>&1 && echo APT_UPDATE=ok || { echo APT_UPDATE=failed; tail -n 20 /tmp/update.log; }
echo "TEKNE_WARNINGS=$(grep -c '^[WE]:.*graewolf.github.io' /tmp/update.log)"
dpkg-query -W -f 'INSTALLED_${Package}=${Version}\n' 'tekne-*' 2>/dev/null | grep -v '=$'
echo "UPGRADABLE=$(apt list --upgradable 2>/dev/null | grep '^tekne-' | cut -d/ -f1 | tr '\n' ' ')"
for pv in @DEBS@; do
	echo "CANDIDATE_${pv%%=*}=$(apt-cache policy "${pv%%=*}" | awk '/Candidate:/ { print $2 }')"
done
"""


# Downloads use curl, not urllib: curl tries IPv6 and IPv4 side by side, so a
# network with broken IPv6 (some phone hotspots) doesn't stall a download
# until GitHub's signed asset link expires.
def curl(url, *args):
    return subprocess.run(["curl", "-fsSL", "--retry", "3", *args, url],
                          check=True, capture_output=True).stdout


def fetch_json(url):
    return json.loads(curl(url))


def find_release(tag):
    """The published release named tag, or the newest one."""
    if tag:
        return fetch_json(f"{API}/tags/{tag}")
    published = [r for r in fetch_json(API) if not r["draft"]]
    if not published:
        sys.exit("error: no published release")
    return max(published, key=lambda r: r["published_at"])


def download(url, path):
    curl(url, "-o", path + ".part")
    os.replace(path + ".part", path)


def release_files(release, cache):
    """Download the release's ISO (checked against its .sha256) and .debs.
    Returns (iso_path, {package: version})."""
    assets = {a["name"]: a["browser_download_url"] for a in release["assets"]}
    isos = [n for n in assets if n.endswith(".iso")]
    if len(isos) != 1 or isos[0] + ".sha256" not in assets:
        sys.exit(f"error: {release['tag_name']} doesn't have one ISO with a .sha256")
    iso = os.path.join(cache, isos[0])
    want = curl(assets[isos[0] + ".sha256"]).decode().split()[0]
    if not (os.path.exists(iso) and sha256(iso) == want):
        print(f"Downloading {assets[isos[0]]}")
        download(assets[isos[0]], iso)
        got = sha256(iso)
        if got != want:
            os.remove(iso)
            sys.exit(f"error: {isos[0]} has SHA-256 {got}, but the release's .sha256 says {want}")
    # GitHub may rename assets (a "~" becomes "."), so each .deb's package and
    # version come from its control file, not its name.
    debs = {}
    for name, url in assets.items():
        if name.endswith(".deb"):
            path = os.path.join(cache, name)
            download(url, path)
            debs[deb_field(path, "Package")] = deb_field(path, "Version")
    return iso, debs


def check(disk, vars_path, workdir, suite, debs):
    script = os.path.join(workdir, "release-check.sh")
    with open(script, "w") as f:
        f.write(GUEST.replace("@SUITE@", suite)
                .replace("@DEBS@", " ".join(f"{p}={v}" for p, v in sorted(debs.items()))))
    cmd = qemu_command("uefi", vars_path, install.MEMORY_MIB) + [
        "-boot", "c", "-drive", f"file={disk},if=virtio,format=qcow2",
        "-fw_cfg", f"name=opt/tekne/release-check,file={script}",
    ]
    with open(os.path.join(workdir, "serial-check.log"), "w") as log:
        proc = start(cmd)
        con = Serial(proc, log)
        try:
            install.serial_login(con, luks=True)
            results = install.run_as_root(con, "release-check", timeout=GUEST_TIMEOUT)
            con.send(f"echo {install.ANSWERS['PASSWORD']} | sudo -S -p '' poweroff\n")
            stop(proc, install.CMD_TIMEOUT)
        finally:
            if proc.poll() is None:
                proc.kill()
    return results


def main():
    args = sys.argv[1:]
    keep = "--keep" in args
    args = [a for a in args if a != "--keep"]
    if len(args) > 1 or (args and args[0].startswith("-")):
        sys.exit(__doc__)

    release = find_release(args[0] if args else None)
    tag = release["tag_name"]
    version = tag.removeprefix("v").replace("-", "~")
    suite = "excalibur-rc" if release["prerelease"] else "excalibur"
    cache = os.path.join(WORK, "cache", tag)
    os.makedirs(cache, exist_ok=True)
    iso, debs = release_files(release, cache)
    print(f"Checking {tag} ({os.path.basename(iso)}) against the live repository, suite {suite}")

    started = time.monotonic()
    workdir = os.path.join(WORK, tag)
    disk, vars_path, answers_path = install.new_case(workdir, "uefi", True)
    try:
        install.install("uefi", True, iso, disk, vars_path, answers_path, workdir)
        results = check(disk, vars_path, workdir, suite, debs)
    except (TimeoutError, RuntimeError) as err:
        print(f"FAIL [release {tag}]: {err}. Logs in {workdir}")
        return 1

    problems = []
    if results.get("APT_UPDATE") != "ok":
        problems.append(f"apt-get update: {results.get('APT_UPDATE')!r}")
    if results.get("TEKNE_WARNINGS") != "0":
        problems.append(f"apt-get update warned about Tekne's repository ({results.get('TEKNE_WARNINGS')} lines)")
    installed = {k.removeprefix("INSTALLED_"): v for k, v in results.items() if k.startswith("INSTALLED_")}
    if not installed:
        problems.append("no tekne-* package is installed")
    for pkg, got in sorted(installed.items()):
        if got != version:
            problems.append(f"{pkg} is installed at {got}, want {version}")
    if results.get("UPGRADABLE", "").strip():
        problems.append(f"apt offers upgrades for: {results['UPGRADABLE'].strip()}")
    for pkg, want in sorted(debs.items()):
        got = results.get(f"CANDIDATE_{pkg}")
        if got != want:
            problems.append(f"the repository's candidate for {pkg} is {got!r}, but the release carries {want}")

    print(f"[release {tag}] installed: {', '.join(f'{p} {v}' for p, v in sorted(installed.items()))}")
    print(f"[release {tag}] the repository offers all {len(debs)} of the release's .debs at their versions"
          if not any("candidate" in p for p in problems) else f"[release {tag}] candidates: {results}")
    for problem in problems:
        print(f"[release {tag}]   {problem}")
    ok = not problems
    print(f"{'PASS' if ok else 'FAIL'} [release {tag}] in {time.monotonic() - started:.0f}s (logs: {workdir})")
    if ok and not keep:
        shutil.rmtree(workdir, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
