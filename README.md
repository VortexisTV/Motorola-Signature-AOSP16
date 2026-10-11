# Motorola Signature (vantage) — Android 16 TrebleDroid ROM

Device-targeted Android 16 system image for the Motorola Signature (codename `vantage`,
product `vantage_g`, SoC SM8845 / platform `canoe`, SKU XT2603-1), built from AOSP +
TrebleDroid and keeping the complete stock vendor side.

## Images

Release notes with hashes, the test status and the install steps are in
[releases/](releases/); the current one is
[vantage_td-20261011-r4](releases/vantage_td-20261011-r4.md). Building one yourself needs the
stock firmware package, from which the build takes 34 files pinned by SHA-256
([BUILDING.md](BUILDING.md)).

## Architecture

```
 Android 16 AOSP (android-16.0.0_r2) + TrebleDroid android-16.0        built here
 └─ system image (system + system_ext + product in one image, GSI layout)
     ├─ AOSP telephony framework, AOSP audio policy, AOSP camera service
     └─ vendor/motorola/vantage  ("integration layer", this repository)
         ├─ stock Qualcomm IMS service + its shared libraries      re-signed / as shipped
         ├─ stock Motorola Camera + its signature-permission host  as shipped (OEM-signed)
         ├─ overlays restating values stock keeps in /product and in its own APK resources
         ├─ privileged-permission allowlists identical to stock
         ├─ IMS network requester (the request stock's vendor CNE app holds)   built from source
         └─ system-side SELinux types the stock vendor policy is written against
 ───────────────────────────── Treble boundary (VINTF, AIDL HALs, policy 202504) ──────────
 Stock Motorola partitions, untouched: vendor, odm, vendor_dlkm, system_dlkm, boot,
 init_boot, vendor_boot, dtbo, modem, dsp, bluetooth, persist, …
     ├─ Qualcomm RIL (qcrilNrd): android.hardware.radio.* AIDL V4 + vendor.qti.hardware.radio.*
     ├─ IMS daemons (imsdaemon, ims_rtp_daemon), IWLAN, CNE
     ├─ Qualcomm AIDL audio HAL (PAL/AGM), camera provider (CamX/CHI + Motorola add-ons)
     └─ modem firmware
```

Only the `system` logical partition is replaced. A TrebleDroid system image carries a
`skip_mount.cfg`, so the stock `system_ext` and `product` partitions stay on the device but
are not mounted; everything the phone needs from them has to be supplied by the integration
layer. That is the central porting problem and is analysed file by file in
[FIRMWARE_ANALYSIS.md](FIRMWARE_ANALYSIS.md).

## Repository layout

| Path | Content |
|---|---|
| `vendor/motorola/vantage/` | Integration layer (synced into the AOSP tree) |
| `vendor/motorola/vantage/components.json` | Seed components (IMS, Camera) |
| `vendor/motorola/vantage/proprietary-files.txt` | Generated closure of stock files, pinned by SHA-256 |
| `vendor/motorola/vantage/proprietary/` | Extracted stock files — **never committed** |
| `vendor/motorola/vantage/{telephony,camera,audio,overlays,sepolicy}/` | Hand-written overlays, allowlists, policy, and the source-built pieces (`telephony/ims-network/`, `audio/vendorext/`) |
| `vendor/motorola/vantage/properties.mk` | Stock system-side properties the vendor side reads, each with its reader |
| `vendor/motorola/vantage/scripts/` | Extraction, analysis, validation and build tooling |
| `device/motorola/vantage/` | `vantage_td` product (inherits TrebleDroid `treble_arm64_bvN`) |
| `manifests/` | Pinned `repo` manifest of the exact source revisions |
| `patches/` | Source patches for projects of the tree, applied by `sync-to-tree.sh`: TrebleDroid's RIL audio bridge, and one entry in AOSP init's table of exported boot parameters |
| `releases/` | Release notes per image: hashes, what was tested, known issues, install steps |
| `reports/` | Machine-readable (JSON) and Markdown analysis/validation results |

Names that differ from the classic vendor-tree layout:

- `vantage-vendor.mk` (generated: modules and copies of the pinned stock files) and `vantage.mk`
  (hand-written: overlays, SELinux, allowlists) together play the role of `device-vendor.mk`.
- There is no `Android.mk`: every module is a Soong module in `Android.bp`.
- Stock IMS and camera files are not kept in hand-maintained `telephony/ims` or
  `camera/configuration` directories. They are listed in `proprietary-files.txt`, pinned by
  SHA-256, and extracted into `proprietary/` at their stock paths. No camera overlay was needed.
- `target-system-libs.txt` lists the libraries the unmodified AOSP image provides; the
  resolver uses it to decide which native dependencies of a stock binary must be ported.

## Documents

- [BUILDING.md](BUILDING.md) — environment, source sync, build commands and results
- [FIRMWARE_ANALYSIS.md](FIRMWARE_ANALYSIS.md) — stock firmware inventory and findings
- [TELEPHONY_PORT.md](TELEPHONY_PORT.md) — radio / IMS / call-audio integration
- [CAMERA_PORT.md](CAMERA_PORT.md) — Motorola Camera integration
- [COMPATIBILITY.md](COMPATIBILITY.md) — verified, failed, unknown per feature
- [TESTING.md](TESTING.md) — automated checks and the on-device acceptance test
- [DSU_READINESS.md](DSU_READINESS.md) — what was verified before the first DSU boot (image, security patch
  level handling of the stock `init`, image composition, one-shot mode), and what cannot be

## Ground rules followed here

- The stock firmware package and the device backups are read-only inputs.
- No stock binary is committed; `proprietary-files.txt` + hashes make the set reproducible.
- No package-signature bypasses. Apps that need the platform signature are re-signed with the
  ROM's own key at build time; OEM-signed apps keep their signature and only receive what
  their own certificate entitles them to.
- SELinux stays enforcing; policy is added, never relaxed globally.
- Nothing is flashed, wiped or unlocked by the tooling. Deployment is a documented, manual,
  reversible procedure ([TESTING.md](TESTING.md)).
