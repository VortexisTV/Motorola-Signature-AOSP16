# Compatibility status

Last updated 2026-10-11, after five DSU sessions on one phone (image revisions 1 to 4). Columns:

- *Static*: what host-side analysis established (PASS / FAIL / WARNING), run against the
  `vantage_td` image, last on revision 4 (reports in `reports/vantage/`).
- *Device*: what the phone logged in a session and, where it can only be heard or seen, what the owner reported. UNKNOWN = not exercised.

A static PASS means the files and configuration are consistent. It is not evidence that the
feature works.

## Foundation

| Item | Static | Device | Notes |
|---|---|---|---|
| Source baseline (AOSP android-16.0.0_r2 + TrebleDroid android-16.0) | PASS: synced, pinned manifest, branch `vantage-baseline` | n/a | |
| System API level vs vendor (SDK 36 / board API 202504) | PASS on the source level; re-checked on the image by `platform.api_levels` | UNKNOWN | |
| Baseline `system.img` (unmodified TrebleDroid) | **built** (2,211,053,568 bytes, ext4); combined SELinux policy with the stock vendor compiles; radio HAL versions accepted | UNKNOWN | `reports/baseline/` |
| `vantage_td` image | **built** (2,556,280,832 bytes, ext4, `e2fsck` clean); preflight 27 PASS / 0 FAIL / 3 WARNING, telephony 14 PASS / 0 FAIL | UNKNOWN | BUILDING.md build log |
| Combined SELinux policy (system + stock vendor 202504) compiles | PASS (`sepolicy.compile`, tree `secilc`, same inputs as `init`) | UNKNOWN | boot-critical |
| Privileged-permission allowlist under `enforce` | PASS (`privapp.allowlist`) | UNKNOWN | boot-critical |
| Native dependencies of every ported library | PASS (`native.needed`) after one fix (`vendor.qti.diaghal-V1-ndk.so`); symbol level: all imports of the 12 ported libraries and of the 47 libraries inside the camera APK resolve (`check_native_symbols.py`) | UNKNOWN | |
| SELinux: what the ported app domains may do, against the stock policy | PASS for the IMS app (nothing stock grants on an object existing here is missing); camera app: 2 unused service lookups not carried over (`sepolicy_diff.py`) | UNKNOWN | sepolicy/README.md |
| SELinux: versioned attributes the stock vendor policy relies on | 1,413 of 1,539 populated; 126 empty (stock-only system types). WARNING: vendor rules on them are dead, as on any GSI; none is on the telephony or camera path | UNKNOWN | later hardening work |
| DSU as the first deployment route | **ready**: descriptor name, key acceptance on the unlocked phone, first-stage DSU support, mounts, sizes, free-space reserve and the no-wipe guard verified without installing | boot **UNKNOWN** | DSU_READINESS.md; not checkable beforehand: extent fragmentation of user data |
| Image fits `super` | PASS: 14.4 GiB to spare in the group | UNKNOWN | |
| Release signing keys | **FAIL / open**: test keys in use | n/a | must be replaced before daily use |

## Priority 1: cellular

| Feature | Static | Device | Notes |
|---|---|---|---|
| Radio HAL interface (AIDL V4, both slots) | PASS (vendor declarations accepted by this framework's matrix, `vintf.radio`) | UNKNOWN | |
| Physical SIM detection, registration, LTE/5G data | no device-specific work needed by analysis | **works** (sessions 2, 3): SIM loaded, LTE registration, mobile data validated; 5G not specifically exercised | worked on the owner's earlier GSI test (different system image, older vendor) |
| APN database | PASS: stock database has default/ims/mms/emergency APNs for 313390 | works for the SIM used (data and IMS networks came up) | |
| Carrier configuration | PASS for 313390 (overlay keys verified against the framework on build); other carriers WARNING | UNKNOWN | |
| SMS | nothing found statically; the RIL's ready signal (`VantageRilReady`) was found on the device | **works** in both directions on revision 4 (session 5: sent, and a reply delivered 12 s later). Before revision 4 the RIL held every incoming SMS (TELEPHONY_PORT.md 3.9) | |
| IMS service present and bindable | PASS: package, required libraries, MMTel overlay, allowlist, SELinux domain; linkage vs AOSP has 3 narrow gaps (SIM hot-swap cache reset, VICE call pull, one unused Motorola field) | **works**: bound | TELEPHONY_PORT.md section 2.1 |
| IMS network request (application-side IMS data network) | PASS (`ims.network_request`): `VantageImsNetwork` holds it. On stock the vendor CNE app does, with a permission it loses under this ROM | **works**: requested and connected | needed for WWAN/WLAN handover and application-side IMS traffic; the earlier GSI log shows IMS registering before any such request, so registration itself probably does not depend on it |
| IMS registration / VoLTE | cannot be established statically | **works**: registered, calls carried `call_type=LTE` | |
| Voice calls (signalling) | n/a | **works**: outgoing and incoming calls reached ACTIVE (sessions 2, 3) | earlier GSI test reached call state ACTIVE over IMS |
| Call audio: earpiece, microphone, speaker | cause of the earlier `audioserver` crash loop identified and absent; stock uses the same AOSP call-patch model; the call-audio bridge was compared with the stock client and three defects fixed (response interface shared by both SIM slots, no wait or re-registration, no audioserver state reporting); the combined policy lets it reach the RIL audio HAL both ways | **works** on revision 2 (session 2; both sides audible on earpiece and speaker, owner's observation) | TELEPHONY_PORT.md section 3. None of this is proof of audible audio; the fix itself is untested on the phone |
| Call audio: Bluetooth | n/a | UNKNOWN | |
| VoWiFi | **Not offered in the first release.** Two signature permissions of the vendor CNE app (`PACKET_KEEPALIVE_OFFLOAD`, `MAINLINE_NETWORK_STACK`) have no grant path without Motorola's platform key | not offered | TELEPHONY_PORT.md section 4.1.1; the owner ruled out the framework trust change for now |
| eSIM | not supported in this iteration (`ro.vendor.hw.esim=false`; LPA is GMS) | expected FAIL | |
| Dual SIM | per-slot HAL instances present | UNKNOWN | |

## Priority 2: Motorola camera

| Feature | Static | Device | Notes |
|---|---|---|---|
| App installable with original signature, required library, permissions, SELinux context | PASS on the vantage image (validate-camera 10 PASS / 0 FAIL / 3 WARNING) | **works**: installed, starts, opens the camera | |
| Java linkage against AOSP framework | PASS: no unresolved reference beyond the 6 it also has on stock | UNKNOWN | the app runs on bundled throwing stubs of Motorola's optional libraries; 24 call sites are not locally guarded (CAMERA_PORT.md section 3) |
| Preview and capture, main camera | n/a | preview seen, captures logged by the HAL (sessions 2, 3); picture quality not assessed | |
| Ultrawide / telephoto / front | n/a | 6 devices listed and the logical multi-camera opened (sessions 2 to 4; from revision 3 with the framework flag readable by the camera HAL only); per-lens result not reported yet | depends on how the HAL lists cameras to an unfiltered framework |
| HDR / night / portrait / macro / pro / high-res | 20 vendor processing libraries are loadable (vendor-public) | UNKNOWN | |
| Video mode and recording | n/a | revision 3, session 4: video mode opens and a 12 s recording was written to the end (HEVC, writer status 0): **logged as working**; whether it plays and looks right is the owner's to say | THIRD_BOOT_REPORT.md section 2 |
| OIS, zoom | n/a | UNKNOWN | |
| Slow motion / high frame rate | n/a | UNKNOWN | |
| Dolby Vision recording | dependencies traced: app feature flag for vantage present, vendor `video/dolby-vision` encoders declared, HAL vendor tag needs the device; no Motorola framework dependency (`video.dolby_vision_inputs`) | UNKNOWN | CAMERA_PORT.md section 4. The earlier "blocked" was a mix-up with the playback picture-mode service |
| Dolby Vision playback picture modes (Bright / Dark / Vivid notification) | not ported: `com.motorola.dolbyvisionservice` requires `moto-core_services` | expected absent | decoding is unaffected |
| AI colour tone, desktop camera, launch gestures | not ported | expected FAIL | |
| Features routed through `moto-core_services` / `moto-settings` | WARNING: libraries intentionally absent | UNKNOWN | CAMERA_PORT.md section 3 |

## Priority 3: other

| Feature | Static | Device | Notes |
|---|---|---|---|
| Wi-Fi, Bluetooth, GPS, NFC, sensors, fingerprint | standard AIDL HALs declared by the vendor; no device-specific work yet | UNKNOWN | fingerprint is under-display with vendor trusted apps; TrebleDroid has generic UDFPS handling only |
| Display refresh rate | stock uses Qualcomm display extensions in SurfaceFlinger that AOSP lacks | UNKNOWN | |
| Audio effects (Dolby) | Dolby `daxService` and Motorola audio apps not ported | expected absent | |
| Hardware video decode/encode | vendor Codec2 services present | UNKNOWN | |
| Qualcomm Tx power administration (`vendor.qti.data.txpwradmin`) | WARNING: Motorola-platform-signed vendor app, runs without its signature permissions under this ROM | UNKNOWN | effect on transmit-power management not analysed |
| Wi-Fi Display, Qualcomm telemetry | framework HALs `sigma_miracast`, `qccsyshal` not provided | expected absent | the vendor compatibility matrix lists them |

## After four sessions (2026-10-11)

The matrix was written before any boot. The sessions confirmed the foundation rows (boot with
the stock vendor, enforcing SELinux, image composition) and showed three classes of gaps that
no static check had caught: stock system-side properties the vendor reads (first boot), a
vendor HAL that changes its behaviour on a Qualcomm framework flag (second), and two places
where AOSP `android-16.0.0_r2` itself differs from what this vendor needs (third: the camcorder
profile file, a screenshot bug with HDR layers). FIRST_, SECOND_ and THIRD_BOOT_REPORT.md.

Revision 3 was booted in the fourth session (FOURTH_BOOT_REPORT.md): video mode, a video
recording, the GNSS assistance daemon and `ro.carrier` were seen working. That session also
gave the cause of the missing incoming SMS, a fourth class of gap: the stock system side
*sends* the vendor RIL a signal unasked (TELEPHONY_PORT.md 3.9). Fixed in revision 4.

Revision 4 was booted in the fifth session (FIFTH_BOOT_REPORT.md): an incoming SMS arrived.

## Open blockers

1. The remaining "UNKNOWN" rows: Bluetooth, GNSS, NFC, fingerprint, dual SIM; a screenshot of the
   video viewfinder (the fix is verified in the binary only).
2. VoWiFi: not offered. The complete fix is a `frameworks/base` change the owner has ruled out
   for now (TELEPHONY_PORT.md section 4.1.1).
3. Release keys: development keys are kept until the ROM is functional (owner's decision).
4. Not ported by design, measured: Qualcomm's telephony component factory does not link
   against AOSP (TELEPHONY_PORT.md section 2.2). Features that only exist there (smart DDS
   switching, Qualcomm 5G icon variants) are absent.
5. Later hardening: re-declare stock's public SELinux object types so that the 126 dead
   vendor rule sets become live again (sepolicy/README.md).
