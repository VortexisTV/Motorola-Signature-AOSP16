# Preflight: preflight

Generated: 2026-10-11T02:51:12

**PASS 27 / FAIL 0 / WARNING 3 / UNKNOWN 0**

Static analysis only. PASS means the checked property holds in the files; it does not prove that the feature works on hardware.

- manifest: `/proj/vendor/motorola/vantage/proprietary-files.txt`
- maps: `/system=/work/aosp/out/target/product/tdgsi_arm64_ab/system /system_ext=/work/aosp/out/target/product/tdgsi_arm64_ab/system/system_ext /product=/work/aosp/out/target/product/tdgsi_arm64_ab/system/product /apex=/work/aosp/out/target/product/tdgsi_arm64_ab/apex /vendor=/work/fw/W2WVS36.55-95-5-1/root/vendor /odm=/work/fw/W2WVS36.55-95-5-1/root/odm`

| Status | Area | Test | Result |
|---|---|---|---|
| WARNING | java | `java.linkage:ims.apk` | 2 references do not resolve against this image (0 more are also unresolved on stock) |
| WARNING | java | `java.linkage:moto-telephony.jar` | 1 references do not resolve against this image (0 more are also unresolved on stock) |
| WARNING | selinux | `sepolicy.unmapped` | 1 empty versioned attributes belong to labels the vendor's own context files assign; vendor rules on those objects are dead (review each) |
| PASS | image | `image.size` | system image (2438 MiB) fits the dynamic partition group with 14.4 GiB to spare |
| PASS | java | `java.linkage:MotCamera5.apk` | all external references resolve (6 unresolved, all pre-existing on stock) |
| PASS | java | `java.linkage:MotoSignatureApp.apk` | all external references resolve |
| PASS | java | `java.linkage:com.motorola.motosignature.jar` | all external references resolve |
| PASS | java | `java.linkage:ims-ext-common.jar` | all external references resolve |
| PASS | java | `java.linkage:moto-ims-ext.jar` | all external references resolve |
| PASS | java | `java.linkage:qti-telephony-hidl-wrapper.jar` | all external references resolve |
| PASS | java | `java.linkage:qti-telephony-utils.jar` | all external references resolve |
| PASS | native | `native.needed` | DT_NEEDED of all 14 ported native libraries resolve in the image |
| PASS | overlays | `overlay.package:config_qualified_networks_service_package` | string/config_qualified_networks_service_package -> vendor.qti.iwlan found under /vendor |
| PASS | overlays | `overlay.package:config_wlan_data_service_package` | string/config_wlan_data_service_package -> vendor.qti.iwlan found under /vendor |
| PASS | overlays | `overlay.package:config_wlan_network_service_package` | string/config_wlan_network_service_package -> vendor.qti.iwlan found under /vendor |
| PASS | overlays | `overlay.targets:android.overlay.vantage.telephony` | all 6 overlaid resources exist in android |
| PASS | overlays | `overlay.targets:com.android.carrierconfig.overlay.vantage` | all 1 overlaid resources exist in com.android.carrierconfig |
| PASS | overlays | `overlay.targets:com.android.phone.overlay.vantage` | all 1 overlaid resources exist in com.android.phone |
| PASS | permissions | `privapp.allowlist` | all privileged permissions of 2 priv-apps are allowlisted or granted by signature |
| PASS | placement | `files.content` | 27 verbatim-installed files are byte-identical to stock |
| PASS | placement | `files.present` | all 36 manifest files are present at their stock paths |
| PASS | platform | `platform.api_levels` | system (SDK 36, LLNDK 202504) is not older than the vendor (SDK 36, board API 202504) |
| PASS | selinux | `sepolicy.compile` | secilc compiled the system policy together with the stock vendor policy the way init does (9 CIL files, 1557891 byte policy) |
| PASS | selinux | `sepolicy.inputs` | system provides the platform policy and the 202504 mapping file |
| PASS | selinux | `sepolicy.mapping:moto_camera_app` | moto_camera_app_202504 is populated by the system policy (12 references in the stock vendor policy bind to it) |
| PASS | selinux | `sepolicy.mapping:vendor_qtelephony` | vendor_qtelephony_202504 is populated by the system policy (23 references in the stock vendor policy bind to it) |
| PASS | selinux | `sepolicy.seapp_domains` | every system-side seapp_contexts domain is declared |
| PASS | signing | `apk.signature` | app certificates match the manifest intent |
| PASS | telephony | `telephony.ims_binding` | org.codeaurora.ims declares an android.telephony.ims.ImsService guarded by BIND_IMS_SERVICE |
| PASS | vintf | `vintf.radio` | all vendor android.hardware.radio.* AIDL versions are accepted by the framework compatibility matrix level 202504 |

## Details

### WARNING: `java.linkage:ims.apk`

2 references do not resolve against this image (0 more are also unresolved on stock)

- methods Landroid/telephony/ims/ImsExternalCallState;-><init>(Ljava/lang/String;Landroid/net/Uri;Landroid/net/Uri;ZIIZZ)V  (used by Lorg/codeaurora/ims/parser/ImsViceParser;)
- methods Lorg/codeaurora/ims/ImsConfigImpl;->resetProvisionedCacheValue()V  (used by Lorg/codeaurora/ims/ImsConfigImplOem;)

### WARNING: `java.linkage:moto-telephony.jar`

1 references do not resolve against this image (0 more are also unresolved on stock)

- fields Landroid/os/Build;->SOC_MANUFACTURER_IS_MTK:Z  (used by Lcom/motorola/android/internal/telephony/MotoExtTelephonyRegistry$DiagnosisEventProxy;, Lcom/motorola/android/telephony/MotoExtTelephonyManager;)

### WARNING: `sepolicy.unmapped`

1 empty versioned attributes belong to labels the vendor's own context files assign; vendor rules on those objects are dead (review each)

- 1539 versioned attributes referenced by vendor/odm rules, 1413 populated, 126 empty
- vendor_hal_atfwd_hwservice_202504: vendor_hwservice_contexts: vendor.qti.hardware.radio.atcmdfwd::IAtCmdFwd

### PASS: `apk.signature`

app certificates match the manifest intent

- image platform certificate sha256=c8a2e9bccf597c2fb6dc66bee293fc13f2fc47ec77bc6b2b0d52c11f51192ab8
- /system_ext/priv-app/ims/ims.apk: re-signed with the image platform certificate
- /product/priv-app/MotCamera5/MotCamera5.apk: keeps OEM certificate be8804a55e9045a5
- /system/app/MotoSignatureApp/MotoSignatureApp.apk: keeps OEM certificate be8804a55e9045a5

### PASS: `image.size`

system image (2438 MiB) fits the dynamic partition group with 14.4 GiB to spare

- system image 2556506112 bytes; group mot_dp_group_a max 31134318592; other stock partitions 13101555712; available for system 18032762880

### PASS: `overlay.targets:android.overlay.vantage.telephony`

all 6 overlaid resources exist in android

- array/config_telephonyEuiccDeviceCapabilities = () (array) size=4 ["gsm,9", "utran,9", "eutran,18", "nfc,17"]
- array/non_removable_euicc_slots = () (array) size=1 [1]
- bool/config_enhanced_iwlan_handover_check = () false
- string/config_qualified_networks_service_package = () "vendor.qti.iwlan"
- string/config_wlan_data_service_package = () "vendor.qti.iwlan"
- string/config_wlan_network_service_package = () "vendor.qti.iwlan"

### PASS: `overlay.targets:com.android.carrierconfig.overlay.vantage`

all 1 overlaid resources exist in com.android.carrierconfig

- xml/vendor = () (file) res/xml/vendor.xml type=XML

### PASS: `overlay.targets:com.android.phone.overlay.vantage`

all 1 overlaid resources exist in com.android.phone

- string/config_ims_mmtel_package = () "org.codeaurora.ims"

### PASS: `platform.api_levels`

system (SDK 36, LLNDK 202504) is not older than the vendor (SDK 36, board API 202504)

- system sdk=36 sdk_full=36.0 llndk_api=202504 fingerprint=motorola/vantage_td/tdgsi_arm64_ab:16/BP2A.250605.031.A3/eng.builde:userdebug/test-keys
- vendor sdk=36 board_api=202504 fingerprint=motorola/vantage_g/vantage:16/W2WVS36V.55-95-ST2.6/160ef0:user/release-keys

### PASS: `privapp.allowlist`

all privileged permissions of 2 priv-apps are allowlisted or granted by signature

- ro.control_privapp_permissions=enforce
- 1208 permission definitions in image
- org.codeaurora.ims: allowlist=['android.permission.INTERACT_ACROSS_USERS', 'android.permission.MODIFY_PHONE_STATE', 'android.permission.READ_NETWORK_USAGE_HISTORY', 'android.permission.READ_PRECISE_PHONE_STATE', 'android.permission.READ_PRIVILEGED_PHONE_STATE', 'android.permission.SUBSTITUTE_NOTIFICATION_APP_NAME', 'android.permission.WRITE_SECURE_SETTINGS']
- com.motorola.camera5: allowlist=['android.permission.START_ACTIVITIES_FROM_BACKGROUND', 'android.permission.STOP_APP_SWITCHES', 'android.permission.WRITE_SECURE_SETTINGS']

### PASS: `sepolicy.inputs`

system provides the platform policy and the 202504 mapping file

- /work/aosp/out/target/product/tdgsi_arm64_ab/system/etc/selinux/plat_sepolicy.cil
- /work/aosp/out/target/product/tdgsi_arm64_ab/system/etc/selinux/mapping/202504.cil
- /work/aosp/out/target/product/tdgsi_arm64_ab/system/system_ext/etc/selinux/system_ext_sepolicy.cil
- /work/aosp/out/target/product/tdgsi_arm64_ab/system/system_ext/etc/selinux/mapping/202504.cil
- /work/aosp/out/target/product/tdgsi_arm64_ab/system/product/etc/selinux/product_sepolicy.cil
- /work/aosp/out/target/product/tdgsi_arm64_ab/system/product/etc/selinux/mapping/202504.cil
- /work/fw/W2WVS36.55-95-5-1/root/vendor/etc/selinux/plat_pub_versioned.cil
- /work/fw/W2WVS36.55-95-5-1/root/vendor/etc/selinux/vendor_sepolicy.cil
- /work/fw/W2WVS36.55-95-5-1/root/odm/etc/selinux/odm_sepolicy.cil

### PASS: `telephony.ims_binding`

org.codeaurora.ims declares an android.telephony.ims.ImsService guarded by BIND_IMS_SERVICE

- /work/aosp/out/target/product/tdgsi_arm64_ab/system/system_ext/priv-app/ims/ims.apk

### PASS: `vintf.radio`

all vendor android.hardware.radio.* AIDL versions are accepted by the framework compatibility matrix level 202504

- android.hardware.radio.config: vendor V[4] framework accepts ['3-4']
- android.hardware.radio.data: vendor V[4] framework accepts ['3-4']
- android.hardware.radio.messaging: vendor V[4] framework accepts ['3-4']
- android.hardware.radio.modem: vendor V[4] framework accepts ['3-4']
- android.hardware.radio.network: vendor V[4] framework accepts ['3-4']
- android.hardware.radio.sap: vendor V[1] framework accepts []
- android.hardware.radio.sim: vendor V[4] framework accepts ['3-4']
- android.hardware.radio.voice: vendor V[4] framework accepts ['3-4']

