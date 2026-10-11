# Stock firmware analysis

Source: `VANTAGE_G_W2WVS36.55_95_5_1_subsidy_DEFAULT_regulatory_DEFAULT_cid50_CFC.xml`
(the package supplied by the owner). Everything here was read from those files or from the
attached device over read-only `adb`; nothing is assumed from other Motorola models.
Machine-derived tables: [reports/firmware-inventory.md](reports/firmware-inventory.md),
raw data: `reports/inventory/*.json`.

## 1. Identity

| Item | Value | Source |
|---|---|---|
| Model / SKU | motorola signature, XT2603-1 | info.txt, `ro.boot.hardware.sku` |
| Codename / product | `vantage` / `vantage_g` | build.prop |
| SoC / platform | SM8845 / `canoe` | `ro.soc.model`, `ro.board.platform` |
| Build | `W2WVS36.55-95-5-1` (user, release-keys), built 2026-06-02 | info.txt, build.prop |
| Android / SDK | 16 / 36 (`sdk_full` 36.0) | system build.prop |
| Security patch | 2026-06-01 (system and vendor) | build.prop, vbmeta |
| Qualcomm base | `LA.QSSI.16.0.R1.11.00.00.1274.090` | `ro.system.build.version.qcom` |
| Vendor API | board API level 202504, first API level 36 | vendor build.prop |
| Kernel | 6.12.38 android16 GKI, 4 KiB pages | `uname -a` on device |
| ABI | arm64-v8a only | `ro.product.cpu.abilist` |
| Modem / FSG | `M8845_DE90_22.2004.01.53.44R` / `FSG-8845-01.29.51` | info.txt |
| Carrier channel | `retin`, cid 50 (Retail) | `ro.carrier`, signing-info.txt |
| Radio | dual SIM DSDS; `ro.vendor.hw.esim=false`, eUICC slot 1 declared non-removable in the product overlay | device props, overlay dump |

The package's `info.txt` says "AB Update Enabled: False / Full Treble Enabled: False". Both are
wrong: the device reports `ro.build.ab_update=true`, slot `_a`, `ro.treble.enabled=true`,
`ro.virtual_ab.enabled=true` with compression, and the super metadata has the Virtual A/B flag.

Device state when inspected: stock build identical to the package, bootloader already
unlocked (`ro.boot.verifiedbootstate=orange`, `ro.boot.flash.locked=0`), SELinux enforcing.

## 2. Package integrity

All 44 images listed in `flashfile.xml` match their MD5 (status PASS). SHA-256 of every file:
[reports/stock-firmware.sha256](reports/stock-firmware.sha256),
[reports/stock-firmware-hashes.md](reports/stock-firmware-hashes.md). The package is never
written to; extraction goes to the build VM (`/work/fw/W2WVS36.55-95-5-1`).

## 3. Image formats and partition layout

| Image | Format | Notes |
|---|---|---|
| `super.img_sparsechunk.0-29` | Android sparse, 30 chunks | 31,138,512,896 byte super; liblp metadata v10.2, 3 slots, Virtual A/B flag |
| `boot.img` | boot header v4 | kernel only (39.9 MB), no ramdisk |
| `init_boot.img` | boot header v4 | generic ramdisk (2.9 MB, lz4) |
| `vendor_boot.img` | vendor boot header v4 | one vendor ramdisk (lz4), DTB, bootconfig; holds `first_stage_ramdisk/fstab.qcom` |
| `recovery.img` | boot header v4 | ramdisk only |
| `dtbo.img`, `pvmfw.img` | raw | |
| `vbmeta.img`, `vbmeta_system.img` | AVB 1.3, SHA256_RSA4096, rollback index 6 | see section 8 |
| `radio.img`, `bootloader.img`, `BTFM.bin`, `dspso.bin` | Motorola/Qualcomm firmware containers | **not analysed further, never modified** |

No `payload.bin`, no separate `system.img`/`vendor.img`: logical partitions exist only inside
`super`. `extract_firmware.py` reads the sparse chunks directly and dumps:

| Logical partition (slot a) | Size | Filesystem |
|---|---:|---|
| system | 711,045,120 | EROFS |
| system_ext | 702,656,512 | EROFS |
| product | 8,855,392,256 | EROFS |
| vendor | 3,215,228,928 | EROFS |
| odm | 291,786,752 | EROFS |
| vendor_dlkm | 27,996,160 | EROFS |
| system_dlkm | 8,495,104 | EROFS |
| system_b | 543,883,264 | (system_other) |

Dynamic partition group `mot_dp_group_a`: maximum 31,134,318,592 bytes, 13,812,600,832 used
by stock. Without `system`, stock uses about 13.1 GB, leaving about 18 GB for a replacement
system image. Physical partitions seen on the device (`/dev/block/by-name`) include the A/B
pairs `boot`, `init_boot`, `vendor_boot`, `dtbo`, `recovery`, `vbmeta`, `vbmeta_system`,
`modem`, `fsg`, `dsp`, `bluetooth`, and the single `persist`, `prodpersist`, `modemst1/2`,
`fsc`, `utags`, `cid`, `metadata`, `super`, `userdata`.

### What the first-stage fstab implies

`system`, `system_ext`, `product`, `vendor`, `odm`, `vendor_dlkm`, `system_dlkm` are all
`logical,first_stage_mount` with both `erofs` and `ext4` entries; `system`, `system_ext` and
`product` are verified through `vbmeta_system`/`vbmeta`, and `system` additionally accepts the
Google GSI keys (`avb_keys=/avb/q-gsi…v-gsi`). `userdata` is f2fs with metadata encryption
(`wrappedkey_v0`, inline crypt) and checkpointing.

Consequence: a GSI-layout system image (system + system_ext + product in one filesystem with
`/system_ext/etc/init/config/skip_mount.cfg`) makes first-stage init skip the stock
`system_ext` and `product`. Those two partitions hold 9.5 GB of Motorola/Qualcomm system-side
software that therefore disappears unless it is ported (section 5).

## 4. Vendor side (kept as shipped)

143 HALs are declared in the vendor/odm VINTF manifests (141 AIDL, 1 HIDL, 1 native; target
FCM level 202504; full list in the generated report). The device compatibility matrix asks the
framework for system SDK 36 and for three framework-side HALs: `android.frameworks.sensorservice`
(AOSP), `vendor.qti.hardware.sigma_miracast_aidl` and `vendor.qti.qccsyshal_aidl` (both provided
by stock `system_ext`, absent from AOSP: Wi-Fi Display and Qualcomm telemetry only). Relevant HALs:

| Area | HAL (version) / component | Notes |
|---|---|---|
| Radio | `android.hardware.radio.{config,data,messaging,modem,network,sim,voice}` **V4**, `…radio.sap` | Standard AIDL, instances `slot1`/`slot2`; implemented by `/vendor/bin/hw/qcrilNrd` (services `vendor.qcrild`, `vendor.qcrild2`) |
| Radio (QTI) | `vendor.qti.hardware.radio.ims` V20 (`IImsRadio/imsradio0,1`), `…qtiradio` V16, `…qtiradioconfig` V6, `…qcrilhook`, `…am` (`IQcRilAudio`), `…uim`, `…lpa`, `…uim_remote_client/server` | Qualcomm extensions; only reachable from system-side Qualcomm apps |
| IMS | `vendor.qti.ims.factoryaidlservice`, `vendor.qti.ImsRtpService` V2, `vendor.qti.ims.datachannelservice` V3; daemons `imsdaemon`, `ims_rtp_daemon`, `ims-dataservice-daemon` | **No `android.hardware.radio.ims`**: AOSP's own IMS radio HAL is not implemented, so IMS must go through Qualcomm's stack |
| Data | `vendor.qti.hardware.data.connectionfactory`, `…iwlandata` V3, `cnd`, `vendor.dpmd`, `port-bridge`, `ipacm`; apps `/vendor/app/{CneApp,IWlanService}` | IWLAN/CNE apps are signed with Motorola's platform key (section 7) |
| Audio | `android.hardware.audio.core.IModule/default` (Qualcomm AIDL HAL, PAL/AGM) | Declares `telephony_rx`/`telephony_tx` device ports with device-to-device routes to earpiece, speaker, USB and Bluetooth sinks |
| Camera | `vendor.qti.camera.provider` (AIDL `ICameraProvider`), `vendor.qti.camera.aon`, `…offlinecamera` | CamX/CHI with Motorola and ArcSoft processing libraries |
| Display | `vendor.qti.hardware.display.composer` (composer3), `…allocator`, Motorola panel/touch/stylus services | |

SELinux: vendor policy version **202504**, precompiled policy in `/odm/etc/selinux` keyed to
the hashes of the stock system/system_ext/product policy. With any other system image the
hashes differ and `init` compiles the policy on the device from the CIL files, which is why
the combined policy can be validated offline (`preflight.py`, `sepolicy.compile`).

`/vendor/etc/selinux/vendor_mac_permissions.xml` maps Motorola's certificates to seinfo values
(`platform`, `common`, `common2`, `release`) and remains active with a custom system.

`ro.control_privapp_permissions=enforce`: a privileged app requesting a privileged permission
that is not allowlisted aborts `system_server` at boot. `preflight.py` checks this.

## 5. System side (replaced): what stock has that AOSP does not

Stock `system` is Qualcomm QSSI 16 with Motorola changes; `system_ext` and `product` add the
rest. Counts: system 31 apps + 51 priv-apps + 37 APEXes; system_ext 15 + 67 + 6;
product 42 + 85 (+127 overlays, 11 preinstalls).

### 5.1 Telephony

| Component | Stock location | Signing | Role | Needed |
|---|---|---|---|---|
| `org.codeaurora.ims` (`ims.apk`) | `/system_ext/priv-app/ims` | platform | Qualcomm `ImsService` (MMTel): VoLTE, VoWiFi, ViLTE, SMS over IMS; talks to `IImsRadio` | **Yes** (ported) |
| `ims-ext-common.jar` | `/product/framework` | - | `org.codeaurora.ims.*` shared library | **Yes** |
| `qti-telephony-utils.jar`, `qti-telephony-hidl-wrapper.jar` | `/system_ext/framework` | - | shared libraries of `ims.apk` | **Yes** |
| `moto-telephony.jar`, `moto-ims-ext.jar` | **`/system/framework`** | - | Motorola libraries `ims.apk` requires (`required=true`) | **Yes** |
| `libimsmedia_jni`, `libimscamera_jni`, `lib-imsvt*`, `lib-imsvideocodec`, `libdiag_system`, `vendor.qti.imsrtpservice@3.x`, `vendor.qti.ImsRtpService-V2-ndk`, `vendor.qti.diaghal@1.0` | `/system_ext/lib64` | - | video-telephony natives (DT_NEEDED + `dlopen`) | Yes (ViLTE) |
| `config_ims_mmtel_package=org.codeaurora.ims` | compiled into stock **`TeleService.apk`** | - | binds the IMS service; empty in AOSP | **Yes** (overlay) |
| `telephony_injection` overlay to `QtiTelephonyComponentFactory` | `/product/overlay/TelephonyResCommonQcomRRO.apk`; 16 jars | platform | replaces ~20 core telephony classes (RIL, ServiceStateTracker, GsmCdmaPhone, data stack) with Qualcomm/Motorola subclasses | **No** (deliberately; see TELEPHONY_PORT.md) |
| `com.qti.phone` (`QtiTelephony`), `QtiTelephonyService`, `qcrilmsgtunnel`, `datastatusnotification` | system_ext/product | platform, shared UID `android.uid.qtiphone` | Qualcomm ExtTelephony service, OEM hook tunnel | Not for basic service; candidate later |
| `ImsRcsService`, `uceShimService`, `dpmserviceapp`, `DynamicDDSService` | `/system_ext/app` | platform, `android.uid.phone` | RCS/UCE, DPM, dynamic DDS | Optional |
| IWLAN bindings (`config_wlan_data_service_package` etc. = `vendor.qti.iwlan`) | `/product/overlay/MotoFrameworkResOverlayQcomCommon.apk` | - | Wi-Fi calling transport | Yes (overlay) |
| `MSimSettings`, `MotoSmart5G`, `ModemStatsService`, Motorola CarrierConfig, Google CarrierSettings | system_ext/product | mixed | Motorola UX and carrier provisioning | No / later |
| Motorola framework services `motoexttelephony`, `moto_ext_telephony.registry` | `services.jar`, `TeleService.apk` | - | `MotoExtTelephonyManager` backend | Not ported; library degrades gracefully (verified in bytecode) |

### 5.2 Camera

| Component | Stock location | Signing | Role |
|---|---|---|---|
| `com.motorola.camera5` (`MotCamera5.apk`, 333 MB, 47 bundled native libraries) | `/product/priv-app/MotCamera5` | Motorola app key `be8804a5…` (seinfo `common2`) | the camera application |
| `com.motorola.motosignature.app` | `/system/app/MotoSignatureApp` | same key | defines 89 Motorola signature permissions, 13 of which the camera requests |
| `com.motorola.motosignature.jar` | `/system/framework` | - | only **required** shared library of the camera |
| `moto-core_services.jar`, `moto-settings.jar`, `moto-active-stylus.jar` | `/system/framework` | - | *optional* libraries; `moto-core_services` needs 34 Motorola classes inside stock `framework.jar` |
| `com.motorola.camera.ai.colortone` (`MotColorTone`, 104 MB) | `/product/priv-app` | same key | AI colour-tone feature |
| `com.motorola.dolbyvisionservice` | `/system/app` | platform | Dolby Vision; requires `moto-core_services` |
| `MotCameraDesktop`, `com.motorola.hardware.camera.desktop.jar` | system_ext | Motorola key `c463fa2a…` | external-display camera; stock `cameraserver` links `motorola.hardware.camera.desktop@1.0/2.0` |
| feature/sysconfig XML (`com.motorola.camera5*.xml`, hidden-API allowlist) | `/product/etc` | - | feature flags the app checks |
| vendor props `vendor.camera.aux.packagelist`, `ro.camera.cfa.packagelist` | vendor | - | consumed by Qualcomm's *framework* patches on stock; AOSP ignores them |

### 5.3 Platform differences that matter

- Stock boot classpath adds `tcmiface.jar`, `qcom.fmradio.jar`, `QPerformance.jar`,
  `UxPerformance.jar`, `WfdCommon.jar`, `payjoy-api.jar`; none is needed by the ported set.
- Stock `cameraserver` and `surfaceflinger` link Qualcomm/Motorola system libraries
  (display config, composer extensions, camera desktop). The AOSP binaries do not; anything
  that depends on those extensions is UNKNOWN until tested on hardware.
- Mainline modules on stock are Google-signed (`com.google.android.*`); the ROM uses AOSP ones.

## 6. Dependency evidence (static)

`check_java_linkage.py` resolves every class, method and field reference of an APK/JAR against
the jars visible at run time (boot classpath incl. APEX jars + declared shared libraries).
Self-test against stock (54 boot jars, 62,479 classes):

| Subject | Result on stock | Platform classes used |
|---|---|---|
| `ims.apk` | all references resolve | 135 from `framework.jar` (all in AOSP namespaces), none from `telephony-common.jar`/`ims-common.jar`; Motorola: 2 classes from `moto-telephony.jar` |
| `moto-telephony.jar`, `moto-ims-ext.jar`, `ims-ext-common.jar`, `qti-telephony-utils.jar`, `qti-telephony-hidl-wrapper.jar` | all resolve | AOSP-namespace classes only |
| `MotCamera5.apk` | resolves except 7 symbols that are also unresolved on stock (shrunk protobuf/mediapipe code) | 773 from `framework.jar`, AOSP namespaces only; 13 classes from the three optional Motorola libraries |
| `moto-core_services.jar` | all resolve | **34 `com.motorola.*` classes inside stock `framework.jar`** |

"AOSP namespace" is necessary, not sufficient: whether each referenced member exists in an
unmodified Android 16 framework is decided by re-running the same check against our own
build (`preflight.py`, `java.linkage:*`).

## 7. Signing keys

106 distinct certificates. The ones that matter:

| Label | SHA-256 prefix | Used by |
|---|---|---|
| Motorola platform | `e0a42da29676e0e7` | 138 packages incl. all Qualcomm telephony apps and the vendor apps `CneApp`, `IWlanService`, `TxPwrAdmin`, `CACertService` |
| Motorola app key (seinfo `common2`) | `be8804a55e9045a5` | `MotCamera5`, `MotoSignatureApp`, `MotColorTone`, 42 more |
| Motorola app key (seinfo `common`) | `c463fa2a0351086d` | 77 packages incl. `MotCameraDesktop` |
| Motorola release | `127524ce62c919b7` | 66 packages |

Components that depend on Motorola's **platform** key cannot be transplanted unchanged:
platform-signature permissions and platform shared UIDs are tied to the ROM's platform key.
System-side ones are re-signed by the build. The vendor-side apps (`CneApp`, `IWlanService`)
stay on `/vendor` with Motorola's signature; under this ROM they keep their SELinux domain
but lose signature-level Android permissions. That is the open blocker for Wi-Fi calling.

## 8. Verified boot

`vbmeta` (rollback index 6) carries hash descriptors for boot, init_boot, vendor_boot, dtbo,
pvmfw, recovery and hashtrees for vendor, odm, product, vendor_dlkm, system_dlkm; it chains
`vbmeta_system` (hashtrees for system and system_ext). A replaced `system` cannot satisfy the
stock hashtree, so booting it requires the bootloader to be unlocked (it is) and verification
of `vbmeta` to be disabled or a custom-signed `vbmeta`/`vbmeta_system`. Deployment details and
rollback are in TESTING.md. `HAB_SECURITY_VERSION 6` / anti-rollback: never flash an older
bootloader or modem; this project flashes neither.
