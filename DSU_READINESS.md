# DSU readiness assessment

> **Status 2026-10-11.** The review below was made for image `c27ba0e9...`; that image and
> revisions 2 and 3 were installed and booted (FIRST_ to FOURTH_BOOT_REPORT.md). The image to
> test now is revision 4, `out/vantage_td-20261011-r4/system.img`, 2,556,506,112 bytes, SHA-256
> `efe1b630cfdeda6f655112825d6df01aece2e0cc7fdf762b97a5296809dd9b3e`. Every static check of this
> page was run again on it (`validate-image.sh`: no FAIL; composition 22 PASS, 1 WARNING). Its
> `KEY_SYSTEM_SIZE` is `2556506112`. The numbers further down are those of the first image.
> What section 1.1 derives from the stock `init` about the security patch level was seen in
> the log of the third session: compared, reported as older, allowed.

Date 2026-10-10, revised the same day (1.1 security patch level, 3.1 image composition, one-shot
evidence). Image `out/vantage_td-20261010/system.img`, 2,556,280,832 bytes, SHA-256
`c27ba0e97d4b5e93bc6e85235fede03cbf3662ea477f79641d2bd345d2fd0154`. Phone: stock
W2WVS36.55-95-5-1, slot `_a`, read over adb today. **Nothing has been installed.** Every row
says where the evidence comes from: the image (`avbtool`, `debugfs`), the stock firmware
(extracted `init_boot`, `vendor_boot`, `gsid`, installer APK), the phone (read-only adb), or
the source of the code that will run (AOSP 16 r2 as built here; stock's own binaries are
Motorola builds of the same components and were checked for the same strings).

## 1. Image: AVB, signing key, patch level

| Item | Found | Consequence for DSU |
|---|---|---|
| AVB footer | version 1.0, vbmeta 1,728 bytes, flags 0 | The installer can read the image's public key; verity is set up for the guest system |
| Signing | SHA256_RSA2048, public key SHA-1 `cdbb7717...` (AOSP test key) | Not a key the phone knows. First-stage `init` treats that as a verification error and **allows it on an unlocked device** (`fs_avb.cpp`: `allow_verification_error = IsAvbPermissive()`, true unless `/metadata/gsi/dsu/avb_enforce` exists). Phone: `ro.boot.vbmeta.device_state=unlocked`, `verifiedbootstate=orange` |
| Hashtree descriptor | partition name `system`, sha256, FEC with 2 roots, root digest `9daf1a28...` | For the DSU partition `system_gsi` first-stage `init` looks the descriptor up under the name `system` (`TransformFstabForDsu` strips the `_gsi` postfix). The names match, so dm-verity protects the guest with the image's own digest |
| Rollback index | 1749081600 | Not enforced while unlocked (`rollback_protection = !allow_verification_error`) |
| Security patch level | image 2025-06-05 (AVB property `com.android.build.system.security_patch`); stock `vbmeta_system` 2026-06-01 | **The stock first-stage `init` compares them, and the image is older.** That code refuses an older image on a locked phone and continues on an unlocked one; this phone is in the unlocked state. Evidence in 1.1. The level in the image was not changed: it is what the AOSP 16.0.0_r2 sources carry. For daily use it is a real gap (twelve months of platform fixes) |
| Filesystem | ext4, `e2fsck -fn` clean; 31 pinned stock files inside it match their hashes | |

### 1.1 Security patch level: what the stock code does with an older image

AOSP's DSU documentation says a guest image must not carry an older security patch level than
the installed system. That rule exists in code in exactly one place, and the stock firmware
has it. (An earlier version of this page said nothing compares the two levels. That was wrong.)

| Question | Answer | Evidence |
|---|---|---|
| Where is the comparison? | First-stage `init`, `IsStandaloneImageRollback()`. When a partition is verified with its own vbmeta (the DSU case: fstab `avb_keys`), it reads the AVB property `com.android.build.<partition>.security_patch` from the phone's vbmeta chain and from the image, and treats "image older" or "either one missing" as a rollback | AOSP `system/core/init/first_stage_mount.cpp`. The stock `init` (in `init_boot`, SHA-256 `51375f80...`) has the same function at `0x37f868`, with the message "Image rollback detected for ..., SPL switches from ... to ..." |
| Does this image take that branch? | Yes. Stock `vbmeta_system` says 2026-06-01, the image 2025-06-05. The one path that skips the comparison ("Top-level vbmeta is disabled") does not apply: the phone's `ro.boot.vbmeta.digest` equals the digest computed from the stock package's vbmeta images, so its vbmeta is the unmodified stock one with flags 0 | `avbtool info_image` on both; `avbtool calculate_vbmeta_digest` on the stock package gives `396306d7...`, the value the phone reports |
| What happens then? | The function asks `AvbHandle::IsDeviceUnlocked()`. Unlocked: it logs "Allowing rollbacked standalone image when the device is unlocked", clears the rollback result and goes on to set up dm-verity with the image's own hash tree. Locked: it returns "rollback", the mount of `/system` fails and the guest does not start | stock disassembly: after the comparison, two call sites (`0x37fb54`, `0x37ff8c`) call `0x4adfd0` and branch on the result; one side sets the rollback flag, the other reaches the "Allowing ..." message and clears it |
| How does the stock code decide "unlocked"? | From one input only, the boot parameter `androidboot.verifiedbootstate`: true exactly for the value `orange`. Not from `ro.boot.flash.locked` and not from anything the guest image could set | stock function `0x4adfd0`: builds the key `verifiedbootstate`, requires a value of 6 characters and compares it with the constants `0x6e61726f`, `0x6567` ("oran", "ge"). Its only other caller is the key-acceptance check (`IsAvbPermissive`) |
| What does this phone report? | `ro.boot.verifiedbootstate=orange`, `ro.boot.vbmeta.device_state=unlocked`, `ro.boot.flash.locked=0`. The bootloader passes the value before `init` decides whether to boot the guest, so it is the same for a stock boot and a DSU boot | read-only adb, 2026-10-10 |
| Is the level compared anywhere else? | Not found. The installer app, `gsid`, `DynamicSystemService` and the `android.os.image` classes contain no patch-level or rollback comparison (AOSP source as built here, and the strings of the stock `gsid`, installer APK and `services.jar`). libavb's rollback-index hook for standalone images is a stub that answers "no rollback". The bootloader never sees the DSU image: it is a set of files inside user data that `init` maps (by design; the bootloader itself was not disassembled) | source grep; strings of the stock binaries |

**Conclusion.** The stock firmware does enforce the comparison, and this image fails it. The
stock code then lets the image through for exactly one reason: the verified boot state
`orange`. "Unlocked bypasses the check" is therefore true on this phone, as a property read
out of the stock binary and of the phone's present state, not as an assumption. If the
bootloader were relocked, the same image would be refused at the first-stage mount (and its
test key would be refused too). The patch level in the image was not altered.

Not covered by this: whether KeyMint, which takes its patch levels from the stock boot chain
and vendor, objects to anything inside the guest. That is not known until the guest runs.

What the first boot adds: both messages go to the kernel log. The session recorder now saves
`dmesg`, and the report shows them under `boot.spl_rollback` if they were readable and still
in the ring buffer. The static part is reproducible with `check_stock_init.py` (run by
`validate-image.sh`; report `reports/vantage/stock-init.json`).

## 2. The phone's side

| Requirement | Found | Result |
|---|---|---|
| DSU logic in first-stage `init` | stock `init` (in `init_boot`) contains `/metadata/gsi/dsu/booted`, `install_status`, `one_shot_boot`, `lp_names`, `avb_enforce` and the `skip_mount.cfg` path | present |
| `/metadata` in the first stage | `fstab.qcom`: `/dev/block/by-name/metadata /metadata f2fs ... first_stage_mount` | present |
| Installer | `com.android.dynsystem` installed; `VerificationActivity` answers `START_INSTALL`; its code has the same paths as AOSP (gzip stream, sparse or raw input, `KEY_SYSTEM_SIZE`, `KEY_ONE_SHOT`); `gsi_tool status`: `normal` | present, nothing installed yet |
| User data filesystem | f2fs, 4 KiB blocks, on `dm-default-key` (metadata encryption with wrapped keys, inline crypto); file-based encryption | supported by design: `gsid` maps the image files beneath `dm-default-key` and writes through that mapping; stock `gsid` has the DSU key directory handling (`/metadata/vold/metadata_encryption/dsu/`), and the guest's `vold` uses the same directory for its own user data |
| Free space | 71.4 GB available (17,432,428 blocks). On a Virtual A/B device `gsid` refuses an allocation that would leave less free space than the size of `super` (31.1 GB). Needed: 8.6 GB guest user data + 2.6 GB system + 31.1 GB reserve + 1.2 GB for the pushed archive = 43.5 GB | met, about 28 GB to spare |
| Lock screen | the installer asks for the device credential before it starts | owner action |
| Extent pinning and fragmentation | stock `gsid` requires pinned, hole-free extents and gives up on too many fragments ("Image doesn't have pinned extents", "created too many split files") | **cannot be checked from an adb shell** (the f2fs sysfs nodes are not readable). If it fails, the installation stops with an error and nothing is changed |
| No update in progress | no DSU installed, `update_engine` idle as far as properties show | the snapshot-merge state itself is not readable without root; the phone has been on this build for a while |

## 3. What the DSU guest will mount

| Mount | Source under DSU | Evidence |
|---|---|---|
| `/` and `/system` | `system_gsi` = this image | `TransformFstabForDsu` rewrites the `system` entries; the stock fstab already lists an ext4 variant |
| `/system_ext`, `/product` | **this image** (`/system/system_ext`, `/system/product`), not the stock partitions | see 3.1: the image's `skip_mount.cfg` removes both stock fstab entries, and the stock first-stage `init` is shown to read it |
| `/vendor`, `/odm`, `/vendor_dlkm`, `/system_dlkm` | stock, from `super`, verified by the stock vbmeta chain as on every boot | fstab entries untouched; the image root provides the mount points |
| `/data` | `userdata_gsi`, a separate 8 GiB image with its own encryption keys | the stock user data is not mounted as `/data`; the DSU files live inside it |
| `/metadata` | shared with stock | DSU bookkeeping and the guest's key directory live there |
| SELinux policy | compiled at boot from this image's CIL plus the stock vendor and odm CIL | the stock precompiled policy is keyed to stock's system hashes, which do not match, so `init` compiles; the same inputs compile with `secilc -c 30`, the version `init` is built with |

### 3.1 What is inside the image, and what could be mounted over it

Read back from the image file with the SHA-256 above (loop-mounted read-only), by
`check_image_composition.py`; report `reports/vantage/image-composition.md`: 14 PASS, 0 FAIL,
1 WARNING.

| Group | Found in the image |
|---|---|
| Layout | `/system_ext` and `/product` are symlinks to `/system/system_ext` (173 files) and `/system/product` (811 files): one image carries all three trees |
| `skip_mount.cfg` | `/system/system_ext/etc/init/config/skip_mount.cfg` lists `/oem`, `/product`, `/system_ext` and their sub-paths. Matched against the stock `fstab.qcom` (the copy in `vendor_boot` and the one in `/vendor` are identical): the entries `system_ext -> /system_ext` and `product -> /product` are removed, and no remaining entry mounts on or under `/system`, `/system_ext` or `/product` |
| Who reads that file | (1) the **stock** first-stage `init`: its mount routine (`0x3800c8`) calls the function that loads this path (`0x3a7d54`) right after mounting `/system`, with logging on ("Skip mounting mountpoint: ..."); (2) this image's second-stage `init`, whenever it reads an fstab (`mount_all`); (3) this image's `init` before loading SELinux policy (`MountMissingSystemPartitions`), which would otherwise try to add both partitions |
| Telephony and IMS, stock files | 22 files byte-identical to the stock firmware: the six shared libraries of the IMS app with their permission XMLs (`ims-ext-common`, `moto-ims-ext`, `moto-telephony`, `qti-telephony-hidl-wrapper`, `qti-telephony-utils`), 11 native libraries, and the two JNI links of the IMS app, which point at files inside the image |
| IMS app | `/system_ext/priv-app/ims/ims.apk`: all 13 payload entries equal the stock APK (name, size, CRC-32); only the signature differs, and the signer is the certificate of this image's `framework-res.apk` |
| Carrier data | `/product/etc/apns-conf.xml` byte-identical to stock |
| Camera | `MotCamera5.apk` and `MotoSignatureApp.apk` byte-identical to stock (Motorola's signatures intact), `com.motorola.motosignature.jar` and its XML, the three `com.motorola.camera5*.xml` feature files, the hidden-API allowlist |
| Built from source | `VantageImsNetwork.apk` and `QcRilAm.apk`, both signed with this image's platform certificate; `QcRilAm.apk` contains the strings that only the reliability patch adds and declares the permission it adds |
| Overlays | the three overlays are in `/product/overlay`, static, priority 100, with the targets `android`, `com.android.phone`, `com.android.carrierconfig`; every compiled value equals the source (7 values, 40 elements of the carrier XML, among them `carrier_wfc_ims_available_bool=false`) |
| Permissions | both privileged-permission allowlists equal the repository files, each on the partition of its app (`org.codeaurora.ims` in `system_ext`, `com.motorola.camera5` in `product`) |
| SELinux | the image's `system_ext` policy declares `vendor_qtelephony` and `moto_camera_app` and carries the three `seapp_contexts` entries |

The one WARNING, `overlays.precedence`: 474 overlays in the image plus the stock `/vendor` and
`/odm` overlays (which stay mounted) were compared with the 8 values our overlays set. No
active overlay with higher precedence sets a different value. Five TrebleDroid overlays for
other vendors' IMS packages could override `config_ims_mmtel_package` if something enabled
them at run time; TrebleDroid's own selection enables the Qualcomm one, which sets the same
value as ours (TELEPHONY_PORT.md 1.1). The device report checks the outcome
(`boot.overlays_active`, `ims.mmtel_package`).

This is evidence about the file. That the phone mounts it this way is checked on the running
guest from `/proc/mounts` (`boot.partition_composition`).

## 4. Sizes and handling

| Item | Value |
|---|---|
| Raw image | 2,556,280,832 bytes = 624,092 blocks of 4,096 bytes (2,515,861,504 of filesystem, then hash tree, FEC and footer) |
| `system_raw.gz` | gzip of exactly that raw image; decompressing it reproduces the image's SHA-256 (checked after export). Sizes and hashes: `SIZES`, `SHA256SUMS` next to it |
| `KEY_SYSTEM_SIZE` | `2556280832`, the uncompressed size: for a raw (non-sparse) stream the installer creates the partition with exactly this size |
| `KEY_USERDATA_SIZE` | `8589934592` (8 GiB) |
| Boot mode | One-shot, selected twice over: the install command passes `--ez KEY_ONE_SHOT true`, and the stock installer's own default is the same (its code reads `KEY_ONE_SHOT` with default `true` and `KEY_ENABLE_WHEN_COMPLETED` with default `false`; `VerificationActivity` copies the caller's extras to the service, which hands the flag to `DynamicSystemManager.setEnable(true, oneShot)` when **Restart** is tapped). The first restart boots the guest, the one after it stock |

## 5. Failures: excluded beforehand, and not

Excluded by the checks above: wrong descriptor name for the DSU partition; key rejection and
rejection for the older patch level (both only while the bootloader stays unlocked, see 1.1); stock `system_ext`/`product` being mounted over the image; SELinux policy not
compiling; privileged-permission and native-library failures of the ported apps (static
validators); insufficient free space; image size or stream format mistakes.

Not excludable without doing it:

| Possible failure | What would happen | Harm |
|---|---|---|
| User data too fragmented for pinned allocation | installer reports an error | none; nothing is installed |
| An update snapshot still merging | `gsid` refuses | none |
| Guest does not reach the launcher (init, HAL or framework problem with this vendor) | boot stalls or loops | none to stock: the one-shot flag was consumed by the attempt, the next start is stock |
| Guest's own user data cannot be set up (wrapped-key metadata encryption on the DSU volume) | guest stalls early | none: this image's `init` refuses to request a data wipe while it runs as DSU (`cannot wipe within GSI`, and the recovery prompt path is suppressed for GSI) |
| Guest boots but telephony, audio or camera misbehave | visible in the session report | none; that is what the test is for |

One thing to know in advance: the guest logs "Vendor interface is incompatible" at boot because
the vendor expects two Qualcomm framework services (Wi-Fi display, telemetry) this ROM does not
ship. TrebleDroid suppresses the warning dialog; the log line is expected.

## 6. Assessment

**Ready for one controlled DSU boot.** Every precondition that can be established offline holds,
on the image, on the stock firmware and on the phone as it is today. What remains is what only
the boot can show. The realistic worst case is an installation that is refused or a guest that
does not come up; in both the phone starts stock again on the next reboot and `super`, `vendor`,
`boot`, modem and stock user data are never written. The procedure and the way back are in
TESTING.md, section "First test".
