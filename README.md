# Tekne

A systemd-free desktop respin of Devuan Excalibur: herbstluftwm on X11 and a
keyboard-driven installer. See [SPEC.md](SPEC.md) for what's planned and
[DECISIONS.md](DECISIONS.md) for why. Licensed GPL-3.0-or-later; the artwork
in `branding/` is CC-BY-SA-4.0.

**Status:** [Tekne 0.2](https://github.com/GraeWolf/tekne/releases/tag/v0.2)
is released: download the ISO, its checksum and build-info from the release
page. The live ISO boots to the herbstluftwm desktop on BIOS and UEFI,
installs with `sudo tekne-install` (optionally with LUKS, with hibernation),
and an installed Tekne updates with `apt`, its own packages included. CI builds
and tests every change.

Tekne 0.3 (SPEC §9), coming next, makes a hybrid-graphics laptop
a daily driver:
- NVIDIA's proprietary driver, opt-in, with PRIME offload
- one passphrase from power-on to the desktop on encrypted installs
- an icon bar and floating pop-ups
- shell defaults

| Guide | For |
|---|---|
| [docs/customizing.md](docs/customizing.md) | Changing an installed Tekne: desktop, keybindings, theme, firewall, kernel, NVIDIA's driver, autologin |
| [docs/building.md](docs/building.md) | Building, testing and releasing the ISO, and where to change things |
| [docs/testing.md](docs/testing.md) | The manual checklist for real hardware |
| [docs/desktop-stack.md](docs/desktop-stack.md), [docs/installer.md](docs/installer.md) | How the desktop and the installer are designed |

## Try it

Write the ISO to a USB stick, disable Secure Boot, and boot it: the desktop
starts on its own (live user `user`, password `live`). `sudo tekne-install`
installs it to a whole disk, which it erases. [docs/testing.md](docs/testing.md)
has the steps and a hardware checklist.

## Build

Needs a Linux host with Podman (or Docker) and root. Everything else runs inside
the pinned Devuan build container. On Tekne (or any Devuan/Debian host), this
installs everything needed to build and test it (DEC-033):

```sh
sudo apt install git podman qemu-system-x86 qemu-utils ovmf python3
sudo scripts/build.sh
```

Outputs in `out/`:

| File | Contents |
|---|---|
| `tekne-<version>-amd64.iso` | Hybrid ISO, boots on BIOS and UEFI (Secure Boot off) |
| `tekne-<version>-amd64.iso.sha256` | Checksum |
| `tekne-<version>-amd64.packages` | Package manifest |
| `build-info.txt` | Git commit, build image, live-build version, ISO size |
| `build.log` | Full build log |

`out/packages/` holds Tekne's own `.deb`s. Dev builds are versioned
`<VERSION>-dev<commit count>.<commit>`. A clean checkout of tag `v<VERSION>`
builds as plain `<VERSION>`. Package versions rise with every commit (DEC-032).
The first build downloads about 1.5 GB; later builds reuse the package cache in
`out/cache/`. More in [docs/building.md](docs/building.md).

The build fails if the package manifest breaks the no-systemd rule
(SPEC.md §4, allowlist in `tests/systemd-allowlist.txt`).

## Test

Needs `qemu-system-x86` and `ovmf` on the host. CI (GitHub Actions,
`.github/workflows/build.yml`) builds the ISO and runs every test below except
`release.py` on every push to `master` and every pull request. Each green run
keeps the ISO as a downloadable artifact for 30 days (DEC-038).

```sh
tests/smoke/live-boot.py                  # live ISO on SeaBIOS and OVMF: sysvinit, desktop, firewall
tests/smoke/repo.py                       # Tekne's APT repository: key, pin, tampered .deb
tests/smoke/install.py                    # unattended installs {BIOS,UEFI} x {plain,LUKS}, each
                                          # booted, checked, hibernated and resumed; LUKS cases
                                          # with autologin and the lock screen (~15 min)
tests/smoke/upgrade.py                    # the last release, upgraded to this build through apt
tests/smoke/nvidia.py                     # tekne-nvidia-repo and tekne-nvidia: install, check, purge
tests/smoke/release.py                    # after publishing: a fresh install from the released ISO
                                          # has no tekne-* updates waiting in the live repository
scripts/test-in-qemu.sh uefi              # the newest ISO in a QEMU window
scripts/test-in-qemu.sh uefi --disk       # ...with a blank 32 GiB virtual disk: sudo tekne-install
scripts/test-in-qemu.sh uefi --installed  # boot that virtual disk after installing
```

The live user is `user`, password `live`.

## Update an installed Tekne

From 0.2, everything updates with apt. Tekne's own packages come from Tekne's
APT repository (DEC-040), which `tekne-apt-sources` sets up: its key is
pinned, and it may only provide `tekne-*` packages.

```sh
sudo apt update && sudo apt upgrade
```

**From 0.1**, which doesn't know Tekne's repository yet: once, install
`tekne-apt-sources` from the [0.2 release](https://github.com/GraeWolf/tekne/releases/tag/v0.2),
then upgrade as above. GitHub serves the file over HTTPS, as it does the ISO.

```sh
curl -fLO https://github.com/GraeWolf/tekne/releases/download/v0.2/tekne-apt-sources_0.2_all.deb
sudo apt install ./tekne-apt-sources_0.2_all.deb
```

**Release candidates:** in `/etc/apt/sources.list.d/tekne.sources`, change
`Suites: excalibur` to `Suites: excalibur-rc`. That suite carries releases
too, so switching back is optional.

**Your own builds** still install the same way as before the repository:

```sh
sudo scripts/build.sh --packages-only     # about a minute
sudo apt install ./out/packages/tekne-{apt-sources,branding,config,desktop}_*.deb
```

A dev build sorts above the release it was built after and below the next
one (DEC-032), so apt moves you on to that release once it's published.

`tests/smoke/upgrade.py` checks the apt path in CI: it installs the previous
release, upgrades it through apt from a test copy of the repository, and
re-runs the installed-system checks. All testing happens in virtual machines;
only files under `out/` are written on the host.
