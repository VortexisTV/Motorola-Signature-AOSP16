#!/usr/bin/env bash
# One-shot firmware pipeline: unpack the stock package, inventory it and populate proprietary/.
#
#   wsl.exe -d moto-aosp -u root -e bash /proj/vendor/motorola/vantage/scripts/extract-firmware.sh \
#       [stock_firmware_dir] [fw_work_dir] [vendor_dir]
#
# Defaults: /stockfw, /work/fw/<build id from flashfile.xml>, the directory above this script.
# The stock package is only ever read. Every copied file is verified against the SHA-256
# pinned in proprietary-files.txt; a mismatch aborts (different firmware build than analysed).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STOCK="${1:-/stockfw}"
VDIR="${3:-$(dirname "$HERE")}"
BUILD_ID="$(sed -n 's/.*software_version version="[^ ]* [^ ]* \([^ ]*\) .*/\1/p' "$STOCK/flashfile.xml" | head -1)"
FW="${2:-/work/fw/${BUILD_ID:-stock}}"
REPORTS="${REPORTS:-$(cd "$VDIR/../../.." && pwd)/reports}"
STAGES="${STAGES:-unpack inventory blobs}"

log() { printf '\n[extract-firmware] %s\n' "$*"; }

if [[ " $STAGES " == *" unpack "* ]]; then
  log "hashing and verifying the stock package"
  python3 -I "$HERE/firmware_hashes.py" "$STOCK" "$REPORTS" | tail -1
  if [ ! -f "$FW/images/vendor.img" ]; then
    log "dumping logical partitions to $FW/images"
    python3 -I "$HERE/extract_firmware.py" "$STOCK" "$FW"
  fi
  log "extracting filesystems, boot images and APEX payloads"
  bash "$HERE/extract_filesystems.sh" "$FW" "$STOCK"
  [ -f "$FW/apex/index.json" ] || python3 -I "$HERE/extract_apex.py" "$FW"
fi

if [[ " $STAGES " == *" inventory "* ]]; then
  log "building the firmware inventory"
  python3 -I "$HERE/analyze_firmware.py" "$FW" "$REPORTS" | tail -3
  python3 -I "$HERE/dump_overlays.py" "$FW" "$REPORTS" || true
fi

if [[ " $STAGES " == *" blobs "* ]]; then
  log "copying pinned stock files into $VDIR/proprietary"
  DEST="$VDIR/proprietary"
  rm -rf "$DEST"
  mkdir -p "$DEST"
  count=0
  while IFS= read -r line; do
    case "$line" in ''|'#'*) continue ;; esac
    spec="${line%%|*}"
    sha=""; [[ "$line" == *"|"* ]] && sha="${line##*|}"
    rel="${spec%%;*}"
    [[ ";$spec;" == *";SYMLINK="* ]] && continue   # symlinks are recreated by install_symlink modules
    part="${rel%%/*}"; sub="${rel#*/}"
    case "$part" in
      system) src="$FW/root/system/system/$sub" ;;
      *)      src="$FW/root/$part/$sub" ;;
    esac
    [ -f "$src" ] || { echo "MISSING in stock firmware: $rel"; exit 1; }
    [ -e "$DEST/$rel" ] && continue   # listed by more than one component
    if [ -n "$sha" ]; then
      got="$(sha256sum "$src" | cut -d' ' -f1)"
      [ "$got" = "$sha" ] || { echo "SHA-256 MISMATCH for $rel (expected $sha, got $got)"; exit 1; }
    fi
    install -D -m 0644 "$src" "$DEST/$rel"
    count=$((count + 1))
  done < "$VDIR/proprietary-files.txt"
  log "$count files copied and verified"
  python3 -I "$HERE/setup_makefiles.py" "$VDIR"
fi
log "done"
