# Phase 11 spike: NVIDIA on the development laptop

Throwaway, like Phase 0's spike: removed once `tekne-nvidia` exists (SPEC §9 Phase 13).
It installs Devuan's NVIDIA driver from `excalibur-backports` by hand, with the pieces
DEC-041 plans for `tekne-nvidia`, and collects evidence for Phase 11's criteria.

| File | Becomes in `tekne-nvidia` |
|---|---|
| `files/tekne-nvidia-spike.pref` | DEC-036's pin, extended to `src:nvidia-graphics-drivers` |
| `files/tekne-nvidia-spike.conf` | modprobe options (module is `nvidia-current` in Debian) |
| `files/80-tekne-nvidia-spike-pm.rules` | runtime power management for the GPU's PCI functions |
| `files/tekne-nvidia-spike-sleep` | the elogind sleep hook (Debian ships only systemd units) |
| `prime-run` | `tekne-prime-run` |
| `files/90-tekne-nvidia-spike-ignoreabi.conf` | nothing: a fallback if XLibre refuses the driver's ABI |

`nvidia-persistenced` is left out: it starts at boot and keeps the GPU initialised,
which stops runtime power-down.

## Baseline (nouveau, 2026-10-03)
`results/baseline-nouveau.txt`. The GPU never powers down on AC: TLP sets
`power/control=on` for its audio function (`RUNTIME_PM_ON_AC=on`). Outputs wired to the
NVIDIA GPU: HDMI-A-1, DP-1 and a second eDP-1 (the laptop has a MUX). The internal
panel (eDP-2) and DP-2..9 are on the AMD GPU. XLibre's log already says it
"implicitly ignor[es the] abi mismatch" for maintained NVIDIA branches.

## Attempt 1: backports driver (2026-10-03): DKMS fails on 7.1
`install.sh` installed `550.163.01-4~bpo13+1`, but its module doesn't build for
`7.1.13+deb13-amd64`: the source still uses `in_irq()` and `vma->__vm_flags`, both gone
from the kernel. Debian's changelogs show the backports package only supports kernels up
to 6.17. Debian's own fixes arrived in sid as `-5` (6.19) and `-5.1` (7.0, June 2026), and
neither is in `excalibur-backports`. `nvidia-kernel-dkms` and `nvidia-driver` are left
unconfigured. Nothing else broke, but the GLX alternative now points at NVIDIA and the
initramfs blacklists `nouveau`, so roll back before rebooting.

Debian's `-5.1` DKMS source (`nvidia-kernel-dkms_550.163.01-5.1_amd64.deb` from
deb.debian.org) does build against 7.1.13 (all five modules, run as the user into the
scratchpad, not installed). The only warnings are objtool's, about NVIDIA's binary blob.

Rolling back hit a second problem: `xserver-xorg-video-nvidia`'s postrm warns about X
config that mentions `nvidia`. XLibre's `xserver-xlibre-common` ships two such files
(`/etc/X11/xorg.conf.d/10-nvidia-*.conf`, its ready-made NVIDIA setup), so the
warning always fires. Its debconf prompt then failed with exit 20 and stopped dpkg.
`rollback.sh` now preseeds `nvidia-support/check-xorg-conf-on-removal=false`, the
switch the postrm provides. `tekne-nvidia` needs the same.

## Attempt 2: NVIDIA's repository (option 3, chosen 2026-10-03)
`install-nvidia-repo.sh`, with `files/nvidia/`. Found before installing (read-only, in a
scratch APT configuration):
- **Repository:** `https://developer.download.nvidia.com/compute/cuda/repos/debian13/x86_64/`,
  a flat repository (`Suites: /`) with `Origin: NVIDIA`. It's signed by
  `0218 2E60 104F CDC2 6EAE 1B85 97A5 D4CB 8793 F200` ("Kitmaker (Debian 13 Trixie)"),
  and `files/nvidia/SHA256SUMS` pins that key.
- **Driver:** 615.71.09. Only open kernel modules (`nvidia-kernel-dkms` is a transitional
  package for `nvidia-kernel-open-dkms`), which suit Ampere. The modules build against
  7.1.13 without errors (all five, built as the user, not installed).
- **Packages:** `--no-install-recommends nvidia-driver` installs 33 packages, all from
  NVIDIA, none of them systemd. Debian's package names are reused, from six source
  packages: `nvidia-graphics-drivers`, `nvidia-kmod-open`, `nvidia-modprobe`,
  `egl-wayland2`, `egl-x11`, `nvidia-egl-gbm`. The pin admits only those, blocks
  `cuda-*` (which `cuda-drivers` shares a source package with), and puts everything
  else at -1.
- **Not wanted:**
  - `nvidia-driver-pinning-615` (a Recommends) writes its own APT pin at priority 1000, and Tekne's pin blocks it.
  - `nvidia-persistenced` (a Recommends) keeps the GPU initialised.
  - `nvidia-powerd` is a hard dependency, but ships only a systemd unit, so nothing starts it on sysvinit. It's the Dynamic Boost daemon, which is optional.
- **Suspend and hibernate:** NVIDIA's `/etc/modprobe.d/nvidia.conf` sets
  `NVreg_UseKernelSuspendNotifiers=1`, plus `PreserveVideoMemoryAllocations=1`,
  `TemporaryFilePath=/var/tmp` and S0ix. The kernel then saves video memory itself, with
  no `nvidia-sleep.sh` and no service, so attempt 2 installs no sleep hook. If suspend
  works, DEC-041's elogind hook isn't needed.
- **Runtime power:** NVIDIA's `60-nvidia.rules` covers the GPU but not its HDMI audio
  function. `files/nvidia/80-tekne-nvidia-spike-pm.rules` adds that.

### After install and reboot (2026-10-03, `results/after-install.txt`)
- `nvidia/615.71.09` was built by DKMS for 7.1.13. `nvidia`, `nvidia_modeset` and
  `nvidia_drm` (modeset=Y, fbdev=Y) are loaded, and `nouveau` isn't. The driver
  parameters are as intended, and the driver reports "Runtime D3: Enabled (fine-grained)".
- The desktop renders on the Radeon 680M. Offloaded OpenGL (`prime-run glxinfo`) and
  Vulkan both run on the RTX 3060.
- XLibre loads NVIDIA's DDX: "Implicitly ignoring abi mismatch", plus a warning
  about the input ABI (have 26.0, need < 25.0).
- **But X has no NVIDIA GPU screen.** The log says `NVIDIA(GPU-0): Failed to acquire
  modesetting permission`, then `Failing initialization of X screen`, and `xrandr
  --listproviders` shows only the AMD `modesetting` provider. Offload still works.
  Reverse PRIME, and so the HDMI port, can't work without that screen.
  - X runs as the user and opens DRM devices through **libseat** with the `seatd`
    backend (`/usr/sbin/seatd -g video`). The XLibre build has no logind support.
    NVIDIA's DDX probably can't become DRM master on the NVIDIA node through
    this path. Not confirmed yet: `dmesg` needs root.
- On AC the GPU stays `active` with `power/control=on`. TLP sets that for every
  driver not on its denylist, and `nvidia`, unlike `nouveau`, isn't on it.

### Battery and suspend (2026-10-03)
- **Idle power-down, on battery** (`results/battery.txt`): the GPU and its audio function
  are runtime-`suspended` and the driver reports "Video Memory: Off". Offload wakes the
  GPU, and it's back to `suspended` within 30 s.
- **Suspend on battery** (s2idle, the only mode this firmware offers): resumes into the
  session, and NVIDIA logs nothing, so the kernel suspend notifiers did their job with no
  sleep hook. But the **internal keyboard is dead after resume**: still bound to
  `hid-asus` with its boot-time input device, the backlight on, no keys. The kernel logs
  nothing about USB `1-3` on resume. `last_hw_sleep` was 17.3 s of about 18 s, which is
  deep S0ix. Re-probing the USB device (`unbind`/`bind` of `1-3`) brings it back.
  - `usbcore quirks=0b05:19b6:b` (`RESET_RESUME`, applied at runtime with a port power
    cycle; the device showed `quirks` = `0x2`) doesn't help. The second suspend
    (34.9 s of hardware sleep) killed the keyboard again. `hid-asus`'s `reset_resume`
    doesn't redo the setup handshake that a full probe does.
  - On `nouveau` and the same 7.1 kernel, the maintainer suspended on AC and on battery
    without losing the keyboard. So the NVIDIA driver is the trigger, probably by
    letting the platform reach deeper S0ix.
- **Suspend on AC: hard hang.** Neither the internal nor an external keyboard
  responded after resume, and the laptop needed a forced power-off. On AC, TLP keeps
  the GPU powered (`control=on`), so at suspend NVIDIA's notifier has live video
  memory to save, which it didn't on battery. The EFI pstore was empty (`efi_pstore`
  loaded), so it was a freeze, not a panic. No other log survives: Tekne has no
  persistent kernel log.
- **Not tested:** hibernate, and external monitors.

### The "AC freeze" was the `RESET_RESUME` quirk (2026-10-03)
Retested with `debug-on.sh`: lockups and stuck tasks panic, the NMI watchdog is on,
`pm_debug_messages` and `pm_print_times` are set, and `kmsg-logger.sh` syncs every
kernel message to `/var/log/tekne-nvidia-spike-kmsg.log`. `gpu-pm.sh` sets the GPU's
runtime power control by hand.

| Suspend | Power | GPU at suspend | `RESET_RESUME` | Result |
|---|---|---|---|---|
| 1 | battery | off | no | resumed, internal keyboard dead |
| 2 | battery | off | yes | resumed, internal keyboard dead |
| 3 | AC | awake | yes | froze (no logging yet) |
| 4 | AC | off | no | resumed, internal keyboard dead |
| 5 | AC | awake | no | resumed, internal keyboard dead |
| 6 | AC | awake | yes | froze: X took no input from either keyboard |

- **Suspend 6:** the kernel resumed completely. All phases finished, tasks
  restarted, Wi-Fi reconnected, and the logger kept writing for 7 minutes. Both
  keyboards' Caps Lock lights still toggled, so the kernel handled input but X
  didn't. The kernel reset `usb 1-3` during resume (344 ms), as the quirk asks.
  Nothing panicked, because no kernel task hung.
- **So the freeze came from the quirk experiment, not from NVIDIA or AC.**
- Every suspend reached s0i3 (`amd_pmc: SMU idlemask s0i3`, 17–35 s of hardware sleep),
  and NVIDIA's device suspended and resumed in milliseconds each time.
- **The internal keyboard** dies in every deep suspend: its controller reboots during
  sleep (the backlight flashes white). USB resumes it as if nothing happened, and only
  a full re-probe brings it back. Candidate fix:
  `files/tekne-asus-kbd-spike-sleep`, an elogind hook that re-probes `0b05:19b6`
  after resume.

## Steps (maintainer)
1. Back up the laptop.
2. `sudo spike/phase11/install-nvidia-repo.sh` (attempt 2; attempt 1 was `install.sh`). It stops before rebooting if DKMS fails.
3. Reboot. If X doesn't start: log in on tty2, check `~/.local/state/xorg/Xorg.0.log`;
   for an ABI error, copy `files/90-tekne-nvidia-spike-ignoreabi.conf` into
   `/etc/X11/xorg.conf.d/` and try again; otherwise `sudo spike/phase11/rollback.sh`.
4. `spike/phase11/check.sh after-install` (on AC).
5. Unplug the charger, wait a minute, `spike/phase11/check.sh battery`.
6. Suspend (`Mod+Shift+e`), resume, `spike/phase11/check.sh after-suspend`.
7. Hibernate, resume, `spike/phase11/check.sh after-hibernate`.
8. External monitors: one on the USB-C port (AMD) and one on HDMI (NVIDIA). For HDMI,
   `xrandr --listproviders`, then `xrandr --setprovideroutputsource NVIDIA-G0 modesetting`
   and `xrandr --auto` (reverse PRIME). Then `spike/phase11/check.sh external`.

Undo everything: `sudo spike/phase11/rollback.sh`, then reboot.

### elogind's hook directory (2026-10-03)
The first hook test did nothing: the hook never ran. Devuan's elogind 255
(`libelogind-shared-255.so`) runs sleep hooks from **`/usr/libexec/system-sleep/`**
and `/etc/elogind/system-sleep/`, not `/usr/lib/elogind/system-sleep/`. That
directory exists only because `tlp` ships `49-tlp-sleep` there, so **TLP's sleep hook
has never run on Tekne**, and attempt 1's NVIDIA hook would have been ignored too. DEC-041's
design names the wrong directory. The keyboard hook is now installed as
`/usr/libexec/system-sleep/tekne-asus-kbd-spike`.

The logger also failed to start: `debug-on.sh` used `pgrep -f kmsg-logger.sh`, which
matched a monitoring command that mentioned the same name. It uses a PID file now.

### The freeze after resume is a VT switch that doesn't come back (2026-10-03)
- The NVIDIA module calls `pm_vt_switch_required(dev, NV_TRUE)` when it probes the GPU
  (`kernel-open/nvidia/nv-pci.c`, and again in `nvidia-drm-drv.c`: "For now, a VT
  switch is required during suspend and resume"). `amdgpu` and `nouveau` opt out.
  So since the NVIDIA install, every suspend and hibernate moves to the kernel's
  suspend console (tty63) and back. Under seatd, X logs `Disabling seat` and
  then `Enabling seat`.
- **Hibernate 1 froze:** X logged `Disabling seat` and nothing after it. The kernel
  finished `hibernation exit` and restarted tasks. Both keyboards' Caps Lock still
  toggled, which a text VT does and X's VT doesn't. So the console stayed on tty63.
  Suspend 6 (`RESET_RESUME`) matches the same picture.
- **Hibernate 2** (`vt-watch.sh`, `results/vt-watch-hibernate.txt`) worked: tty63 at
  resume, then tty1 two seconds later, then `Enabling seat`, then the keyboard hook.
- **Candidate fix:** `files/tekne-vt-restore-spike-sleep`. It records the VT before sleep
  and, if the kernel hasn't switched back within 2 s, runs `chvt` back to it, like
  NVIDIA's own `nvidia-sleep.sh`. It logs every resume, so failures can be counted.
- **Hibernate 3 and 4,** with both hooks: 3 resumed fine. 4 froze again, but the VT hook
  logged `hibernate resumed on tty1`, so the kernel *had* switched back. X logged
  `Disabling seat` at 16:50:59 and nothing after that, so seatd never re-enabled X's seat
  (or X couldn't take it). The power button then shut down cleanly through elogind,
  so the rest of the system was working. The VT theory was wrong; the problem is
  seatd/X's seat handling. (`vt-watch.sh` had stopped with the session that started it,
  so it didn't record this one.)
- **Next:** libseat 0.9.1 also has a **logind backend** (elogind), and XLibre uses seatd
  only because `seatd` runs and comes first. `~/.xserverrc` runs the same server with
  `LIBSEAT_BACKEND=logind`, with no root needed and `rm ~/.xserverrc` to undo it.
  elogind would then handle the session across VT switches, and it hands X its DRM fds
  as master, which may also fix NVIDIA's "Failed to acquire modesetting permission".

### Results under libseat's logind backend (2026-10-03)
With `~/.xserverrc` (`LIBSEAT_BACKEND=logind`), X logs "Seat opened with backend
'logind'", and the seat changes come from `libseat/backend/logind.c`.
`results/vt-watch-logind.txt` records each console switch.
- **Hibernate: 3 of 3 resumed** (17:07, 17:09, 17:11). Each time the console went to
  tty63 and back to tty1 within 2–3 s, X logged `Enabling seat`, and the keyboard hook
  re-probed `1-3`. Under seatd, 2 of 4 had frozen.
- **Suspend: 2 of 2 resumed** (17:20, 17:21), the same way.
- New harmless noise: `seatd_libseat no libseat ID` at every switch (seen under seatd
  too), and once `modeset(0): Failed to set CTM property: -13` just after a resume.
- **The NVIDIA X screen still fails** ("Failed to acquire modesetting permission"),
  so logind's DRM-master handover isn't what the NVIDIA DDX needs.
- polybar started about 6 s after X at the first login with logind. Not yet compared
  with seatd.
