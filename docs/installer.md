# tekne-installer

A gum-based TUI that installs the running live system to a single whole disk,
with optional LUKS2 encryption, on BIOS or UEFI machines. Scope is fixed by DEC-005.

## 1. Approach

The installer **copies the live system image** to the target, then removes
live-only packages and configures the target system. This is the same model
Devuan's `refractainstaller` uses. It needs no network during install, and the
installed system matches what the user tested live.

The source is the pristine squashfs (`/run/live/rootfs/filesystem.squashfs`), not
the running root. Changes the live session makes at runtime therefore never
reach the installed system: the live user, autologin, and files live-config
generates at boot.

Implementation: `/usr/sbin/tekne-install`, a bash script using `gum` for all
prompts, packaged as `tekne-installer` (live image only). The interactive and
unattended paths share every validation and install step.

## 2. Flow

1. **Preflight**
   - The script must run as root in the live session. Otherwise it exits.
   - It detects the firmware mode (`/sys/firmware/efi` means UEFI, otherwise BIOS) and shows it. Installing in the other mode isn't supported.
   - It lists candidate disks (`lsblk`), excluding the live medium, read-only devices, and disks smaller than 20 GiB plus the swapfile size (installed RAM, rounded up to the next GiB).
2. **Target disk.** The user picks a disk with `gum choose`, which shows model, size, and existing partitions.
3. **Encryption.** "Encrypt the disk?" (`gum confirm`). If yes, the user enters a passphrase twice (`gum input --password`), with a minimum length and a match check.
4. **System settings**
   - Hostname (default `tekne`)
   - Timezone (a filtered list from `/usr/share/zoneinfo`)
   - Locale (a curated short list, with an option to type one)
   - Keyboard layout (defaults to the live session's layout)
5. **User.** Full name, username (validated), and password twice. The user joins `sudo`, `audio`, `video`, `netdev`, `plugdev`, and `bluetooth`. The root account is locked.
6. **Summary and confirmation.** Show every choice. The user has to type the disk name (for example `nvme0n1`) to proceed. Anything else aborts, and nothing has been written yet.
7. **Partition**, from a fixed layout (§3).
8. **Encrypt and format.** Run `cryptsetup luksFormat --type luks2` if encryption was chosen, then `mkfs.vfat` for the ESP and `mkfs.ext4` for the other partitions.
9. **Copy** the live root to the target with `rsync -aHAX` (excluding `/proc`, `/sys`, `/dev`, `/run`, `/tmp`, `/media`, and live-only paths), and show progress. `/boot`'s contents are copied in a second pass, because `/boot` is a separate partition and a hard link can't cross filesystems: from kernel 7.2, `/usr/lib/modules/VERSION/vmlinuz` and `config` are hard links to the copies in `/boot`.
10. **Configure the target** in a chroot:
    - `fstab` and `crypttab` by UUID. The LUKS mapping is named `tekne`, so the boot prompt reads "Please unlock disk tekne:" (DEC-037)
    - Hostname, `/etc/hosts`, timezone, locale, and keyboard (`/etc/default/keyboard`)
    - Create the user, lock root, and create the user's XDG directories (`xdg-user-dirs-update`, named for the chosen locale)
    - Purge the live packages (`live-boot*`, `live-config*`, `live-tools`) and `tekne-installer`. Remove Tekne's live-only files (`0161-tekne-autologin`, `tekne-serial-getty`), and restore `/etc/inittab` from `/usr/share/sysvinit/inittab`, which drops the live image's serial test getty.
    - Create the swapfile (DEC-017): `/swapfile`, size = RAM rounded up to the next GiB, mode 0600, created with `mkswap --file` so it has no holes
    - Configure resume: `resume=UUID=<root fs UUID> resume_offset=<offset>` go on the kernel command line (`GRUB_CMDLINE_LINUX`), because initramfs-tools reads `resume_offset` only from there. The offset is the first physical extent from `filefrag -v /swapfile`. `/etc/initramfs-tools/conf.d/resume` gets `RESUME=UUID=…`, which makes sure the resume hook is in the initramfs.
    - Install `grub-pc` (BIOS) or `grub-efi-amd64` (UEFI) offline from `.deb`s the build downloads into `/usr/share/tekne-installer/debs/`. The two conflict, so neither can be in the live image; their `-bin` packages are. debconf is preseeded so future GRUB upgrades reinstall to the right disk, and on UEFI keep the removable-media copy.
    - `cryptsetup`, `cryptsetup-initramfs`, `efibootmgr` and the GRUB package are marked manually installed, so `apt autoremove` can't take them.
    - Run `update-initramfs -u -k all`
    - Run `grub-install` (UEFI: with an NVRAM entry, plus `--removable`; `efivarfs` is mounted first if needed), then `update-grub`
11. **Finish.** Unmount, close LUKS, copy the install log to the target's `/var/log/tekne-installer.log`, and offer to reboot.

## 3. Partition layouts (GPT in both modes)

| # | UEFI | BIOS | Size | FS |
|---|---|---|---|---|
| 1 | ESP | BIOS boot (`bios_grub`) | 512 MiB / 1 MiB | vfat / none |
| 2 | `/boot` | `/boot` | 1 GiB | ext4 |
| 3 | `/` (LUKS2 if encrypted) | `/` (LUKS2 if encrypted) | rest | ext4 |

`/boot` is a separate, unencrypted partition in both modes. This keeps GRUB simple,
because GRUB's LUKS2 support is limited, and only one passphrase prompt (in the
initramfs) is needed.

## 4. Error handling

- `set -Eeuo pipefail` plus an `ERR`/`EXIT` trap. The trap unmounts everything under the target mountpoint, closes the LUKS mapping, and prints the log path.
- There's no rollback: once step 7 starts, the disk has been wiped. Each run starts from scratch, so a failed install is fixed by re-running the installer.
- Every command and its output goes to `/var/log/tekne-installer.log`, which never contains passphrases or passwords.
- Passwords are passed to `cryptsetup` and `chpasswd` on stdin, never as command-line arguments.

## 5. UX rules

- Every prompt screen shows its step number (for example "step 3/5"), and `Esc` goes back until the confirmation step.
- No destructive action happens before the confirmation (§2 step 6).
- Messages are short and technical. No wizard fluff.

## 6. Unattended mode (for tests)

`tekne-install --answers <file>` reads a `KEY=value` answers file: `DISK=`,
`CONFIRM_DISK=`, `ENCRYPT=`, `LUKS_PASSPHRASE=`, `HOSTNAME=`, `TZ=`, `LOCALE=`,
`KEYMAP=`, `FULLNAME=`, `USERNAME=`, `PASSWORD=`, and `SERIAL_CONSOLE=`. The last
adds a serial getty and `console=ttyS0` to the installed system, for tests. The
file is parsed, never sourced, and unknown keys are an error. Every value goes
through the same validation as the interactive prompts.

For automated tests, the answers file reaches the live system through **QEMU
fw_cfg** (`-fw_cfg name=opt/tekne/answers,file=…`). The `tekne-autoinstall`
init script (in `tekne-installer`) runs the installer unattended and then
powers off, but only when **both** of these hold:
- the live system was booted from the "serial console" GRUB entry (`tekne.serial`)
- the fw_cfg answers file exists

fw_cfg exists only in QEMU, so an automated install can never erase a disk on
real hardware, and there's no extra boot menu entry. (GRUB 2.12 in Excalibur
has no `hiddenentry`, so a hidden entry wasn't an option.)

`tests/smoke/install.py` runs the {BIOS, UEFI} × {plain, LUKS} matrix on blank
virtual disks. It then boots each installed disk, logs in over serial, and runs
`tests/smoke/installed-checks.sh` as root (also passed via fw_cfg) to check:
- A login prompt appears (for LUKS runs, after the passphrase is sent over serial).
- The no-systemd runtime check passes.
- The user can `sudo`.
- `lsblk` shows the expected layout.
- No live-* packages remain.
- Hostname, timezone, locale and keyboard match the answers file; root is locked; the user is in `sudo`.
- Tekne's firewall is loaded, and the right GRUB package is installed.
- The swapfile is active and RAM-sized, and the kernel's `resume=`/`resume_offset=` match the root filesystem and swapfile.

Then it hibernates each installed system with `loginctl hibernate`, boots the disk again, and checks that the same session resumed (a token written to `/dev/shm` before hibernating is still there).
