#!/usr/bin/env bash
# Export a built image for installation: the raw image, its gzip (the form the Dynamic System
# Update installer takes) and checksums.
#
#   wsl.exe -d moto-aosp -u builder -e bash /proj/vendor/motorola/vantage/scripts/export-image.sh <name>
#
# Writes /proj/out/<name>/{system.img,system_raw.gz,SHA256SUMS,SIZES} and prints the two values
# dsu-preflight.sh needs for this image. Run validate-image.sh first: nothing here judges the image.
set -euo pipefail
NAME="${1:?usage: export-image.sh <name>   (for example vantage_td-$(date +%Y%m%d))}"
PROJ="${PROJ:-/proj}"
AOSP_DIR="${AOSP_DIR:-/work/aosp}"
OUT="${OUT:-$AOSP_DIR/out/target/product/tdgsi_arm64_ab}"
IMG="${IMG:-$OUT/system.img}"
DEST="${DEST:-$PROJ/out/$NAME}"

[ -f "$IMG" ] || { echo "no image at $IMG: build first" >&2; exit 1; }
if [ "$(xxd -l 4 -p "$IMG")" = "3aff26ed" ]; then
  echo "$IMG is an Android sparse image; the DSU installer needs the raw one (simg2img)" >&2
  exit 1
fi
mkdir -p "$DEST"
cp "$IMG" "$DEST/system.img"
# -n: no file name or time in the header, so the same image always gives the same archive.
gzip -n -c "$DEST/system.img" > "$DEST/system_raw.gz"
cd "$DEST"
sha256sum system.img system_raw.gz > SHA256SUMS
stat -c '%s %n' system.img system_raw.gz > SIZES
sha="$(cut -d' ' -f1 SHA256SUMS | head -n 1)"
[ "$(gzip -dc system_raw.gz | sha256sum | cut -d' ' -f1)" = "$sha" ] || { echo "the archive does not unpack to the image" >&2; exit 1; }
cat SHA256SUMS SIZES
echo
echo "exported to $DEST"
echo "for dsu-preflight.sh:  IMAGE_SHA256=$sha IMAGE_SIZE=$(stat -c %s system.img)"
