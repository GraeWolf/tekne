#!/bin/bash
# Runs inside the build container; started by scripts/build.sh.
# /src is the repository (read-only). /out receives the outputs and keeps
# live-build's package cache between builds.
set -euo pipefail

: "${TEKNE_VERSION:?}" "${TEKNE_PKG_VERSION:?}" "${TEKNE_GIT_SHA:?}" "${TEKNE_GIT_DIRTY:?}"
: "${TEKNE_BASE_IMAGE:?}" "${TEKNE_IMAGE_ID:?}"
NAME="tekne-${TEKNE_VERSION}-amd64"
WORK=/build

rm -rf /out/packages
if [ "${TEKNE_PACKAGES_ONLY:-no}" = yes ]; then
	/src/scripts/build-packages.sh /src/packages /out/packages "${TEKNE_PKG_VERSION}"
	exit 0
fi
rm -f /out/tekne-*-amd64.* /out/build-info.txt /out/build.log
rm -rf /out/test-repo

rm -rf "${WORK}"
mkdir -p "${WORK}/cache"
cp -a /src/live-build/auto /src/live-build/config "${WORK}/"

# Only the downloaded .deb caches persist. The bootstrap stage cache stays in
# the work directory, so every build starts from a freshly bootstrapped base.
for stage in bootstrap chroot binary; do
	mkdir -p "/out/cache/packages.${stage}"
	ln -s "/out/cache/packages.${stage}" "${WORK}/cache/packages.${stage}"
done

# Tekne's own packages (packages/*), also copied to out/packages/ for updating
# installed systems by hand (DEC-006). live-build installs every .deb in
# config/packages.chroot/ during its package-list step, before the third-party
# repositories exist, so tekne-desktop goes into the chroot as a plain file
# instead; config/hooks/normal/0500-tekne-desktop.hook.chroot installs it.
# tekne-nvidia-repo and tekne-nvidia stay out of the image altogether: they're
# opt-in, published in Tekne's repository only (DEC-041).
/src/scripts/build-packages.sh /src/packages /out/packages "${TEKNE_PKG_VERSION}" 2>&1 | tee /out/build.log
mkdir -p "${WORK}/config/packages.chroot" "${WORK}/config/includes.chroot/var/cache/tekne"
for deb in /out/packages/*.deb; do
	case "$(basename "${deb}")" in
		tekne-desktop_*) cp "${deb}" "${WORK}/config/includes.chroot/var/cache/tekne/" ;;
		tekne-nvidia*)   ;;
		*)                cp "${deb}" "${WORK}/config/packages.chroot/" ;;
	esac
done

# The live ISO's GRUB uses tekne-branding's theme, the same one installed
# systems get (DEC-034). Its background also replaces live-build's default
# splash.png, which is Debian's artwork.
mkdir -p "${WORK}/branding" "${WORK}/config/bootloaders/grub-pc/themes"
dpkg-deb -x /out/packages/tekne-branding_*_all.deb "${WORK}/branding"
cp -a "${WORK}/branding/usr/share/grub/themes/tekne" "${WORK}/config/bootloaders/grub-pc/themes/"
cp "${WORK}/branding/usr/share/grub/themes/tekne/background.png" "${WORK}/config/bootloaders/grub-pc/splash.png"

cd "${WORK}"
lb config 2>&1 | tee -a /out/build.log
lb build 2>&1 | tee -a /out/build.log

# DEC-040: the build keeps away from Tekne's own repository (config/apt/apt.conf).
# The hook 0510-check-apt-origins checks that up to the hooks; this covers the
# apt-get update live-build runs after them, whose indexes go into the image.
if ls chroot/var/lib/apt/lists/ | grep -q 'graewolf\.github\.io'; then
	echo "FAIL: the image has indexes from Tekne's own repository" | tee -a /out/build.log
	exit 1
fi

cp live-image-amd64.packages "/out/${NAME}.packages"
echo "==> Checking the no-systemd rule (SPEC.md §4)" | tee -a /out/build.log
/src/scripts/check-no-systemd.sh "/out/${NAME}.packages" 2>&1 | tee -a /out/build.log

cp live-image-amd64.hybrid.iso "/out/${NAME}.iso"
(cd /out && sha256sum "${NAME}.iso" > "${NAME}.iso.sha256")

cat > /out/build-info.txt <<EOF
version: ${TEKNE_VERSION}
package_version: ${TEKNE_PKG_VERSION}
git_sha: ${TEKNE_GIT_SHA}
git_dirty: ${TEKNE_GIT_DIRTY}
build_date: $(date -u +%Y-%m-%dT%H:%M:%SZ)
base_image: ${TEKNE_BASE_IMAGE}
build_image_id: ${TEKNE_IMAGE_ID}
live_build: $(dpkg-query -W -f '${Version}' live-build)
iso: ${NAME}.iso
iso_size_bytes: $(stat -c %s "/out/${NAME}.iso")
iso_sha256: $(cut -d' ' -f1 "/out/${NAME}.iso.sha256")
packages: $(wc -l < "/out/${NAME}.packages")
EOF
# One line per Tekne .deb, "deb: FILE SHA256". CI's release and publishing
# jobs check the .debs they publish against these (DEC-040).
(cd /out/packages && for deb in *.deb; do echo "deb: ${deb} $(sha256sum < "${deb}" | cut -d' ' -f1)"; done) >> /out/build-info.txt
cat /out/build-info.txt

# A test repository (DEC-040): the same layout as the published one, built by
# the same script, but signed with a throwaway key made for this build only
# and thrown away with it. tests/smoke/repo.py serves it to the live ISO in
# QEMU. It holds this build's Tekne packages and a decoy: a "base-files" with
# a higher version than any real one, which tekne-apt-sources' pin must keep
# from ever being installed. wrong-key.gpg is another throwaway key, for
# checking that apt refuses a repository signed by a key it doesn't trust.
echo "==> Building the test repository" | tee -a /out/build.log
TR="$(mktemp -d)"
mkdir -p "${TR}/debs" "${TR}/decoy/DEBIAN" /out/test-repo
cp /out/packages/tekne-{apt-sources,branding,config,desktop,nvidia-repo,nvidia}_*.deb "${TR}/debs/"
printf '%s\n' "Package: base-files" "Version: 99:0" "Architecture: all" \
	"Maintainer: Tekne project <noreply@tekne.invalid>" \
	"Description: decoy for tests/smoke/repo.py; must never be installed" > "${TR}/decoy/DEBIAN/control"
dpkg-deb --root-owner-group -b "${TR}/decoy" "${TR}/debs/base-files_99.0_all.deb" >/dev/null
for key in test wrong; do
	mkdir -m 700 "${TR}/gnupg-${key}"
	GNUPGHOME="${TR}/gnupg-${key}" gpg --batch --quiet --passphrase '' \
		--quick-gen-key "Tekne ${key} repository key (throwaway, this build only)" ed25519 sign 1d
	GNUPGHOME="${TR}/gnupg-${key}" gpg --batch --export > "/out/test-repo/${key}-key.gpg"
done
GNUPGHOME="${TR}/gnupg-test" TEKNE_REPO_VERIFY_KEY=/out/test-repo/test-key.gpg \
	/src/scripts/build-repo.sh /out/test-repo/repo excalibur="${TR}/debs" excalibur-rc="${TR}/debs" 2>&1 | tee -a /out/build.log
for key in test wrong; do GNUPGHOME="${TR}/gnupg-${key}" gpgconf --kill gpg-agent; done
rm -rf "${TR}"

# The signing-subkey rotation in docs/building.md, with throwaway keys and
# this container's APT, which is Devuan's like Tekne's (DEC-040).
echo "==> Testing the signing key rotation" | tee -a /out/build.log
/src/tests/key-rotation.sh 2>&1 | tee -a /out/build.log
