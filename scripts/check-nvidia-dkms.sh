#!/bin/bash
# DEC-041: compile NVIDIA's open kernel module, as tekne-nvidia would install
# it, against the kernel this ISO ships, so a backports kernel that breaks the
# driver can't reach a release unnoticed. Runs as root in the build container
# (scripts/build-in-container.sh), after the image is built; it changes only
# the container.
#   check-nvidia-dkms.sh MANIFEST
# Prints "nvidia_dkms: VERSION KERNEL" for build-info.txt on success.
set -euo pipefail

MANIFEST="${1:?usage: $0 MANIFEST}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"
die() { echo "FAIL: $*" >&2; exit 1; }

# The image's one kernel (0505-backports-kernel guarantees there's one).
read -r kpkg kver_deb < <(awk -F'\t' '$1 ~ /^linux-image-[0-9][^ ]*-amd64(:amd64)?$/ { print $1, $2 }' "${MANIFEST}")
[ -n "${kpkg:-}" ] || die "no linux-image-VERSION-amd64 in ${MANIFEST}"
kver="${kpkg%:amd64}"
kver="${kver#linux-image-}"
echo "==> NVIDIA's open module against ${kver} (${kver_deb})" >&2

# The same sources, keys and pins installed systems use: Devuan's backports
# for the headers (DEC-036), NVIDIA's repository for the module (DEC-041).
(cd "${SRC}/packages/tekne-nvidia-repo/keys" && sha256sum --check --strict --quiet SHA256SUMS) \
	|| die "NVIDIA's key doesn't match its recorded checksum"
install -D -m 0644 "${SRC}/packages/tekne-nvidia-repo/keys/nvidia.gpg" /usr/share/tekne/keyrings/nvidia.gpg
install -m 0644 "${SRC}/packages/tekne-nvidia-repo/sources/tekne-nvidia.sources" \
	"${SRC}/packages/tekne-apt-sources/sources/tekne-backports.sources" /etc/apt/sources.list.d/
install -m 0644 "${SRC}/packages/tekne-nvidia-repo/preferences/tekne-nvidia.pref" \
	"${SRC}/packages/tekne-apt-sources/preferences/tekne-backports.pref" /etc/apt/preferences.d/
apt-get update -qq >&2
# g++ too: the open module has C++ parts (nvidia-kernel-open-dkms depends on it).
apt-get install -y -qq --no-install-recommends "linux-headers-${kver}=${kver_deb}" make g++ >&2

# apt-get download checks the .deb against the repository's signed index.
work="$(mktemp -d)"
(cd "${work}" && apt-get download -qq nvidia-kernel-open-dkms >&2)
deb="$(ls "${work}"/nvidia-kernel-open-dkms_*.deb)"
nv_version="$(dpkg-deb -f "${deb}" Version)"
dpkg-deb -x "${deb}" "${work}/x"
src="$(ls -d "${work}"/x/usr/src/nvidia-*/)"

# The command dkms.conf gives, minus DKMS itself.
if ! make -C "${src}" -j"$(nproc)" KERNEL_UNAME="${kver}" \
	IGNORE_PREEMPT_RT_PRESENCE=1 IGNORE_XEN_PRESENCE=1 modules > "${work}/make.log" 2>&1; then
	tail -n 40 "${work}/make.log" >&2
	die "NVIDIA ${nv_version} doesn't build for ${kver}"
fi
for m in nvidia nvidia-modeset nvidia-drm nvidia-uvm; do
	[ -n "$(find "${src}" -name "${m}.ko" -print -quit)" ] || die "${m}.ko wasn't built"
done
echo "==> OK: NVIDIA ${nv_version} builds for ${kver}" >&2
rm -rf "${work}"
echo "nvidia_dkms: ${nv_version} ${kver}"
