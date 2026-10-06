# Testing Tekne

Automated tests run in QEMU and never touch the host's disks (see README):
`tests/smoke/live-boot.py`, `tests/smoke/repo.py`, `tests/smoke/install.py`,
`tests/smoke/upgrade.py`, `tests/smoke/nvidia.py`. CI (`.github/workflows/build.yml`,
DEC-038) runs all five on every push and pull request. `tests/smoke/release.py`
is run by hand after each release is published (docs/building.md, "Release").

This file is the manual checklist for what they can't cover: real hardware
(SPEC §5.2).

## Live-USB hardware check

Booting the live USB **doesn't touch the internal disk**: the live system runs
from the stick and RAM. Do this on any machine before installing Tekne on it
(it's part of the release candidate gate, SPEC §7).

### Prepare

1. Write the ISO to a USB stick. **Check the device name first** (`lsblk`); this
   overwrites the whole stick:

   ```sh
   sudo dd if=out/tekne-<version>-amd64.iso of=/dev/sdX bs=4M status=progress oflag=sync
   ```

2. Disable Secure Boot in the firmware setup (DEC-016); Tekne's boot chain
   isn't signed.
3. Boot from the stick (usually via a one-time boot menu key such as F12, F9
   or Esc) and pick "Tekne live". If the screen stays black, try "Tekne live
   (safe graphics)". The desktop starts on its own; the live user is `user`,
   password `live`.

### Checklist

Note anything that fails, with the output of `lspci -nn` and `dmesg | tail -50`.

| Area | Check |
|---|---|
| Graphics | Desktop appears at the panel's native resolution; no tearing when moving windows |
| External display | Plug in a monitor: `xrandr` lists it; `xrandr --output <name> --auto --right-of eDP-1` shows the desktop on it |
| Wi-Fi | Click the bar's network module (opens `nmtui`) → Activate a connection → join a network; Brave loads a page |
| Wired | If there's a port: plugging a cable gets an address (`ip addr`) |
| Audio | Play a video in Brave: sound from the speakers; volume keys and mute change it; headphones switch output (`pavucontrol`) |
| Microphone | `pavucontrol` → Input Devices shows the level moving when you speak |
| Brightness | Brightness keys change the panel backlight |
| Keyboard | Special keys, touchpad clicks and scrolling work |
| Bluetooth | `blueman-manager` sees nearby devices |
| Suspend | `Mod+Shift+e` → suspend, then wake with the power button or lid: the desktop comes back, Wi-Fi reconnects |
| Lock | `Mod+Escape` locks; your password (`live`) unlocks |
| Battery | The bar shows the battery; unplugging the charger changes it |

Hibernation can't be checked from the live USB (it needs the installed
system's swapfile). It's checked by `tests/smoke/install.py` in QEMU, and on
real hardware after the first install (SPEC §7, Phase 3).

### Hybrid NVIDIA laptops

On a laptop with an integrated GPU (Intel or AMD) plus an NVIDIA GPU, the
integrated one normally drives the internal panel and Tekne's desktop. The
kernel also loads the open `nouveau` driver for the NVIDIA GPU, which lets it
power down when idle but can cause trouble on some models. Check:

1. `lsmod | grep nouveau` shows it loaded, and `dmesg | grep -i nouveau` has no
   errors or hangs.
2. `cat /sys/bus/pci/devices/0000:01:00.0/power/runtime_status` (adjust the
   address from `lspci`) says `suspended` after a minute idle.
3. Suspend/resume (above) works with `nouveau` loaded.
4. If any of these fail, reboot, press `e` on the "Tekne" boot entry, add
   `modprobe.blacklist=nouveau` to the end of the `linux` line, press Ctrl-X,
   and repeat the checklist. If that fixes it, Tekne should blacklist
   `nouveau` by default; record the decision in DECISIONS.md.

### NVIDIA's driver (`tekne-nvidia`)

On an installed system, after installing NVIDIA's driver the way
[customizing.md](customizing.md) describes (DEC-041). It supports Turing (GTX 16xx,
RTX 20xx) and newer GPUs. CI checks that the packages install and purge cleanly
in QEMU (`tests/smoke/nvidia.py`), but only real hardware can check the driver:

1. **Module:** after a reboot, `lsmod | grep -E '^nvidia'` lists `nvidia`,
   `nvidia_modeset` and `nvidia_drm`, and `lsmod | grep nouveau` lists nothing.
   `/usr/sbin/dkms status` shows the module `installed` for `uname -r`.
2. **Offload:** `tekne-prime-run glxinfo -B | grep vendor` reports NVIDIA, and plain
   `glxinfo -B` reports the integrated GPU (`glxinfo` is in `mesa-utils`).
3. **Power:** on battery, the GPU's `power/runtime_status` (see above) says
   `suspended` a minute after the last offloaded program exits, and
   `/proc/driver/nvidia/gpus/*/power` says "Video Memory: Off". On AC it stays
   `active`: TLP keeps it powered there (a known limitation, DEC-041).
4. **Suspend and hibernate,** on AC and on battery: the session resumes and every
   keyboard works. (ASUS N-KEY keyboards need DEC-044's hook, which tekne-config
   ships.)
5. **A kernel upgrade:** after `apt upgrade` brings a new backports kernel, DKMS
   builds the module for it (step 1 after rebooting).
6. **External monitors:** outputs wired to the integrated GPU work. Outputs wired to
   the NVIDIA GPU (often HDMI) don't yet (DEC-041); note which ones.
7. **Back to nouveau:** `sudo tekne-nvidia-remove`, then reboot. `nouveau` is
   loaded again, and `dpkg -l '*nvidia*'` lists only `firmware-nvidia-graphics`.

### Autologin after the LUKS passphrase

On an encrypted install with autologin (DEC-042), whether it was chosen in the
installer or turned on with `sudo tekne-autologin on`. `install.py` checks the
same things in QEMU. On hardware they confirm the real keyboard, display and
suspend:

1. **One passphrase:** from power-on, the LUKS passphrase is the only thing you
   type before the desktop appears.
2. **Still locked where it should be:** `Mod+Escape` and suspend lock the screen,
   and only your password unlocks it. `sudo` asks for it. `Ctrl+Alt+F2` shows a
   login prompt.
3. **Keyring:** the first app that needs a secret (Brave, for example) asks for
   your password once. After that, nothing asks again until the next boot.
4. **Logout:** the power menu's logout brings the desktop straight back.

## Before installing on a machine you depend on

The installer erases the whole disk (DEC-005): there's no dual-boot option.

- Push every git repository and back up your home directory, SSH and GPG
  keys, and anything else on the disk.
- Pass the live-USB check above on that machine.
- Keep the USB stick: it's also your rescue system.
