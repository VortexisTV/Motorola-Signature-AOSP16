# Camera port

Goal: run the original Motorola camera application (`com.motorola.camera5`, version
10.0.56.61) on the AOSP camera service against the untouched stock camera HAL.
**Nothing here has been tested on the device.** A package or library being present is never
reported as a working feature.

## 1. What the stock camera stack consists of

| Layer | Stock component | Under this ROM |
|---|---|---|
| Application | `MotCamera5.apk` (333 MB, 3 dex files, 14,388 classes, 47 bundled native libraries) | installed unmodified, keeps Motorola's signature |
| Signature permissions | `MotoSignatureApp.apk` defines 89 Motorola permissions (same certificate as the camera) | installed unmodified |
| Required shared library | `com.motorola.motosignature.jar` (1 class) | installed |
| Optional shared libraries | `moto-core_services`, `moto-settings`, `moto-active-stylus` | **not installed** (section 3) |
| In-app processing natives | 26 vendor libraries named in the manifest's `uses-native-library`: ArcSoft HDR / night / portrait / refocus / super-resolution, Qualcomm QNN and SNPE runtimes, `libenginepostproc.moto.so`, `libfastcvopt.so`, `libOpenCL.so`, `libcdsprpc.so` | unchanged on `/vendor`; loadable only if listed in `/vendor/etc/public.libraries.txt` (checked by `validate-camera.py`) |
| Framework | AOSP `android.hardware.camera2` plus Qualcomm/Motorola framework patches (auxiliary-camera filtering, Motorola wrappers) | AOSP `camera2` only |
| Camera service | QSSI `cameraserver` linked against `motorola.hardware.camera.desktop@1.0/2.0` | AOSP `cameraserver` |
| HAL | `android.hardware.camera.provider` AIDL V3, instance `vendor_qti/0` (CamX/CHI + Motorola nodes), `vendor.qti.hardware.camera.aon`, `...offlinecamera`, `vendor.qti.hardware.dsp`, Dolby `vendor.dolby.dvs`/`dms` | unchanged |
| SELinux | domain `moto_camera_app` (product policy) with vendor grants for the camera HAL, DSP (`vendor_xdsp_device`), perf HAL, ArcSoft post-processing HAL | type and attributes re-declared; vendor grants attach through `moto_camera_app_202504` |

## 2. Integration module

`components.json` -> component `camera`:

- `product/priv-app/MotCamera5/MotCamera5.apk` (`PRESIGNED`, privileged)
- `system/app/MotoSignatureApp/MotoSignatureApp.apk` (`PRESIGNED`)
- `system/framework/com.motorola.motosignature.jar` + its permission XML
- feature/sysconfig files: `com.motorola.camera5.xml`, `...vantage.xml`, `...lens.xml`,
  `hiddenapi-whitelist-com.motorola.camera5.xml`
- `camera/permissions/privapp-permissions-vantage-camera.xml`: the three privileged
  permissions stock allowlists (`STOP_APP_SWITCHES`, `WRITE_SECURE_SETTINGS`,
  `START_ACTIVITIES_FROM_BACKGROUND`)
- `sepolicy/`: `moto_camera_app`, `motoappdomain`, `moto_qcxdsp_domain` and the stock
  `seapp_contexts` lines (`seinfo=common2`; that seinfo is defined by the stock vendor's
  `vendor_mac_permissions.xml`, so no Motorola certificate is stored in this tree)

Signature handling: the camera is not platform-signed on stock either. It receives
Motorola's own permissions because `MotoSignatureApp` carries the same certificate, and
Android's privileged permissions through the allowlist. Both mechanisms work unchanged with
the original signatures. `com.motorola.permission.WRITE_SECURE_SETTINGS` (defined by
Motorola's settings provider, platform-signed) and `com.motorola.imagertuning.content.ACCESS`
(defined nowhere in the firmware) are simply not granted.

## 3. Dependencies on Motorola's framework

Static linkage of `MotCamera5.apk` against stock: every platform reference is to an
AOSP-namespace class (773 from `framework.jar`). Its Motorola dependencies are confined to
the optional libraries:

| Library | Classes the camera uses | What the library itself needs |
|---|---|---|
| `moto-core_services` | `CLIManager`, `MotoPerfManagerWrapper`, `MotoStorageManager`, `IScreenTimeControlService`, `MotoBackProgressAnimator`, wrappers for `BiometricManager`, `DisplayManager`, `WindowManager` | 34 `com.motorola.*` classes that exist only inside Motorola's `framework.jar` and are backed by Motorola system services |
| `moto-settings` | `MotorolaSettings$Global/$Secure` | Motorola's settings provider (`com.motorola.android.providers.settings`, platform-signed, `android.uid.system`) |
| `moto-active-stylus` | `TouchHalStylusManager` | Motorola classes inside `framework.jar` |

Measured against the AOSP 16 framework built here (`reports/linkage-aosp-baseline.json`):
`MotCamera5.apk` has **no** unresolved reference beyond the six shrinker artefacts it also has
on stock (mediapipe/protobuf). The reason is that the APK bundles its own copies of the three
libraries' API: 133 classes, 111 of which are plain stubs that throw `RuntimeException`. On
stock the real shared libraries shadow them; on this ROM the stubs are what runs.

`dex_guard_scan.py` (report `reports/camera-stub-guards.json`) finds 40 call sites into those
namespaces. All calls to `MotorolaSettings`, the stylus manager, `MotoStorageManager` and the
`*_wrap` helpers sit inside try/catch blocks. 24 sites are not locally guarded: 20 to
`CLIManager` (cover-display support) and 4 to `MotoPerfManagerWrapper`, in `OrientationEvent`,
`Camera`, `Util`, `CliCameraActivity` and `LaunchManager`.

Tracing the bytecode around them (invokes, branches, strings) shows they are conditional:

- `Util.isCLIState()` returns before touching `CLIManager` unless `SettingsHelper.hasCliDisplay()`;
  `Camera.onCreate()` only reaches `CLIManager.getInstance().hasFeature()` inside
  `if (isCliDisplay())`. This phone has no cover display.
- `Camera.onStop()` calls `MotoPerfManagerWrapper.perfHintStart()` only when the per-device
  value `mExitPerfHintDuration` is set. The APK is a vantage-specific build: its
  `assets/config_device_vantage` (60 keys) and `assets/app_feature_vantage` contain no perf-hint
  or cover-display entry.

So no unguarded stub call is expected on the launch path for this device. That is an inference
from configuration plus bytecode structure, not an execution: if the app aborts with
`RuntimeException: Stub!`, the stack trace names the site, and the remedy is a small
source-built `moto-core_services` shim (no-op `MotoPerfManagerWrapper`, `CLIManager` reporting
no cover display) rather than Motorola's real library.

The same device config shows what the app expects from the HAL: camera types `BACK_MAIN`,
`FRONT_MAIN`, `BACK_TELE`, `BACK_WIDE`, `BACK_MACRO`, logical depth and zoom-blending cameras,
`physical-camera-count: 4`, and a mapping by **sensor name** (`mot_imx09a`, `imx816`,
`mot_imx882`, `mot_s5kjns`, ...), i.e. it identifies cameras through vendor metadata rather
than fixed IDs.

### 3.1 What the missing Motorola framework members are, and which camera features use them

`moto-core_services.jar` measured against the AOSP framework of this build
(`check_java_linkage.py`): 40 missing classes (34 in `com.motorola.*`, 6 Motorola additions in
`android.*`), 110 missing methods on AOSP classes and 5 missing fields. Joined with the
camera's 40 call sites into the library:

| Camera code (feature) | Library class | Call sites / in try-catch | Motorola framework members behind it | Applies to this phone |
|---|---|---|---|---|
| Cover-display ("CLI") handling in `OrientationEvent`, `CliCameraActivity`, `CliLayoutManager`, `LaunchManager`, `Util`, `Camera` | `CLIManager` | 25 / 5 | `com.motorola.cli.CliManagerCore`, `ICliManager`, `android.app.ICliAppContinuityObserver`, `ISnippetCliObserver` | No: there is no cover display; the calls are behind `hasCliDisplay()` |
| Performance hint when the camera is left (`Camera.onStop`) | `MotoPerfManagerWrapper` | 4 / 0 | `com.motorola.perf.MotoPerfManager` | Gated by a per-device value that the vantage configuration does not set |
| HDR viewfinder surface (`CameraSurfaceViewComponent`) | `DisplayManager_wrap` | 1 / 1 | `DisplayManager.setForceHdrLayerPresent(int, boolean)` | Yes, caught: the display is not told to stay in HDR mode for the preview. Possible visible effect: preview brightness in HDR and Dolby Vision video modes |
| Window colour mode (`ColorUtil`) | `WindowManager_wrap` | 1 / 1 | field `WindowManager.LayoutParams.motoPrivateFlags` | Yes, caught |
| Storage helper (`StorageUtils`) | `MotoStorageManager` | 2 / 2 | none missing | Yes, caught |
| Motorola settings keys (`Camera`, `LidStateHelper`, `SettingsManager`) | `MotorolaSettings$Global`, `$Secure` | 5 / 5 | Motorola's settings provider | Yes, caught: defaults are used |
| Stylus (`Camera`) | `TouchHalStylusManager` | 2 / 2 | Motorola input classes | No stylus on this phone |

The remaining missing classes (`MotoActivityManagerCore`, `MotoDesktopManager`,
`MaxeSensingManager`, `MotoNfcManager`, PayJoy, face service, PRC permission manager, game
optimisation, screen helper, `MotoWindowManagerCore`, ...) are used by other parts of
`moto-core_services`, not by the camera. No capture mode (HDR, night, portrait, macro, pro,
high resolution, slow motion, Dolby Vision recording) goes through any of these classes: the
processing lives in the app's own libraries and in the vendor camera HAL.

These three are declared `android:required="false"`, i.e. the application is built to run
without them. Installing `moto-core_services.jar` on AOSP would make the class resolve and
then fail deeper (its own references into the missing framework classes), which is worse than
the library being absent. Decision: do not install them. Consequence: any camera feature
that goes through these classes (cover-display "CLI", performance hints, Motorola settings
keys, stylus) is expected to be unavailable. Whether the app handles their absence gracefully
at every call site is **UNKNOWN**; the 13 call sites are listed by
`check_java_linkage.py --dump-refs` for targeted review if the app misbehaves.

Whether the 773 AOSP-namespace classes resolve member-for-member against an unmodified
Android 16 framework is checked by `preflight.py` (`java.linkage:MotCamera5.apk`) on our build.

## 4. Feature expectations

| Feature | Depends on | Assessment |
|---|---|---|
| App launches, preview, still capture (main camera) | AOSP camera2 + provider AIDL V3 + SELinux domain + permissions | Static checks on the vantage image: no FAIL (`reports/vantage/validate-camera.md`); **UNKNOWN** on hardware |
| Ultrawide / telephoto / front, lens switching | HAL exposing the cameras to AOSP. Stock limits auxiliary cameras to `vendor.camera.aux.packagelist=com.motorola.camera3,com.motorola.camera5,com.motorola.motocit` through a Qualcomm *framework* patch; AOSP has no such filter (TrebleDroid adds its own camera-id properties). Whether the HAL lists all cameras to an unfiltered framework is not knowable statically. | **UNKNOWN** |
| HDR, night, portrait, super-resolution, refocus | In-app ArcSoft/QNN libraries on `/vendor` + DSP access granted to `moto_qcxdsp_domain` by the vendor policy | Libraries present; loadability checked statically; **UNKNOWN** on hardware |
| Vendor tags (Motorola/Qualcomm) | Provided by the HAL through standard camera2 metadata | Expected to pass through; **UNKNOWN** |
| OIS / zoom | HAL | **UNKNOWN** |
| Slow motion / high frame rate | HAL constrained high-speed configurations + codec HAL | **UNKNOWN** |
| Dolby Vision recording | Traced in the app (`SettingsHelper.isDolbyVisionSupported`, `SettingsManager.setupVideoDolbyVisionEncoderSupport`): (1) the per-device feature list, which for vantage contains `VIDEO_DOLBY_VISION` and `VIDEO_DOLBY_VISION_8K_30FPS`; (2) a camera-HAL vendor tag (`com.lenovo.moto.control.dolbyvision_support`); (3) an encoder for `video/dolby-vision` in `MediaCodecList`, which the stock vendor declares (`c2.dolby.encoder.hevc`, `c2.qti.dv.encoder`). No Motorola framework class or system service is involved. | Static inputs present (`video.dolby_vision_inputs`); **UNKNOWN** on hardware. An earlier revision called this "blocked"; that was wrong, see the next row. |
| Dolby Vision playback picture modes | `com.motorola.dolbyvisionservice`: a client of the vendor `vendor.dolby.dvs` HAL that reacts to Dolby Vision *playback* (notification with Bright / Dark / Vivid, brightness scaling). It requires `moto-core_services`. It has no camera, recording or encoder code. | Not ported. Decoding itself is done by the vendor decoders and is not affected. |
| AI colour tone | `MotColorTone.apk` (104 MB) + `com.motorola.aicore` | Not ported in this iteration |
| Desktop / external-display camera | `MotCameraDesktop` + Motorola `cameraserver` extension | Not ported; requires Motorola's `cameraserver` |
| Camera launch gesture, quick capture | Motorola sensor + SystemUI/Actions apps | Not ported |

## 4.1 First boot (2026-10-10): the app refused to start

Motorola Camera selects its configuration by `ro.product.device` (variant suffix stripped) and
ships `config_device_vantage` only. The guest reported `tdgsi_arm64_ab`, so the app showed
"Please use the official app for your device" (`JsonConfig: Parse json file(config_device) for
tdgsi failed`). The ROM now reports the stock identity (`ro.product.device=vantage`,
`ro.product.name=vantage_g`, model "motorola signature"); the vendor derives
`ro.vendor.product.device/name` from them, which the ArcSoft camera libraries and Motorola's
hardware table read as well.

Also seen and **not explained yet**: the camera service listed 2 devices; stock lists 6
(2 of them "normal"). To be re-read on the next boot with the corrected identity. The vendor
camera libraries also read `ro.build.type` and `ro.build.tags`, which differ from stock on this
userdebug build. FIRST_BOOT_REPORT.md sections 3.2 and 4.

## 4.2 Second and third boot: the camera set, and video mode

**Six cameras need the Qualcomm vendor-framework flag.** The stock camera HAL
(`com.qti.chi.override.so`) loads a reduced "GSI" configuration with 2 cameras unless
`ro.vendor.qti.va_aosp.support=1`. With it the HAL lists 6 devices (5 back, 1 front) and the
app opens the logical multi-camera, device 4, as on stock: seen after a provider restart on the
second boot and for a whole boot on the third. The same flag makes other vendor components
expect Qualcomm's system-side services (the GNSS XTRA daemon gave up and stayed down), so from
revision 3 the property has an SELinux type of its own that only the camera HAL can read
(`sepolicy/private/property.te`). SECOND_BOOT_REPORT.md section 5, THIRD_BOOT_REPORT.md
section 4.

**Video mode needs the camcorder profile file stock reads.** The app asks
`CamcorderProfile` for the profiles of its camera and stops with a `NullPointerException` in
`VideoMode.getSessionStreamRequest` when there are none. AOSP's libmedia read
`media_profiles_V1_0.xml` (cameras 0 and 1); the stock libmedia builds the name from the
vendor's `ro.media.xml_variant.codecs` and reads `media_profiles_canoe_sku3.xml` (cameras 0, 1,
2). Proven on the guest by making zygote read the stock file: video mode then opens.
Revision 3 copies the vendor's variant to `ro.media.xml_variant.profiles` in an init fragment
(`init/init.vantage.media.rc`). Recording itself has not been tried yet.
THIRD_BOOT_REPORT.md section 2.

**A screenshot of the video viewfinder killed surfaceflinger** (an HDR layer plus an
`android-16.0.0_r2` bug in the screenshot code, fixed upstream in `_r3`): patched from
revision 3, `patches/frameworks/native`. THIRD_BOOT_REPORT.md section 3.

**Known, not fixed:** the idle camera process is killed once about 30 s after boot by a
broadcast of the TrebleDroid app it does not expect. THIRD_BOOT_REPORT.md section 5.

## 5. Next actions

Done: `vantage_td` built; `preflight.py` and `validate-camera.py` report no FAIL on it
(app under `/product/priv-app` with its original certificate, privileged and hidden-API
allowlists present, domain `moto_camera_app` with 12 vendor rules bound to it; linkage: no
unresolved reference that is not also unresolved on stock).

1. Acceptance test (TESTING.md section 3): launch, each lens, each mode, with `logcat`
   captured so failures can be attributed (missing class, SELinux denial, HAL error).
