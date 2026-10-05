# Desktop Stack

herbstluftwm on Xorg. Everything a desktop environment would normally provide is
chosen explicitly here. All of it is pulled in by the `tekne-desktop` metapackage
and configured by `tekne-config`.

> Phase 2 checked every package: all exist in Excalibur (or in the Brave and
> XLibre repositories, DEC-026), and resolving the whole stack from an empty
> system pulls in no systemd package. Substitutions are in the Notes column.
> `packages/tekne-desktop/debian/control` is the authoritative list.

## 1. Components

| Role | Choice | Notes |
|---|---|---|
| Display server | `xlibre` (metapackage), `xinit` | X11 only (DEC-004). XLibre from its third-party repo (DEC-027); Excalibur backports aren't needed. Runs NVIDIA's 615 driver for PRIME offload; outputs wired to the NVIDIA GPU don't work yet (DEC-041) |
| Login | tty1 login → `startx` (DEC-014) | Live session: autologin on tty1 |
| Seat/session | `elogind`, `libpam-elogind`, `polkitd` | Rootless X, device access, lid/power keys. Devuan's `libelogind-compat` replaces `libsystemd0` in the desktop image, and `udev` is Devuan's transitional package for `eudev` |
| Window manager | `herbstluftwm` | |
| Bar | `polybar` | Tags, window title, network, volume, battery, clock, tray |
| Launcher | `rofi` | App launcher, window switcher, power menu |
| Notifications | `dunst` | |
| Compositor | `picom` | Tear-free, minimal effects |
| Polkit agent | `lxpolkit` | Needed for GUI privilege prompts |
| Screen lock | `xss-lock` + `i3lock` | Locks on suspend and idle |
| Network UI | `network-manager` (`nmcli`, `nmtui`) | DEC-011. No tray applet. Clicking polybar's network module opens `nmtui` in a terminal |
| Audio | `pipewire`, `pipewire-pulse`, `wireplumber`, `pavucontrol`, `pamixer` | DEC-012 |
| Bluetooth | `bluez`, `blueman` | |
| Power/laptop | elogind (lid/suspend/hibernate, DEC-017), `brightnessctl`, `tlp` | tlp has no systemd dependency. Its sleep hook is in a directory Devuan's elogind doesn't read, so tekne-config's `/usr/libexec/system-sleep/49-tekne-tlp` runs it (DEC-025) |
| Terminal | `alacritty` | Started through `tekne-terminal`, Tekne's `x-terminal-emulator` alternative, which adds Tekne's config (DEC-034) |
| File manager | `thunar` + `gvfs`, `tumbler` | Removable media and trash. `tumbler` provides Thunar's thumbnails |
| Editor | `neovim` (CLI) + `mousepad` (GUI) | |
| Browser | `brave-origin` (default), `firefox-esr` (fallback) | DEC-028. Brave Origin from Brave's APT repo (DEC-026). Default set by `/etc/xdg/mimeapps.list` (tekne-config) and by pointing the `x-www-browser` alternative at `brave-origin-stable` on first install (tekne-desktop postinst). Firefox policies in tekne-config |
| Keyring | `gnome-keyring`, `libpam-gnome-keyring` | DEC-030. Secret Service for Brave, Melia, Firefox and NetworkManager. Unlocked by PAM at tty1 login, through tekne-config's `tekne-gnome-keyring` PAM profile (Excalibur's own profile covers password changes only) |
| Email | Melia, not preinstalled | DEC-029. `tekne-get-melia` downloads and verifies the signed `.deb` on demand |
| Screenshots | `maim` + `xclip` | `tekne-screenshot`, bound to `Mod+p` / `Mod+Shift+p` |
| Clipboard | `xclip`, `copyq` | `clipmenu` isn't packaged in Excalibur; CopyQ replaces it (`Mod+v`). `cliphist` and `clipman` are Wayland-only |
| Images/PDF | `feh` (also sets wallpaper), `zathura` | |
| Fonts | `fonts-noto`, `fonts-noto-color-emoji`, `fonts-jetbrains-mono` | |
| Theming | Tokyo Night colours; dark Adwaita (GTK) and `papirus-icon-theme`, `lxappearance` | DEC-034. No Tokyo Night GTK theme is packaged in Devuan |
| Firewall | `nftables` + Tekne ruleset | DEC-023 |
| Time sync | `chrony` | DEC-024. Must not use systemd-timesyncd |

Developer tools aren't in the ISO (DEC-033); see the README for the one-line install.

## 2. Session startup

With no systemd user services, the X session itself starts everything. It uses
Debian's standard `startx` → `Xsession` path, so a user's own `~/.xinitrc` or
`~/.xsession` still takes precedence. Order matters:

1. **tty1 login.** `/etc/profile.d/tekne-startx.sh` exports `LIBSEAT_BACKEND=logind`
   (unless already set) and runs `exec startx` on tty1 if
   `$DISPLAY` is unset. To opt out, a user creates `~/.config/tekne/no-startx`. In the
   live session, Tekne's live-config component `0161-tekne-autologin` adds agetty's
   `--autologin` to the tty1–6 gettys. live-config's own `0160-sysvinit` component never
   works on Excalibur: it checks for a package named `sysvinit`, which no longer exists,
   and its `sh -c "/bin/login -f"` inittab line leaves `login` stopped by job control.
2. **`/etc/X11/Xsession`** (from `x11-common`). Its `75dbus_dbus-launch` step starts the
   D-Bus session bus (`dbus-x11`), then it runs the `x-session-manager` alternative.
3. **`tekne-session`**, registered as `x-session-manager` by `tekne-config`:
   - `gnome-keyring-daemon --start --components=secrets` attaches to the keyring that
     PAM started and unlocked at login (DEC-030), and exports its environment.
   - It runs `exec herbstluftwm --autostart /usr/share/tekne/herbstluftwm/autostart`,
     or plain `herbstluftwm` if the user has `~/.config/herbstluftwm/autostart`.
4. **The herbstluftwm autostart** sets keybindings, tags, theme and rules, then starts
   each of these once via `tekne-run-once` (herbstluftwm re-runs autostart on reload):
   - `pipewire`, `wireplumber` and `pipewire-pulse` as three processes, because Debian's
     PipeWire config doesn't start the other two
   - `lxpolkit`, `picom` (with `/usr/share/tekne/picom.conf`), `dunst`,
     `copyq --start-server`, `blueman-applet`
   - `xss-lock --transfer-sleep-lock -- i3lock`
   - the wallpaper, `/usr/share/backgrounds/tekne/tekne.png` from `tekne-branding`, set with `feh` (it isn't a running process)
   - `polybar` with `/usr/share/tekne/polybar/config.ini`

`herbstluftwm`, `polybar`, `dunst` and `nftables` each own their default config file as a
conffile. Tekne never overwrites or diverts those files. It passes its own files from
`/usr/share/tekne/` with each program's config option, or uses a place the program reads
in addition to its own file: `/etc/xdg/dunst/dunstrc.d/` for dunst, `/etc/rofi.rasi` for
rofi.

### Seat and sleep hooks
- **Seat (DEC-045).** XLibre opens its DRM and input devices through libseat. With
  `LIBSEAT_BACKEND=logind` it takes them from elogind, which also manages Tekne's
  sessions, instead of from seatd (installed because `libseat1` depends on
  `seatd | logind`). Under seatd, X sometimes didn't get its seat back after a
  suspend's VT switch, which the NVIDIA driver forces on every suspend.
- **Sleep hooks.** Devuan's elogind runs executables in `/usr/libexec/system-sleep/`
  (and `/etc/elogind/system-sleep/`) with `pre`/`post` and the sleep operation, not in
  `/usr/lib/elogind/system-sleep/`. tekne-config ships two there:
  - `49-tekne-tlp` runs tlp's own hook (`tlp suspend` / `tlp resume`), which tlp
    installs where elogind doesn't look (DEC-025).
  - `tekne-asus-keyboard` re-probes the ASUS N-KEY keyboard (`0b05:19b6`) after resume,
    because deep sleep resets its controller. It does nothing on other machines
    (DEC-044).

## 3. Keybindings (defaults)

`Mod` = Super. The full list ships as `/usr/share/tekne/keybindings.txt` and is
shown by `tekne-keys` on `Mod+F1`. The bindings themselves are in
`/usr/share/tekne/herbstluftwm/autostart`.

| Keys | Action |
|---|---|
| `Mod+Return` | Terminal (`tekne-terminal`) |
| `Mod+Space` | rofi launcher |
| `Mod+Shift+Space` | Cycle frame layout (herbstluftwm's default was `Mod+Space`) |
| `Mod+Tab` | rofi window switcher |
| `Mod+v` | Clipboard history (`copyq toggle`) |
| `Mod+1..9` / `Mod+Shift+1..9` | Switch to / move window to tag |
| `Mod+h/j/k/l` | Focus left/down/up/right |
| `Mod+Shift+h/j/k/l` | Move window |
| `Mod+Ctrl+h/j/k/l` | Resize frame |
| `Mod+u` / `Mod+o` | Split vertical / horizontal |
| `Mod+r` | Remove frame |
| `Mod+f` / `Mod+s` | Fullscreen / toggle floating |
| `Mod+w` | Close window |
| `Mod+Shift+r` | Reload herbstluftwm |
| `Mod+Escape` | Lock screen |
| `Mod+Shift+e` | rofi power menu (logout, suspend, hibernate, reboot, poweroff) |
| `Mod+F1` | Keybinding cheatsheet |
| `Mod+p` / `Mod+Shift+p` | Screenshot full / selection (replaces herbstluftwm's default `Mod+p` pseudotile, which is left unbound) |
| Media / brightness keys | pamixer / brightnessctl |

## 4. Configuration ownership

- System defaults live under `/usr/share/tekne/`, shipped by `tekne-config`, and are used only when the user has no config of their own.
- User config under `~/.config` always wins. Tekne never writes to an existing home directory after install.
- `tekne-config` upgrades never touch user files. Changes to `/etc/skel` only affect newly created users.
