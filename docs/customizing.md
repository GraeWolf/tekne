# Customizing Tekne

Tekne's defaults are meant to be changed. This page lists where each one lives
and how to replace it. For building your own ISO, see
[building.md](building.md).

## How defaults work

- **Your config wins.** Tekne's defaults live in `/usr/share/tekne/` and
  `/etc/`. Each program reads them only when you have no config of your own in
  `~/.config`. Tekne's packages never write to your home directory.
- **Copy, then edit.** For most programs, the quickest start is to copy Tekne's
  file into `~/.config` and change the copy.
- **Edits to `/etc` survive upgrades.** Files under `/etc` that Tekne ships are
  conffiles: if a Tekne update changes one you've edited, dpkg asks which
  version to keep.

## The desktop session

You log in on tty1, which starts X (`startx`), which runs `tekne-session`,
which starts herbstluftwm with Tekne's autostart. The autostart sets the
keybindings, colours and window rules, and starts the session programs: audio
(PipeWire), the bar, notifications, the compositor, the clipboard manager, the
lock screen and the wallpaper. Details: [desktop-stack.md](desktop-stack.md).

| What | Tekne's default | To change it |
|---|---|---|
| Window manager setup, keybindings, startup programs | `/usr/share/tekne/herbstluftwm/autostart` | Copy it to `~/.config/herbstluftwm/autostart` and make it executable. `tekne-session` then runs herbstluftwm with yours instead. Keep the lines that start the session programs, or start them some other way. |
| Keybinding cheat sheet (`Mod+F1`) | `/usr/share/tekne/keybindings.txt` | It lists Tekne's defaults; it doesn't follow your autostart. |
| Bar | `/usr/share/tekne/polybar/config.ini` (bar `tekne`), started by the autostart | Copy it to `~/.config/polybar/config.ini`, and in your autostart copy change the `polybar` line to `--config=$HOME/.config/polybar/config.ini`. |
| Launcher, window switcher, power menu (rofi) | `/etc/rofi.rasi`, which selects `/usr/share/tekne/rofi/tokyonight.rasi` | Create `~/.config/rofi/config.rasi`. rofi reads it after Tekne's file, so you can override single settings, or set your own `@theme`. |
| Notifications (dunst) | `/etc/xdg/dunst/dunstrc.d/50-tekne.conf`, on top of dunst's own `/etc/xdg/dunst/dunstrc` | Create `~/.config/dunst/dunstrc`. dunst then uses only yours, so start from a copy of `/etc/xdg/dunst/dunstrc`. |
| Terminal | `tekne-terminal`: alacritty with `/usr/share/tekne/alacritty.toml` | Copy that file to `~/.config/alacritty/alacritty.toml`; `tekne-terminal` uses yours from then on. To use another terminal everywhere, see "Default applications" below. |
| Compositor | `/usr/share/tekne/picom.conf`, started by the autostart | Change the `picom` line in your autostart copy. |
| Wallpaper | `/usr/share/backgrounds/tekne/tekne.png`, set with `feh` by the autostart | Change the `feh` line in your autostart copy, e.g. `feh --no-fehbg --bg-fill ~/Pictures/wall.png`. |
| Lock screen | `xss-lock` runs `i3lock --color=1a1b26` | Change the `xss-lock` line in your autostart copy. |
| GTK theme, icons, font | Dark Adwaita, Papirus-Dark icons, Noto Sans: `/etc/xdg/gtk-3.0/settings.ini`, `/etc/xdg/gtk-4.0/settings.ini`, and a GSettings default for the dark style | Run `lxappearance`, or write `~/.config/gtk-3.0/settings.ini`. For GTK 4 and libadwaita apps: `sudo apt install libglib2.0-bin`, then `gsettings set org.gnome.desktop.interface color-scheme default`. |
| Colours | Tokyo Night in all of the above (DEC-034) | Each program's own config; there's no single theme switch. |
| Shell defaults: `cat` is `batcat --paging=never`, `bat` is `batcat`, and fastfetch runs when `tekne-terminal` opens a terminal | `/usr/share/tekne/bash/tekne.bashrc`, sourced by the line in `~/.bash_aliases` that new users get from `/etc/skel` | Delete that line to drop all of it, or create `~/.config/tekne/no-fastfetch` to keep the aliases only. Users created before Tekne 0.3 don't have the line; add it to `~/.bash_aliases` to opt in: `[ -r /usr/share/tekne/bash/tekne.bashrc ] && . /usr/share/tekne/bash/tekne.bashrc`. |
| fastfetch output | `/usr/share/tekne/fastfetch/config.jsonc`, with Tekne's logo | Create `~/.config/fastfetch/config.jsonc` (`fastfetch --gen-config`); it's used instead. |
| SSH keys | `/etc/ssh/ssh_config.d/tekne.conf` sets `AddKeysToAgent yes`, so the session's `ssh-agent` (started by Xsession) keeps a key after its passphrase is entered once | Set `AddKeysToAgent no` in `~/.ssh/config`. |
| XDG user directories (Documents, Downloads, ...) | Created by the installer and, if missing, by `tekne-session` at each login (`xdg-user-dirs-update`) | Edit `~/.config/user-dirs.dirs`. |

### Starting the desktop

- **Plain console on tty1:** create `~/.config/tekne/no-startx`. Logging in on
  tty1 then gives a shell; run `startx` yourself when you want the desktop.
- **Your own X session:** a `~/.xsession` or `~/.xinitrc` replaces
  `tekne-session` entirely.

## Default applications

| What | How to change it |
|---|---|
| Web browser (Brave Origin) | `xdg-settings set default-web-browser firefox-esr.desktop`, which writes `~/.config/mimeapps.list`. Programs that call `x-www-browser` use `sudo update-alternatives --config x-www-browser`. |
| Other file types (PDF, images, text, folders) | Tekne's choices are in `/etc/xdg/mimeapps.list`; entries in `~/.config/mimeapps.list` take precedence. |
| Terminal (`x-terminal-emulator`) | `sudo update-alternatives --config x-terminal-emulator`. `Mod+Return` runs `tekne-terminal`; change that in your autostart copy. |
| Email (Melia, not installed) | `sudo tekne-get-melia` downloads it and installs it only if its signature and checksum verify (DEC-029). |

## System settings

### Firewall

`/etc/tekne/nftables.conf`, loaded at boot by the `tekne-firewall` init
script (DEC-023). Inbound traffic is dropped except replies, loopback, IPv6
housekeeping, and local container and VM bridges (podman, Docker, libvirt).
To open a port, add a rule to the `input` chain, for example `tcp dport 22
accept`, then:

```sh
sudo service tekne-firewall reload
sudo service tekne-firewall status
```

`sudo service tekne-firewall stop` removes it until the next boot.

### Boot screen and console

- **Console colours and messages:** `/etc/default/grub.d/tekne-console.cfg`
  sets the Tokyo Night console palette and `loglevel=3` (DEC-037). Edit it,
  then run `sudo update-grub`.
- **Everything on screen while booting:** remove `quiet` from
  `GRUB_CMDLINE_LINUX_DEFAULT` in `/etc/default/grub`, then `sudo update-grub`.
  Without `quiet`, the banner above the LUKS prompt is also skipped.
- **GRUB theme:** `/etc/default/grub.d/tekne-theme.cfg` selects
  `/boot/grub/themes/tekne`. Point `GRUB_THEME` elsewhere, or delete the line
  for GRUB's plain menu, then `sudo update-grub`.

### Swap and hibernation

The installer creates `/swapfile` the size of your RAM and configures resume
for it (DEC-017). Hibernation depends on the swapfile's position on disk, so
don't recreate or move it by hand. To resize it:

```sh
sudo tekne-swap-resize 32    # GiB; at least your RAM, to hibernate reliably
```

### Kernel

Tekne's kernel comes from Devuan's `excalibur-backports` (DEC-036). The pin is
`/etc/apt/preferences.d/tekne-backports.pref`. To go back to the stable
kernel, delete that pin, then:

```sh
sudo apt install linux-image-amd64/excalibur
```

Keep the backports kernel installed until the stable one has booted
successfully; GRUB lists both under "Advanced options".

### NVIDIA graphics

Tekne uses the open `nouveau` driver for NVIDIA GPUs. For NVIDIA's own driver,
with PRIME offload on hybrid laptops and the GPU powered off when idle, install
it from NVIDIA's repository (DEC-041). It supports Turing (GTX 16xx, RTX 20xx)
and newer GPUs, and needs Secure Boot off (DEC-016), like Tekne itself:

```sh
sudo apt install tekne-nvidia-repo
sudo apt update
sudo apt install tekne-nvidia
```

`tekne-nvidia-repo` adds NVIDIA's repository, pinned to the driver's own
packages (DEC-026). Systems without it never contact NVIDIA. `tekne-nvidia`
installs the driver and builds its kernel module with DKMS, which takes a few
minutes and needs about 1 GiB, then sets it up for Tekne. Reboot afterwards.

- The desktop stays on the integrated GPU. To run a program on the NVIDIA GPU:
  `tekne-prime-run PROGRAM`, for example `tekne-prime-run glxinfo -B`.
- Each new kernel from `apt upgrade` gets the module rebuilt by DKMS. Tekne's
  build checks that NVIDIA's module builds for every kernel it ships.
- Suspend and hibernate work through the driver itself, with no extra setup.
- Known limitations: on AC power the GPU stays on, because TLP keeps devices
  powered when plugged in. Outputs wired to the NVIDIA GPU (often HDMI) don't
  work yet; outputs on the integrated GPU do.

To go back to `nouveau`, remove the driver with `tekne-nvidia-remove`, then
reboot. It purges both packages and everything built from the driver's source
packages, including the configuration that blacklists `nouveau`; apt lists it all
and asks first:

```sh
sudo tekne-nvidia-remove
```

`apt purge --autoremove tekne-nvidia` alone would leave most of the driver
installed. GTK 4 needs `libvulkan1`, which recommends a Vulkan driver, and apt
keeps every installed Vulkan driver it could use, NVIDIA's included. The compiler
and the running kernel's headers stay installed afterwards (apt keeps those), as
does the module-signing key DKMS made in `/var/lib/dkms/`.

### APT repositories

Besides Devuan's, Tekne enables its own repository (DEC-040), Brave's and
XLibre's repositories and `excalibur-backports`, each pinned to the few
packages Tekne takes from it (DEC-026). NVIDIA's is added only by
`tekne-nvidia-repo` (see above). The files are
`/etc/apt/sources.list.d/tekne*.sources`,
`/etc/apt/sources.list.d/brave-browser-release.sources` and
`/etc/apt/preferences.d/tekne*.pref`. To install another package from
backports, name the suite: `sudo apt install foo/excalibur-backports`.

### Updating Tekne

`sudo apt update && sudo apt upgrade` updates everything from 0.2 on,
including Tekne's own `tekne-*` packages, which come from Tekne's APT
repository (DEC-040). A system installed from 0.1 needs one extra step first,
and release candidates are a one-line change: see "Update an installed Tekne"
in the [README](../README.md).

If you edit `/etc/apt/sources.list.d/tekne.sources` (for example to follow
release candidates), dpkg asks whether to keep your version when a
`tekne-apt-sources` update changes that file. Keep yours unless the update's
notes say the address or key changed.
