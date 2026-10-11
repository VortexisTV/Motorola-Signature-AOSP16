#!/usr/bin/env bash
# Initialise and sync the pinned AOSP 16 + TrebleDroid source tree.
#
#   wsl.exe -d moto-aosp -u builder -e env PINNED=1 bash /proj/vendor/motorola/vantage/scripts/sync-source.sh
#
# Baseline (verified 2026-10-09):
#   AOSP          android-16.0.0_r2  (SDK 36.0, matches stock ro.build.version.sdk_full)
#   TrebleDroid   treble_manifest android-16.0 @ e218100 ("Up to r2"), whose replace.xml
#                 swaps 27 AOSP projects for TrebleDroid forks at android-16.0.0_r2-td
#                 (patches already applied in-tree, no separate patch step needed).
set -euo pipefail

AOSP_DIR="${AOSP_DIR:-/work/aosp}"
AOSP_TAG="${AOSP_TAG:-android-16.0.0_r2}"
TD_MANIFEST_URL="${TD_MANIFEST_URL:-https://github.com/TrebleDroid/treble_manifest}"
TD_MANIFEST_BRANCH="${TD_MANIFEST_BRANCH:-android-16.0}"
TD_MANIFEST_REV="${TD_MANIFEST_REV:-e218100519751f55d11d5b095adfc4d0d47f138c}"
JOBS="${JOBS:-8}"
PIN_OUT="${PIN_OUT:-/proj/manifests}"
PIN_FILE="$PIN_OUT/pinned-$AOSP_TAG-td.xml"
# PINNED=1: the exact revisions of the committed manifest, which the released images were built
#           from (TrebleDroid's device tree follows a branch, so PINNED=0 may fetch a newer one).
# PINNED=0: the AOSP tag plus TrebleDroid's manifest at the revision below; afterwards the
#           committed manifest is rewritten with what was fetched (use this to move the baseline).
PINNED="${PINNED:-0}"

mkdir -p "$AOSP_DIR"
cd "$AOSP_DIR"

if [ ! -d .repo/manifests ]; then
  repo init -u https://android.googlesource.com/platform/manifest -b "$AOSP_TAG" --depth=1 </dev/null
fi

if [ "$PINNED" = 1 ]; then
  # The committed manifest names every project, the TrebleDroid ones included, by commit.
  [ -f "$PIN_FILE" ] || { echo "no pinned manifest at $PIN_FILE" >&2; exit 1; }
  rm -rf .repo/local_manifests
  cp "$PIN_FILE" .repo/manifests/vantage-pinned.xml
  repo init -m vantage-pinned.xml </dev/null
  echo "using the pinned manifest $PIN_FILE"
else
  if [ ! -d .repo/local_manifests/.git ]; then
    rm -rf .repo/local_manifests
    git clone -q -b "$TD_MANIFEST_BRANCH" "$TD_MANIFEST_URL" .repo/local_manifests
  fi
  git -C .repo/local_manifests fetch -q origin "$TD_MANIFEST_BRANCH"
  git -C .repo/local_manifests checkout -q "$TD_MANIFEST_REV"
  echo "local_manifests @ $(git -C .repo/local_manifests rev-parse HEAD)"
fi
if [ "${INIT_ONLY:-0}" = 1 ]; then
  echo "initialised only (INIT_ONLY=1): $(repo manifest | grep -c '<project ') projects in the manifest"
  exit 0
fi

ok=0
for attempt in 1 2 3 4; do
  echo "=== repo sync attempt $attempt ($(date -Is)) ==="
  if repo sync -c -j"$JOBS" --force-sync --no-tags --no-clone-bundle --optimized-fetch --prune; then
    ok=1
    break
  fi
  JOBS=4
  sleep 30
done
[ "$ok" = 1 ] || { echo "repo sync failed after retries"; exit 1; }

if [ "$PINNED" != 1 ]; then
  mkdir -p "$PIN_OUT"
  repo manifest -r -o "$PIN_FILE"
  echo "pinned manifest written to $PIN_FILE"
fi
echo "=== sync complete ($(date -Is)) ==="
du -sh "$AOSP_DIR" 2>/dev/null || true
