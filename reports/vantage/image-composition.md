# Image composition

Image `/work/aosp/out/target/product/tdgsi_arm64_ab/system.img`

SHA-256 `efe1b630cfdeda6f655112825d6df01aece2e0cc7fdf762b97a5296809dd9b3e`

PASS 22 / FAIL 0 / WARNING 1 / UNKNOWN 0

| Status | Check | Finding |
|---|---|---|
| PASS | `layout.single_image` | /system_ext and /product are symlinks into the image; content lives in /system/system_ext (183 files) and /system/product (812 files) |
| PASS | `layout.skip_mount` | skip_mount.cfg removes the stock fstab entries /product (product), /system_ext (system_ext); no remaining entry mounts on or under /system, /system_ext or /product |
| PASS | `stock.files` | 33 stock files in the image are byte-identical to the manifest hash and to the stock firmware; 2 JNI links point at files inside the image |
| PASS | `stock.resigned` | system_ext/priv-app/ims/ims.apk: all 13 payload entries equal the stock APK (name, size, CRC-32); only the signature differs, signer = the certificate of this image's framework-res.apk |
| PASS | `built.app` | /system/system_ext/app/VantageImsNetwork/VantageImsNetwork.apk: package vantage.telephony.imsnetwork, signed with this image's platform certificate |
| PASS | `built.app` | /system/system_ext/app/VantageRilReady/VantageRilReady.apk: package vantage.telephony.rilready, signed with this image's platform certificate |
| PASS | `built.app` | /system/app/QcRilAm/QcRilAm.apk: package me.phh.qcrilam, signed with this image's platform certificate |
| PASS | `built.ril_ready` | VantageRilReady runs in the system UID, is persistent and carries the OEM hook request for the RIL |
| PASS | `built.qcrilam_patched` | QcRilAm.apk in the image contains all 3 string literals that only the reliability patch adds, and declares the permission it adds (android.permission.MODIFY_AUDIO_ROUTING) |
| PASS | `built.overlay` | VantageCarrierConfigOverlay -> com.android.carrierconfig, static, priority 100: 0 values and 40 XML elements equal the source |
| PASS | `built.overlay` | VantageFrameworkTelephonyOverlay -> android, static, priority 100: 6 values and 0 XML elements equal the source |
| PASS | `built.overlay` | VantageTelephonyOverlay -> com.android.phone, static, priority 100: 1 values and 0 XML elements equal the source |
| PASS | `built.permissions` | 2 privileged-permission allowlists in the image equal the repository files: /system_ext/etc/permissions/privapp-permissions-vantage-telephony.xml, /product/etc/permissions/privapp-permissions-vantage-camera.xml |
| PASS | `built.privapp_partition` | org.codeaurora.ims (/system_ext/priv-app/ims/ims.apk) has its allowlist on the same partition: privapp-permissions-vantage-telephony.xml |
| PASS | `built.privapp_partition` | com.motorola.camera5 (/product/priv-app/MotCamera5/MotCamera5.apk) has its allowlist on the same partition: privapp-permissions-vantage-camera.xml |
| PASS | `built.sepolicy` | system_ext policy in the image declares vendor_qtelephony, moto_camera_app and carries all 3 seapp_contexts entries |
| PASS | `built.properties` | all 28 stock properties of properties.mk are in the build.prop of the partition stock uses |
| PASS | `built.identity` | ro.product.device/name/brand/manufacturer/model will be vantage/vantage_g/motorola/motorola/motorola signature: the stock values |
| PASS | `built.audio_vendor_extension` | audio parameter parser service, loader, stock library and its dependency, service and file labels, policy domain and both properties are in the image |
| PASS | `built.webview_default` | the effective WebView provider list (android.overlay.vantage.framework) has com.android.webview as its default, which is /system/product/app/webview/webview.apk |
| PASS | `built.media_profiles` | init copies the vendor's media variant to ro.media.xml_variant.profiles; the stock vendor image has a profile file for each of _canoe_sku1, _canoe_sku2, _canoe_sku3, _canoe_v1, _canoe_v2, _canoe_v3 |
| PASS | `built.vendor_framework_flag` | ro.vendor.qti.va_aosp.support=1 is set, has its own type vantage_vendor_framework_prop, hal_camera_server may read it, and no stock vendor or odm property_contexts names it |
| WARNING | `overlays.precedence` | 8 values set by our 3 overlays; 475 overlays in the image and the stock /vendor and /odm overlays for the same targets were compared: 0 active overlay(s) with higher precedence set a different value, 5 could at run time, 3 are overridden by ours or inactive, 1 set the same value |

## `layout.skip_mount`

```
patterns: /oem /product /system_ext /oem/* /product/* /system_ext/* /system/*
still mounted from the stock fstab: /boot /data /dtbo /init_boot /metadata /misc /mnt/product/logks /mnt/product/persist /mnt/vendor/persist /odm /recovery /storage/usbotg /system /system_dlkm /vendor /vendor/bt_firmware /vendor/dsp /vendor/firmware_mnt /vendor/fsg /vendor/soccp_firmware /vendor_boot /vendor_dlkm
```

## `stock.resigned`

```
stock signer e0a42da29676e0e729df57021312dad6f91a0508d9f3332285e552e5d0235f3b
image signer c8a2e9bccf597c2fb6dc66bee293fc13f2fc47ec77bc6b2b0d52c11f51192ab8
```

## `built.qcrilam_patched`

```
audioserver is down
audioserver is up
cannot watch the audioserver state
```

## `built.overlay`

```
array/config_telephonyEuiccDeviceCapabilities = ['gsm,9', 'utran,9', 'eutran,18', 'nfc,17']
array/non_removable_euicc_slots = ['1']
bool/config_enhanced_iwlan_handover_check = false
string/config_qualified_networks_service_package = vendor.qti.iwlan
string/config_wlan_data_service_package = vendor.qti.iwlan
string/config_wlan_network_service_package = vendor.qti.iwlan
```

## `built.overlay`

```
string/config_ims_mmtel_package = org.codeaurora.ims
```

## `overlays.precedence`

```
com.android.phone string/config_ims_mmtel_package: also set by me.phh.treble.overlay.flossims_telephony (image /product, mutable, priority 80, property gate on) = "me.phh.ims"  [mutable: applies only if something enables it at run time]
com.android.phone string/config_ims_mmtel_package: also set by me.phh.treble.overlay.hwims_telephony (image /product, mutable, priority 79, property gate on) = "com.huawei.ims"  [mutable: applies only if something enables it at run time]
com.android.phone string/config_ims_mmtel_package: also set by me.phh.treble.overlay.mtkims_telephony (image /product, mutable, priority 79, property gate on) = "com.mediatek.ims"  [mutable: applies only if something enables it at run time]
com.android.phone string/config_ims_mmtel_package: also set by me.phh.treble.overlay.slsiims_telephony (image /product, mutable, priority 0, property gate on) = "com.shannon.imsservice"  [mutable: applies only if something enables it at run time]
com.android.phone string/config_ims_mmtel_package: also set by me.phh.treble.overlay.sprdims_telephony (image /product, mutable, priority 79, property gate on) = "com.spreadtrum.ims"  [mutable: applies only if something enables it at run time]
android string/config_qualified_networks_service_package: also set by android.auto_generated_rro_product__ (image /product, static, priority 1, property gate on) = "com.android.telephony.qns"  [lower precedence than ours]
android string/config_wlan_data_service_package: also set by android.auto_generated_rro_product__ (image /product, static, priority 1, property gate on) = "com.google.android.iwlan"  [lower precedence than ours]
android string/config_wlan_network_service_package: also set by android.auto_generated_rro_product__ (image /product, static, priority 1, property gate on) = "com.google.android.iwlan"  [lower precedence than ours]
com.android.phone string/config_ims_mmtel_package: also set by me.phh.treble.overlay.cafims_telephony (image /product, mutable, priority 79, property gate on) = "org.codeaurora.ims"
```
