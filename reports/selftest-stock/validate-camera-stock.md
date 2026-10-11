# Camera validation: validate-camera-stock

Generated: 2026-10-09T21:30:00

**PASS 9 / FAIL 0 / WARNING 2 / UNKNOWN 6**

Static analysis only. PASS means the checked property holds in the files; it does not prove that the feature works on hardware.

- maps: `/system=/work/fw/W2WVS36.55-95-5-1/root/system/system /system_ext=/work/fw/W2WVS36.55-95-5-1/root/system_ext /product=/work/fw/W2WVS36.55-95-5-1/root/product /apex=/work/fw/W2WVS36.55-95-5-1/apex /vendor=/work/fw/W2WVS36.55-95-5-1/root/vendor /odm=/work/fw/W2WVS36.55-95-5-1/root/odm`

| Status | Area | Test | Result |
|---|---|---|---|
| WARNING | camera | `native.vendor_private` | 17 vendor libraries named by the app exist but are not public; the app cannot load them (identical on stock, since /vendor is unchanged) |
| WARNING | camera | `permissions.unavailable` | 3 requested permissions cannot be granted in this image (their definers are not ported or use another key) |
| UNKNOWN | hardware | `hw.ai_processing` | Motorola/ArcSoft/QNN processing quality compared with stock: requires the device |
| UNKNOWN | hardware | `hw.dolby_vision` | Dolby Vision recording (stock service not ported; expected unavailable): requires the device |
| UNKNOWN | hardware | `hw.launch_preview` | application start and live preview: requires the device |
| UNKNOWN | hardware | `hw.lenses` | main, ultrawide, telephoto and front cameras (HAL camera list as seen by AOSP): requires the device |
| UNKNOWN | hardware | `hw.still_modes` | HDR, night, portrait, macro, pro and high-resolution capture: requires the device |
| UNKNOWN | hardware | `hw.video` | video recording, stabilisation, slow motion / high frame rate: requires the device |
| PASS | camera | `app.installed` | com.motorola.camera5 10.0.56.61 installed under /product with its original certificate |
| PASS | camera | `app.required_libraries` | required shared libraries present: ['com.motorola.motosignature'] |
| PASS | camera | `hal.provider` | vendor declares android.hardware.camera.provider (aidl) V3 ['ICameraProvider/vendor_qti/0'] |
| PASS | camera | `native.other_soc` | 52 libraries named by the app do not exist on this device (other SoC variants); optional by manifest |
| PASS | camera | `native.vendor_public` | 20 vendor processing libraries are on /vendor and in the vendor public-library list (loadable by the app) |
| PASS | camera | `permissions.hidden_api` | com.motorola.camera5 is on the hidden-API allowlist (it is not platform-signed and uses non-SDK interfaces) |
| PASS | camera | `permissions.motorola` | 14 Motorola permissions are defined in the image by packages sharing the camera's certificate (granted by signature) |
| PASS | camera | `permissions.privapp` | privileged allowlist under /product: ['android.permission.START_ACTIVITIES_FROM_BACKGROUND', 'android.permission.STOP_APP_SWITCHES', 'android.permission.WRITE_SECURE_SETTINGS'] |
| PASS | camera | `selinux.app_context` | com.motorola.camera5 runs in moto_camera_app; moto_camera_app_202504 is mapped and referenced 12 times by the stock vendor policy |

## Details

### WARNING: `native.vendor_private`

17 vendor libraries named by the app exist but are not public; the app cannot load them (identical on stock, since /vendor is unchanged)

- libQnnHtp.so
- libQnnHtpPrepare.so
- libQnnSystem.so
- libSNPE.so
- libbase.so
- libc++.so
- libcutils.so
- libdmabufheap.so
- libhardware.so
- libhidlbase.so
- libion.so
- liblzma.so
- libprocessgroup.so
- libunwindstack.so
- libutils.so
- libvmmem.so
- vendor.qti.hardware.dsp@1.0.so

### WARNING: `permissions.unavailable`

3 requested permissions cannot be granted in this image (their definers are not ported or use another key)

- com.motorola.imagertuning.content.ACCESS
- com.motorola.ccc.notification.READ_NOTIFICATIONS <- com.motorola.ccc.notification (different certificate)
- com.motorola.permission.WRITE_SECURE_SETTINGS <- com.motorola.android.providers.settings (different certificate)

### PASS: `app.installed`

com.motorola.camera5 10.0.56.61 installed under /product with its original certificate

- /work/fw/W2WVS36.55-95-5-1/root/product/priv-app/MotCamera5/MotCamera5.apk
- version 10.0.56.61
- certificate be8804a55e9045a580d204979f6efb15c058731aa1021b78c046feab8ae76a26

### PASS: `native.vendor_public`

20 vendor processing libraries are on /vendor and in the vendor public-library list (loadable by the app)

- libOpenCL.so
- libarc.ion.so
- libarcsoft_dualcam_refocus_image.so
- libarcsoft_dualcam_refocus_image_8845.so
- libarcsoft_dualcam_refocus_preview.so
- libarcsoft_dualcam_refocus_preview_8845.so
- libarcsoft_portrait_distortion_correction.so
- libarcsoft_qnnhtp.so
- libarcsoft_stellartrack.so
- libarcsoft_tf_sr.so
- libarcsoft_turbo_fusion_raw_portrait_super_night.so
- libarcsoft_turbo_fusion_raw_super_night.so
- libarcsoft_turbo_hdr_raw.so
- libarcsoft_turbo_hdr_raw_portrait.so
- libarcsoft_turbo_motion_capture_raw.so
- libcdsprpc.so
- libenginepostproc.moto.so
- libfastcvopt.so
- libportrait_repair_qnn.so
- libqti-perfd-client.so

### PASS: `permissions.motorola`

14 Motorola permissions are defined in the image by packages sharing the camera's certificate (granted by signature)

- com.motorola.camera.ai.colortone.PERMISSION_ACCESS_PROVIDER <- com.motorola.camera.ai.colortone
- com.motorola.camera.permission.CAMERA_STATE <- com.motorola.camera.ai.colortone
- com.motorola.camera.permission.COLOR_TONE_TRAINING_STATE <- com.motorola.camera5
- com.motorola.camera.permission.CONTROL_CAMERA <- com.motorola.camera5
- com.motorola.camera5.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION <- com.motorola.camera5
- com.motorola.hardware.ACCESS_CLI <- com.motorola.motosignature.app
- com.motorola.permission.ACCESS_APUSYS <- com.motorola.motosignature.app
- com.motorola.permission.ACCESS_CHECKIN <- com.motorola.motosignature.app
- com.motorola.permission.ACCESS_MOT_IMAGER <- com.motorola.motosignature.app
- com.motorola.permission.CONTROL_DISPLAY_BRIGHTNESS <- com.motorola.motosignature.app
- com.motorola.permission.GET_ZEN_MODE_CONFIG <- com.motorola.motosignature.app
- com.motorola.permission.MANAGE_NOTIFICATIONS <- com.motorola.motosignature.app
- com.motorola.permission.SET_ZEN_MODE_CONFIG <- com.motorola.motosignature.app
- com.motorola.permission.mobiledesktop.rdp <- com.motorola.mobiledesktop

### PASS: `selinux.app_context`

com.motorola.camera5 runs in moto_camera_app; moto_camera_app_202504 is mapped and referenced 12 times by the stock vendor policy

- user=_app isPrivApp=true seinfo=common2 domain=moto_camera_app name=com.motorola.camera5 type=app_data_file levelFrom=user
- user=_app isPrivApp=true seinfo=common2 domain=moto_camera_app name=com.motorola.camera5:* type=app_data_file levelFrom=user

