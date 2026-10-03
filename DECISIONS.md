# Decision Log

Each decision has a permanent ID (`DEC-nnn`) that never changes. Its current state
is in the **Status** line:

- **Decided**: confirmed by the maintainer.
- **Proposed**: a default that needs confirmation. It's safe to build on until changed.
- **Open**: needs an answer before the phase listed.
- **Superseded**: replaced by another decision (named in the entry).

When a decision changes, edit the entry in place and add a dated line to its
**History**. Don't delete entries or reuse IDs.

---

### DEC-001 Base: Devuan Excalibur
- **Status:** Decided
- **Why:** Excalibur is the current Devuan stable release. Daedalus is oldstable, and starting a new distro on it would shorten the support window for no benefit.
- **History:** 2026-09-28 decided.

### DEC-002 Init: sysvinit
- **Status:** Decided
- **Why:** It's Devuan's default and the best-tested path. runit and OpenRC are out of scope for v1.
- **History:** 2026-09-28 decided.

### DEC-003 Build tool: Debian's live-build, pinned
- **Status:** Decided, confirmed by Phase 0
- **What:** Debian trixie's `live-build` `1:20250505+deb13u1`, pinned by SHA-256, pointed at Devuan's mirrors and keyring. **Not** Devuan's own `live-build` package.
- **Why:** It's scriptable, well documented, and supports hybrid ISOs, package lists, hooks, and local `.deb` injection. Devuan's package (`4.0.3-1+devuan2`) is a 2016 fork of jessie-era live-build that was never updated. It has no `grub-efi` stage, so it can't build a UEFI-bootable ISO.
- **Phase 0 result:** The spike (`spike/phase0/`, removed in Phase 1 but kept in git history at `f96d08e`) built a 317 MB console-only hybrid ISO. It booted to a login prompt in about 16 s on both SeaBIOS and OVMF, with sysvinit as PID 1.
- **Required `lb config` settings** (full list in `live-build/auto/config`):
  - `--mode debian --distribution excalibur --parent-distribution excalibur`
  - Every `--mirror-*` and `--parent-mirror-*` option set to `http://deb.devuan.org/merged/`. Security then resolves to `excalibur-security` correctly.
  - `--keyring-packages devuan-keyring`
  - `--initsystem sysvinit`. live-build then adds `live-config-sysvinit` and `sysvinit-core`.
  - `--bootloaders "grub-pc grub-efi"`: GRUB for both firmware types, so one menu config and later one GRUB theme. The default BIOS loader (isolinux) has no menu timeout.
  - `--uefi-secure-boot disable` (DEC-016)
- **Carry into Phase 1:**
  - The build container needs Devuan's `debootstrap` (it has the `excalibur` script).
  - Install Debian's live-build `.deb` in the container, checksum-verified. The spike runs it from source, which needs a `dpkg-parsechangelog` shim.
  - Keep live-build's package cache outside the per-build work directory. The spike deletes it on every run, so rebuilds re-download everything.
  - The spike turned live-build's firmware autodetection off (`--firmware-chroot false`). Phase 2 must list DEC-013's firmware packages explicitly or prove that autodetection works against Devuan's mirrors.
- **Fallback (not needed):** Devuan live-sdk or refracta tooling.
- **History:** 2026-09-28 decided, pending Phase 0. Same day, Phase 0 confirmed it, and the choice was narrowed to Debian's current live-build after Devuan's fork was found to lack UEFI support.

### DEC-004 Desktop: herbstluftwm on X11
- **Status:** Decided
- **Why:** Keyboard-driven manual tiling, fully scriptable at runtime through `herbstclient`, with a small footprint and no desktop-environment dependencies to untangle from systemd. It suits the technical audience (DEC-007).
- **Consequence:** Every component a desktop environment would normally provide has to be chosen explicitly (DEC-025). Wayland is out of scope, because herbstluftwm is X11-only.
- **History:** 2026-09-28 decided.

### DEC-005 Installer: gum TUI, guided whole-disk, optional LUKS
- **Status:** Decided
- **Scope (v1):** One target disk, fully wiped. Filesystem per DEC-018. Optional LUKS2. BIOS and UEFI. No manual partitioning or dual-boot.
- **Why:** This is the smallest installer that covers a daily-driver laptop. Every extra layout multiplies the test matrix.
- **History:** 2026-09-28 decided.

### DEC-006 In-repo `.deb` packages, no hosted repository
- **Status:** Decided. Its "no hosted repository" part is superseded from 0.2 by DEC-040.
- **Why:** Packaged config survives upgrades, can use `dpkg-divert` for files owned by other packages, and can be cleanly removed. Hosting a repo is deferred to keep v1 small.
- **Consequence:** In 0.1, installed systems don't receive Tekne package updates automatically. From 0.2 they do, through Tekne's own APT repository (DEC-040). Tekne's packages are still built in this repository and baked into the ISO, so installs need no network.
- **History:** 2026-09-28 decided. 2026-10-01: revisited after v0.1, as planned; the maintainer chose a signed Tekne APT repository for 0.2 (DEC-040).

### DEC-007 Audience: technical users
- **Status:** Decided
- **Consequence:** No GUI settings apps. The docs may assume Linux literacy. Discoverability is handled with a keybinding cheatsheet.
- **History:** 2026-09-28 decided.

### DEC-008 Name: Tekne
- **Status:** Decided
- **Form:** "Tekne" in prose and user-facing text (`os-release` `NAME`, GRUB, the installer); `tekne` for identifiers: `ID=tekne`, package names (`tekne-*`), paths (`/usr/share/tekne`, `/etc/tekne`), commands (`tekne-install`, `tekne-session`, ...), the `inet tekne` firewall table and the ISO file name. It's Greek (τέχνη) for craft.
- **Migration:** the project was called satori until 0.1-rc2 development. Each `tekne-*` package `Conflicts:` and `Replaces:` its `satori-*` predecessor, so one `apt install --purge ./out/packages/tekne-{apt-sources,branding,config,desktop}_*.deb` removes the satori packages (with their diversions, alternatives and firewall table) and installs Tekne's; `tests/smoke/upgrade.py` checked this on a satori UEFI+LUKS install. Things an install already has keep their old names: the LUKS mapping (`satori_root`), the hostname, and the UEFI boot entry until GRUB is reinstalled.
- **History:** 2026-09-28 decided as "satori". 2026-09-30: the maintainer renamed the distribution to Tekne; the placeholder art changed from an ensō (satori's Zen meaning) to a geometric T (DEC-034).

### DEC-009 Architecture: amd64 only
- **Status:** Decided
- **History:** 2026-09-28 decided.

### DEC-010 Definition of "systemd-free"
- **Status:** Decided
- See [SPEC.md §4](SPEC.md#4-the-no-systemd-rule). A package whose name contains `systemd` is allowed only through a commented entry in `tests/systemd-allowlist.txt`.
- **Allowlist:** empty. Phase 0 allowlisted `libsystemd0`, a shared library with no daemon that `libpam-modules` depends on. The desktop image doesn't have it: Devuan's `libelogind-compat` replaces it (docs/desktop-stack.md), and the `0.1-rc1` manifest has no package whose name contains `systemd`.
- **Required substitutions:**
  - `opensysusers` (Devuan's systemd-free implementation) for the virtual package `systemd-sysusers`. Without it, apt satisfies dependencies like `cron-daemon-common`'s `systemd | systemd-standalone-sysusers | systemd-sysusers` with Debian's `systemd-standalone-sysusers`, which is built from systemd's source. `opensysusers` must be in the base package list.
  - Devuan provides `eudev` (and `libudev1` from it) in place of systemd's udev. This needs no action.
- **History:** 2026-09-28 decided. Same day, Phase 0 finalised the allowlist and recorded the `opensysusers` substitution. 2026-09-29: the maintainer emptied the allowlist, since `libsystemd0` no longer appears in the image.

### DEC-011 Networking: NetworkManager (nmcli/nmtui)
- **Status:** Decided
- **Why:** Best Wi-Fi/VPN coverage and works under Devuan with elogind. `nmcli`/`nmtui` suit the audience. connman and ifupdown are weaker on laptops.
- **UI:** No tray applet. Wi-Fi is managed with `nmtui`/`nmcli`, and clicking polybar's network module opens `nmtui`.
- **History:** 2026-09-28 proposed and confirmed. Same day, the maintainer dropped `nm-applet` in favour of `nmtui` only.

### DEC-012 Audio: PipeWire (pipewire-pulse, WirePlumber)
- **Status:** Decided, verified on real hardware
- **Why:** It's the Trixie-era default. Without systemd user units, the X session starts it from autostart ([docs/desktop-stack.md](docs/desktop-stack.md) §2).
- **Risk:** This is the component most likely to misbehave without systemd. Phase 2 has to confirm it works on real hardware.
- **History:** 2026-09-28 proposed and confirmed. 2026-09-29: verified in QEMU (Phase 2) and on the development laptop (speakers, headphones, microphone, volume keys).

### DEC-013 Include non-free firmware
- **Status:** Decided
- **Why:** A laptop daily driver without Wi-Fi or GPU firmware isn't usable. This means enabling the `non-free-firmware` area plus `firmware-linux`, `firmware-iwlwifi`, `firmware-realtek`, `firmware-amd-graphics`, and so on.
- **History:** 2026-09-28 proposed and confirmed.

### DEC-014 Login: console login on tty1 + `startx`, no display manager
- **Status:** Decided
- **Why:** It's the simplest setup and has the fewest moving parts. elogind still registers the session through PAM. The live session autologins on tty1.
- **Alternative:** LightDM, if a graphical greeter is wanted later.
- **Live session:** autologin on tty1–6 comes from Tekne's own live-config component (`live-build/config/includes.chroot/usr/lib/live/config/0161-tekne-autologin`), using agetty's `--autologin`. live-config's `0160-sysvinit` is broken on Excalibur (see docs/desktop-stack.md §2).
- **History:** 2026-09-28 proposed and confirmed. Same day (Phase 2), added the live-session autologin component.

### DEC-015 No Plymouth in v1
- **Status:** Decided
- **Why:** It's cosmetic, and it complicates the LUKS prompt and debugging. We'll have a GRUB theme and a text boot instead. The text boot is styled instead (DEC-037).
- **History:** 2026-09-28 proposed and confirmed. 2026-09-30: reconfirmed; the maintainer chose a styled text LUKS screen over Plymouth (DEC-037).

### DEC-016 Secure Boot not supported in v1
- **Status:** Decided
- **Why:** It needs Devuan's shim and signed GRUB chain checked for the ISO and for installed systems. Documented as "disable Secure Boot" for v1. Revisit once Phase 3 is stable.
- **Note:** Secure Boot's kernel lockdown also blocks hibernation (DEC-017), so adding Secure Boot later means solving that too. From 0.3, the NVIDIA module that DKMS builds (DEC-041) is unsigned, so Secure Boot would also need a machine-owner key and module signing.
- **History:** 2026-09-28 proposed and confirmed. 2026-10-03: left out of 0.3 again (SPEC §9.3); added the note about DKMS modules.

### DEC-017 Swap: swapfile sized for hibernation, hibernation supported
- **Status:** Decided
- **Design:**
  - A swapfile at `/swapfile` on the root filesystem, so it sits inside LUKS when encryption is chosen. That avoids a second encrypted partition or LVM.
  - Size: equal to installed RAM, rounded up to the next GiB, so a hibernation image always fits. The installer's minimum disk size grows accordingly ([docs/installer.md](docs/installer.md) §2).
  - Resume: the installer puts `resume=UUID=<root fs UUID> resume_offset=<swapfile physical offset>` (offset from `filefrag -v`) on the kernel command line via `GRUB_CMDLINE_LINUX`. initramfs-tools reads `resume_offset` only from the kernel command line. `/etc/initramfs-tools/conf.d/resume` gets `RESUME=UUID=…` so the resume hook is included. The initramfs unlocks LUKS before it tries to resume, so one passphrase prompt covers both.
  - Trigger: `loginctl hibernate` (elogind), bound in the rofi power menu. The lid close action stays suspend.
- **Constraints:** The swapfile must not be recreated or moved without updating `resume_offset`. `tekne-config` ships `tekne-swap-resize SIZE_GIB`, which recreates the swapfile, updates `/etc/default/grub` and runs `update-grub`, and writes `/sys/power/resume_offset` so hibernation works before the next reboot. Hibernation is incompatible with Secure Boot lockdown (DEC-016).
- **Acceptance:** `tests/smoke/install.py` hibernates and resumes all four install cases in QEMU. On real hardware it passed with LUKS on the development laptop (2026-09-29); without LUKS it's untested on real hardware.
- **History:** 2026-09-28 proposed as "swapfile, no hibernation". Changed the same day by the maintainer to support hibernation. 2026-09-29 (Phase 3): corrected the resume mechanism. `RESUME_OFFSET` in `conf.d` is not read by initramfs-tools; the offset goes on the kernel command line. Same day, hibernate/resume passed on real hardware with LUKS.

### DEC-018 Filesystem: ext4
- **Status:** Decided
- **Why:** Simple and robust, and it supports swapfile hibernation with a fixed offset (DEC-017). btrfs snapshots are a possible v2 feature.
- **History:** 2026-09-28 proposed and confirmed.

### DEC-019 Repository license: GPL-3.0-or-later
- **Status:** Decided
- **Why:** The repo is mostly scripts and configuration in a GPL-heavy ecosystem. Copyleft keeps derivative respins open.
- **Scope:** Everything in the repo except `branding/`, which carries its own license in `branding/LICENSE`: CC-BY-SA-4.0 (DEC-034).
- **History:** 2026-09-28 decided. 2026-09-29 (Phase 4): the maintainer chose CC-BY-SA-4.0 for `branding/`.

### DEC-020 Release hosting: GitHub Releases
- **Status:** Decided, "for now"
- **Why:** Free, integrates with CI (Phase 5), and supports checksums and release notes.
- **Constraint:** Each release asset must be under 2 GiB. The ISO size should be tracked from Phase 2 on.
- **History:** 2026-09-28 decided.

### DEC-021 Source of the `gum` binary
- **Status:** Decided
- **Policy:** Use the Excalibur package if one exists. Otherwise vendor a pinned upstream release, verify its checksum, and repackage it as an in-repo `gum` `.deb`.
- **Outcome (Phase 0):** Excalibur `main` packages `gum` `0.14.4-1+b6`, so we use the distro package and there's no vendored `gum` package.
- **History:** 2026-09-28 decided. Same day, Phase 0 found gum packaged in Excalibur.

### DEC-022 Accounts: sudo user, root locked
- **Status:** Decided
- **Why:** This is the norm for single-user workstations. The installer creates one sudo-capable user and locks the root password.
- **History:** 2026-09-28 recorded (previously only in SPEC.md §3.6 and installer.md).

### DEC-023 Security and privacy defaults
- **Status:** Decided
- **Defaults** (all shipped by `tekne-config`):
  - **Firewall:** `/etc/tekne/nftables.conf`, loaded at boot by the `tekne-firewall` init script. Inbound traffic is dropped except loopback, established/related replies, the ICMPv6 and DHCPv6 traffic IPv6 needs, and traffic from local container and VM bridges. Forwarding is allowed only from those bridges, for replies, and for ports a container engine publishes (DNAT); everything else forwarded is dropped. All outbound traffic is allowed.
    - Devuan's `nftables` package ships only a systemd unit, so nothing else would load a ruleset at boot.
    - The ruleset replaces only its own `inet tekne` table and never runs `flush ruleset`, so rules from other software (libvirt, Docker) survive.
    - Other software's accept rules can't override Tekne's drops (a drop in any nftables table is final), so the bridges are accepted in Tekne's own table: `podman*`, `cni-podman*`, `docker0`, `br-*` (Docker's user networks) and `virbr*` (libvirt). Without this, containers and VMs on a bridge network get no DNS and no network at all, which broke building Tekne on Tekne (DEC-033). Traffic from outside reaches a bridge only through a port someone publishes deliberately (`podman run -p`).
    - `tekne-firewall` starts after `nftables`, in case `orphan-sysvinit-scripts` is installed later: that script's default config flushes everything.
  - **Nothing listens on the network.** The only listener is `chronyd` on loopback, and there's no SSH server. The smoke test fails if anything else listens beyond loopback.
  - **No `popularity-contest`.**
  - **Firefox ESR:** `/usr/share/firefox-esr/distribution/policies.json` turns off telemetry, studies, Pocket, and sponsored tiles and suggestions.
  - **Brave Origin:** Origin already removes most telemetry. The binary still honours `BraveP3AEnabled`, `BraveStatsPingEnabled`, `BraveWebDiscoveryEnabled` and `MetricsReportingEnabled`, so `/etc/brave/policies/managed/tekne.json` sets all four to false as a backstop.
  - **NetworkManager:** `/etc/NetworkManager/conf.d/tekne-privacy.conf` sets `wifi.scan-rand-mac-address=yes` explicitly. It's NetworkManager's default, pinned so a default change can't undo it.
- **History:** 2026-09-28 recorded (previously only in SPEC.md §3.6). Same day, added the Brave Origin policy check (DEC-028). 2026-09-29 (Phase 2): implemented, with the firewall and listener checks added to the smoke test. 2026-09-29: the maintainer approved accepting local container and VM bridges and published ports, after the firewall stopped `scripts/build.sh` resolving names on satori.

### DEC-024 Time sync: chrony
- **Status:** Decided
- **Why:** It works without systemd and handles laptops that suspend and roam well. It replaces `systemd-timesyncd`, which the no-systemd rule forbids.
- **History:** 2026-09-28 recorded (previously only in docs/desktop-stack.md).

### DEC-025 Desktop component selection
- **Status:** Decided. Phase 2 verified every package: each exists in Excalibur (or a DEC-026 repository) and passes the no-systemd rule.
- The component table and keybindings in [docs/desktop-stack.md](docs/desktop-stack.md) are the source of truth. This entry covers the choices not recorded elsewhere, such as the bar, launcher, notifications, compositor, lock screen, terminal, file manager, editor, and keybindings.
- **History:** 2026-09-28 recorded as Proposed. Same day, the maintainer revised it (XLibre, nautilus, neovim, no nm-applet, new keybindings) and it was marked Decided. Same day, the file manager was reverted from nautilus to thunar, to avoid nautilus's large GNOME dependency tree and its file indexer. Same day (Phase 2), the maintainer chose CopyQ to replace `clipmenu`, which isn't packaged in Excalibur. 2026-09-29: the Phase 2 package check is complete (see docs/desktop-stack.md).

### DEC-026 Third-party APT repositories
- **Status:** Decided
- **Policy:** An outside repository (anything other than Devuan's) is allowed only if all of these hold:
  1. Its signing key is stored in this repo, and the build checks it against a recorded SHA-256 checksum.
  2. Its `.sources` entry uses `Signed-By:` for that key alone and ships in the `tekne-apt-sources` package, not as a loose file. It stays enabled on installed systems, so they receive updates.
  3. An `/etc/apt/preferences.d/` pin restricts it to the packages we want from it. Everything else from it gets priority -1, so it can't replace Devuan packages.
  4. Its packages pass the no-systemd rule (SPEC §4), like any other package.
  5. No package from that repository may leave its key somewhere APT trusts for every repository (such as `/etc/apt/trusted.gpg.d/`). Keeping each key scoped is the whole point of rule 2. Brave's `brave-keyring` links its key there from its postinst, unless it finds Brave's own sources file (`brave-browser-release.sources` with `Signed-By: /usr/share/keyrings/brave-browser-archive-keyring.gpg`). So `tekne-apt-sources` ships exactly that file, puts Tekne's checksum-pinned key at that path, and diverts `brave-keyring`'s copy of the key aside. The build fails if any globally trusted key isn't owned by `devuan-keyring` or `debian-archive-keyring`.
- **In the build:** live-build's own mechanism for extra repositories (`config/archives/*.key.chroot`) trusts keys globally, so it isn't used. The package lists install `tekne-apt-sources`, then the chroot hook `0500-tekne-desktop` runs `apt-get update` and installs `tekne-desktop`. The build therefore uses exactly the keys, sources and pins that installed systems use. The hook `0510-check-apt-origins` then fails the build if any installed package came from a third-party repository outside its pin.
- **Current repositories:**
  - Brave (for `brave-origin*`, DEC-028)
  - XLibre for Devuan (for `xlibre*`/`xserver-xlibre*`, DEC-027)
  - Devuan `excalibur-backports` was expected to be needed for XLibre, but isn't: every Phase 2 build resolved XLibre 25.2 from Excalibur stable alone. It's enabled for the kernel only (DEC-036). It's Devuan's own archive rather than a third party, but it's scoped the same way: a `.sources` entry in `tekne-apt-sources` with `Signed-By` Devuan's key, and a pin limited to the kernel packages.
- **Why:** Some chosen components aren't in Devuan stable. This doesn't conflict with DEC-006, which is about Tekne hosting its *own* repository. Tekne's own repository (DEC-040, from 0.2) follows these same rules.
- **History:** 2026-09-28 decided. Same day (Phase 2), added rule 5 after finding that `brave-keyring` installs a globally trusted key, and recorded how the build applies the policy. 2026-09-30: `excalibur-backports` enabled for the kernel (DEC-036).

### DEC-027 X server: XLibre
- **Status:** Decided, verified on real hardware
- **Why:** This is the maintainer's choice. XLibre is an actively developed fork of the Xorg server. It has dropped its libsystemd dependency, and the Devuan project publicly supports it.
- **Source:** The XLibre Devuan repository (`xlibre-debian.github.io/devuan`). XLibre's docs say Excalibur needs backports, but Phase 2 builds resolve without them. Its packages are signed by an individual volunteer's key (DEC-026 applies). Devuan maintainers are working on first-party packages. Switch to those when they reach Devuan stable.
- **Risks:**
  - It depends on a volunteer-run repository.
  - Compatibility with the proprietary NVIDIA driver is undocumented. The 0.3 spike tests it (DEC-041, SPEC §9 Phase 11).
  - The fallback is Devuan's `xserver-xorg`, a package-list change only.
- **History:** 2026-09-28 decided (maintainer edit to desktop-stack.md). 2026-09-29: verified on the development laptop (AMD GPU on the internal and an external display, with the NVIDIA GPU on `nouveau`). 2026-10-03: NVIDIA compatibility is to be tested in 0.3's Phase 11 (DEC-041). If it fails, the fallback above comes back to the maintainer.

### DEC-028 Browsers: Brave Origin (default) + Firefox ESR (fallback)
- **Status:** Decided
- **Why:**
  - Brave Origin is Brave without AI, crypto, VPN, Rewards, Tor and most telemetry, and it's free on Linux.
  - Firefox ESR comes from Devuan's own repositories. It stays as a fallback that doesn't depend on an outside repository.
- **Source:** `brave-origin` from Brave's official APT repository (DEC-026). Brave's stable channel only, never beta or nightly.
- **Default:** `/etc/xdg/mimeapps.list` (shipped by tekne-config) makes `brave-origin.desktop` the XDG default for web pages and links; a user's `~/.config/mimeapps.list` still wins. `tekne-desktop`'s postinst points the `x-www-browser` alternative at `/usr/bin/brave-origin-stable`, on first install only, so a later choice survives upgrades.
- **History:** 2026-09-28 decided.

### DEC-029 Melia: install on demand, not bundled
- **Status:** Decided
- **Why:**
  - Melia is proprietary, closed-source, maintained by one person, and paid beyond one account.
  - Its redistribution terms don't clearly allow bundling it in an ISO.
  - It updates itself from inside the app, bypassing dpkg.
- **Design:**
  - `tekne-config` ships `tekne-get-melia`. It downloads the current `.deb` and signed `SHA256SUMS` from the project's GitHub releases.
  - It checks the signature against a key fingerprint stored in the package, then checks the checksum, then installs the `.deb` with `apt`.
  - A first-run notice or the keybinding cheatsheet mentions it.
- **Revisit if:** the author grants redistribution permission in writing, or publishes an APT repository.
- **History:** 2026-09-28 decided.

### DEC-030 Secret Service: gnome-keyring
- **Status:** Decided
- **Why:** Brave, Melia, Firefox and NetworkManager all store credentials through the Secret Service API. herbstluftwm provides none.
- **Design:**
  - At a console login (PAM service `login`), `pam_gnome_keyring` receives the login password, starts the daemon, and creates or unlocks the `login` keyring with it.
  - `tekne-session` then runs `gnome-keyring-daemon --start --components=secrets`, which attaches the running daemon to the X session's D-Bus.
  - Excalibur's `libpam-gnome-keyring` profile only handles password changes; Debian relies on display managers adding `pam_gnome_keyring` to their own PAM files, and Tekne has none (DEC-014). So `tekne-config` ships the `pam-auth-update` profile `tekne-gnome-keyring`: auth and session lines with `only_if=login`, so `sudo` and `su` never start keyring daemons for root.
  - It has priority -1, so it comes after `pam_elogind` (priority 0), which sets up the `XDG_RUNTIME_DIR` the daemon needs. `pam-auth-update` breaks priority ties by reverse name, which would otherwise put it first.
  - `tests/smoke/install.py` checks, on each installed system after a password login, that the daemon runs, the `login` keyring exists, and the PAM order is right.
  - **With autologin** (DEC-042, encrypted installs only), PAM gets no password, so the `login` keyring starts locked. The first app that needs a secret asks for the password once per session. The keyring stays encrypted with the login password.
- **History:** 2026-09-28 decided. 2026-09-29 (Phase 3): the maintainer's QEMU test found the keyring asking to be created at first login and to be unlocked at the next; added the `satori-gnome-keyring` PAM profile. 2026-10-03: the maintainer chose one unlock prompt per session under autologin (DEC-042) over an empty-password keyring.

### DEC-031 Build container: pinned Devuan image, rootful Podman or Docker
- **Status:** Decided
- **What:**
  - `container/Containerfile` starts from `docker.io/devuan/devuan:excalibur`, pinned by digest.
  - It installs Devuan's `debootstrap` and Debian's live-build `.deb`, verified by SHA-256. The fallback download is snapshot.debian.org's permanent address for that file.
  - `sudo scripts/build.sh` builds the image and runs it `--privileged`. It uses Podman if installed, else Docker.
- **Why:**
  - It works the same on any host.
  - live-build needs chroots, mounts and device nodes, which require a rootful, privileged container. Rootless Podman can't create device nodes, so debootstrap fails there.
  - live-build runs in the container's own filesystem, so there are no bind-mount `nodev` problems. Only the `.deb` package cache is kept on the host (`out/cache/`).
- **Updating the pins:** Change the digest or the live-build version and checksums in the Containerfile in one commit, and note it in CHANGELOG.md.
- **History:** 2026-09-28 decided (Phase 1). 2026-09-29: the image build and the build run use the host's network (`--network=host`). On satori the firewall (DEC-023, before its amendment) blocked a bridge network's DNS, and the build needs no network isolation.

### DEC-032 Package versions increase with every build
- **Status:** Decided
- **Why:** Installed systems get Tekne updates by installing newer `.deb`s from `out/packages/` (DEC-006). APT only upgrades to a higher version, and every build used to produce version `0.1`.
- **Scheme:** `scripts/build.sh` derives the package version from `VERSION` and git; `scripts/build-packages.sh` stamps it into each package's changelog at build time.
  - A clean checkout of tag `v<VERSION>` gets `VERSION` itself, with `-` turned into `~` (`0.1-rc1` becomes `0.1~rc1`, which Debian sorts before `0.1`).
  - Any other build gets `<that>~dev<commit count>.g<short commit>`, e.g. `0.1~rc1~dev131.gb996478`. The commit count rises on every commit, so later builds sort higher, and every dev build sorts before the release it leads to.
  - After tagging a release, bump `VERSION` to the next one (e.g. `0.1-rc2`), so later dev builds sort above the tag.
  - After a release candidate, the next one is the next *candidate* (`0.1-rc2` → `0.1-rc3`), never the final version: Debian compares the parts after `~` alphabetically, so `0.1~dev60` sorts *below* `0.1~rc2`, and a system installed from rc2 couldn't upgrade to it. The final version (`0.1`) goes into `VERSION` only in the release commit itself, which is tagged at once. After a final release, the next one is the next series' first candidate (`0.2-rc1`).
  - Dirty-tree builds get the same version as their commit; `build-info.txt` records `git_dirty`.
- **History:** 2026-09-29 proposed (release candidate gate). Same day, confirmed by the maintainer after it carried the first update of the installed laptop from `0.1~rc1` to `0.1~rc2~dev22`. 2026-10-01: added the rule for the version after a release candidate, after `VERSION=0.1` following `v0.1-rc2` turned out to sort dev builds below rc2 (caught before it was pushed).

### DEC-033 Developer tools: documented install, not in the ISO
- **Status:** Decided
- **Why:** Building and testing Tekne needs `git`, `podman`, QEMU and OVMF. Putting them in the ISO would push it towards GitHub's 2 GiB asset limit (DEC-020) and burden users who never build Tekne. This replaces SPEC's original optional `developer.list.chroot`, which was never built.
- **Design:** The README gives one `apt install` command, using Devuan packages only. On an installed Tekne it's all that's needed to run `scripts/build.sh` and the smoke tests.
- **History:** 2026-09-29 proposed (release candidate gate). Same day, confirmed by the maintainer after building satori on the installed laptop with the README command.

### DEC-034 Branding: Tokyo Night, placeholder art, CC-BY-SA-4.0
- **Status:** Decided
- **Theme:** Tokyo Night (night) everywhere Tekne styles something: the GRUB theme, wallpaper, herbstluftwm, polybar, rofi, dunst, alacritty and i3lock. Background `#1a1b26`, foreground `#c0caf5`, accent blue `#7aa2f7`, magenta `#bb9af7`, red `#f7768e`, dim `#565f89`.
- **Artwork:** placeholders until real art exists: a geometric T in a ring, in a blue-to-magenta gradient, with no text so rendering needs no fonts (until the rename to Tekne, an ensō). Sources are SVGs in `branding/`, rendered to PNG when `tekne-branding` is built (the build container has `librsvg2-bin`). Replacing a file with real art of the same name and size needs no code change.
- **License:** `branding/` is CC-BY-SA-4.0 (DEC-019); the rest of the repository stays GPL-3.0-or-later.
- **`tekne-branding`** (identity): `/usr/lib/os-release` (and so `/etc/os-release`) says `ID=tekne`, `ID_LIKE="devuan debian"`, `VERSION_CODENAME=excalibur`, with this build's version, and credits Devuan. Devuan's copy is diverted to `/usr/lib/os-release.devuan`, so reinstalling or upgrading `base-files` can't restore it. live-build's bootstrap stage turns `/etc/os-release` into a frozen copy of Devuan's file (with `IMAGE_ID=live`), which would also reach installed systems, so the build hook `0530-os-release` restores base-files' symlink to `/usr/lib/os-release`, then checks that os-release survives reinstalling `base-files`. Also the GRUB theme, the wallpaper (`/usr/share/backgrounds/tekne/tekne.png`) and the logo.
- **GRUB theme:** one `theme.txt` for the live ISO and installed systems, using GRUB's own `unicode.pf2` font. On installed systems `tekne-branding` copies it to `/boot/grub/themes/tekne`, because with LUKS GRUB can't read `/usr`, and `/etc/default/grub.d/tekne-theme.cfg` sets `GRUB_THEME`. The live ISO shows it on screen and a plain text menu on the serial port, which the automated tests use. Its background also replaces live-build's default splash, which is Debian's artwork, and its entries are Tekne's own ("Tekne live", "Tekne live (safe graphics)") instead of live-build's "Live system".
- **Consequence:** GRUB's distributor name comes from `os-release`, so menu entries read "Tekne GNU/Linux". On UEFI, the next `grub-install` (for example when the GRUB package is upgraded) also creates an `EFI/tekne` boot entry. Systems installed before tekne-branding keep their old `devuan` entry alongside it.
- **Configuration** (`tekne-config`, each used only when the user has no config of their own): `/etc/rofi.rasi` selects the rofi theme and is read before `~/.config/rofi/config.rasi`; `/etc/xdg/dunst/dunstrc.d/50-tekne.conf` is a drop-in on dunst's own dunstrc; `tekne-terminal` runs alacritty with `/usr/share/tekne/alacritty.toml` (alacritty 0.15 has no system-wide config) and is now the `x-terminal-emulator` alternative, which had been xterm's `lxterm`.
- **GTK and icons:** Devuan packages no Tokyo Night GTK theme, so GTK apps get dark Adwaita (built into GTK) and Papirus-Dark icons (`papirus-icon-theme`, about 23 MB on the ISO), set in `/etc/xdg/gtk-3.0` and `gtk-4.0` `settings.ini` and a GSettings override. A packaged Tokyo Night GTK theme would need a third-party source (DEC-026).
- **Not changed:** `/etc/issue` and `/etc/issue.net` still name Devuan (DEC-035). `/etc/motd`'s Devuan notice is kept as attribution.
- **History:** 2026-09-29 decided (Phase 4): the maintainer chose placeholders, CC-BY-SA-4.0 and Tokyo Night. 2026-09-30: the first ISO build failed the os-release check because of live-build's copy; the hook now restores the symlink.

### DEC-035 Console login greeting (`/etc/issue`)
- **Status:** Decided: option 1, keep Devuan's text
- **Problem:** the console login prompt, the first thing an installed Tekne shows after the LUKS prompt, reads "Devuan GNU/Linux excalibur". `/etc/issue` and `/etc/issue.net` are `base-files` conffiles, and dpkg can't divert a conffile, so SPEC §3.3's "`issue` via `dpkg-divert`" isn't possible.
- **Options:**
  1. Keep Devuan's text. The Phase 4 check is about logos, and this is text. Simplest.
  2. `tekne-branding` rewrites `/etc/issue` on first install, only if it's still Devuan's unmodified text. dpkg then treats it as a local change: a later `base-files` update to that file asks which version to keep (rare, but it happens at Devuan releases). This breaks Debian policy, which says packages don't edit other packages' conffiles.
  3. The installer points the `getty` lines in `/etc/inittab` at a Tekne issue file (`agetty --issue-file`). That covers installed systems only, and lives in the installer rather than a package.
- **Decision:** option 1 for v0.1. The Phase 4 check is about logos, and the greeting is text that also serves as attribution. Revisit if a Tekne `base-files` becomes worthwhile.
- **History:** 2026-09-29 opened (Phase 4). 2026-09-30: the maintainer chose option 1.

### DEC-036 Kernel from `excalibur-backports`
- **Status:** Decided
- **What:** Tekne's kernel is Devuan's `linux-image-amd64` from `excalibur-backports` (Debian's trixie-backports build; 7.1.13 when decided), not the stable 6.12 kernel. It's still the stock Devuan/Debian kernel, unpatched.
- **Why:** Tekne targets laptops, and the stable kernel wasn't enough for the development laptop (ASUS ROG Zephyrus G15, GA503RM). On 6.12, `hid-asus` failed to set up its internal keyboard (`Asus failed to request functions: -75`), after which the keyboard sent nothing, including at the LUKS prompt. 7.0 and 7.1 reworked that handshake; on 7.1.13 the keyboard, its Fn keys and its backlight all work.
- **How:**
  - `tekne-apt-sources` ships `/etc/apt/sources.list.d/tekne-backports.sources` (`Signed-By` Devuan's archive key) and `/etc/apt/preferences.d/tekne-backports.pref`, which pins only the kernel packages (`linux-image-*`, `linux-headers-*`, `linux-base-*`, `linux-binary-*`, `linux-modules-*`, `linux-kbuild-*`, `linux-compiler-*`) at 500. Backports is `NotAutomatic`, so nothing else comes from it unless asked for by name.
  - In the build, live-build installs the stable kernel before that source exists; the hook `0505-backports-kernel` then upgrades to the backports kernel and purges the stable one, so the image and installed systems carry exactly one kernel. It fails the build if that isn't the result.
  - `tests/smoke/install.py` checks installed systems run the backports kernel.
- **Trade-offs:** Debian's security team doesn't formally cover backports; the kernel team updates backports kernels, usually shortly after stable. A new kernel series arrives every few months, so there's more change than on stable; the QEMU install tests (including hibernate/resume) are the guard. Firmware stays at stable's versions.
- **Fallback:** removing the pin and reinstalling `linux-image-amd64` from stable is a package change only.
- **NVIDIA (from 0.3):** the pin also covers the NVIDIA driver packages that `tekne-nvidia` depends on (DEC-041), because the backports driver is the one built for the backports kernel. The exact package names come from the 0.3 spike. They're installed only on systems that install `tekne-nvidia`.
- **History:** 2026-09-30 decided by the maintainer, after the backports kernel fixed the development laptop's keyboard. 2026-10-03: the maintainer agreed to extend the pin to the NVIDIA driver packages for `tekne-nvidia` (DEC-041). It takes effect when that package is built (SPEC §9 Phase 13).

### DEC-037 Styled text boot and LUKS prompt
- **Status:** Decided
- **What:** the text console from GRUB to the login prompt, above all the LUKS passphrase screen, matches the desktop, without Plymouth (DEC-015):
  - **Palette:** `vt.default_red`/`grn`/`blu` on the kernel command line set the 16 console colours to Tokyo Night, with `#1a1b26` as the background. Installed systems get them from `tekne-branding`'s `/etc/default/grub.d/tekne-console.cfg`; the live ISO from `--bootappend-live` in `live-build/auto/config`. They also apply to console logins.
  - **Quiet:** `loglevel=3` keeps kernel errors that aren't ours to fix (ACPI BIOS table bugs, the absent PS/2 keyboard) off the screen; they stay in `dmesg`.
  - **Banner:** `tekne-branding` ships the initramfs script `init-premount/tekne-banner`. On `quiet` boots it clears the console, shows "T E K N E" centred, and leaves the cursor so that cryptroot's "Please unlock disk NAME:" prompt comes out centred below it. It sits before cryptroot rather than in the unlock path (no `keyscript`), so a failure can't stop the disk being unlocked. Without `quiet`, it does nothing, for debugging.
  - **Disk name:** new installs name the LUKS mapping `tekne`, so the prompt reads "Please unlock disk tekne:". Existing installs keep theirs.
- **Tested:** in QEMU, a satori UEFI+LUKS install migrated to Tekne shows the banner and centred prompt, and unlocks over the serial console with the banner in its initramfs.
- **History:** 2026-09-30 decided: the maintainer chose styled text over Plymouth.

### DEC-038 CI: GitHub Actions on a hosted runner
- **Status:** Decided
- **What:** `.github/workflows/build.yml` runs on pushes to `master`, version tags, pull requests and manual dispatch. Commits that only change Markdown or the license texts are skipped (`paths-ignore`); GitHub never applies path filters to tag pushes, so release tags always build. One job on GitHub's `ubuntu-24.04` runner (4 CPUs, 16 GB, KVM):
  1. Frees disk space (the build peaks around 15 GB) and enables KVM with GitHub's documented udev rule.
  2. Builds with `sudo CONTAINER_ENGINE=docker scripts/build.sh`, the same command as a local build, so CI uses the pinned build container and its checks (no-systemd, APT origins, kernel, os-release).
  3. Runs `tests/smoke/live-boot.py`, `tests/smoke/repo.py` (DEC-040), `tests/smoke/install.py` (all four cases, with hibernate/resume) and `tests/smoke/upgrade.py` (the previous release upgraded to this build through apt, SPEC §8).
  4. Uploads the ISO, its checksum, the package manifest, `build-info.txt` and Tekne's `.deb`s as the `tekne-iso` artifact for 30 days; on failure, the build and serial logs instead.
- **Why:** GitHub already hosts the repository and the releases (DEC-020); the repository is public, so hosted runners and artifact storage cost nothing. Running the same scripts as a local build keeps one way to build and test.
- **Pinning:** actions are pinned by commit (`actions/checkout` v7.0.1, `actions/upload-artifact` v7.0.1), per the rule that every external build input is pinned. The runner image itself isn't pinnable; the build happens inside the digest-pinned container, so it only supplies Docker, QEMU and OVMF.
- **Not covered:** real hardware (docs/testing.md). Until 2026-10-02 `tests/smoke/upgrade.py` wasn't either, because it needed an install kept from an earlier build; it now starts from the previous release's ISO.
- **History:** 2026-09-30 proposed (Phase 5). 2026-10-01: the first run on `master` was green (run 36802153183); the maintainer confirmed the design and asked for docs-only commits to skip the build. 2026-10-02: added `repo.py`, and the `.deb`s to the artifact, for DEC-040. Same day (SPEC §8 Phase 9): added `upgrade.py`, from the previous release.

### DEC-039 Releases created by CI from a tested tag
- **Status:** Decided
- **What:** pushing a `v*` tag makes CI create the release, so the files on GitHub Releases are exactly the ones its tests passed on. The steps are in [docs/building.md](docs/building.md), "Release"; the checks are in `scripts/ci-release.sh`, which can be dry-run locally (`DRY_RUN=1`).
- **Design:** a second job, `release`, in `.github/workflows/build.yml`:
  - It runs only for `v*` tags, and only after `build-and-test` passes.
  - Only this job gets `permissions: contents: write`. The build job stays read-only, so the 30-minute build with root never holds a token that can write to the repository.
  - It downloads the `tekne-iso` artifact with `actions/download-artifact`, pinned by commit (v8.0.1, `3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c`), and creates the release with the runner's `gh`, using the job's own token.
  - **Checks before uploading:** `build-info.txt` must show the tag's version (e.g. `0.1` for `v0.1`) and `git_dirty: no`, which proves it was a clean build of the tag; the ISO's `.sha256` must verify; every file must be under GitHub's 2 GiB limit (DEC-020); and CHANGELOG.md must have a section for the version, which becomes the release notes. Any failure stops the release.
  - **Files:** the ISO, its `.sha256`, the package manifest, `build-info.txt`, and Tekne's `.deb`s apart from `tekne-installer` (DEC-040), each checked against the SHA-256 that `build-info.txt` records for it.
  - **Draft first:** the release is created as a draft, so a person reads it and presses "Publish". Tags with a `-` (e.g. `v0.1-rc2`) are marked as pre-releases.
- **Why:** removes the download-and-reupload of a 2 GB file by hand; ties every release to a green test run; keeps a human decision before anything is public.
- **Alternatives:** keep the manual steps; or publish without a draft, which is fully automatic but leaves no review before a release is public.
- **History:** 2026-10-01 proposed (Phase 6), at the maintainer's request. Same day, decided by the maintainer and implemented as the `release` job and `scripts/ci-release.sh`. 2026-10-02: releases also carry the `.deb`s that Tekne's APT repository is built from (DEC-040).

### DEC-040 Tekne APT repository on GitHub Pages
- **Status:** Decided. Built in Phase 8 (SPEC §8); first published with 0.2-rc1, and in use since Tekne 0.2 (2026-10-03).
- **What:** from 0.2, installed systems get Tekne's own packages with `apt update && apt upgrade`, from a signed APT repository at `https://graewolf.github.io/tekne/apt/`. It amends DEC-006, which deferred a hosted repository until after v0.1. Tekne's packages are still built in this repository and baked into the ISO.
- **Why:** in 0.1, `tekne-*` updates reach an installed system only if its user builds them from this repository (DEC-006). That works for the maintainer only, so fixes to the firewall, pins or session wait until each user rebuilds.
- **Rules:** the repository is held to DEC-026 as if it were a third party:
  - `tekne-apt-sources` ships its public key, checked against `keys/SHA256SUMS`.
  - Its `.sources` entry uses `Signed-By` with that key alone.
  - An `/etc/apt/preferences.d/` pin, `tekne.pref`, limits it to `tekne-*` packages. Everything else from it gets priority -1. The pin matches the repository's signed `Origin: Tekne` (`o=Tekne`) rather than its host name, so the tests can serve the repository from anywhere and still exercise the shipped pin.
  - It carries `tekne-apt-sources`, `tekne-branding`, `tekne-config` and `tekne-desktop`. `tekne-installer` belongs only in the live image, and Devuan packages are never mirrored. From 0.3 it also carries `tekne-nvidia` (DEC-041), which is published but not in the ISO.
- **Hosting:** GitHub Pages for this repository, next to the releases (DEC-020). The four packages total about 350 KB per release. Installed systems contact GitHub on `apt update`, as they already do for XLibre's repository. The URL is written into every installed system, so moving it later needs a `tekne-apt-sources` update that runs while the old URL still answers.
- **Suites** (one `main` component each):
  - `excalibur`: releases. `tekne-apt-sources` points here.
  - `excalibur-rc`: pre-releases and releases, so a system that follows it also gets finals. A tester switches to it by editing the suite in `/etc/apt/sources.list.d/tekne.sources`.
  - Dev builds are never published. Dogfooding between candidates still uses `scripts/build.sh --packages-only` (DEC-032).
- **Signing key:** a dedicated Ed25519 repository key, not anyone's personal key.
  - The primary key is certify-only. It's kept offline by the maintainer and never on a machine or service that CI can reach.
  - A signing subkey with a one-year expiry is the only key CI holds. It's a secret of a GitHub Actions environment, `repo-publish`, that needs the maintainer's approval to run. Only the `sign` job of `.github/workflows/publish-repo.yml` uses that environment. This is the same split as DEC-039's write token.
  - **The key** (created 2026-10-02): `packages/tekne-apt-sources/keys/tekne.gpg`, with its checksum in `keys/SHA256SUMS`.
    - Primary: `2401BB7742E09C29AA41B29441BEF97FD11D7B37` (Ed25519, certify only, no expiry).
    - Signing subkey: `82C321645DE72C0575A968AC64CE1E0BA73FF9F4` (Ed25519, expires 2027-10-02, so it must be rotated before then).
    - Revoked: `0565CDB56C65979D951C3E5608DEE513068CADDB`, the first signing subkey. It was exposed before it signed anything (History, 2026-10-02).
    - The primary key's passphrase-protected backup and its revocation certificate are on a USB stick the maintainer keeps offline. No copy is on the development laptop.
  - **Rotation** (steps in docs/building.md, checked by `tests/key-rotation.sh` on every build): before the subkey expires, the maintainer adds a new one with the offline primary. A `tekne-apt-sources` update carrying the new public key is published while the old subkey still signs, and the CI secret is swapped after that. The steps go in `docs/building.md`.
- **Publishing:**
  - DEC-039's `release` job also attaches the four `.deb`s to the draft release, so they're files that passed CI's tests, and `build-info.txt` records their checksums.
  - `.github/workflows/publish-repo.yml` runs when a person publishes a release (`release: published`), or by hand (for example after a key rotation). Pushes, tags and drafts never change the repository.
  - Its `sign` job (`scripts/ci-publish-repo.sh`) rebuilds both suites from the published releases' `.deb`s: the newest release for `excalibur`, and the newest release or pre-release for `excalibur-rc`, both by Debian version order. Releases without `.deb`s (from before 0.2) are skipped, and a suite with no release is published empty. It refuses any `.deb` whose checksum or version differs from that release's `build-info.txt`, or a build-info from a dirty tree. It finds each `.deb` by its contents rather than its file name, because GitHub may rename release assets with special characters (versions like `0.2~rc1` contain a `~`).
  - It builds and signs the repository in the build container with `scripts/build-repo.sh` (`apt-ftparchive`, `gpg`), the same script and tools that make every build's test repository. The signatures must verify against `keys/tekne.gpg`, or nothing is published, so a wrong CI secret can't reach users.
  - A separate `deploy` job deploys GitHub Pages: `actions/deploy-pages` needs GitHub's own `github-pages` environment, and a job has only one environment. That job never sees the key. GitHub's default `github-pages` environment allows only `master`, but a release's run is on its tag, so the environment also allows tags `v*` (added 2026-10-02, before the first publish).
  - The site is derived entirely from published releases and keeps no state of its own. Older versions stay downloadable as release assets.
- **Build isolation:** the build hook `0500-tekne-desktop` runs `apt-get update` with `tekne-apt-sources`'s files in place, and live-build runs it again after all hooks (`chroot_archives remove`), so a hook can't simply disable the source. Without isolation, a build would also fail outright while the repository doesn't exist yet (a 404 is an apt error).
  - `live-build/config/apt/apt.conf` sends the repository's host through a proxy that isn't there. live-build installs that file for every chroot stage and removes it before the image is made. apt-get update then warns "Failed to fetch" and carries on, since a network failure is only a warning.
  - `0510-check-apt-origins` fails the build if any index came from the Tekne repository, or if the `tekne-*` packages don't all have one version. `scripts/build-in-container.sh` checks the image's indexes after `lb build` too.
- **Tests:** every full build also writes `out/test-repo/`: the same layout made by `build-repo.sh`, signed with a throwaway key made for that build, plus a decoy `base-files 99:0` and a second throwaway key. `tests/smoke/repo.py` serves it to the live ISO in QEMU, with the shipped `.sources` (only URL and key swapped) and pin. apt must accept it only with the right key, refuse a `.deb` with one byte changed, and keep the decoy at -1.
- **From 0.1:** a 0.1 system has no Tekne source, so it joins once by installing 0.2's `tekne-apt-sources` `.deb` from the release page. After that, `apt upgrade` brings the rest. CI's upgrade test (SPEC §8, Phase 9) runs this path from the 0.1 ISO until 0.2 is out.
- **Alternatives:**
  - Sign `InRelease` locally with the offline key, with CI only uploading. That keeps the key off GitHub entirely, but every release needs a manual signing step.
  - A domain of the maintainer's own pointed at Pages, so the hosting could move without touching installed systems. Not wanted for now.
- **History:** 2026-10-01 proposed (SPEC §8) and decided by the maintainer: a CI-held signing subkey behind an approval gate, the `github.io` address, and a pre-release suite. 2026-10-02: the maintainer created the key, moved the primary key offline, and set up the `repo-publish` environment, its secrets and Pages; the fingerprints are recorded above. Same day, the first signing subkey (`0565…`) was exposed: a terminal read in a Claude Code session returned its passphrase-protected private block into the session transcript. It had signed nothing, and nothing trusted it yet. The maintainer revoked it (reason: compromised), added `82C3…` from the offline primary, changed the passphrase on all keys, and replaced both CI secrets. This was a first run of the rotation steps. Same day (Phase 8): implemented, with the pin on `o=Tekne`, the build isolation through `config/apt/apt.conf`, and publishing split into `sign` and `deploy` jobs. 2026-10-03: 0.2-rc1 and then 0.2 published; GitHub renamed the rc's `.deb` assets (`~` to `.`), as anticipated. The development laptop moved from 0.1 through both with apt. Same day: the maintainer agreed SPEC §9 (0.3), which adds `tekne-nvidia` to the repository (DEC-041).

### DEC-041 NVIDIA proprietary driver: opt-in `tekne-nvidia`
- **Status:** Decided, pending the Phase 11 spike (SPEC §9)
- **What:** `tekne-nvidia` installs Devuan's proprietary NVIDIA driver and makes it work without systemd. It's published in Tekne's repository (DEC-040), not in the ISO and not installed by default. Users install it with `sudo apt install tekne-nvidia`, and purging it returns to `nouveau`.
- **Why:**
  - The development laptop's discrete GPU (RTX 3060, Ampere) runs on `nouveau`.
  - Debian's driver handles suspend and hibernate only through systemd units, so on Tekne nothing would call `nvidia-sleep.sh`.
  - Installing the driver pulls in DKMS, a compiler and kernel headers, about 90 packages. That's too much to add to an ISO already at 1.85 GiB of GitHub's 2 GiB limit (DEC-020), and the installer needs no network (DEC-006).
- **Version:** 550.163.01, the only branch in Devuan (and in Debian up to forky). It comes from `excalibur-backports` (`-4~bpo13+1` when decided), the build meant for the backports kernel, under DEC-036's pin. NVIDIA's own repository (570 and later) was the alternative, and would have been a third-party repository under DEC-026.
- **Design:**
  - Depends on `nvidia-driver`, `nvidia-kernel-dkms`, `firmware-nvidia-gsp` and `linux-headers-amd64`. Simulating the install on Excalibur pulled in no systemd package.
  - An elogind sleep hook, `/usr/lib/elogind/system-sleep/tekne-nvidia`, calls `nvidia-sleep.sh` around suspend and hibernate. With no NVIDIA module loaded, it does nothing.
  - Modprobe options: `NVreg_PreserveVideoMemoryAllocations=1`, a temporary file path on disk, and `NVreg_DynamicPowerManagement=0x02`, so the idle GPU powers off.
  - `tekne-prime-run CMD` runs a program on the NVIDIA GPU (PRIME render offload). X stays on the integrated GPU, so a missing or broken module costs offload, not the desktop.
  - Every build compiles the DKMS module against the kernel the ISO ships, so a backports kernel that breaks the driver can't reach a release unnoticed.
  - The installer prints a hint when it sees an NVIDIA GPU, but doesn't install the driver.
- **Spike (SPEC §9 Phase 11):** the design stands if, on the laptop, the backports driver builds against Tekne's kernel and works with XLibre (DEC-027) for offload, suspend, hibernate and runtime power-down. If XLibre doesn't work with it, the X server question goes back to the maintainer.
- **History:** 2026-10-03 decided by the maintainer with SPEC §9 (Q1: backports).

### DEC-042 Autologin after LUKS
- **Status:** Decided
- **What:** on encrypted installs, tty1 logs the user in after the LUKS passphrase and starts the X session, so one passphrase reaches the desktop. Plain installs keep the password login (DEC-014). The lock screen, `sudo` and the other ttys still ask for the password.
- **How:**
  - `/etc/inittab` isn't a conffile: `sysvinit-core`'s postinst generates it, and the installer already rewrites it. For new installs, the installer asks whether to log in automatically when LUKS is chosen, and adds `--autologin USER` to tty1's getty line. Existing installs use `tekne-autologin on|off` (`tekne-config`), which refuses unless `/` is on dm-crypt. Package scripts never edit inittab.
  - `tekne-startx.sh` no longer uses `exec startx`. If X exits with an error within a few seconds, it leaves a marker for the rest of the boot and stays on a console shell, so a broken X can't loop through autologin.
  - The keyring starts locked and asks for the password once per session (DEC-030).
  - `xss-lock` locks before suspend and hibernate, so resuming still needs the password.
- **Not changed:** the console greeting stays Devuan's (DEC-035).
- **History:** 2026-10-03 decided by the maintainer with SPEC §9 (Q2: one keyring prompt; Q4: no change to DEC-035).

### DEC-043 Symbols font: vendored Nerd Fonts "Symbols Only"
- **Status:** Decided
- **What:** `tekne-config` ships Nerd Fonts' "Symbols Only" font, from an upstream release pinned by SHA-256 and checked when the package is built. A fontconfig fallback makes its symbols available after JetBrains Mono, in polybar and alacritty alike. polybar's right-hand modules use its icons instead of text.
- **Why:** neither Devuan nor Debian packages Nerd Fonts. The packaged `fonts-font-awesome` (4.7) and `fonts-material-design-icons-iconfont` cover the bar but not the wider set that terminal tools use.
- **License:** MIT, with the bundled icon sets under their own permissive licences. All are recorded in `tekne-config`'s `debian/copyright`. The font isn't Tekne's artwork, so it stays out of `branding/` (DEC-034).
- **Updating:** change the version and checksum in one commit, and note it in CHANGELOG.md, as for DEC-031's pins.
- **History:** 2026-10-03 decided by the maintainer with SPEC §9 (Q3).
