# Building Tekne

How the ISO is built, tested and released, and where to change things. To
change an installed system rather than the build, see
[customizing.md](customizing.md). What Tekne is and why: [SPEC.md](../SPEC.md)
and [DECISIONS.md](../DECISIONS.md).

## Requirements

- A Linux host with root, Podman or Docker, and about 20 GB free. The build
  itself runs in a container, so the host distribution doesn't matter.
- Network access to Devuan's mirror and the Brave, XLibre and NVIDIA repositories. NVIDIA's is used only for the module check after the image is built (step 6).
- For the tests: QEMU and OVMF, and ideally KVM (`/dev/kvm`).

On Tekne, or any Devuan or Debian host, one command installs all of it
(DEC-033):

```sh
sudo apt install git podman qemu-system-x86 qemu-utils ovmf python3
```

## Build

```sh
sudo scripts/build.sh                   # packages and ISO (about 10 min; the first build downloads about 1.5 GB)
sudo scripts/build.sh --packages-only   # just Tekne's .debs, for updating an installed system (about 1 min)
```

`scripts/build.sh` uses Podman if it's installed, otherwise Docker
(`CONTAINER_ENGINE=docker` forces Docker). Both the image build and the build
run use the host's network, so the host's firewall can't get in the way.

### What happens

1. **Build container.** `container/Containerfile` builds a Devuan Excalibur
   image, pinned by digest, with Debian's live-build `.deb` checked against its
   SHA-256 (DEC-003, DEC-031).
2. **Version.** From `VERSION` and git (DEC-032). A clean checkout of tag
   `v<VERSION>` builds as `<VERSION>`. Anything else builds as
   `<VERSION>-dev<commit count>.<short commit>`, and the packages get the
   Debian form, e.g. `0.1~rc2~dev40.gabc1234`, so every build upgrades the
   last.
3. **Packages.** Every directory under `packages/` is built with debhelper into
   `out/packages/`. `tekne-branding` also renders the SVGs in `branding/`.
4. **live-build.** `live-build/auto/config` holds every `lb config` option.
   The package lists and Tekne's packages are installed, then the chroot hooks
   run in order:

   | Hook | Does | Fails the build if |
   |---|---|---|
   | `0500-tekne-desktop` | `apt-get update` with `tekne-apt-sources`' repositories, then installs `tekne-desktop` | it can't install |
   | `0505-backports-kernel` | Switches to the `excalibur-backports` kernel and purges the stable one (DEC-036) | there isn't exactly one kernel, from backports |
   | `0510-check-apt-origins` | Checks the third-party repositories (DEC-026) | a globally trusted key isn't Devuan's or Debian's, or a third-party repository supplied a package outside its pin |
   | `0520-installer-grub-debs` | Downloads `grub-pc` and `grub-efi-amd64` for the installer | their versions don't match the installed GRUB binaries |
   | `0530-os-release` | Restores the `/etc/os-release` symlink live-build replaces | os-release doesn't say Tekne after reinstalling `base-files`, or the GRUB theme is missing from `/boot` |
   | `9900-fontconfig-cache` | Builds the system font cache | no cache was built |

5. **No-systemd check.** `scripts/check-no-systemd.sh` checks the package
   manifest against SPEC §4 and `tests/systemd-allowlist.txt` (which is
   empty).
6. **NVIDIA module check (DEC-041).** `scripts/check-nvidia-dkms.sh` compiles
   NVIDIA's open kernel module, as `tekne-nvidia` would install it, against the
   kernel the image ships. It installs that kernel's headers from backports and
   downloads `nvidia-kernel-open-dkms` through NVIDIA's repository, with
   `tekne-nvidia-repo`'s key and pin. This changes the build container only, never
   the image. If the module doesn't build, the build fails, so a backports kernel
   that breaks the driver can't reach a release. It takes about 2 minutes.

### Outputs

In `out/`, with the build's version in each name:

| File | Contents |
|---|---|
| `tekne-<version>-amd64.iso` | Hybrid ISO, BIOS and UEFI (Secure Boot off) |
| `tekne-<version>-amd64.iso.sha256` | Checksum |
| `tekne-<version>-amd64.packages` | Package manifest |
| `build-info.txt` | Git commit, dirty flag, base image digest, build image, live-build version, ISO size and checksum, the NVIDIA module check (`nvidia_dkms: VERSION KERNEL`), and a `deb:` line with each `.deb`'s SHA-256 |
| `build.log` | Full log |
| `packages/` | Tekne's `.deb`s |
| `test-repo/` | A test APT repository of this build's packages and a decoy, signed with a throwaway key made for this build (`test-key.gpg`), plus a second throwaway key (`wrong-key.gpg`). For `repo.py` (DEC-040). |
| `cache/` | live-build's package cache, reused by later builds (root-owned; delete it with `sudo rm -rf out/cache` to start fresh) |

## Test

```sh
tests/smoke/live-boot.py               # live ISO on BIOS and UEFI: sysvinit, desktop processes, firewall, os-release
tests/smoke/repo.py                    # Tekne's APT repository: right key, wrong key, tampered .deb, pin (DEC-040)
tests/smoke/install.py                 # unattended installs {BIOS,UEFI} x {plain,LUKS}: booted, checked, hibernated and resumed
tests/smoke/install.py uefi luks --keep   # one case, keeping the VM in out/install-test/uefi-luks
tests/smoke/upgrade.py                 # install the previous release, upgrade it to this build with apt, re-check it
tests/smoke/upgrade.py out/install-test/uefi-luks   # the same upgrade, from a kept install.py case
scripts/test-in-qemu.sh uefi           # the newest ISO in a QEMU window (--disk, --installed)
```

They run without root and only write under `out/`. The installer runs only in
VMs: the unattended mode needs QEMU's fw_cfg, so it can't erase a real disk.
For real hardware there's the manual checklist in [testing.md](testing.md).
If the tests are much slower than usual, check the host CPU isn't stuck in a
low power state before suspecting Tekne.

## CI

`.github/workflows/build.yml` (DEC-038) runs the same `scripts/build.sh`,
`live-boot.py`, `repo.py` and `install.py` on GitHub's runners for every push
to `master`, every pull request and every tag, except commits that only change
Markdown or license texts. A green run keeps the ISO, checksum, manifest,
build-info and Tekne's `.deb`s as the `tekne-iso` artifact for 30 days; a
failed run keeps the build and serial logs. For a `v*` tag, a second job turns
a green run into a draft release (see "Release" below).

`.github/workflows/publish-repo.yml` (DEC-040) publishes Tekne's APT
repository when a release is published; see "Release".

## Where to change things

| To change | Edit | Notes |
|---|---|---|
| The desktop's packages | `packages/tekne-desktop/debian/control` | Check the package exists in Excalibur, and build: the no-systemd check fails the build on a systemd package. Record the choice in docs/desktop-stack.md. |
| Desktop defaults (session, keybindings, bar, theme, firewall, browser policies) | `packages/tekne-config/files/` | Defaults go under `/usr/share/tekne` or `/etc`, never in home directories. |
| Identity (os-release, GRUB theme, wallpaper, logo, console palette, LUKS banner) | `packages/tekne-branding/` and `branding/` | Artwork is CC-BY-SA-4.0. Replacing an SVG with real art of the same name and size needs no other change. |
| APT repositories | `packages/tekne-apt-sources/` | Third-party repositories only under DEC-026: a key checked against `keys/SHA256SUMS`, a `.sources` file with `Signed-By`, and a pin limited to specific packages. Tekne's own repository (DEC-040) follows the same rules; the build never fetches from it (`live-build/config/apt/apt.conf`). |
| The installer | `packages/tekne-installer/files/usr/sbin/tekne-install` | Design in [installer.md](installer.md). Test with `install.py` and `scripts/test-in-qemu.sh --disk`, never on a real disk. |
| Base packages and firmware | `live-build/config/package-lists/` | |
| The live session only | `live-build/config/includes.chroot/`, `live-build/config/hooks/live/` | Nothing an installed system keeps belongs here. |
| Boot menu of the ISO | `live-build/config/bootloaders/grub-pc/` | live-build replaces any line containing its `LINUX_LIVE` placeholder, comments included. |

Every decision has an entry in DECISIONS.md. When one changes, update the
entry (with a dated History line) and every doc that refers to it, in the same
commit.

## Pinned inputs

Every external input is pinned. To update one, change it and its checksum in
one commit and note it in CHANGELOG.md.

| Input | Where |
|---|---|
| Build container base image | `container/Containerfile`: `FROM ...@sha256:...` |
| Debian live-build | `container/Containerfile`: version, SHA-256, and snapshot.debian.org SHA-1 |
| Tekne's, Brave's and XLibre's signing keys | `packages/tekne-apt-sources/keys/` and `keys/SHA256SUMS` (checked when the package builds); Tekne's fingerprints are in DEC-040, and rotating its signing subkey is above |
| The previous release, for the upgrade test | `tests/smoke/previous-release`: tag, ISO name and SHA-256 |
| Melia's signing key | `packages/tekne-config/files/usr/share/tekne/keyrings/melia.gpg`, and its fingerprint in `tekne-get-melia` |
| GitHub Actions | `.github/workflows/build.yml` and `publish-repo.yml`: each `uses:` names a commit |

Packages from Devuan's mirror aren't pinned to versions: a build gets the
current ones, and the manifest records exactly which (SPEC §5.3).

## Tekne's APT repository

Installed systems get Tekne's packages from `https://graewolf.github.io/tekne/apt/`
(DEC-040), which `tekne-apt-sources` configures. `excalibur` carries releases;
`excalibur-rc` carries pre-releases and releases. It's built only from
published GitHub releases (see "Release" below), never from a push or a dev
build, and a build never fetches from it (`live-build/config/apt/apt.conf`).

Publishing needs two GitHub environments, set up once in the repository's
settings. If either is ever recreated, check:

| Environment | Setting |
|---|---|
| `repo-publish` | Required reviewer: the maintainer. Secrets `TEKNE_REPO_SIGNING_KEY` and `TEKNE_REPO_SIGNING_PASSPHRASE`. No branch restriction: publishing runs on a release's tag. |
| `github-pages` | Created by GitHub when Pages is set to deploy from GitHub Actions. It allows only `master` by default; it also needs a tag rule `v*`, or the `deploy` job is refused for every release. |

`scripts/build-repo.sh` builds and signs it. Every build runs it to make
`out/test-repo/`, signed with a throwaway key, for `tests/smoke/repo.py` and
`upgrade.py`; CI's `publish-repo` workflow runs it with the real signing
subkey.

### The signing key

| | |
|---|---|
| Public key | `packages/tekne-apt-sources/keys/tekne.gpg`, checksum in `keys/SHA256SUMS`, fingerprints in DEC-040 |
| Primary key (certify only) | Offline, on the maintainer's USB stick, with its revocation certificate. Never on a machine or service CI can reach. |
| Signing subkey | `TEKNE_REPO_SIGNING_KEY` and `TEKNE_REPO_SIGNING_PASSPHRASE`, secrets of the `repo-publish` environment, which needs the maintainer's approval to run |
| Expiry | The signing subkey expires a year after it's made (DEC-040 has the date). Rotate it at least a month before. |

Handle the secret key material with care:
- Work in a RAM keyring (`/dev/shm`), delete it when done, and stop its agent first (`gpgconf --homedir DIR --kill gpg-agent`).
- Never print a secret key in a terminal. To copy one into a GitHub secret, run `copyq disable`, then `xclip -selection clipboard < FILE`; after pasting, clear the clipboard and run `copyq enable`. CopyQ saves its history to disk.
- Write a new backup to a `.new` file and check it (`gpg --list-packets FILE | grep 'key packet'`) before replacing the old one. gpg skips any key whose passphrase prompt fails, and still writes the rest.
- To change one key's passphrase, use `gpg-connect-agent --homedir DIR 'PASSWD <keygrip>' /bye` (keygrips come from `gpg --with-keygrip -K`). `gpg --passwd` with terminal prompts asks for every key in a row without saying which, which makes mistakes easy.

### Rotating the signing subkey

The order matters. Installed systems trust only the key file
`tekne-apt-sources` gave them, so they must receive the new subkey, signed
with the old one, before the repository is signed with the new one. A system
that misses that update has to install the new `tekne-apt-sources` by hand.
`tests/key-rotation.sh`, which every build runs, checks this sequence with
throwaway keys.

1. In a RAM keyring, import the primary key from the USB stick and add a
   subkey:

   ```sh
   mkdir -m 700 /dev/shm/tekne-key
   gpg --homedir /dev/shm/tekne-key --import /path/to/usb/tekne-repo-primary.asc
   gpg --homedir /dev/shm/tekne-key --quick-add-key 2401BB7742E09C29AA41B29441BEF97FD11D7B37 ed25519 sign 1y
   ```

2. Export the public key to `packages/tekne-apt-sources/keys/tekne.gpg`,
   update its line in `keys/SHA256SUMS` and the fingerprints in DEC-040, and
   commit:

   ```sh
   gpg --homedir /dev/shm/tekne-key --export 2401BB7742E09C29AA41B29441BEF97FD11D7B37 > packages/tekne-apt-sources/keys/tekne.gpg
   ```

3. Release and publish that change as usual. CI still signs with the old
   subkey, so every system accepts the update and now trusts both subkeys.
   Leave time for systems to install it before the old subkey expires.
4. Export the new subkey alone and replace `TEKNE_REPO_SIGNING_KEY` with it
   (copying it as above, never printing it). Then run the `publish-repo`
   workflow by hand (Actions → publish-repo → Run workflow) to re-sign the
   repository with it.

   ```sh
   gpg --homedir /dev/shm/tekne-key --armor --export-secret-subkeys 'NEW_SUBKEY_FINGERPRINT!' > /dev/shm/tekne-key/ci-subkey.asc
   ```

5. Back up the primary key, now with the new subkey, to the USB stick: export
   to a `.new` file, check it, then replace the old backup. Delete the RAM
   keyring.

If a subkey is exposed, rotate the same way at once, but first revoke it
(`gpg --edit-key`, `key N`, `revkey`, reason "compromised") so the exported
public key carries the revocation. The update that delivers it is still
signed with the old subkey, because that's the only one systems trust. DEC-040's
History records the one time this happened.

## Release

Releases are published on GitHub Releases (DEC-020) and created by CI from a
tested tag (DEC-039).

1. Set `VERSION` to the release (e.g. `0.1`, or `0.1-rc2` for a release
   candidate). In CHANGELOG.md, move the "Unreleased" entries under a heading
   for it, `## 0.1 (YYYY-MM-DD)`, and commit.
2. Tag and push:

   ```sh
   git tag -a v0.1 -m "Tekne 0.1"
   git push origin master v0.1
   ```

   CI builds the tag (a clean checkout of `v<VERSION>`, so the ISO is named
   `tekne-0.1-amd64.iso` and its packages are `0.1`) and runs every test.
3. If they pass, the `release` job runs `scripts/ci-release.sh`. It checks
   that `build-info.txt` shows a clean build of exactly that version, that the
   ISO's checksum verifies, that every file is under GitHub's 2 GiB limit, and
   that CHANGELOG.md has the version's section, and that Tekne's `.deb`s match
   the checksums in `build-info.txt`. Then it creates a **draft** release with
   the ISO, `.sha256`, `.packages`, `build-info.txt` and the `.deb`s (all but
   `tekne-installer`, including the opt-in `tekne-nvidia-repo` and
   `tekne-nvidia`, which aren't in the ISO), and the CHANGELOG section as notes. Tags with a `-` are
   marked as pre-releases.
4. Review the draft on GitHub and press "Publish".
5. Publishing starts `.github/workflows/publish-repo.yml` (DEC-040), which
   waits for your approval in the `repo-publish` environment. Once approved, it
   rebuilds Tekne's APT repository from the published releases' `.deb`s
   (checked again against their `build-info.txt`), signs it with the CI
   signing subkey, checks the signatures against `keys/tekne.gpg`, and deploys
   it to GitHub Pages: a release goes into `excalibur` and `excalibur-rc`, a
   pre-release into `excalibur-rc` only.
   Once it has deployed, run `tests/smoke/release.py`. It installs the
   published ISO in QEMU and checks, against the live repository, that the
   fresh install has no `tekne-*` updates waiting, and that the repository
   offers every `.deb` the release carries at its version. It needs no
   arguments: it checks the newest published release.
6. After a **final** release, point `tests/smoke/previous-release` at it (its
   tag, ISO name, and the ISO's SHA-256 from its `.sha256` asset), so CI's
   upgrade test starts from it (SPEC §8, Phase 9). Release candidates don't
   count: during a candidate cycle the test keeps starting from the last
   final release, which is what users upgrade from.
7. Set `VERSION` to the next version and commit, so later dev builds sort above
   the release: after a release candidate, the next candidate (`0.1-rc2` →
   `0.1-rc3`); after a final release, the next series (`0.1` → `0.2-rc1`).
   Never the final version straight after a candidate: `0.1~dev…` sorts below
   `0.1~rc2`, so systems installed from the candidate couldn't upgrade. The
   final version goes into `VERSION` only in the release commit (DEC-032).

If a check fails, nothing is released or published; the job log says which
check. To try the release checks on a local build:
`DRY_RUN=1 scripts/ci-release.sh v0.1 out`.
