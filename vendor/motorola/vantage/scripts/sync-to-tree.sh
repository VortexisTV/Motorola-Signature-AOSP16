#!/usr/bin/env bash
# Copy the integration layer from this repository into the AOSP tree and populate proprietary/.
#
#   wsl.exe -d moto-aosp -u builder -e bash /proj/vendor/motorola/vantage/scripts/sync-to-tree.sh
#
# The git repository (/proj) is the source of truth; the copies inside the AOSP tree are derived.
set -euo pipefail
PROJ="${PROJ:-/proj}"
AOSP_DIR="${AOSP_DIR:-/work/aosp}"
FW="${FW:-/work/fw/W2WVS36.55-95-5-1}"
STOCK="${STOCK:-/stockfw}"

mkdir -p "$AOSP_DIR/vendor/motorola/vantage" "$AOSP_DIR/device/motorola/vantage"
rsync -a --delete --no-perms --no-owner --no-group --chmod=D755,F644 \
  --exclude 'proprietary/' --exclude '__pycache__/' \
  "$PROJ/vendor/motorola/vantage/" "$AOSP_DIR/vendor/motorola/vantage/"
rsync -a --delete --no-perms --no-owner --no-group --chmod=D755,F644 \
  "$PROJ/device/motorola/vantage/" "$AOSP_DIR/device/motorola/vantage/"

# Source patches for projects of the tree: patches/<project path>/*.patch, applied with git apply
# inside that project. Applying is idempotent; a patch that no longer applies stops the sync.
if [ -d "$PROJ/patches" ]; then
  while IFS= read -r p; do
    rel="${p#$PROJ/patches/}"
    dir="$AOSP_DIR/$(dirname "$rel")"
    if git -C "$dir" apply --check --reverse "$p" 2>/dev/null; then
      echo "patch already applied: $rel"
    elif git -C "$dir" apply --check "$p" 2>/dev/null; then
      git -C "$dir" apply "$p" && echo "patch applied: $rel"
    else
      echo "PATCH DOES NOT APPLY: $rel" >&2
      exit 1
    fi
  done < <(find "$PROJ/patches" -name '*.patch' | sort)
fi

STAGES=blobs REPORTS="$PROJ/reports" bash "$AOSP_DIR/vendor/motorola/vantage/scripts/extract-firmware.sh" \
  "$STOCK" "$FW" "$AOSP_DIR/vendor/motorola/vantage"

# Keep the generated glue in the repository identical to what the tree uses.
cmp -s "$AOSP_DIR/vendor/motorola/vantage/Android.bp" "$PROJ/vendor/motorola/vantage/Android.bp" \
  || echo "NOTE: generated Android.bp differs from the committed copy; re-run setup_makefiles.py in the repository"
echo "tree updated: $AOSP_DIR/vendor/motorola/vantage ($(find "$AOSP_DIR/vendor/motorola/vantage/proprietary" -type f | wc -l) proprietary files)"
