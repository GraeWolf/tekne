#!/bin/bash
# Build every package under packages/ into a .deb. Runs inside the build
# container (scripts/build-in-container.sh), which has debhelper and dpkg-dev.
#   build-packages.sh SOURCE_DIR OUTPUT_DIR VERSION
# VERSION (from scripts/build.sh, DEC-032) replaces the version in each
# package's newest changelog entry, so every build's packages upgrade the last.
set -euo pipefail

USAGE="usage: $0 SOURCE_DIR OUTPUT_DIR VERSION"
SRC="${1:?${USAGE}}"
DEST="${2:?${USAGE}}"
VERSION="${3:?${USAGE}}"
dpkg --validate-version "${VERSION}" || { echo "error: invalid package version ${VERSION}" >&2; exit 1; }
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

mkdir -p "${DEST}"
for dir in "${SRC}"/*/; do
	[ -f "${dir}/debian/control" ] || continue
	name="$(basename "${dir}")"
	echo "==> Building package ${name}"
	cp -a "${dir}" "${TMP}/${name}"
	# tekne-branding renders the artwork in the repository's branding/
	# directory, which is licensed separately (CC-BY-SA-4.0, DEC-019).
	if [ "${name}" = tekne-branding ]; then
		cp -a "${SRC}/../branding" "${TMP}/${name}/branding"
	fi
	# tekne-config ships Nerd Fonts' symbols fonts (DEC-043): a pinned upstream
	# release, refused unless its checksum matches vendor/nerd-fonts.pin.
	if [ -f "${dir}/vendor/nerd-fonts.pin" ]; then
		url="$(sed -n 's/^URL=//p' "${dir}/vendor/nerd-fonts.pin")"
		sha="$(sed -n 's/^SHA256=//p' "${dir}/vendor/nerd-fonts.pin")"
		curl -fsSL --retry 3 -o "${TMP}/nerd-fonts.tar.xz" "${url}"
		echo "${sha}  ${TMP}/nerd-fonts.tar.xz" | sha256sum -c --quiet \
			|| { echo "error: ${url} doesn't match vendor/nerd-fonts.pin" >&2; exit 1; }
		mkdir -p "${TMP}/${name}/vendor/nerd-fonts"
		tar -xJf "${TMP}/nerd-fonts.tar.xz" -C "${TMP}/${name}/vendor/nerd-fonts"
		rm "${TMP}/nerd-fonts.tar.xz"
	fi
	sed -i "1s/^\(${name}\) ([^)]*)/\1 (${VERSION})/" "${TMP}/${name}/debian/changelog"
	grep -q "^${name} (${VERSION})" "${TMP}/${name}/debian/changelog" \
		|| { echo "error: couldn't set ${name}'s version" >&2; exit 1; }
	# --no-check-builddeps: the check always demands build-essential (a C
	# toolchain), which these architecture-independent packages never use.
	# debhelper, their only real build dependency, is in the container.
	(cd "${TMP}/${name}" && dpkg-buildpackage --build=binary --no-sign --no-check-builddeps)
done

cp "${TMP}"/*.deb "${DEST}/"
ls -1 "${DEST}"/*.deb
