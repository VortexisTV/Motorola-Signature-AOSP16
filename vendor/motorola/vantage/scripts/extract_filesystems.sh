#!/usr/bin/env bash
# Extract the filesystems and boot images of an unpacked stock firmware.
#
#   wsl.exe -d moto-aosp -u root -e bash /proj/vendor/motorola/vantage/scripts/extract_filesystems.sh <fw_out_dir> <stock_firmware_dir>
#
# <fw_out_dir> is the output directory of extract_firmware.py (contains images/).
# Results:
#   <fw_out_dir>/root/<partition>/   extracted EROFS/ext4 trees (ownership + modes preserved when root)
#   <fw_out_dir>/boot/<image>/       unpacked boot/init_boot/vendor_boot/recovery + ramdisks
# The stock firmware directory is only read.
set -uo pipefail
FW="${1:?usage: extract_filesystems.sh <fw_out_dir> <stock_firmware_dir>}"
STOCK="${2:?usage: extract_filesystems.sh <fw_out_dir> <stock_firmware_dir>}"
# unpack_bootimg.py is part of the AOSP tree (system/tools/mkbootimg): sync the source first.
UNPACK_BOOTIMG="${UNPACK_BOOTIMG:-${AOSP_DIR:-/work/aosp}/system/tools/mkbootimg/unpack_bootimg.py}"

mkdir -p "$FW/root" "$FW/boot"

for img in "$FW"/images/*.img; do
  name=$(basename "$img" .img)
  dest="$FW/root/$name"
  if [ -e "$FW/root/.$name.extracted" ]; then echo "skip $name (already extracted)"; continue; fi
  rm -rf "$dest"; mkdir -p "$dest"
  if [ "$(xxd -s 1024 -l 4 -p "$img")" = "e2e1f5e0" ]; then
    fsck.erofs --extract="$dest" --overwrite --preserve "$img" > "$FW/root/$name.extract.log" 2>&1
    rc=$?
  elif [ "$(xxd -s 1080 -l 2 -p "$img")" = "53ef" ]; then
    debugfs -R "rdump / $dest" "$img" > "$FW/root/$name.extract.log" 2>&1
    rc=$?
  else
    echo "$name: unknown filesystem, skipped"; continue
  fi
  if [ "$rc" -ne 0 ]; then echo "$name: extraction FAILED rc=$rc (see $FW/root/$name.extract.log)"; continue; fi
  touch "$FW/root/.$name.extracted"
  echo "$name: $(find "$dest" -type f | wc -l) files, $(find "$dest" -type l | wc -l) symlinks, $(du -sh "$dest" | cut -f1)"
done

unpack_ramdisk() {  # <ramdisk file> <dest dir>
  local rd="$1" dest="$2" magic
  mkdir -p "$dest"
  magic=$(xxd -l 4 -p "$rd")
  case "$magic" in
    02214c18) lz4 -dc "$rd" 2>/dev/null ;;   # lz4 legacy frame
    04224d18) lz4 -dc "$rd" 2>/dev/null ;;   # lz4 frame
    1f8b*)    gzip -dc "$rd" 2>/dev/null ;;
    28b52ffd) zstd -dc "$rd" 2>/dev/null ;;
    fd377a58) xz -dc "$rd" 2>/dev/null ;;
    *)        cat "$rd" ;;
  esac | (cd "$dest" && cpio -idm --quiet --no-absolute-filenames 2>/dev/null)
  echo "    ramdisk $(basename "$rd") [magic $magic] -> $(find "$dest" -type f | wc -l) files"
}

if [ -f "$UNPACK_BOOTIMG" ]; then
  for name in boot init_boot vendor_boot recovery; do
    src="$STOCK/$name.img"
    [ -f "$src" ] || continue
    out="$FW/boot/$name"
    rm -rf "$out"; mkdir -p "$out"
    python3 -I "$UNPACK_BOOTIMG" --boot_img "$src" --out "$out" --format=info > "$out/header.txt" 2>"$out/unpack.err" \
      || echo "$name: unpack_bootimg failed (see $out/unpack.err)"
    echo "$name: $(ls "$out" | tr '\n' ' ')"
    for rd in "$out"/ramdisk "$out"/vendor_ramdisk "$out"/vendor-ramdisk-by-name/* "$out"/vendor_ramdisk[0-9]*; do
      [ -f "$rd" ] || continue
      unpack_ramdisk "$rd" "$out/rootfs-$(basename "$rd")"
    done
  done
else
  echo "unpack_bootimg.py not found at $UNPACK_BOOTIMG; boot images skipped" >&2
  echo "  (validate-image.sh needs the unpacked init_boot ramdisk: run sync-source.sh, then this script again)" >&2
fi
