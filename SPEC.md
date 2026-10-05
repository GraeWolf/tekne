# Tekne — Project Specification

> Living document. Decisions and their rationale live in [DECISIONS.md](DECISIONS.md);
> this file describes *what* Tekne is and *how we'll know each phase is done*.
> Detailed designs: [docs/desktop-stack.md](docs/desktop-stack.md), [docs/installer.md](docs/installer.md).

## 1. Overview

**Tekne** is a systemd-free, amd64 desktop Linux distribution built as a respin of
**Devuan Excalibur** (Devuan 6, Debian Trixie-based). It ships a preconfigured
**herbstluftwm** tiling desktop on X11 and a keyboard-driven **TUI installer** built
with `gum`.

### Goals
- A hybrid (BIOS + UEFI) ISO that boots to a working live desktop and installs to disk.
- No systemd as init or as a package, as defined precisely in §4.
- Opinionated, keyboard-first defaults that a technical user can adopt or strip down easily.
- The whole build is scripted from this repository. There are no manual or undocumented steps.
- tekne-specific configuration ships as `.deb` packages, so it survives `apt upgrade` and stays under dpkg's control.

### Non-goals (v1)
- Custom kernel or kernel patches. We use Devuan's stock kernel, from `excalibur-backports` (DEC-036).
- Hosting or mirroring Devuan packages. Tekne packages are built in-repo and baked into the ISO (DEC-006). From 0.2, Tekne's own APT repository carries only those packages (DEC-040). Third-party repositories are allowed only under DEC-026.
- Wayland. herbstluftwm is X11-only.
- Manual partitioning, dual-boot, or filesystems other than ext4 in the installer.
- Secure Boot (DEC-016) and Plymouth (DEC-015).
- Architectures other than amd64.
- Bit-for-bit reproducible ISOs. v1 targets a *repeatable* build (§5.3).

## 2. Audience

Technical Linux users, starting with the maintainer. They are comfortable with a
tiling window manager, a terminal, and editing dotfiles. They want a systemd-free
daily driver without hand-assembling Devuan plus a window manager each time.

In practice this means:
- Documentation can assume Linux literacy. It still has to be complete for anything tekne-specific, such as keybindings, config locations, and how to rebuild.
- Defaults should be discoverable (for example a keybinding cheatsheet), but no GUI settings apps are required.
- A single-user laptop or workstation is the primary target. Server and embedded use are out of scope.

## 3. Architecture

### 3.1 Base system
| Item | Value |
|---|---|
| Base | Devuan Excalibur (`excalibur`, `excalibur-updates`, `excalibur-security`) |
| Mirror | `deb.devuan.org/merged` |
| Archive areas | `main contrib non-free non-free-firmware` (see DEC-013) |
| Init | `sysvinit-core` |
| Session/seat | `elogind` + `libpam-elogind`, `polkitd` |
| Kernel | Devuan/Debian stock `linux-image-amd64`, from `excalibur-backports` (DEC-036) |
| Package manager | APT, unmodified |
| Third-party repos | Brave (`brave-origin`, `brave-keyring`) and XLibre for Devuan (`xlibre*`), each pinned to specific packages (DEC-026). From 0.3, opt-in: NVIDIA's, for the display driver (DEC-041) |
| Tekne repo | From 0.2: `https://graewolf.github.io/tekne/apt/`, pinned to `tekne-*` packages (DEC-040) |

### 3.2 Build tooling
- **Debian's live-build** (`1:20250505+deb13u1`, pinned by checksum), configured for Devuan (DEC-003). Devuan's own `live-build` package is a 2016 fork without UEFI support, so it isn't used.
  - All `lb config` flags live in `live-build/auto/config`. Nobody types flags by hand.
  - Mirrors, distribution, and archive areas must be set explicitly to Devuan values. live-build defaults to Debian.
  - BIOS and UEFI both boot through GRUB (`--bootloaders "grub-pc grub-efi"`), so there's one boot menu config.
  - live-build's package cache lives outside the per-build work directory, so rebuilds don't re-download everything.
  - Third-party repositories (DEC-026) are added to the build chroot from the same pinned keys and `.sources` files that `tekne-apt-sources` ships. The build fails if a key doesn't match its recorded checksum.
- **Build host:** a privileged Devuan Excalibur container (Podman or Docker) defined in `container/`, with the base image pinned by digest (DEC-031). The host OS doesn't matter. It only needs the container engine and root.
- **In-repo packages:** `packages/*` are built with `debhelper` inside the same container, then placed in `live-build/config/packages.chroot/` before `lb build`.

### 3.3 Tekne packages
| Package | Contents |
|---|---|
| `tekne-desktop` | Metapackage that depends on the full desktop stack ([docs/desktop-stack.md](docs/desktop-stack.md)). Installed during the build by a chroot hook, after `tekne-apt-sources` has configured the third-party repositories (DEC-026). |
| `tekne-config` | System-wide defaults in `/usr/share/tekne/` (used only when the user has no config of their own): the `tekne-session` X session, herbstluftwm autostart and keybindings, polybar and picom configs, startx on tty1, the default browser, browser policies, firewall ruleset, NetworkManager MAC randomisation. Helper scripts: `tekne-run-once`, `tekne-keys`, `tekne-powermenu`, `tekne-screenshot`, `tekne-get-melia` (DEC-029), `tekne-swap-resize` (DEC-017), and from 0.3 `tekne-nmtui`. From 0.3 also Nerd Fonts' symbols fonts (DEC-043) and elogind sleep hooks (DEC-025, DEC-044). |
| `tekne-apt-sources` | Third-party `.sources` entries, their pinned signing keys, and `/etc/apt/preferences.d/` pins (DEC-026); also Devuan's `excalibur-backports`, pinned to the kernel packages (DEC-036), and from 0.2 Tekne's own repository, pinned to `tekne-*` (DEC-040). |
| `tekne-branding` | `os-release` via `dpkg-divert` (owned by `base-files`; `/etc/issue` is a conffile and can't be diverted, see DEC-035), wallpaper, GRUB theme, logo, rendered from `branding/` (DEC-034). |
| `tekne-nvidia-repo` | From 0.3, opt-in: NVIDIA's APT repository, its checksum-pinned key and a pin limited to the display driver (DEC-041, DEC-026). In Tekne's repository, not the ISO. |
| `tekne-nvidia` | From 0.3, opt-in: NVIDIA's driver from that repository, plus runtime power management for the GPU's audio function, modprobe options and `tekne-prime-run` (DEC-041). In Tekne's repository, not the ISO. |
| `tekne-installer` | The gum TUI installer ([docs/installer.md](docs/installer.md)) and the QEMU-only `tekne-autoinstall` init script. Installed in the live image only, purged from the target. |

Rule: **no loose overlay files for anything a user might need updated.** The
`includes.chroot/` overlay is reserved for live-session-only tweaks.

In 0.1 there's no hosted repository (DEC-006), so installed systems get Devuan updates
through APT but get Tekne package updates only by manually installing newer `.deb`s.
From 0.2, Tekne's packages are also published in a signed APT repository (DEC-040,
§8), and `apt upgrade` covers both.

### 3.4 Desktop stack
herbstluftwm on Xorg, started with `startx` from a tty1 login (DEC-014). The full
component list, keybindings, and session startup order are in
[docs/desktop-stack.md](docs/desktop-stack.md).

### 3.5 Installer
A gum-based TUI that copies the live filesystem to disk. It supports guided
whole-disk installs, with optional LUKS2 encryption, on BIOS and UEFI. It creates
a RAM-sized swapfile and configures resume, so hibernation works out of the box
(DEC-017). Design: [docs/installer.md](docs/installer.md).

### 3.6 Security and privacy defaults
Recorded as DEC-022 (accounts) and DEC-023 (everything else).

- Installer offers LUKS2 full-disk encryption (the root filesystem and swapfile are encrypted; `/boot` isn't).
- nftables firewall enabled: inbound traffic denied except established/related and local container/VM bridges, forwarding only for those bridges and deliberately published ports, all outbound allowed (DEC-023).
- `sudo` for the installer-created user; the root account is locked.
- No `popularity-contest`. Firefox ESR policies turn off telemetry, studies, and sponsored content. Brave Origin's remaining telemetry, if any, is switched off with managed policies.
- NetworkManager uses randomised MAC addresses when scanning Wi-Fi.
- No services listen on the network by default. There's no SSH server.

### 3.7 Branding
- Name "Tekne". `/usr/lib/os-release` diverted to a Tekne version that keeps `ID_LIKE=devuan debian`.
- GRUB theme on both the live ISO and installed systems. Default wallpaper. Text boot (no Plymouth in v1), styled: Tokyo Night console colours and a centred banner above the LUKS prompt (DEC-037).
- Tokyo Night colours throughout, with placeholder artwork (a geometric T) until real art exists; GTK uses dark Adwaita with Papirus icons (DEC-034).
- Devuan and Debian logos and trademarks removed from user-visible branding. Attribution to Devuan kept in `os-release`, the docs, and `/usr/share/doc`.

## 4. The "no systemd" rule

An image **passes** only if all of these hold:
1. PID 1 is sysvinit's `init`, and `/run/systemd/system` doesn't exist.
2. None of these packages are installed: `systemd`, `systemd-sysv`, `systemd-timesyncd`, `systemd-resolved`, `systemd-boot`, `libpam-systemd`.
3. Every installed package whose name contains `systemd` is on an explicit allowlist in `tests/systemd-allowlist.txt`. It's empty: Phase 0 allowed `libsystemd0`, which the desktop image no longer has (DEC-010). Each entry needs a comment explaining why. The base package list must include `opensysusers` so that nothing pulls in `systemd-standalone-sysusers`.

Rules 2 and 3 are checked by `scripts/check-no-systemd.sh` against every build's
package manifest. Rule 1 is checked at runtime by the QEMU smoke test. A failure
fails the build.

## 5. Build, test and release

### 5.1 Build
```
sudo scripts/build.sh       # builds container → builds packages/ → lb config/build → no-systemd check
```
The version comes from the `VERSION` file. A clean checkout of tag `v<VERSION>` builds as `<VERSION>`; anything else builds as `<VERSION>-dev<commit count>.<short commit>` (§5.4).
Output goes to `out/` (git-ignored):
- `tekne-<version>-amd64.iso` and `.sha256`
- `tekne-<version>-amd64.packages`: the package manifest
- `build-info.txt`: git SHA, dirty flag, build date, base image digest, build image ID, live-build version, ISO size and checksum, package count, the NVIDIA module check (DEC-041), and each Tekne `.deb`'s SHA-256 (DEC-040)
- `build.log`: the full live-build log
- `packages/`: Tekne's `.deb`s
- `test-repo/`: a test copy of Tekne's APT repository, signed with a throwaway key made for this build, for `tests/smoke/repo.py` (DEC-040)
- `cache/`: live-build's downloaded-package cache, reused between builds (root-owned)

### 5.2 Test
- `scripts/test-in-qemu.sh`: boots the ISO under SeaBIOS or OVMF in a QEMU window, for hands-on testing.
- `tests/smoke/` automated tests, driven over the serial console. The live ISO's GRUB menu has a "serial console" entry (hotkey `s`) that sends kernel output to `ttyS0` and starts a serial login prompt. Tests press `s` at the menu; the default entry is unaffected.
  - `tests/smoke/live-boot.py`: the live image boots on BIOS and UEFI, a login prompt appears, and the no-systemd runtime check passes.
  - `tests/smoke/repo.py`: in the live image, apt accepts the build's test repository only with its key, refuses a tampered `.deb`, and the shipped pin keeps everything but `tekne-*` at -1 (DEC-040).
  - `tests/smoke/upgrade.py`: installs the previous release from its published ISO (pinned in `tests/smoke/previous-release`), upgrades it to the current build with `apt upgrade` from the build's test repository, reboots and re-runs `install.py`'s checks, hibernate/resume included (DEC-040). It can also start from a kept `install.py` case.
  - `tests/smoke/nvidia.py`: installs the ISO (UEFI and LUKS), installs `tekne-nvidia-repo` and `tekne-nvidia` from the build's test repository and NVIDIA's, checks the driver and DKMS module and that no systemd package came with them, reruns `install.py`'s checks, then purges both the documented way and checks again (DEC-041).
  - `tests/smoke/install.py`: install matrix, {BIOS, UEFI} × {plain, LUKS} = 4 unattended installs (answers file via QEMU fw_cfg, [docs/installer.md](docs/installer.md) §6). Each installed system must boot to a login prompt and pass `tests/smoke/installed-checks.sh`. `tests/smoke/qemu_serial.py` holds the shared QEMU and serial-console code.
- `tests/key-rotation.sh`: the signing-subkey rotation in `docs/building.md`, with throwaway keys and APT, in the build container on every build (DEC-040).
- Manual QA checklist in `docs/testing.md`, for things that are hard to automate on real hardware: Wi-Fi, audio, suspend/resume, hibernate/resume, backlight, external monitors.

### 5.3 Reproducibility
v1 promises a **repeatable** build. The same git SHA and the same container digest
produce an ISO with the same package set, apart from newer versions from Devuan
mirrors. The package manifest records exactly what went in. Bit-for-bit
reproducibility is a possible later goal.

### 5.4 Versioning and release
- Versions follow `<major>.<minor>`, with the Devuan base in the release notes, for example "Tekne 0.1 (Excalibur)".
- Git tags `v0.1` etc. Release artifacts are the ISO, its checksum, the manifest, and build-info.
- `VERSION` holds the next release (`0.1`, `0.1-rc1`, ...). A clean checkout of tag `v<VERSION>` builds as that version. Anything else builds as `<VERSION>-dev<commit count>.<short commit>`. Tekne's `.deb`s get the Debian form of the same version, which always increases (DEC-032). After tagging a release, bump `VERSION` to the next one: after a release candidate, the next candidate, because `0.1~dev…` sorts below `0.1~rc2` (DEC-032).
- Releases are published on GitHub Releases (DEC-020). Each asset must be under 2 GiB, so the ISO size is tracked in build-info from Phase 2 on.
- `CHANGELOG.md` is maintained from Phase 1 onward.

### 5.5 Licensing
- Everything in the repo except `branding/`: GPL-3.0-or-later (DEC-019), full text in `LICENSE`.
- Branding assets in `branding/`: CC-BY-SA-4.0 (DEC-019, DEC-034), full text in `branding/LICENSE`.

## 6. Repository layout

```
tekne/
├── README.md
├── VERSION                        # base version, e.g. 0.1
├── LICENSE                        # GPL-3.0-or-later
├── SPEC.md
├── DECISIONS.md
├── CHANGELOG.md
├── container/
│   └── Containerfile              # pinned Devuan Excalibur build env
├── live-build/
│   ├── auto/{config,build,clean}
│   └── config/
│       ├── apt/apt.conf           # build only: keeps the build away from Tekne's own repository (DEC-040)
│       ├── package-lists/
│       │   ├── base.list.chroot
│       │   ├── live.list.chroot   # live-only: live-boot, live-config, tekne-installer
│       ├── packages.chroot/       # generated: tekne-*.deb (git-ignored)
│       ├── bootloaders/grub-pc/   # GRUB menu for BIOS and UEFI, incl. the serial test entry
│       ├── includes.chroot/       # live-session-only overlays
│       └── hooks/{normal,live}/
├── packages/
│   ├── tekne-desktop/debian/
│   ├── tekne-config/{debian/,files/}
│   ├── tekne-branding/{debian/,files/}
│   ├── tekne-apt-sources/{debian/,keys/,sources/,preferences/}
│   └── tekne-installer/{debian/,files/}
├── branding/                      # source SVGs (CC-BY-SA-4.0) → rendered into tekne-branding
├── scripts/
│   ├── build.sh                   # host side: container build + run (needs root)
│   ├── build-in-container.sh      # container side: live-build, checks, outputs
│   ├── build-packages.sh
│   ├── build-repo.sh              # Tekne's signed APT repository from .debs (DEC-040)
│   ├── check-no-systemd.sh
│   ├── ci-publish-repo.sh         # CI: publish the repository from published releases (DEC-040)
│   ├── ci-release.sh              # CI: draft GitHub release from a tested tag (DEC-039)
│   └── test-in-qemu.sh
├── tests/
│   ├── key-rotation.sh            # the signing-subkey rotation, with throwaway keys (DEC-040)
│   ├── systemd-allowlist.txt
│   └── smoke/                     # serial-console tests: live-boot.py, repo.py, install.py,
│                                  # upgrade.py, nvidia.py, installed-checks.sh, qemu_serial.py
└── docs/
    ├── building.md
    ├── customizing.md
    ├── desktop-stack.md
    ├── installer.md
    └── testing.md
```

## 7. Phases and acceptance criteria

Each phase is one or more small commits and ends only when every one of its criteria passes.

**Phase 0: Feasibility spike**. ✔ Complete (2026-09-28). See DEC-003, DEC-010 and DEC-021.
- A throwaway live-build config for Excalibur produces a console-only hybrid ISO.
- ✅ The ISO boots to a login prompt in QEMU on SeaBIOS and OVMF.
- ✅ The manifest is inspected, the allowlist in §4 is drafted, and no forbidden packages are present.
- ✅ Findings are recorded in DECISIONS.md: whether live-build is confirmed or replaced (DEC-003), which `gum` path applies (DEC-021), and which `lb config` flags were needed.

**Phase 1: Build system**. ✔ Complete (2026-09-28). A clean clone of `1b35a66` built in about 7 minutes, and both boot tests passed. See DEC-031.
- Scaffold the layout in §6: the container, `build.sh`, `check-no-systemd.sh`, and the manifest and build-info outputs.
- ✅ `scripts/build.sh` on a clean checkout produces an ISO without manual steps.
- ✅ An automated live boot test (BIOS and UEFI) plus the systemd runtime check pass.

**Phase 2: Desktop stack**. ✔ Complete (2026-09-29). Smoke tests pass on BIOS and UEFI, and the maintainer checked the launcher, audio, network and browser by hand in QEMU. The real-laptop checks passed on the development laptop after the `v0.1-rc1` install (2026-09-29), apart from a missing battery indicator, fixed for rc2.
- `tekne-desktop` and `tekne-config` packages. The live session autologs in and starts herbstluftwm.
- ✅ The live session reaches herbstluftwm with the bar, launcher, notifications, the bar's network module (DEC-011), and working audio. `tests/smoke/live-boot.py` checks that every session process is running. Launcher, audio and network are checked by hand in QEMU and on at least one real laptop.
- ✅ Every added package passes the no-systemd check, including those from third-party repositories. Any substitutions are documented in docs/desktop-stack.md.
- ✅ Third-party repositories are restricted by their pins: `apt-cache policy` shows no Devuan package replaced by a Brave or XLibre package.
- ✅ Brave Origin is the default browser.
- ✅ The DEC-023 security defaults are in place: `tests/smoke/live-boot.py` checks that Tekne's firewall is loaded and that nothing listens beyond loopback; the browser and NetworkManager policy files are installed.
- ✅ `tekne-get-melia` installs Melia, and it refuses a download whose signature or checksum is wrong.

**Phase 3: Installer**. ✔ Complete (2026-09-29). All four unattended installs pass with hibernate/resume in QEMU, and the maintainer completed an interactive install and the keyring test in QEMU. On real hardware (2026-09-29): the maintainer installed `v0.1-rc1` interactively with LUKS on the development laptop, and it passed the manual checklist, the Phase 2 laptop checks and hibernate/resume. Hibernate/resume without LUKS is checked in QEMU only: the only laptop is encrypted.
- `tekne-installer` (using Excalibur's `gum` package, DEC-021).
- ✅ All four unattended install-matrix runs pass (§5.2).
- ✅ An interactive install in QEMU (`scripts/test-in-qemu.sh --disk`) completes and the installed system boots to the desktop.
- ✅ An interactive install on real hardware, with LUKS, boots and passes the manual checklist. This includes the Phase 2 desktop checks deferred from QEMU: Wi-Fi, audio, brightness keys, suspend and the lock screen.
- ✅ Hibernate and resume work in QEMU for all four install cases: `tests/smoke/install.py` hibernates each installed system and checks that the same session resumes. On real hardware too, with and without LUKS (DEC-017).
- ✅ On an installed system, Brave Origin saves and recalls a password through gnome-keyring without an extra unlock prompt (DEC-030). Moved from Phase 2: the live session autologins, so PAM has no password to unlock the keyring with.

**Release candidate gate (`v0.1-rc1`): before installing on the development laptop**. ✔ Passed (2026-09-29). `v0.1-rc1` (`c77c411`) built clean; the upgrade test moved an installed system from `0.1~dev20` to `0.1~rc1`; live-boot and all four install cases pass. The maintainer pushed the repository, backed up the laptop, disabled Secure Boot, and passed the live-USB hardware check, including the hybrid NVIDIA GPU with `nouveau` loaded (so Tekne doesn't blacklist it). Tekne `0.1-rc1` is installed on the development laptop, and Phases 4–6 continue there.
- The only laptop is also the development machine, and the installer erases the whole disk. So these must pass before Tekne is installed there. Phases 4–6 then continue on the installed system.
- ✅ Package versions increase with every build (DEC-032), and `tests/smoke/upgrade.py` upgrades an installed system from one build's packages to the next and re-runs the installed-system checks. That's how changes reach the laptop while dogfooding (DEC-006).
- ✅ One documented command installs everything needed to build and test Tekne on Tekne (DEC-033).
- ✅ `v0.1-rc1` is tagged and built from a clean tree, and its ISO passes `live-boot.py` and `install.py`.
- ✅ (maintainer) The repository is pushed and the laptop is backed up.
- ✅ (maintainer) A live-USB hardware check on the laptop passes: Wi-Fi, the AMD GPU on the internal display and an external monitor, audio, brightness keys, suspend/resume, and the hybrid NVIDIA GPU with `nouveau` loaded (boots, suspends, battery drain). If `nouveau` misbehaves, decide whether Tekne blacklists it.
- ✅ (maintainer) Secure Boot is disabled in the laptop's firmware (DEC-016).

**Phase 4: Branding**. ✔ Complete (2026-09-30). `tekne-branding`, the Tokyo Night theme and placeholder art (DEC-034). The build checks that os-release survives reinstalling `base-files`; the live ISO's GRUB menu shows only Tekne's theme and entries; `live-boot.py` and all four `install.py` cases pass on `0.1-rc2-dev34`. The console login greeting keeps Devuan's text (DEC-035).
- `tekne-branding`, the GRUB theme, wallpaper, and os-release diversion.
- ✅ `os-release` still shows Tekne after `apt install --reinstall base-files`.
- ✅ No Devuan or Debian logos appear on the boot menu, GRUB, or desktop.

**Phase 5: CI and QA**. ✔ Complete (2026-10-01). `.github/workflows/build.yml` (DEC-038, Decided): the first run on `master` ([36802153183](https://github.com/GraeWolf/tekne/actions/runs/36802153183), `b6b69e3`) built the ISO, passed `live-boot.py` and all four `install.py` cases, and kept the ISO as the `tekne-iso` artifact, in 38 minutes.
- A CI pipeline builds on push and runs the automated tests. `docs/testing.md` has the manual checklist.
- ✅ A green CI run on `master` (the default branch) produces downloadable ISO artifacts.

**Phase 6: Docs and first release**. ✔ Complete (2026-10-01). `docs/building.md`, `docs/customizing.md`, the README and the CHANGELOG are written. [Tekne 0.1](https://github.com/GraeWolf/tekne/releases/tag/v0.1) is released with its ISO, checksum, manifest and build-info, created by CI from a green build of the `v0.1` tag (`f302523`, DEC-039) after the [`v0.1-rc2` pre-release](https://github.com/GraeWolf/tekne/releases/tag/v0.1-rc2) passed a live-USB check on the development laptop.
- `docs/building.md`, `docs/customizing.md`, README, and CHANGELOG.
- ✅ The `v0.1` tag is released with its ISO, checksum, manifest, and build-info.

## 8. Tekne 0.2

> **Status:** ✔ Complete (2026-10-03). Agreed by the maintainer on 2026-10-01 and recorded as
> DEC-040, which amends DEC-006. [Tekne 0.2](https://github.com/GraeWolf/tekne/releases/tag/v0.2)
> is released, and installed systems update Tekne's packages with apt.

### 8.1 Theme: updates through APT

0.1's largest gap is updates. Devuan's packages update with `apt upgrade`, but
Tekne's own `tekne-*` packages reach an installed system only when someone builds
them from this repository and installs the `.deb`s by hand (DEC-006, §3.3). That
works for the maintainer and nobody else, and a fix to a firewall rule or a kernel
pin waits until each user rebuilds. DEC-006 said to revisit this after v0.1.

0.2 makes an installed Tekne updatable with apt alone: Tekne's packages are
published in a signed APT repository, held to the same rules as any outside
repository (DEC-026), and CI tests the upgrade from the last release on every build.
0.2 does little else, so that the new update path gets the release's full attention.

### 8.2 Goals
1. **A signed Tekne APT repository.** Installed systems get `tekne-*` updates with `apt update && apt upgrade`. The repository is held to DEC-026's rules like any third-party repository: its key is pinned by checksum in `tekne-apt-sources`, its `.sources` entry uses `Signed-By` with that key alone, and an APT pin limits it to `tekne-*` packages.
2. **Publishing behind the existing human gate.** The repository changes only when a person publishes a GitHub release (DEC-039), and it's built from that release's tested `.deb`s. Neither a push nor a tag reaches users' APT on its own.
3. **Tested upgrades.** On every build, CI installs the previous release from its published ISO and upgrades it to the current build through apt. This closes the `upgrade.py` gap in DEC-038's "Not covered".
4. **A defined path from 0.1.** A 0.1 system joins the repository with one documented step. After that, plain apt upgrades are enough.

### 8.3 Not in 0.2
§1's non-goals still apply. In particular:
- **Secure Boot (DEC-016).** Its kernel lockdown blocks hibernation (DEC-017), so it needs a design decision of its own, not packaging work. It's a candidate for a later spike.
- **Installer changes:** no manual partitioning, dual-boot or btrfs (DEC-005, DEC-018).
- **Dev builds in the repository.** Only tested pre-releases and releases are published. Dogfooding between candidates still uses `scripts/build.sh --packages-only`.
- **Devuan packages in the repository.** The repository carries Tekne's own packages only, and `tekne-installer` isn't published, since it belongs only in the live image.

### 8.4 Design
A summary; DEC-040 is the full decision.
- **Hosting:** GitHub Pages for this repository, next to the releases (DEC-020). Tekne's published `.deb`s total about 350 KB per release, well inside Pages' limits. Installed systems contact GitHub on `apt update`, as they already do for XLibre's repository. The URL, `https://graewolf.github.io/tekne/apt/`, is written into every installed system.
- **Suites:** `excalibur` carries releases. `excalibur-rc` carries pre-releases as well as releases, so a system that follows it also receives finals. Both have a `main` component and are generated with `apt-ftparchive` in the build container. `tekne-apt-sources` points at `excalibur`. A tester switches to `excalibur-rc` by editing one line of its `.sources` file.
- **Signing key:** a dedicated repository key, not anyone's personal key. Custody: the primary key stays offline with the maintainer. A signing subkey with a one-year expiry is a GitHub Actions secret in a `repo-publish` environment that needs the maintainer's approval to run, and only the publishing job can read it. That's the same split DEC-039 makes for the write token. Rotation ships the new public key in a `tekne-apt-sources` update before the old subkey expires.
- **Publishing:** the `release` job (DEC-039) also attaches the `tekne-*` `.deb`s, minus `tekne-installer`, to the draft release, so they're tested files too. A new `publish-repo` job runs when a person publishes that release (`release: published`). It checks each `.deb` against checksums recorded in the build's `build-info.txt`, regenerates the suites, signs them and deploys Pages.
- **Build isolation:** hook `0500` runs `apt-get update` with `tekne-apt-sources`'s files in place, so the Tekne source would be active inside the build chroot. The build disables it there, so an ISO only ever contains the packages built from its own commit.

### 8.5 Maintainer's answers (2026-10-01)
- **Q1, key custody:** a signing subkey held by CI behind an approval gate, with the primary key offline. Signing locally with the offline key was the alternative.
- **Q2, URL:** the plain `graewolf.github.io` address, not a domain of the maintainer's own.
- **Q3, pre-release suite:** yes, `excalibur-rc`.
- **Q4, anything else in 0.2:** no. Real artwork, a second-machine hardware check, DEC-035's option 3 and a Secure Boot spike all stay out.

### 8.6 Phases and acceptance criteria
Phase numbers continue from §7.

**Phase 7: Repository decisions**. ✔ Complete (2026-10-02). DEC-040 is Decided. The key exists, with its primary half on an offline USB stick. The `repo-publish` environment holds the signing subkey and its passphrase, and Pages deploys from GitHub Actions.
- DEC-040 for the repository (hosting, suites, key custody, publishing). DEC-006 gets a History line pointing to it, and §1, §3.1 and §3.3 change to match. Done 2026-10-01.
- (maintainer) Generate the key. Then create the `repo-publish` environment with the maintainer as required reviewer, store the signing subkey (`TEKNE_REPO_SIGNING_KEY`) and its passphrase (`TEKNE_REPO_SIGNING_PASSPHRASE`) as its secrets, and set Pages to deploy from GitHub Actions. Done 2026-10-02.
- ✅ The maintainer has marked the repository decision Decided, and Q1 to Q4 are answered. Passed 2026-10-01 (DEC-040, §8.5).
- ✅ The repository key exists. Its public half is in `packages/tekne-apt-sources/keys/` with a line in `SHA256SUMS`, and its fingerprint is in DECISIONS.md. The primary private key isn't on any machine or service CI can reach. Passed 2026-10-02: `tekne.gpg`, primary `2401BB77…D11D7B37` (DEC-040). Only the signing subkey goes to CI.

**Phase 8: Building and publishing the repository**. ✔ Complete (2026-10-03). `repo.py`, `live-boot.py` and all four `install.py` cases pass in CI. `v0.2-rc1` was built and tested by CI ([37076283810](https://github.com/GraeWolf/tekne/actions/runs/37076283810)); publishing it ran `publish-repo` ([37079968254](https://github.com/GraeWolf/tekne/actions/runs/37079968254)) after the maintainer's approval. Both suites verify against `keys/tekne.gpg` (signing subkey `82C3…F9F4`); `excalibur-rc` has the four packages at `0.2~rc1` and `excalibur` is empty. From this laptop (0.1), apt with the shipped source and pin offers `0.2~rc1` at 500, and the `.deb` it downloads matches the release's `build-info.txt`. GitHub renamed the `.deb` assets (`~` became `.`), which `ci-publish-repo.sh` handles by reading each package's contents. Publishing the final `v0.2` ([37126935156](https://github.com/GraeWolf/tekne/actions/runs/37126935156)) updated both suites to `0.2`, so the release path is confirmed too. `repo.py` checks the shipped files in the live image; Phase 9's upgrade test checks them on an installed system.
- A script builds a signed repository from a directory of `.deb`s with a given key. `tekne-apt-sources` ships the source, key and pin. The `release` job attaches the `.deb`s, and the `publish-repo` job publishes them.
- ✅ The same script, run locally with a throwaway test key, produces the same layout as CI, so the repository can be tested without the real key.
- ✅ On an installed system, `apt-cache policy` shows the Tekne repository offering only `tekne-*` packages. Everything else from it is at priority -1 (DEC-026 rule 3). The build's global-key check still passes, because the Tekne key is trusted only through `Signed-By`.
- ✅ The build never fetches from the published repository. Every `tekne-*` package in the manifest is the one built from this commit, and `0510-check-apt-origins` fails the build otherwise.
- ✅ apt refuses the repository when its index is signed by another key, or when a `.deb` doesn't match its `Packages` checksum. This is tested in QEMU against a local copy, not the live site.
- ✅ Publishing a pre-release updates `excalibur-rc` only, and publishing a release updates both suites. A push, a tag or an unpublished draft changes nothing, and `publish-repo` is the only job that can read the signing key.
- ✅ `publish-repo` refuses any `.deb` whose checksum differs from the one in that build's `build-info.txt`.

**Phase 9: Upgrade testing in CI**. ✔ Complete (2026-10-02). `tests/smoke/upgrade.py` installs v0.1 from its released ISO (pinned in `tests/smoke/previous-release`) with UEFI and LUKS, runs the one-time step, upgrades with `apt upgrade` from the build's test repository, reboots, and passes every installed-system check, hibernate/resume included. CI's first run with it ([37067604103](https://github.com/GraeWolf/tekne/actions/runs/37067604103), `acbcf50`) was green in 39 minutes, moving all four packages from `0.1` to `0.2~rc1~dev57`.
- `tests/smoke/upgrade.py` can start from a release ISO and upgrade through apt from a repository served to the VM. That repository is built by Phase 8's script with the test key. Only the URL and the key differ from what installed systems use. The pin and the rest of the `.sources` entry are the shipped ones.
- ✅ The previous release's ISO is a pinned input: its checksum is committed in this repository and updated at each release, and CI checks the download against it.
- ✅ On every CI build, a UEFI+LUKS system installed from the previous release's ISO upgrades to the current build with `apt update && apt upgrade`, then passes `installed-checks.sh` and hibernate/resume. Until 0.2 is out, the previous release is 0.1, so this test also runs Goal 4's one-time step.

**Phase 10: Migration, docs, and the 0.2 release**. ✔ Complete (2026-10-03). The docs are written (README, `docs/customizing.md`, `docs/building.md`'s repository, key and rotation sections, CHANGELOG), and `tests/key-rotation.sh` passes on the host and in CI's build container ([37071566366](https://github.com/GraeWolf/tekne/actions/runs/37071566366)). The development laptop, on 0.1, joined `excalibur-rc` with the one-time step and upgraded to `0.2~rc1`; after dogfooding rc1 (no rc2, maintainer's decision), [Tekne 0.2](https://github.com/GraeWolf/tekne/releases/tag/v0.2) was built and tested by CI from its tag ([37124396622](https://github.com/GraeWolf/tekne/actions/runs/37124396622), all four test suites) and published into `excalibur` and `excalibur-rc`. The laptop then reached 0.2 with a plain `apt update && apt upgrade`. An install from the published 0.2 ISO, in QEMU with UEFI and LUKS, fetched the live repository on its first `apt update` and had nothing upgradable.
- README ("Update an installed Tekne"), `docs/customizing.md`, `docs/building.md` (publishing and key rotation), and CHANGELOG with 0.1's one-time step. DEC-039 is updated for the extra assets and the `publish-repo` job.
- ✅ (maintainer) The development laptop, running 0.1, joins `excalibur-rc` with the documented one-time step and installs `0.2-rc1` from it with `apt upgrade`. The next release then arrives with plain `apt update && apt upgrade`: a candidate or 0.2 itself, since `excalibur-rc` carries both. (Until 2026-10-03 this said "the next candidate"; the maintainer chose to dogfood rc1 and release 0.2 directly, without an rc2.)
- ✅ The key-rotation steps work against test keys: a system that trusts the old subkey accepts a `tekne-apt-sources` update carrying the new one, then verifies a repository signed with it.
- ✅ `v0.2` is released through CI (DEC-039), and publishing it updates `excalibur`. On a system freshly installed from the 0.2 ISO, `apt list --upgradable` shows no `tekne-*` packages.

## 9. Tekne 0.3

> **Status:** Agreed by the maintainer on 2026-10-03 (answers in §9.6). The new
> decisions are DEC-041 (NVIDIA), DEC-042 (autologin) and DEC-043 (the symbols
> font). On 2026-10-05, after the Phase 11 spike, the maintainer redesigned DEC-041 and
> added DEC-044 (hardware quirks) and DEC-045 (X's seat backend); answers in §9.6.
> Nothing is built yet.

### 9.1 Theme: the hybrid-graphics laptop as a daily driver

0.1 made Tekne installable, and 0.2 made it updatable. The development laptop
runs it every day, and it still has gaps:
- Its NVIDIA GPU runs on `nouveau` (release candidate gate, §7).
- It asks for two passwords on every boot: LUKS, then the console login.
- The bar shows text labels.
- `nmtui` opens as a tiled window.
- `~/Documents` and the other user directories don't exist, because nothing runs `xdg-user-dirs-update`. Tekne has no XDG autostart.
- Some everyday tools are missing.

0.3 is about the machine Tekne already runs on:
1. The proprietary NVIDIA driver, working the systemd-free way, with suspend, hibernate and power-down of the idle GPU.
2. One passphrase from power-on to desktop on encrypted installs.
3. Fixes for the daily annoyances, in the packages that ship the defaults.

The NVIDIA driver is the hard part and gets the most attention. The Phase 11 spike
found that Devuan's driver doesn't build for Tekne's kernel. NVIDIA's own works with
XLibre (DEC-027), but brought two resume problems with it that Tekne fixes for all
installs (DEC-044, DEC-045). The rest is small configuration work that QEMU can test.

### 9.2 Goals
1. **NVIDIA proprietary driver, opt-in.**
   - Two opt-in packages, published in Tekne's repository (DEC-041). `tekne-nvidia-repo` adds NVIDIA's Debian 13 repository under DEC-026's rules. `tekne-nvidia` installs NVIDIA's current driver from it and makes it work without systemd:
     - suspend and hibernate through the driver's kernel notifiers, with no hook
     - runtime power management, so the discrete GPU sleeps when idle on battery
     - a PRIME render-offload launcher
   - Resume works reliably on every install, NVIDIA or not: X takes its seat from elogind (DEC-045), and a device-matched quirk brings back ASUS keyboards that deep sleep resets (DEC-044).
   - The internal display stays on the integrated GPU. If the NVIDIA module fails to build or load, the desktop still works.
   - Removing the package goes back to `nouveau`.
2. **Autologin after LUKS.**
   - On encrypted installs, the LUKS passphrase is the only password needed to reach the desktop. tty1 logs the user in automatically and starts the session. The lock screen, `sudo` and other ttys still ask for the password.
   - Plain (unencrypted) installs keep the password login.
   - New installs choose this in the installer. Existing installs, such as the laptop, turn it on with one command.
3. **Desktop polish** (`tekne-config`, `tekne-desktop`):
   - **Bar:** Nerd Font icons in the right-hand modules, the clock in the centre, and all nine tags on the left, coloured as active, occupied or empty.
   - **Floating windows:** `nmtui` and Blueman open as floating, centred windows when launched from the bar.
   - **Shell:** `bat` instead of `cat`, and `fastfetch` when an interactive terminal opens.
   - **Session:** the ssh-agent keeps a key once its passphrase is entered, and XDG user directories exist.
   - **Packages:** `ffmpeg` and `imagemagick` are installed by default.

### 9.3 Not in 0.3
§1's non-goals still apply. Of the candidates from §8.3, §8.5 and 0.2's known limitations:
- **Secure Boot (DEC-016).** It already conflicts with hibernation (DEC-017), and a DKMS-built NVIDIA module is unsigned, so Secure Boot would also need a machine-owner key and module signing. Design that once, after the NVIDIA work exists. Adding it first would mean designing it twice.
- **Manual partitioning and dual-boot (DEC-005).** They multiply the install matrix, and the only real user runs whole-disk LUKS.
- **Real artwork (DEC-034).** This needs an artist, not engineering. DEC-034 already allows same-named files to replace the placeholders, so the art can arrive in any `tekne-branding` update.
- **A second machine.** There isn't one. `tekne-nvidia` is the first hardware-specific package, and docs/testing.md gets an NVIDIA section, so other hybrid laptops can report results.
- **Devuan testing (Freia), and newer alacritty, neovim and fastfetch.** 0.3 uses Excalibur's versions. A newer neovim waits for 0.4 (Q6). See §9.5.
- **The installer offering the NVIDIA driver.** The driver needs DKMS, a compiler and kernel headers, roughly 90 packages. Shipping them would push the ISO past GitHub's 2 GiB asset limit (DEC-020): the last local build is already 1.85 GiB. Fetching them during install would add a network dependency the installer doesn't have. In 0.3 it's a few apt commands after installing (DEC-041), and the installer prints that hint when it sees an NVIDIA GPU.
- **Outputs wired to the NVIDIA GPU (HDMI on the development laptop).** Rootless X can't get modesetting permission from NVIDIA's DDX (DEC-041). Phase 11 runs a root-X test to find the cause, but HDMI doesn't block 0.3 (§9.6, P8).
- **The GPU powering off on AC.** TLP keeps it powered when plugged in. Documented for 0.3 and revisited later (P7).
- **DEC-035 (the Devuan console greeting).** The maintainer kept option 1 (Q4), even though autologin edits the same tty1 getty line.
- **A Bluetooth bar module.** The tray icon is enough (Q5). Blueman's manager window floats and is centred however it's opened.

### 9.4 Proposed design

**NVIDIA (DEC-041, redesigned 2026-10-05).** The Phase 11 spike (`spike/phase11/README.md`) found:
- **Devuan's driver doesn't build.** 550.163.01 is Devuan's only driver. The backports build supports kernels up to 6.17, but Tekne runs 7.1 (DEC-036). Debian's 7.0 fixes are only in sid and forky.
- **NVIDIA's own works.** 615.71.09 from NVIDIA's Debian 13 repository uses open kernel modules (Turing and newer), builds for 7.1, and pulls in no systemd package. Its own modprobe settings make the kernel handle suspend and hibernate (`NVreg_UseKernelSuspendNotifiers=1`).
- **It runs with XLibre.** XLibre loads NVIDIA's DDX despite the ABI mismatch. Offload rendering works, and the idle GPU powers off on battery.

`tekne-nvidia-repo` (Architecture all) ships NVIDIA's repository `.sources` entry, its checksum-pinned key, and a pin that admits only the driver's six source packages. Everything else from NVIDIA, CUDA included, gets -1. It follows DEC-026, whose rule 2 now allows an opt-in package to carry a repository, so systems without NVIDIA never contact it.

`tekne-nvidia` (Architecture all) would:
- Depend on `nvidia-driver` and `nvidia-kernel-open-dkms` from that repository, and on `linux-headers-amd64` from backports through DEC-036's existing kernel pin. It doesn't pull in `nvidia-persistenced` (which keeps the GPU initialised) or `nvidia-settings`.
- Ship modprobe options (`NVreg_DynamicPowerManagement=0x02`, `nvidia-drm` `modeset=1`) and a udev rule enabling runtime power management for the GPU's HDMI audio function, which NVIDIA's rules leave out.
- Ship `tekne-prime-run CMD`, which sets the PRIME offload variables. X stays on `amdgpu`, so a missing or broken module costs offload, not the desktop.
- Have no sleep hook.
- Not be in the ISO and not be installed by default.

Every build compiles NVIDIA's open module against the kernel the ISO ships, so a backports kernel that breaks the driver can't reach a release unnoticed. The 7.1.13 → 7.2.6 backports move, under way on 2026-10-05, is the first real case.

**Resume fixes from the spike (all installs).**
- **X's seat backend (DEC-045).** NVIDIA forces a VT switch on every suspend. Under seatd, X sometimes never got its seat back (2 of 4 hibernates froze its input), while with libseat's logind backend 5 of 5 resumes worked. `tekne-startx.sh` exports `LIBSEAT_BACKEND=logind`.
- **ASUS keyboard after deep sleep (DEC-044).** s0i3 reboots the ITE 8910 keyboard's controller (`0b05:19b6`). An elogind hook in `/usr/libexec/system-sleep/` re-probes that device after resume, and does nothing on other machines.
- **TLP's sleep hook (DEC-025).** `tlp` puts it in `/usr/lib/elogind/system-sleep/`, which Devuan's elogind never reads. `tekne-config` runs it from `/usr/libexec/system-sleep/49-tekne-tlp`, a wrapper that does nothing without tlp.

**Autologin (DEC-042).**
- **Where it's set.** `/etc/inittab` isn't a conffile. `sysvinit-core`'s postinst generates it, and the installer already rewrites it (`tekne-install`). For new installs, the installer asks "Log in automatically after unlocking?" when LUKS is chosen and adds `--autologin USER` to tty1's getty line. Existing installs use `tekne-autologin on|off` from `tekne-config`. It refuses unless `/` is on dm-crypt. Package scripts never edit inittab.
- **Keyring (DEC-030).** With autologin, PAM never sees a password, so the `login` keyring starts locked. The first app that needs a secret (Brave, Melia) asks for the password once per session (Q2). The secrets stay encrypted with the login password, not only by LUKS.
- **Locking.** `xss-lock` already locks before suspend and hibernate, so resuming still needs the password. Autologin affects only a fresh boot, after the LUKS passphrase.
- **No restart loop.** A broken X (for example a bad NVIDIA setup) would otherwise loop: startx fails, getty respawns, autologin starts X again. `tekne-startx.sh` stops using `exec`. If X exits with an error within a few seconds, it leaves a marker for the rest of the boot and stays on a console shell. tty2–6 keep normal logins.

**Desktop polish.**
- **Nerd Font symbols.**
  - Neither Devuan nor Debian packages Nerd Fonts. The packaged alternatives, `fonts-font-awesome` 4.7 and `fonts-material-design-icons-iconfont`, have the bar's icons but not the wider Nerd Fonts set.
  - Tekne vendors the Nerd Fonts "Symbols Only" release (MIT licence), pinned by SHA-256 like live-build's `.deb`, into `tekne-config`, with a fontconfig fallback (Q3, DEC-043). That way JetBrains Mono shows the symbols in polybar and alacritty alike.
- **polybar:**
  - Icons with no text for volume, Wi-Fi (with the SSID kept), Ethernet, battery (an icon that changes with charge level) and the clock.
  - `modules-center = date`, and the window title shortened to fit.
  - `xworkspaces` shows empty tags in `disabled`, occupied tags in `foreground` and the active tag on `primary`. Urgent tags keep `alert`.
- **Floating windows.**
  - The bar starts `nmtui` with `tekne-terminal --class tekne-float`.
  - herbstluftwm rules float and centre `instance=tekne-float`, `class=Blueman-manager` and `class=Pavucontrol`. The bar's right-click on the volume module opens Pavucontrol, so it's included for consistency.
  - Blueman stays in the tray, with no Bluetooth bar module (Q5). The rule applies however its manager window is opened.
- **Shell.**
  - Debian installs `bat` as `batcat`.
  - `tekne-config` ships `/usr/share/tekne/bash/tekne.bashrc`:
    - aliases `cat='batcat --paging=never'` and `bat=batcat`
    - runs `fastfetch` in interactive shells started by `tekne-terminal` (not on ttys, over SSH, or in nested shells)
    - an opt-out file, like `no-startx`
  - `/etc/skel/.bash_aliases` sources it, and Debian's default `.bashrc` already reads that file. Existing users add one line, given in the CHANGELOG, because Tekne never writes into an existing home.
- **fastfetch logo.** fastfetch would show Devuan's logo, because `ID_LIKE=devuan`, and §3.7 removes Devuan logos from user-visible branding. Tekne ships a fastfetch config with a text-art Tekne logo and Tokyo Night colours.
- **ssh-agent.** It's already running: Devuan's Xsession starts it (`use-ssh-agent` in `/etc/X11/Xsession.options`). What's missing is `AddKeysToAgent yes`, shipped as `/etc/ssh/ssh_config.d/tekne.conf`. A passphrase is then asked once per X session.
- **XDG user directories.** `xdg-user-dirs` is installed, but its autostart entry is for desktop environments, and herbstluftwm doesn't run it. `tekne-session` runs `xdg-user-dirs-update` at every login. It's idempotent, so new and existing users both get the directories on their next login.
- **`ffmpeg`, `imagemagick`, `bat` and `fastfetch`.** These are added to `tekne-desktop`'s Depends. All are in Excalibur `main`. The ISO's size increase is measured against DEC-020's limit.

### 9.5 Devuan testing (Freia)

The maintainer asked whether Tekne should move to testing because stable is outdated.
Recommendation: **not for 0.3, and probably never as the base.** Instead, fix specific
packages, and prepare for Freia while it's still testing.

What testing would bring today (Debian trixie compared with forky, which is what Excalibur and Freia track):
- `neovim` 0.10 → 0.12, `alacritty` 0.15 → 0.17, `fastfetch` 2.40 → 2.67.
- Not the NVIDIA driver (550 in both), `polybar` or `herbstluftwm` (the same versions).
- Not the kernel or Mesa either: backports already has kernel 7.1 (forky has 7.2) and Mesa 26.1.6 (the same as forky).

What it would cost:
- **Security.** Debian's security team doesn't support testing. Fixes reach it through unstable, often days or weeks later, and Devuan adds its own lag. That's a poor fit for a daily driver whose firewall and pins are meant to be dependable (DEC-023, DEC-026).
- **Breakage that lands on Tekne.** Transitions break testing for days at a time. Devuan also has to follow every Debian change towards systemd with a fork, so Freia lags and breaks in ways Excalibur doesn't.
- **Releases.** A Tekne release would be a snapshot of a moving target, and CI's "repeatable build" (§5.3) would drift daily. The Brave and XLibre repositories would need Freia suites too.
- **Timing.** Forky is expected to freeze in 2027, and Devuan Freia becomes stable some months after Debian 14. A move made now would have a short life before Freia is stable anyway.

Alternatives, roughly from least to most work:
1. **Backports, per package**, the way DEC-036 does the kernel: pin named packages from `excalibur-backports` when they're there.
2. **Upstream releases for one or two tools**, verified and installed on demand, like `tekne-get-melia` (DEC-029).
3. **A non-blocking CI job that builds and boots Tekne against Freia.** Breakage then shows up early, and moving to Freia when it becomes stable is planned work rather than a surprise. This could become 0.4's theme.

**The packages that matter (Q6): alacritty, neovim and fastfetch.** None of them is in
`excalibur-backports` (checked 2026-10-03), so option 1 doesn't apply. 0.3 keeps
Excalibur's versions: fastfetch 2.40 already does what Goal 3 needs. A newer neovim waits
for 0.4, and how to provide it is decided when 0.4 is planned. The candidates are a
verified upstream tarball and the Freia CI job. Alacritty has no Linux binaries upstream,
so it most likely waits for Freia to become stable. The options:

| | Excalibur | Freia | Upstream binaries | Rebuilding Freia's source for Excalibur |
|---|---|---|---|---|
| fastfetch | 2.40.4 | 2.67.1 | Yes: a `.deb` per release | Easy: C and CMake |
| neovim | 0.10.4 | 0.12.4 | Yes: a Linux x86_64 tarball per release | Moderate: newer libuv, LuaJIT and tree-sitter |
| alacritty | 0.15.1 | 0.17.0 | No Linux binaries | Hard: Debian builds Rust programs from packaged crates, which Excalibur has in older versions |

### 9.6 Maintainer's answers (2026-10-03)
- **Q1, NVIDIA source:** Devuan's `excalibur-backports`, with DEC-036's pin extended to the driver packages (DEC-041). NVIDIA's own repository was the alternative.
- **Q2, keyring with autologin:** one password prompt per session, at the first app that needs a secret (DEC-042). An empty-password keyring was the alternative.
- **Q3, symbols font:** vendor Nerd Fonts' "Symbols Only" font, pinned by checksum (DEC-043). The packaged Font Awesome and Material Design fonts were the alternative.
- **Q4, DEC-035:** no. The console greeting keeps Devuan's text.
- **Q5, Bluetooth:** the tray icon is enough.
- **Q6, testing:** the packages that feel too old are alacritty, neovim and fastfetch. None of them is in backports. 0.3 keeps Excalibur's versions, and neovim waits for 0.4 (§9.5).
- **Q7, fastfetch and `cat`:** as proposed. fastfetch runs in every new terminal, and `cat` is aliased to `batcat --paging=never`.

**After the Phase 11 spike (2026-10-05):**
- **P1, driver source:** NVIDIA's Debian 13 repository, under DEC-026 (DEC-041). This replaces Q1's backports, whose 550 driver doesn't build on 7.1.
- **P2, enabling it:** an opt-in `tekne-nvidia-repo` package, not `tekne-apt-sources`, so systems without NVIDIA never contact NVIDIA's server. Shipping it enabled everywhere, or disabled with a helper, were the alternatives.
- **P3, sleep hook:** none. 615's kernel notifiers handle suspend and hibernate.
- **P4, ASUS keyboard:** a device-matched hook in `tekne-config`, recorded as DEC-044 "Hardware quirks", and reported upstream to `hid-asus`.
- **P5, X's seat backend:** `LIBSEAT_BACKEND=logind` is the default for all installs (DEC-045).
- **P6, TLP's sleep hook:** `tekne-config` links it into `/usr/libexec/system-sleep/`.
- **P7, GPU power on AC:** accepted and documented for 0.3; revisit later.
- **P8, HDMI:** run the root-X test to find the cause, but HDMI doesn't block 0.3.

### 9.7 Phases and acceptance criteria
Phase numbers continue from §8.

**Phase 11: Decisions and the NVIDIA spike**. In progress. The spike's kit, results and findings are in `spike/phase11/` (`1bf9e27`). DEC-041 was redesigned and DEC-044 and DEC-045 added on 2026-10-05.
- DEC-041, DEC-042 and DEC-043, with History lines on the Decided entries they amend (DEC-016, DEC-027, DEC-030, DEC-036, DEC-040). Done 2026-10-03. After the spike: DEC-041 redesigned, DEC-044 and DEC-045 added, and History lines on DEC-025, DEC-026, DEC-027, DEC-036 and DEC-040. Done 2026-10-05.
- (maintainer) On the laptop, after a backup, install the NVIDIA driver by hand. Attempt 1 used `excalibur-backports`, whose module didn't build. Attempt 2 used NVIDIA's repository (`spike/phase11/install-nvidia-repo.sh`). The driver is removable with `spike/phase11/rollback.sh`, and tty2 stays available for recovery.
- ✅ The DKMS module builds against Tekne's current backports kernel. Passed 2026-10-03 on 7.1.13 with NVIDIA 615. Recheck on 7.2.6 once backports finishes moving.
- ✅ With XLibre, the desktop stays on the AMD GPU. An offloaded program runs on the NVIDIA GPU: `glxinfo` with the offload variables reports NVIDIA. Passed 2026-10-03, Vulkan too.
- ✅ Suspend/resume and hibernate/resume work with the module loaded. On battery, the GPU's runtime status is `suspended` when idle. Passed 2026-10-03 with the spike's equivalents of DEC-044 and DEC-045 (5 of 5 resumes). On AC the GPU stays on (P7). Without DEC-045, 2 of 4 hibernates froze X's input.
- ✅ External monitors work on the ports wired to the AMD GPU. For ports wired to the NVIDIA GPU (HDMI), a test with X running as root shows whether "Failed to acquire modesetting permission" is a permissions problem, and the result is recorded in DEC-041. HDMI doesn't block 0.3 (P8). Not done yet: it needs an external monitor.

**Phase 12: Desktop polish**. ✔ Complete (2026-10-05). Built in `22de822`, `1da1281`, `a641c00` and `026a241`. Along the way, Debian's move to kernel 7.2.6 needed three fixes: `linux-base` in DEC-036's pin (`2f660b7`), the installer copying `/boot` in a second pass because of 7.2's cross-filesystem hard links (`b82ad10`), and a checked `pkgmaster.devuan.org` fallback for a lagging mirror (`eab2683`). CI on `master` passed every test at `eab2683` (run 37305665749), including the upgrade from v0.2 and the new per-user checks. On the laptop (packages `0.3~rc1~dev77`, kernel 7.2.6, NVIDIA 615 rebuilt by DKMS), the maintainer confirmed the bar, the terminal, the floating pop-ups, the ssh-agent, and suspend and hibernate with the packaged hooks and no `~/.xserverrc`. With the keyboard hook disabled, 7.2.6 still loses the keyboard, and the `hid-asus` report was sent on 2026-10-05.
- `tekne-config` and `tekne-desktop` changes from §9.2 Goal 3, and the resume fixes from §9.4: DEC-045's `LIBSEAT_BACKEND=logind`, DEC-044's keyboard hook, and the TLP hook link. docs/desktop-stack.md §2 is updated for the seat backend.
- ✅ Every added package exists in Excalibur and passes the no-systemd check, the vendored font is checksum-pinned (DEC-043), and the ISO stays under 2 GiB.
- ✅ In the live session, `live-boot.py` checks that:
  - polybar runs with Tekne's config
  - `fc-match` finds the symbols font
  - `/etc/ssh/ssh_config.d/tekne.conf` sets `AddKeysToAgent`
  - the herbstluftwm rules float and centre `tekne-float`, Blueman's manager and Pavucontrol
  - X logged "Seat opened with backend 'logind'" (DEC-045). Installed systems run no X during the tests, so this is checked in the live session
- ✅ On each installed system, `install.py` checks that:
  - the user's XDG directories exist after the first login
  - an interactive `tekne-terminal` shell has the `cat` alias
  - fastfetch shows the Tekne logo, not Devuan's
  - tty1's `startx` gets `LIBSEAT_BACKEND=logind` (DEC-045), and the existing hibernate/resume checks still pass
  - `/usr/libexec/system-sleep/` has TLP's hook wrapper and the ASUS keyboard hook, which does nothing in QEMU (no such device)
- ✅ (maintainer) In QEMU and on the laptop: the bar shows the icons, the centred clock and all nine tags in three states. `nmtui` and Blueman open floating and centred from the bar, and an SSH key's passphrase is asked once per session.
- ✅ (maintainer) On the laptop, with the spike's `~/.xserverrc` and hooks removed and the packaged ones installed, suspend and hibernate resume with a working internal keyboard. The `hid-asus` report has been filed.

**Phase 13: `tekne-nvidia`**
- `tekne-nvidia-repo` and `tekne-nvidia` from §9.4 (DEC-041), published in Tekne's repository with the other four, and documented in `docs/customizing.md` and docs/testing.md. The spike's files are replaced by the packages, and `spike/phase11/` is removed, kept in git history like Phase 0's.
- ✅ `tekne-nvidia-repo`'s key matches its recorded checksum, and the build's global-key check still passes. On an installed system, `apt-cache policy` shows NVIDIA's repository offering only the driver's six source packages; everything else from it, `cuda-*` and `nvidia-driver-pinning-*` included, is at -1.
- ✅ Every build compiles NVIDIA's open DKMS module against the kernel the ISO ships, from a source verified by the repository's signature, and fails if it doesn't build.
- ✅ In QEMU (no NVIDIA GPU), installing both packages on an installed UEFI+LUKS system leaves it booting to the desktop and passing `installed-checks.sh`, hibernate/resume included. Purging them passes the same checks. Installing pulls in no systemd package.
- ✅ (maintainer) On the laptop, with the spike rolled back, the documented install steps give Phase 11's results without any manual step. Purging brings back `nouveau`.

**Phase 14: Autologin after LUKS**
- The installer question, `tekne-autologin` and the change to `tekne-startx.sh` (DEC-042). docs/installer.md and docs/desktop-stack.md §2 are updated.
- ✅ `install.py`'s LUKS cases enable autologin. After the passphrase, the session starts on tty1 with no login, and the lock screen still asks for the password. The plain cases still need a password login and still unlock the keyring through PAM (DEC-030).
- ✅ `tekne-autologin on` refuses on a system without an encrypted root.
- ✅ With a deliberately broken X configuration, tty1 starts X at most twice and then stays on a console shell. tty2 still offers a normal login.
- ✅ (maintainer) On the laptop (0.2, upgraded through apt), `tekne-autologin on` gives one passphrase from power-on to desktop.

**Phase 15: Docs and the 0.3 release**
- README, `docs/customizing.md` (the shell snippet line for existing users, NVIDIA and autologin), docs/testing.md, and the CHANGELOG.
- ✅ `v0.3-rc1` is released through CI (DEC-039) and published to `excalibur-rc`. The laptop upgrades to it with `apt upgrade` and is dogfooded.
- ✅ `v0.3` is released and published to `excalibur`. CI's upgrade test from v0.2 passes, and a fresh 0.3 install has no `tekne-*` packages to upgrade.

## 10. Notes for Claude Code sessions
- Keep SPEC.md and DECISIONS.md current. When a decision's status or content changes, update DECISIONS.md (with a dated History line) and every doc that references its `DEC-nnn` ID in the same commit.
- Before adding any package, check that it exists in Excalibur and run the no-systemd check. Package names and systemd-free substitutes change between releases.
- Never download build inputs without pinning them (a checksum or container digest).
