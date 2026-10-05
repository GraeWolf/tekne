#!/bin/sh
# Create a draft GitHub release from a tested tag build (DEC-039). Run by the
# release job in .github/workflows/build.yml, after build-and-test passed:
#   scripts/ci-release.sh TAG DIR
# DIR holds the tekne-iso artifact (ISO, .sha256, .packages, build-info.txt,
# and packages/ with Tekne's .debs).
# With DRY_RUN=1 it checks everything and prints the gh command instead.
# Needs GH_TOKEN (contents: write) and gh, which GitHub's runners have.
set -eu

die() { echo "ci-release: $*" >&2; exit 1; }

TAG="${1:?usage: $0 TAG DIR}"
DIR="${2:?usage: $0 TAG DIR}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${TAG#v}"
[ "${VERSION}" != "${TAG}" ] || die "tag ${TAG} doesn't start with v"
NAME="tekne-${VERSION}-amd64"
INFO="${DIR}/build-info.txt"
MAX_BYTES=2147483648   # GitHub Releases' limit per file (DEC-020)

# 1. It's a clean build of exactly this tag: scripts/build.sh only gives a
#    build the plain version when the checkout is clean and at tag v<VERSION>.
[ -f "${INFO}" ] || die "${INFO} missing"
field() { sed -n "s/^$1: //p" "${INFO}"; }
[ "$(field version)" = "${VERSION}" ] \
	|| die "build-info.txt says version '$(field version)', not ${VERSION}: not a clean build of ${TAG} (is VERSION ${VERSION}?)"
[ "$(field git_dirty)" = no ] || die "build-info.txt says the tree was dirty"

# 2. Every file is there, under the size limit, and the checksum verifies.
#    The .debs are the ones installed systems get from Tekne's APT repository
#    once the release is published (DEC-040); tekne-installer belongs only in
#    the live image. Each must match the checksum the build recorded.
FILES="${DIR}/${NAME}.iso ${DIR}/${NAME}.iso.sha256 ${DIR}/${NAME}.packages ${INFO}"
PKG_VERSION="$(field package_version)"
for p in tekne-apt-sources tekne-branding tekne-config tekne-desktop tekne-nvidia-repo tekne-nvidia; do
	deb="${DIR}/packages/${p}_${PKG_VERSION}_all.deb"
	[ -f "${deb}" ] || die "${deb} missing"
	want="$(field deb | awk -v f="$(basename "${deb}")" '$1 == f { print $2 }')"
	[ -n "${want}" ] || die "build-info.txt has no checksum for $(basename "${deb}")"
	[ "$(sha256sum < "${deb}" | cut -d' ' -f1)" = "${want}" ] || die "$(basename "${deb}") doesn't match build-info.txt"
	FILES="${FILES} ${deb}"
done
for f in ${FILES}; do
	[ -f "${f}" ] || die "${f} missing"
	size="$(stat -c %s "${f}")"
	[ "${size}" -lt "${MAX_BYTES}" ] || die "${f} is ${size} bytes, over GitHub's 2 GiB limit"
done
(cd "${DIR}" && sha256sum --check --strict "${NAME}.iso.sha256") || die "ISO checksum doesn't match"

# 3. CHANGELOG.md has a section for this version ("## 0.1 (date)"); its body
#    becomes the release notes.
NOTES="$(mktemp)"
trap 'rm -f "${NOTES}"' EXIT
awk -v v="${VERSION}" '
	/^## / { if (found) exit; found = ($2 == v); next }
	found && (started || NF) { started = 1; print }
' "${REPO}/CHANGELOG.md" > "${NOTES}"
grep -q '[^[:space:]]' "${NOTES}" || die "CHANGELOG.md has no section for ${VERSION}"

# 4. A draft, so a person reviews it and presses Publish. Versions with a
#    "-" (0.1-rc2) are pre-releases.
set -- gh release create "${TAG}" --draft --verify-tag --title "Tekne ${VERSION}" --notes-file "${NOTES}"
case "${VERSION}" in *-*) set -- "$@" --prerelease ;; esac
# shellcheck disable=SC2086
set -- "$@" ${FILES}

if [ "${DRY_RUN:-0}" = 1 ]; then
	echo "ci-release: dry run; would run: $*"
	echo "--- release notes:"
	cat "${NOTES}"
	exit 0
fi
"$@"
echo "ci-release: draft release ${TAG} created; review and publish it on GitHub"
