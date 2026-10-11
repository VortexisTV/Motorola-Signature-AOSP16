#!/usr/bin/env bash
# Run every static check against a built image: the three validators on the output tree, then
# the image file itself (filesystem check, and every pinned stock file read back out of it).
#
#   wsl -d moto-aosp -u root -e bash /proj/vendor/motorola/vantage/scripts/validate-image.sh
#
# Run as root: the extracted stock vendor/build.prop is mode 0600. Exit status 0 = no FAIL.
set -uo pipefail
PROJ="${PROJ:-/proj}"
AOSP_DIR="${AOSP_DIR:-/work/aosp}"
FW="${FW:-/work/fw/W2WVS36.55-95-5-1}"
OUT="${OUT:-$AOSP_DIR/out/target/product/tdgsi_arm64_ab}"
IMG="${IMG:-$OUT/system.img}"
REPORTS="${REPORTS:-$PROJ/reports/vantage}"
V="$PROJ/vendor/motorola/vantage"
S="$V/scripts"
HOSTBIN="$AOSP_DIR/out/host/linux-x86/bin"

MAPS=(--map "/system=$OUT/system" --map "/system_ext=$OUT/system/system_ext"
      --map "/product=$OUT/system/product" --map "/apex=$OUT/apex"
      --map "/vendor=$FW/root/vendor" --map "/odm=$FW/root/odm")
BASE=(--baseline-map "/system=$FW/root/system/system" --baseline-map "/system_ext=$FW/root/system_ext"
      --baseline-map "/product=$FW/root/product" --baseline-map "/apex=$FW/apex")
rc=0
mkdir -p "$REPORTS"

python3 -I "$S/preflight.py" "${MAPS[@]}" "${BASE[@]}" --manifest "$V/proprietary-files.txt" \
    --inventory "$PROJ/reports/inventory" --reports "$REPORTS" --secilc "$HOSTBIN/secilc" \
    --expect-mapped vendor_qtelephony --expect-mapped moto_camera_app \
    --overlay-package com.android.phone.overlay.vantage --overlay-package android.overlay.vantage.telephony \
    --overlay-package com.android.carrierconfig.overlay.vantage \
    --system-img "$IMG" --super-layout "$FW/super_layout.json" --policy-out "$REPORTS/combined.sepolicy" || rc=1
python3 -I "$S/validate-telephony.py" "${MAPS[@]}" --aosp-tree "$AOSP_DIR" --reports "$REPORTS" || rc=1
python3 -I "$S/validate-camera.py" "${MAPS[@]}" --inventory "$PROJ/reports/inventory" --reports "$REPORTS" || rc=1

# Symbol-level linkage of every ported native library, and of the libraries inside the camera APK.
echo "Native symbols:"
python3 -I "$S/check_native_symbols.py" "${MAPS[@]}" "${BASE[@]}" --manifest "$V/proprietary-files.txt"     --out "$REPORTS/native-symbols.json" | tail -n 1 || rc=1
python3 -I "$S/check_native_symbols.py" "${MAPS[@]}" "${BASE[@]}" --baseline-map "/vendor=$FW/root/vendor"     --apk /product/priv-app/MotCamera5/MotCamera5.apk --out "$REPORTS/native-symbols-camera.json" | tail -n 1 || rc=1

# What the combined policy lets the ported app domains do, compared with the stock policy.
# Exit status 4 = stock grants something on a label that exists here; listed for review, not a FAIL.
echo "SELinux, effective permissions versus stock:"
if python3 -c "import setools" 2>/dev/null && [ -s "$REPORTS/combined.sepolicy" ]; then
  ctx=()
  for d in "$OUT/system/etc/selinux" "$OUT/system/system_ext/etc/selinux" "$OUT/system/product/etc/selinux"            "$FW/root/vendor/etc/selinux" "$FW/root/odm/etc/selinux"; do ctx+=(--contexts "$d"); done
  python3 -I "$S/sepolicy_diff.py" --ours "$REPORTS/combined.sepolicy"       --stock "$FW/root/odm/etc/selinux/precompiled_sepolicy" "${ctx[@]}"       --domain vendor_qtelephony --domain moto_camera_app --out "$REPORTS" || [ $? -eq 4 ] || rc=1
  python3 -I "$S/sepolicy_diff.py" --ours "$REPORTS/combined.sepolicy"       --query system_app vendor_hal_telephony_service2 service_manager find       --query system_app rild binder call --query rild system_app binder call       --query vendor_qtelephony vendor_hal_telephony_service2 service_manager find       --query vendor_qtelephony rild binder call --query init audio_vendor_parameter_parser process transition --query audio_vendor_parameter_parser audio_vendor_parameter_parser_service service_manager add --query audioserver audio_vendor_parameter_parser_service service_manager find --query audioserver audio_vendor_parameter_parser binder call --query audio_vendor_parameter_parser servicemanager binder call --query hal_camera_default vantage_vendor_framework_prop file read --query shell vantage_vendor_framework_prop file read --deny hal_audio_default vantage_vendor_framework_prop file read --deny hal_bluetooth_default vantage_vendor_framework_prop file read --deny vendor_cnd vantage_vendor_framework_prop file read --deny vendor_hal_imsrtp vantage_vendor_framework_prop file read --deny vendor_ims_service vantage_vendor_framework_prop file read --deny vendor_qccvendor vantage_vendor_framework_prop file read --deny vendor_location_xtra_daemon vantage_vendor_framework_prop file read || rc=1
else
  echo "  [UNKNOWN] setools not installed (apt install setools) or no compiled policy; comparison skipped"
fi
rm -f "$REPORTS/combined.sepolicy"

# The image file itself.
echo "Image file: $IMG"
if e2fsck -fn "$IMG" > /dev/null 2>&1; then
  echo "  [PASS   ] image.fsck: e2fsck -fn reports a clean filesystem"
else
  echo "  [FAIL   ] image.fsck: e2fsck -fn reports errors"; rc=1
fi
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
checked=0; bad=0
while IFS= read -r line; do
  case "$line" in ''|'#'*) continue ;; esac
  spec="${line%%|*}"; sha="${line##*|}"; rel="${spec%%;*}"
  case ";$spec;" in *";SYMLINK="*|*";CERT="*) continue ;; esac   # recreated links, re-signed apps
  part="${rel%%/*}"; sub="${rel#*/}"
  case "$part" in system) path="/system/$sub" ;; *) path="/system/$part/$sub" ;; esac
  rm -f "$tmp/f"
  debugfs -R "dump $path $tmp/f" "$IMG" > /dev/null 2>&1
  got="$( [ -f "$tmp/f" ] && sha256sum "$tmp/f" | cut -d' ' -f1 )"
  checked=$((checked + 1))
  if [ "$got" != "$sha" ]; then
    echo "  [FAIL   ] image.content: $path differs from the pinned stock file (got ${got:-nothing})"
    bad=$((bad + 1)); rc=1
  fi
done < "$V/proprietary-files.txt"
[ "$bad" -eq 0 ] && echo "  [PASS   ] image.content: $checked pinned stock files read back from the image match their SHA-256"

# What the image contains, file by file, and what the stock fstab would mount over it.
echo "Image composition:"
mnt="$tmp/mnt"; mkdir -p "$mnt"
if mount -o ro,loop,noload "$IMG" "$mnt" 2>/dev/null; then
  python3 -I "$S/check_image_composition.py" --root "$mnt" --manifest "$V/proprietary-files.txt" --repo "$PROJ" --stock "$FW/root" --fstab "$FW/root/vendor/etc/fstab.qcom" --stock-overlays "$PROJ/reports/inventory/overlays.json" --hostbin "$HOSTBIN" --out "$REPORTS" --image "$IMG" || rc=1
  # Source patches: applied in the tree, and visible in the binaries of this image.
  echo "Source patches:"
  python3 -I "$S/check_source_patches.py" --repo "$PROJ" --aosp "$AOSP_DIR" --product-out "$OUT" --root "$mnt" --toolbin "$(dirname "$(ls "$AOSP_DIR"/prebuilts/clang/host/linux-x86/clang-r*/bin/llvm-objdump | tail -n 1)")" --out "$REPORTS" || rc=1
  umount "$mnt"
else
  echo "  [UNKNOWN] image.composition: cannot loop-mount the image (run as root)"
fi

# What the stock first-stage init, which is the one that boots a DSU guest, does with it.
echo "Stock first-stage init:"
OBJDUMP="$(ls "$AOSP_DIR"/prebuilts/clang/host/linux-x86/clang-r*/bin/llvm-objdump 2>/dev/null | tail -n 1)"
python3 -I "$S/check_stock_init.py" "$FW/boot/init_boot/rootfs-ramdisk/init" "$OBJDUMP" --out "$REPORTS/stock-init.json" || rc=1
spl() { "$HOSTBIN/avbtool" info_image --image "$1" 2>/dev/null | grep -o "system.security_patch -> '[0-9-]*'" | cut -d"'" -f2 | head -n 1; }
ours="$(spl "$IMG")"; theirs="$(spl "${STOCKFW:-/stockfw}/vbmeta_system.img")"
if [ -z "$ours" ] || [ -z "$theirs" ]; then
  echo "  [UNKNOWN] image.spl: security patch level property not readable (image '$ours', stock '$theirs')"
elif [[ "$ours" < "$theirs" ]]; then
  echo "  [INFO   ] image.spl: image $ours is older than stock $theirs: first-stage init reports a rollback and continues only when the verified boot state is orange (unlocked); a locked phone refuses this image"
else
  echo "  [INFO   ] image.spl: image $ours is not older than stock $theirs: no rollback branch"
fi
echo "  size $(stat -c %s "$IMG") bytes, sha256 $(sha256sum "$IMG" | cut -d' ' -f1)"
exit $rc
