# Changelog

## 0.3-rc1 (2026-10-06)

Tekne 0.3 makes a hybrid-graphics laptop a daily driver (SPEC §9).
- NVIDIA's own driver is an opt-in install, with PRIME offload and the idle
  GPU powered off.
- Encrypted installs can go from the LUKS passphrase straight to the desktop.
- Resume is more reliable on every machine.
- The bar, the shell and a few pop-ups are less rough.

Tested in CI on every build (BIOS and UEFI, plain and LUKS, hibernation
included), and on the development laptop, an ASUS ROG Zephyrus G15 (AMD and
NVIDIA RTX 3060), with kernel 7.2.6.

**Upgrading from 0.2:**

```sh
sudo apt update && sudo apt upgrade
```

Use `apt`, not `apt-get upgrade`: `tekne-desktop` gains new dependencies,
which `apt-get upgrade` would hold it back for. Then, optionally:
- **Shell defaults** for users created before 0.3: add this line to
  `~/.bash_aliases`:
  `[ -r /usr/share/tekne/bash/tekne.bashrc ] && . /usr/share/tekne/bash/tekne.bashrc`
- **Autologin** on an encrypted install: `sudo tekne-autologin on`, then reboot.
- **NVIDIA's driver:** the three commands in
  [docs/customizing.md](docs/customizing.md), "NVIDIA graphics".

**Testing a release candidate** on 0.2: in
`/etc/apt/sources.list.d/tekne.sources`, change `Suites: excalibur` to
`Suites: excalibur-rc`, then upgrade as above. A system installed from a
candidate's ISO follows `excalibur` and gets 0.3 when it's released.

### Added
- **NVIDIA's driver, opt-in** (DEC-041): `tekne-nvidia-repo` adds NVIDIA's
  repository, pinned to the display driver, and `tekne-nvidia` installs the driver
  (615, open kernel modules, Turing and newer) with PRIME offload
  (`tekne-prime-run`), power-off of the idle GPU, and suspend and hibernate
  without systemd. Neither is in the ISO; docs/customizing.md has the three
  commands, and `sudo tekne-nvidia-remove` goes back to `nouveau`. Every build
  checks that NVIDIA's module builds for its kernel.
- **Autologin after the LUKS passphrase** (DEC-042): on encrypted installs, one
  passphrase from power-on to the desktop. The installer asks (default yes), and
  existing installs run `sudo tekne-autologin on`. The lock screen, `sudo` and
  tty2–6 still ask for the password, and the keyring asks for it once per
  session. If X fails within 15 seconds, tty1 stays on a console shell for the
  rest of the boot instead of looping.
- **Bar:** all nine tags (active, occupied or empty), the clock in the centre,
  and icons instead of text for volume, Wi-Fi, Ethernet, battery and the clock,
  from Nerd Fonts' "Symbols Only" fonts (v3.5.1, pinned by checksum, DEC-043).
  The same fonts are fontconfig's fallback after JetBrains Mono, so icons also
  render in the terminal.
- **Floating windows:** `nmtui` (from the bar's network modules, through the new
  `tekne-nmtui`), Blueman's manager and Pavucontrol open floating and centred.
- **Shell defaults** for new users, through `~/.bash_aliases` from `/etc/skel`:
  `cat` runs `batcat --paging=never`, and fastfetch, with Tekne's logo, runs
  when `tekne-terminal` opens a terminal. Users created before 0.3 can opt in
  with one line (above, and in docs/customizing.md).
- **SSH keys:** `AddKeysToAgent yes`, so the session's `ssh-agent` asks for a
  key's passphrase once per session. `openssh-client` is now installed (the
  client only; there's still no SSH server).
- **XDG user directories** (Documents, Downloads, ...): created by the
  installer, and by `tekne-session` at each login if they're missing.
- **Packages:** `bat`, `fastfetch`, `ffmpeg`, `imagemagick`, `openssh-client`.

### Fixed
- **Resume:** X now takes its seat from elogind rather than seatd
  (`LIBSEAT_BACKEND=logind`, DEC-045). Under seatd, X sometimes ignored every
  keyboard after resuming, when a driver forced a VT switch on suspend.
- **ASUS N-KEY keyboards** (`0b05:19b6`) work again after deep sleep: an
  elogind hook re-probes them on resume (DEC-044).
- **TLP's suspend/resume handling** now runs: tlp installs its hook where
  Devuan's elogind doesn't look (DEC-025).
- **Kernel 7.2:** `linux-base` comes from backports too, which kernel 7.2.6
  needs. Without it, builds failed and installed systems stayed on 7.1
  (DEC-036).
- **Installing with kernel 7.2:** its packages hard-link the kernel in
  `/usr/lib/modules` to the copy in `/boot`, a separate partition, so every
  install failed with "Invalid cross-device link". The installer now copies
  `/boot` in a second pass.

### Build and tests
- When a Devuan mirror hasn't synced the backports kernel yet, the build
  fetches it from `pkgmaster.devuan.org`, the archive the mirrors sync from.
  Each file must match the SHA-256 in the signed index (DEC-036).
- New QEMU tests:
  - `tests/smoke/nvidia.py` installs, checks and purges the NVIDIA packages.
  - `install.py`'s LUKS cases check autologin, the lock screen and the
    keyring, and break X on purpose to check tty1 doesn't loop.
  - `upgrade.py` turns autologin on after upgrading, like an existing install.
- `tests/smoke/release.py`, run after publishing a release, checks that a fresh
  install from the released ISO has no `tekne-*` updates waiting.

**Known limitations:**
- Outputs wired to the NVIDIA GPU (HDMI on the development laptop) don't work
  with NVIDIA's driver yet (DEC-041). External monitors on the AMD GPU's ports
  haven't been tested on hardware yet.
- With NVIDIA's driver, the GPU stays powered on AC: TLP keeps it on when
  plugged in.
- Secure Boot must be off (DEC-016), and NVIDIA's DKMS module is unsigned.
- The installer takes a whole disk: no dual-boot or manual partitioning (DEC-005).
- The artwork is a placeholder, and the console login greeting still names
  Devuan (DEC-035).
- Real-hardware testing so far is one laptop.

## 0.2 (2026-10-03)

Tekne 0.2 makes an installed Tekne updatable with apt alone. Tekne's own
packages now come from Tekne's signed APT repository (DEC-040), so
`sudo apt update && sudo apt upgrade` updates them along with Devuan's. The
desktop and installer are the same as 0.1.

- **Tekne's APT repository** is `https://graewolf.github.io/tekne/apt/`,
  set up by `tekne-apt-sources`. Its key is pinned in that package and
  trusted for this repository only, and an APT pin lets it provide nothing
  but `tekne-*` packages, so it can never replace a Devuan package.
- **Signed with a key whose primary half is kept offline:** primary
  `2401BB7742E09C29AA41B29441BEF97FD11D7B37`, signing subkey
  `82C321645DE72C0575A968AC64CE1E0BA73FF9F4`. The subkey expires on
  2027-10-02 and will be replaced before then through an ordinary update.
- **Published only from tested releases:** the repository changes only when
  the maintainer publishes a GitHub release and approves the publish. It's
  built from the exact `.deb`s CI built and tested, each checked against the
  checksum that build recorded, and its signatures are checked against the
  key installed systems trust before anything goes live.
- **Tested on every build:** CI checks that apt accepts the repository only
  with its key and refuses a tampered package. It also installs 0.1 from its
  released ISO, upgrades it through apt, and checks the result, hibernation
  included.

**Upgrading from 0.1:** once, install this release's `tekne-apt-sources`,
then upgrade as usual:

```sh
curl -fLO https://github.com/GraeWolf/tekne/releases/download/v0.2/tekne-apt-sources_0.2_all.deb
sudo apt install ./tekne-apt-sources_0.2_all.deb
sudo apt update && sudo apt upgrade
```

**From 0.2-rc1:** `sudo apt update && sudo apt upgrade`. Systems that follow
`excalibur-rc` also get future release candidates; to follow releases only,
change `Suites: excalibur-rc` back to `Suites: excalibur` in
`/etc/apt/sources.list.d/tekne.sources`.

**Known limitations:**
- Secure Boot must be off (DEC-016).
- The installer takes a whole disk: no dual-boot or manual partitioning (DEC-005).
- Tekne's updates come from GitHub Pages, so they depend on it being up;
  Devuan's packages don't.
- The artwork is a placeholder, and the console login greeting still names
  Devuan (DEC-035).
- Real-hardware testing so far is one laptop: an ASUS ROG Zephyrus G15 with
  AMD and NVIDIA graphics.

### Changes since 0.2-rc1
- None to the system: this is 0.2-rc1 rebuilt from the tag with Devuan's
  current packages.
- CI's upgrade test always starts from the last final release, not a
  release candidate, since that's what users upgrade from.

## 0.2-rc1 (2026-10-02)

First release candidate of Tekne 0.2, which makes an installed Tekne
updatable with apt alone. Tekne's own packages now come from Tekne's signed
APT repository (DEC-040), so `sudo apt update && sudo apt upgrade` updates
them along with Devuan's. The desktop and installer are the same as 0.1.

The repository is signed with a key whose primary half is kept offline:
primary `2401BB7742E09C29AA41B29441BEF97FD11D7B37`, signing subkey
`82C321645DE72C0575A968AC64CE1E0BA73FF9F4`. It's published only from
releases that passed CI and that the maintainer published and approved.

**Testing this candidate on a 0.1 system:**
1. Download this release's `tekne-apt-sources` `.deb` (GitHub may show a `.`
   where the version has a `~`) and install it:
   `sudo apt install ./tekne-apt-sources_*_all.deb`
2. In `/etc/apt/sources.list.d/tekne.sources`, change `Suites: excalibur` to
   `Suites: excalibur-rc`. Release candidates are published only there;
   `excalibur` stays empty until 0.2 is released.
3. `sudo apt update && sudo apt upgrade`. Later candidates arrive the same way.

**Installing from this ISO:** the installed system follows `excalibur`, so
it gets Tekne updates from 0.2 on. Switch it to `excalibur-rc` (step 2 above)
to receive further candidates.

### Added
- Tekne's own APT repository (DEC-040), so installed systems get `tekne-*`
  updates with `apt update && apt upgrade`. `tekne-apt-sources` adds its source
  (`https://graewolf.github.io/tekne/apt/`, suite `excalibur`), its key and a
  pin that allows only `tekne-*` packages from it. It's published from GitHub
  releases once a person publishes one, and signed with a key whose primary
  half is kept offline; fingerprints are in DEC-040.
- `scripts/build-repo.sh` builds and signs the repository;
  `.github/workflows/publish-repo.yml` and `scripts/ci-publish-repo.sh`
  publish it to GitHub Pages after the maintainer approves.
- Every build writes a test repository signed with a throwaway key
  (`out/test-repo/`), and `tests/smoke/repo.py` checks in QEMU that apt takes
  it only with the right key, refuses a tampered package, and never installs
  anything but `tekne-*` from it. CI runs it on every build.
- `build-info.txt` records each `.deb`'s SHA-256, and releases carry the
  `.deb`s, checked against it.
- `tests/smoke/upgrade.py` now installs the previous release from its
  published ISO (pinned in `tests/smoke/previous-release`) and upgrades it to
  the current build with `apt upgrade`, as installed systems will; CI runs it
  on every build. From 0.1 it also runs the one-time step of installing the
  new `tekne-apt-sources`.
- `tests/key-rotation.sh`, run by every build: the signing-subkey rotation
  in docs/building.md, with throwaway keys and Devuan's APT.

### Changed
- The build never contacts Tekne's own repository: `live-build/config/apt/apt.conf`
  blocks it while the image is built, and the build fails if anything came
  from it. Expect "Failed to fetch .../tekne/apt/..." warnings in the build log.
- The build container also installs `gnupg`, to sign repositories.

## 0.1 (2026-10-01)

The first release of **Tekne**: a systemd-free desktop respin of Devuan 6
Excalibur, for technical users on amd64 laptops and desktops.

- **Desktop:** herbstluftwm on XLibre, with polybar, rofi, dunst, picom,
  PipeWire, NetworkManager (`nmtui`), Brave Origin and Firefox ESR, all in Tokyo
  Night colours. Keybindings are listed with `Mod+F1`.
- **Installer:** `sudo tekne-install` installs the live system to a whole disk,
  on BIOS or UEFI, optionally encrypted with LUKS2, with a RAM-sized swapfile
  for hibernation.
- **No systemd:** sysvinit, elogind and eudev; the build fails if any systemd
  package gets in (SPEC §4).
- **Kernel 7.1** from Devuan's `excalibur-backports`.
- **Defaults:** a firewall that drops inbound traffic, no listening services,
  telemetry off in both browsers.
- **Built and tested by CI:** every build boots on BIOS and UEFI, and installs
  on both, with and without LUKS, including hibernate and resume. This release's
  files come from a green build of its tag.

Read [docs/customizing.md](https://github.com/GraeWolf/tekne/blob/v0.1/docs/customizing.md)
to change the defaults and
[docs/building.md](https://github.com/GraeWolf/tekne/blob/v0.1/docs/building.md)
to build your own ISO.

**Known limitations:**
- Secure Boot must be off (DEC-016).
- The installer takes a whole disk: no dual-boot or manual partitioning (DEC-005).
- Tekne's own `tekne-*` packages update by building them from this repository,
  not from an APT repository (DEC-006). Devuan's packages update with `apt` as
  usual.
- The artwork is a placeholder, and the console login greeting still names
  Devuan (DEC-035).
- Real-hardware testing so far is one laptop: an ASUS ROG Zephyrus G15 with
  AMD and NVIDIA graphics.

**Upgrading:** from 0.1-rc2, build this version's packages and install them
(`sudo scripts/build.sh --packages-only`, then
`sudo apt install ./out/packages/tekne-{apt-sources,branding,config,desktop}_*.deb`).
From 0.1-rc1 (satori), follow the steps under 0.1-rc2.

### Changes since 0.1-rc2
- Release documentation only; the system is the same as 0.1-rc2, rebuilt from
  the tag with Devuan's current packages.
- DEC-032 records how `VERSION` advances after a release candidate, so dev
  builds always sort above the last candidate.

## 0.1-rc2 (2026-10-01)

Second release candidate: the distribution is now **Tekne** (formerly
satori), with branding (Phase 4), CI (Phase 5), the 7.1 kernel from
backports, and a styled boot screen. Every build is tested in CI: live boot
on BIOS and UEFI, and installs on BIOS and UEFI, with and without LUKS,
including hibernate and resume.

**Upgrading from 0.1-rc1 (satori):** build this version's packages
(`sudo scripts/build.sh --packages-only`), then run
`sudo apt install --purge ./out/packages/tekne-{apt-sources,branding,config,desktop}_*.deb`
and reboot. It removes the `satori-*` packages cleanly. The LUKS mapping and
hostname keep their names.

### Changed
- **Renamed from satori to Tekne** (DEC-008): packages are now `tekne-*`,
  and so are paths, commands, the firewall table and the ISO name. The
  placeholder art is now a geometric T instead of an ensō.
- Kernel 7.1 from Devuan's `excalibur-backports` instead of stable's 6.12
  (DEC-036). `tekne-apt-sources` adds the suite, pinned to the kernel
  packages only. Fixes ASUS ROG laptop keyboards that `hid-asus` failed to set
  up on 6.12 (dead keyboard, even at the LUKS prompt).
- Firewall (DEC-023): traffic from local container and VM bridges (podman,
  Docker, libvirt) is accepted, as are ports a container engine publishes.
  Before, containers and VMs on a bridge network had no network at all.
- `tekne-config` declares the packages its helper scripts call (herbstluftwm,
  rofi, maim, xclip and others), instead of relying on `tekne-desktop`.
- The no-systemd allowlist (DEC-010) is empty: `libsystemd0` is no longer in
  the image, because Devuan's `libelogind-compat` replaces it.

### Added
- Branding (Phase 4, DEC-034): the `tekne-branding` package. `os-release`
  says Tekne (Devuan's copy is diverted, so `base-files` upgrades can't bring
  it back); a GRUB theme for the live ISO and installed systems, a wallpaper
  and a logo. The artwork is a placeholder, rendered from SVGs in `branding/`
  (CC-BY-SA-4.0).
- Tokyo Night colours for herbstluftwm, polybar, rofi, dunst, alacritty and the
  lock screen; dark Adwaita with Papirus icons for GTK apps.
- A styled boot console (DEC-037): Tokyo Night console colours, firmware
  error spam kept off the screen (`loglevel=3`), and a centred "T E K N E"
  banner above a centred LUKS passphrase prompt. New installs name the
  encrypted disk `tekne`. Still text, no Plymouth (DEC-015).
- `tekne-terminal`: alacritty with Tekne's config unless you have your own.
  It's the `x-terminal-emulator` alternative, which had been xterm's `lxterm`.
- Live ISO boot menu: "Tekne live" and "Tekne live (safe graphics)"
  (`nomodeset`) replace live-build's "Live system" entries and Debian splash.
- CI (Phase 5, DEC-038): GitHub Actions builds the ISO and runs the live-boot
  and install tests on every push to `master` and every pull request, and keeps
  the ISO as a downloadable artifact.
- Releases from CI (DEC-039): pushing a `v*` tag builds and tests it, then
  `scripts/ci-release.sh` checks the build and creates a draft GitHub release
  with the ISO, checksum, manifest and build-info.
- Docs (Phase 6): `docs/customizing.md` (changing an installed system) and
  `docs/building.md` (building, testing, releasing, and where to change
  things); the README links them and says how to try Tekne.
- The build container installs `librsvg2-bin`, to render the artwork.

### Fixed
- Audio sometimes missing after login: WirePlumber exits if PipeWire isn't
  listening yet, and the session started them together. The autostart now
  waits (up to 5 s) for PipeWire's socket first.
- The bar had no battery indicator on laptops whose battery or charger isn't
  named `BAT0`/`ADP1`, polybar's defaults (for example `BAT1` and `ACAD`). The
  herbstluftwm autostart now detects the names from `/sys/class/power_supply`.
- `scripts/build.sh` failed on Tekne itself: the container couldn't resolve
  names, because Tekne's firewall (DEC-023) dropped the forwarded and inbound
  traffic that a container bridge network needs. The build container now uses
  the host's network.
- `service tekne-firewall status` said "NOT loaded" when run without root,
  because nft can't read the ruleset then. It now says it needs root.

## 0.1-rc1 (2026-09-29)

First release candidate: the build system, desktop and installer (Phases 1-3).
Real-hardware checks happen before it's installed on the development laptop
(release candidate gate, SPEC §7).

### Added
- Build system (Phase 1): `scripts/build.sh` builds a hybrid BIOS/UEFI Devuan
  Excalibur live ISO in a pinned build container, using Debian's live-build.
- Package manifest, checksum and `build-info.txt` for every build.
- No-systemd check (SPEC.md §4) that fails the build; `libsystemd0` is the only
  allowlisted package.
- Headless QEMU boot test for BIOS and UEFI (`tests/smoke/live-boot.py`) and an
  interactive launcher (`scripts/test-in-qemu.sh`).
- Desktop (Phase 2): `satori-desktop`, `satori-config` and `satori-apt-sources`
  packages, built from `packages/` into `out/packages/`. The live session logs
  in on tty1 and starts herbstluftwm with polybar, rofi, dunst, picom, CopyQ,
  PipeWire and gnome-keyring.
- Brave Origin (default browser) and XLibre from their own repositories, with
  keys scoped by `Signed-By`, APT pins, and a build-time check that no other
  package came from them. `brave-keyring`'s globally trusted key is diverted.
- Firmware and CPU microcode for common laptop hardware.
- `satori-get-melia`: downloads Melia and installs it only if the signature and
  checksum verify.
- Security and privacy defaults (DEC-023): nftables firewall (`satori-firewall`),
  Firefox ESR and Brave telemetry policies, Wi-Fi scan MAC randomisation.
- Installer (Phase 3): `satori-install`, a gum TUI that installs the live system
  to a whole disk with optional LUKS2, on BIOS or UEFI, with a RAM-sized
  swapfile and resume configured for hibernation. Unattended mode for tests.
- `satori-swap-resize` recreates the swapfile and keeps hibernation working.
- `tests/smoke/install.py`: unattended {BIOS, UEFI} × {plain, LUKS} installs in
  QEMU, each booted and checked. Answers reach the VM through QEMU fw_cfg, so
  automated installs can't run on real hardware.
- Package versions rise with every build (DEC-032), so an installed system
  upgrades with `apt install ./out/packages/...`; `tests/smoke/upgrade.py`
  tests it. `scripts/build.sh --packages-only` builds just the `.deb`s.
- README: one command installs the tools to build satori on satori (DEC-033).

### Fixed
- Installer: the timezone and keyboard steps showed only a few matches,
  because the current value was pre-typed as the search. They now start with
  the full list (418 timezones, including aliases such as Europe/Oslo) and the
  current value first.
- Console logins now unlock the GNOME keyring (no create or unlock prompts).
- Live-session autologin on Excalibur: live-config's sysvinit component never
  ran, so satori ships its own using agetty `--autologin`.
