# Preflight: preflight-stock

Generated: 2026-10-09T21:35:35

**PASS 12 / FAIL 0 / WARNING 0 / UNKNOWN 0**

Static analysis only. PASS means the checked property holds in the files; it does not prove that the feature works on hardware.

- manifest: `/proj/vendor/motorola/vantage/proprietary-files.txt`
- maps: `/system=/work/fw/W2WVS36.55-95-5-1/root/system/system /system_ext=/work/fw/W2WVS36.55-95-5-1/root/system_ext /product=/work/fw/W2WVS36.55-95-5-1/root/product /apex=/work/fw/W2WVS36.55-95-5-1/apex /vendor=/work/fw/W2WVS36.55-95-5-1/root/vendor /odm=/work/fw/W2WVS36.55-95-5-1/root/odm`

| Status | Area | Test | Result |
|---|---|---|---|
| PASS | image | `image.size` | system image (678 MiB) fits the dynamic partition group with 16.1 GiB to spare |
| PASS | native | `native.needed` | DT_NEEDED of all 11 ported native libraries resolve in the image |
| PASS | permissions | `privapp.allowlist` | all privileged permissions of 2 priv-apps are allowlisted or granted by signature |
| PASS | placement | `files.present` | all 34 manifest files are present at their stock paths |
| PASS | platform | `platform.api_levels` | system (SDK 36, LLNDK 202504) is not older than the vendor (SDK 36, board API 202504) |
| PASS | selinux | `sepolicy.compile` | secilc compiled the system policy together with the stock vendor policy the way init does (9 CIL files, 2676939 byte policy) |
| PASS | selinux | `sepolicy.inputs` | system provides the platform policy and the 202504 mapping file |
| PASS | selinux | `sepolicy.mapping:moto_camera_app` | moto_camera_app_202504 is populated by the system policy (12 references in the stock vendor policy bind to it) |
| PASS | selinux | `sepolicy.mapping:vendor_qtelephony` | vendor_qtelephony_202504 is populated by the system policy (23 references in the stock vendor policy bind to it) |
| PASS | selinux | `sepolicy.seapp_domains` | every system-side seapp_contexts domain is declared |
| PASS | signing | `apk.signature` | app certificates match the manifest intent |
| PASS | vintf | `vintf.radio` | all vendor android.hardware.radio.* AIDL versions are accepted by the framework compatibility matrix level 202504 |

## Details

### PASS: `apk.signature`

app certificates match the manifest intent

- image platform certificate sha256=e0a42da29676e0e729df57021312dad6f91a0508d9f3332285e552e5d0235f3b
- /system_ext/priv-app/ims/ims.apk: re-signed with the image platform certificate
- /system_ext/app/QtiTelephonyService/QtiTelephonyService.apk: re-signed with the image platform certificate
- /product/priv-app/MotCamera5/MotCamera5.apk: keeps OEM certificate be8804a55e9045a5
- /system/app/MotoSignatureApp/MotoSignatureApp.apk: keeps OEM certificate be8804a55e9045a5

### PASS: `image.size`

system image (678 MiB) fits the dynamic partition group with 16.1 GiB to spare

- system image 711045120 bytes; group mot_dp_group_a max 31134318592; other stock partitions 13101555712; available for system 18032762880

### PASS: `platform.api_levels`

system (SDK 36, LLNDK 202504) is not older than the vendor (SDK 36, board API 202504)

- system sdk=36 sdk_full=36.0 llndk_api=202504 fingerprint=motorola/vantage_g/msi:16/W2WVS36M.55-95-ST2.6/79cc28:user/release-keys
- vendor sdk=36 board_api=202504 fingerprint=motorola/vantage_g/vantage:16/W2WVS36V.55-95-ST2.6/160ef0:user/release-keys

### PASS: `privapp.allowlist`

all privileged permissions of 2 priv-apps are allowlisted or granted by signature

- ro.control_privapp_permissions=enforce
- 1828 permission definitions in image
- org.codeaurora.ims: allowlist=['android.permission.INTERACT_ACROSS_USERS', 'android.permission.MODIFY_PHONE_STATE', 'android.permission.READ_NETWORK_USAGE_HISTORY', 'android.permission.READ_PRECISE_PHONE_STATE', 'android.permission.READ_PRIVILEGED_PHONE_STATE', 'android.permission.SUBSTITUTE_NOTIFICATION_APP_NAME', 'android.permission.WRITE_SECURE_SETTINGS']
- com.motorola.camera5: allowlist=['android.permission.START_ACTIVITIES_FROM_BACKGROUND', 'android.permission.STOP_APP_SWITCHES', 'android.permission.WRITE_SECURE_SETTINGS']

### PASS: `sepolicy.inputs`

system provides the platform policy and the 202504 mapping file

- /work/fw/W2WVS36.55-95-5-1/root/system/system/etc/selinux/plat_sepolicy.cil
- /work/fw/W2WVS36.55-95-5-1/root/system/system/etc/selinux/mapping/202504.cil
- /work/fw/W2WVS36.55-95-5-1/root/system_ext/etc/selinux/system_ext_sepolicy.cil
- /work/fw/W2WVS36.55-95-5-1/root/system_ext/etc/selinux/mapping/202504.cil
- /work/fw/W2WVS36.55-95-5-1/root/product/etc/selinux/product_sepolicy.cil
- /work/fw/W2WVS36.55-95-5-1/root/product/etc/selinux/mapping/202504.cil
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

