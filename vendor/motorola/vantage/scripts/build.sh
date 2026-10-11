#!/usr/bin/env bash
# Build a system image from the synced tree.
#
#   wsl.exe -d moto-aosp -u builder -e bash /proj/vendor/motorola/vantage/scripts/build.sh
#
# Environment overrides:
#   TARGET   lunch product   (default treble_arm64_bvN = TrebleDroid arm64, A/B, vanilla, no su)
#   RELEASE  release config  (default bp2a, the android-16.0.0_r2 release config)
#   VARIANT  eng|userdebug|user (default userdebug)
#   GOALS    make goals      (default systemimage)
#   JOBS     parallel jobs   (default 10; ~24 GB RAM + swap is tight for more)
set -o pipefail   # not -u/-e: build/envsetup.sh and lunch are not written for them

# Soong analysis needs about 38 GB; on plain disk swap it thrashes for hours. The zram device is
# lost whenever the WSL VM restarts, so check instead of assuming.
if ! grep -q zram /proc/swaps && [ "${ALLOW_NO_ZRAM:-0}" = "0" ]; then
  echo "no zram swap is active: run scripts/wsl-zram.sh as root first (ALLOW_NO_ZRAM=1 to build anyway)" >&2
  exit 3
fi

AOSP_DIR="${AOSP_DIR:-/work/aosp}"
TARGET="${TARGET:-treble_arm64_bvN}"
RELEASE="${RELEASE:-bp2a}"
VARIANT="${VARIANT:-userdebug}"
GOALS="${GOALS:-systemimage}"
JOBS="${JOBS:-10}"

cd "$AOSP_DIR" || exit 1

# TrebleDroid generates its product makefiles (treble_<arch>_<variant>.mk) on demand.
( cd device/phh/treble && bash generate.sh ) || exit 1

# ccache is deliberately not used: the Soong sandbox mounts everything outside out/ read-only,
# so a cache directory elsewhere fails with "ccache: error: Read-only file system".
unset USE_CCACHE CCACHE_EXEC CCACHE_DIR
export LC_ALL=C.UTF-8

echo "=== build start $(date -Is): $TARGET-$RELEASE-$VARIANT goals=[$GOALS] jobs=$JOBS ==="
# shellcheck disable=SC1091
source build/envsetup.sh
lunch "$TARGET-$RELEASE-$VARIANT" || { echo "lunch failed"; exit 1; }

# shellcheck disable=SC2086
make -j"$JOBS" $GOALS
rc=$?
echo "=== build end $(date -Is) rc=$rc ==="
if [ "$rc" -eq 0 ]; then
  ls -la "$OUT"/*.img 2>/dev/null
fi
exit "$rc"
