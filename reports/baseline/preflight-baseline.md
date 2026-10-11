# Preflight: preflight-baseline

Generated: 2026-10-09T23:53:03

**PASS 8 / FAIL 3 / WARNING 1 / UNKNOWN 1**

Static analysis only. PASS means the checked property holds in the files; it does not prove that the feature works on hardware.

- manifest: `/proj/vendor/motorola/vantage/proprietary-files.txt`
- maps: `/system=/work/aosp/out/target/product/tdgsi_arm64_ab/system /system_ext=/work/aosp/out/target/product/tdgsi_arm64_ab/system/system_ext /product=/work/aosp/out/target/product/tdgsi_arm64_ab/system/product /apex=/work/aosp/out/target/product/tdgsi_arm64_ab/apex /vendor=/work/fw/W2WVS36.55-95-5-1/root/vendor /odm=/work/fw/W2WVS36.55-95-5-1/root/odm`

| Status | Area | Test | Result |
|---|---|---|---|
| FAIL | placement | `files.present` | 33 of 34 manifest files are not in the image |
| FAIL | selinux | `sepolicy.mapping:moto_camera_app` | moto_camera_app_202504 is used 12 times by the stock vendor policy but no system-side type is mapped to it; those vendor rules are dead |
| FAIL | selinux | `sepolicy.mapping:vendor_qtelephony` | vendor_qtelephony_202504 is used 23 times by the stock vendor policy but no system-side type is mapped to it; those vendor rules are dead |
| WARNING | overlays | `overlay.targets` | none of the expected overlay packages were found in the image |
| UNKNOWN | platform | `platform.api_levels` | could not read API levels from build.prop |
| PASS | image | `image.size` | system image (2109 MiB) fits the dynamic partition group with 14.7 GiB to spare |
| PASS | native | `native.needed` | DT_NEEDED of all 0 ported native libraries resolve in the image |
| PASS | permissions | `privapp.allowlist` | all privileged permissions of 0 priv-apps are allowlisted or granted by signature |
| PASS | selinux | `sepolicy.compile` | secilc compiled the system policy together with the stock vendor policy the way init does (9 CIL files, 1544123 byte policy) |
| PASS | selinux | `sepolicy.inputs` | system provides the platform policy and the 202504 mapping file |
| PASS | selinux | `sepolicy.seapp_domains` | every system-side seapp_contexts domain is declared |
| PASS | signing | `apk.signature` | app certificates match the manifest intent |
| PASS | vintf | `vintf.radio` | all vendor android.hardware.radio.* AIDL versions are accepted by the framework compatibility matrix level 202504 |

## Details

### FAIL: `files.present`

33 of 34 manifest files are not in the image

- /product/etc/permissions/ims_ext_common.xml
- /product/framework/ims-ext-common.jar
- /system/etc/permissions/moto-ims-ext.xml
- /system/etc/permissions/moto-telephony.xml
- /system/framework/moto-ims-ext.jar
- /system/framework/moto-telephony.jar
- /system_ext/etc/permissions/qti_telephony_hidl_wrapper.xml
- /system_ext/etc/permissions/qti_telephony_utils.xml
- /system_ext/framework/qti-telephony-hidl-wrapper.jar
- /system_ext/framework/qti-telephony-utils.jar
- /system_ext/lib64/lib-imsvideocodec.so
- /system_ext/lib64/lib-imsvt.so
- /system_ext/lib64/lib-imsvtextutils.so
- /system_ext/lib64/lib-imsvtutils.so
- /system_ext/lib64/libdiag_system.so
- /system_ext/lib64/libimscamera_jni.so
- /system_ext/lib64/libimsmedia_jni.so
- /system_ext/lib64/vendor.qti.ImsRtpService-V2-ndk.so
- /system_ext/lib64/vendor.qti.diaghal@1.0.so
- /system_ext/lib64/vendor.qti.imsrtpservice@3.0.so
- /system_ext/lib64/vendor.qti.imsrtpservice@3.1.so
- /system_ext/priv-app/ims/ims.apk
- /system_ext/priv-app/ims/lib/arm64/libimscamera_jni.so
- /system_ext/priv-app/ims/lib/arm64/libimsmedia_jni.so
- /system_ext/app/QtiTelephonyService/QtiTelephonyService.apk
- /product/etc/permissions/com.motorola.camera5.lens.xml
- /product/etc/permissions/com.motorola.camera5.vantage.xml
- /product/etc/permissions/com.motorola.camera5.xml
- /product/etc/sysconfig/hiddenapi-whitelist-com.motorola.camera5.xml
- /product/priv-app/MotCamera5/MotCamera5.apk
- /system/app/MotoSignatureApp/MotoSignatureApp.apk
- /system/etc/permissions/com.motorola.motosignature.xml
- /system/framework/com.motorola.motosignature.jar

### WARNING: `overlay.targets`

none of the expected overlay packages were found in the image

- android.overlay.vantage.telephony
- com.android.carrierconfig.overlay.vantage
- com.android.phone.overlay.vantage

### UNKNOWN: `platform.api_levels`

could not read API levels from build.prop

- system sdk=36 sdk_full=36.0 llndk_api=202504 fingerprint=google/treble_arm64_bvN/tdgsi_arm64_ab:16/BP2A.250605.031.A3/eng.builde:userdebug/test-keys
- vendor sdk=None board_api=None fingerprint=None

### PASS: `apk.signature`

app certificates match the manifest intent

- image platform certificate sha256=c8a2e9bccf597c2fb6dc66bee293fc13f2fc47ec77bc6b2b0d52c11f51192ab8

### PASS: `image.size`

system image (2109 MiB) fits the dynamic partition group with 14.7 GiB to spare

- system image 2211053568 bytes; group mot_dp_group_a max 31134318592; other stock partitions 13101555712; available for system 18032762880

### PASS: `privapp.allowlist`

all privileged permissions of 0 priv-apps are allowlisted or granted by signature

- ro.control_privapp_permissions=disable
- 1110 permission definitions in image

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

