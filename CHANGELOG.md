# Changelog

## 2026-10-11

### Fifth DSU session (image revision 4)
- **Revision 4 booted; an incoming SMS arrived** twelve seconds after the message it answers
  (`UNSOL_INCOMING_IMS_SMS`, acknowledged, delivered), with nothing done by hand. Calls, SMS
  sending, six cameras, video mode and a video recording as before; no native crash. Device
  report 28 PASS, 0 FAIL. Owner: "It all works". FIFTH_BOOT_REPORT.md.
- **Report check corrected:** `sms.ril_ready` reported a failure because the sender's boot-time
  log lines had rotated out of the log; it now judges by a delivered SMS.

### Fourth DSU session (image revision 3) and the incoming-SMS cause
- **Revision 3 booted.** Logged as working on the phone: everything of the earlier sessions,
  plus video mode in Motorola Camera, a 12 s video recording written to the end (HEVC, writer
  status 0), six cameras with the framework flag readable by the camera HAL only, the GNSS
  assistance daemon staying up, `ro.carrier=retin`. Device report 26 PASS, 0 FAIL.
  FOURTH_BOOT_REPORT.md.
- **Incoming SMS, cause proven on the phone:** the Qualcomm RIL runs with "power-on
  optimisation" (on by default in its own property database) and keeps incoming SMS in a
  buffer until it receives the OEM hook request `QCRIL_EVT_HOOK_SET_ATEL_UI_STATUS`. On stock
  Qualcomm's telephony service (`QtiTelephony.apk`) sends it; AOSP has no sender. Sending the
  same 17 bytes by hand on the running guest released a held SMS within 10 ms. The earlier
  guess (the sender using chat messages) was wrong.
- **Fix:** new source-built system app `VantageRilReady` (`telephony/ril-ready/`): sends the
  request per SIM slot under the stock conditions, again after a RIL or modem restart, and
  logs the RIL's answer. No SELinux or permission change.
- **The app tried on the running guest** (the build that is in revision 4): both slots
  signalled, the RIL answered both with error 0; after killing the RIL daemon it signalled the
  new instance, which accepted too. Not yet seen: an SMS arriving on a fresh boot of
  revision 4.
- **Image revision 4:** 2,556,506,112 bytes, SHA-256 `efe1b630...9dd9b3e`,
  `out/vantage_td-20261011-r4/`. `validate-image.sh`: no FAIL. Not booted.
- **`.qtidataservices` crash located:** the vendor CNE app unregisters a network callback that
  is not registered (boot, RIL restart). It restarts; no effect seen; not fixed.
- **Tooling:** the device report has `sms.ril_ready` (FAIL on images without the sender); the
  composition check has `built.ril_ready`.

## 2026-10-10

### Third DSU session and image revision 3
- **Session (revision 2 with the vendor-framework flag set for everyone):** registration, data,
  IMS, SMS sending and two calls as before; the camera HAL lists all 6 devices. New failures:
  Motorola Camera stops when switched to video (owner's report), the GNSS XTRA daemon is down.
  THIRD_BOOT_REPORT.md.
- **Video mode, cause proven on the guest:** AOSP's libmedia read `media_profiles_V1_0.xml`
  (2 cameras), the stock libmedia reads the file named by the vendor's media variant
  (`media_profiles_canoe_sku3.xml`, 3 cameras); the app gets no profile for its camera and hits
  a `NullPointerException`. With zygote made to read the stock file, video mode opens. Fix:
  `init/init.vantage.media.rc` copies `ro.media.xml_variant.codecs` to
  `ro.media.xml_variant.profiles`. Recording itself is untested.
- **surfaceflinger abort on a screenshot of the video viewfinder:** `android-16.0.0_r2` closes
  the LUT descriptor of an HDR layer twice in the screenshot code; this phone's display HAL
  supplies such LUTs. Fixed upstream in `_r3`; the same one-expression change is now
  `patches/frameworks/native/0001-...patch`.
- **Vendor-framework flag limited to the camera HAL:** `ro.vendor.qti.va_aosp.support` keeps the
  stock value 1 but has its own SELinux type that only `hal_camera_server` and `shell` can
  read. The audio and Bluetooth HALs, CNE, the IMS daemons, `qcc-vendor` and the XTRA daemon
  no longer see it, as on the first two boots.
- **Known, not fixed:** the idle camera process is killed once about 30 s after boot by a
  `PACKAGE_CHANGED` broadcast of the TrebleDroid app with an empty component list.
- **Tooling:** `check_source_patches.py` (each patch applied in the tree and visible in the
  image's binaries), `sepolicy_diff.py --deny`, two composition checks
  (`built.media_profiles`, `built.vendor_framework_flag`), and the device report recognises the
  failures of this session by their log lines.

### Root diagnosis on the guest: camera cause found
- **Owner's observations:** calls audible both ways on earpiece and speaker; outgoing SMS
  arrived; an SMS sent to this phone did not arrive.
- **Camera cause (proven on the device):** the Qualcomm camera HAL loads a reduced "GSI" camera
  configuration unless `ro.vendor.qti.va_aosp.support=1`. Setting it and restarting the camera
  provider brought all 6 devices back and Motorola Camera opened the logical multi-camera it
  uses on stock. Five other candidates were tested and ruled out (build type and tags,
  `camera.mot.*`, SELinux, aux package lists, secure-hardware value). The flag had been left out
  of revision 2 on purpose; that was wrong. Now in `properties.mk`. What it changes in the
  vendor's IMS, CNE, Bluetooth and GNSS components is not known yet.
- **`ro.carrier`:** stays `unknown` because AOSP's init does not export it from
  `androidboot.carrier` as Motorola's does. New `patches/system/core/0001-...patch` (one table
  entry in init).
- **Incoming SMS:** no trace of a message reaching the phone in the logs. RCS routing of the
  sender is a possible explanation, not verified.
- For validation without a new install the flag was put into the guest's `/data/local.prop`.
  No new image was built; revision 3 follows the regression test with the flag active from boot.
- SECOND_BOOT_REPORT.md section 5 has the experiments and the evidence.

### Second DSU boot (image revision 2)
- **Logged as working on the phone:** LTE registration, mobile data (validated), IMS registered,
  three SMS sent over IMS (status sent), an outgoing and an incoming call, the voice session in
  the vendor audio HAL with handset and speaker (opened, started, switched and stopped with
  status 0; the RIL's `vsid`/`call_state` parameters arrived through the new vendor extension),
  Motorola Camera start and preview, WebView. Device report: 21 PASS, 0 FAIL.
  SECOND_BOOT_REPORT.md. Whether the calls were audible is the owner's observation to add.
- **Still failing:** Motorola Camera shows "Multiple cameras aren't working" (70400001). The
  vendor camera HAL exposes 2 cameras here and 6 on stock; cause not established (candidates and
  evidence in the report). TrebleDroid's camera switch was checked and is not the cause.
- The call-audio bridge did not block on this boot (it did on the first, without network).
- Found: `ro.boot.secure_hardware` and `ro.carrier` come from Motorola's `init`/system scripts,
  are read by the vendor (camera settings, RIL, thermal, ...) and are missing here.
- `device-session.sh` now streams the log from the first moment adb answers and, started on
  stock with a guest installed, waits for the guest: start-up-only messages (camera provider,
  bridge) were missing from both recordings.

### First DSU boot, and image revision 2
- **The ROM booted on the phone** on the first attempt (owner's test, 15:29): launcher reached,
  SELinux enforcing, SIM read, stock IMS service bound, image composition as predicted.
  FIRST_BOOT_REPORT.md has the evidence, the failures and their causes.
- **Failures and causes:** no service (the guest allowed the modem only 2G/3G because stock's
  `ro.telephony.default_network` lives in partitions this system does not mount); Motorola Camera
  refused to start (device name `tdgsi` instead of `vantage`); no WebView (TrebleDroid's provider
  list defaults to Google WebView); the call-audio bridge never completed its registration
  (cause unknown); and, found by reading the audio path, call parameters could not reach the
  AIDL audio HAL without stock's vendor-extension library.
- **Image revision 2** (`af010184...`, 2,556,428,288 bytes, `out/vantage_td-20261010-r2/`):
  27 stock properties with their readers (`properties.mk`), stock device identity, WebView
  overlay, stock `libaudiohalvendorextn.so` hosted by AOSP's unmodified parameter parser
  service with the reference device's policy, bridge patch revision 2 (step logging). Selected
  from a comparison of all stock system-side properties with the running guest (252 missing or
  different; 31 read by the stock vendor side).
- **Not carried on purpose:** the stock security patch level, `ro.vendor.qti.va_aosp.support`,
  build type/tags, Bluetooth stack selection, audio tuning without a known reader
  (FIRST_BOOT_REPORT.md section 4).
- Tooling: `check_image_composition.py` checks properties, identity, the audio extension and the
  WebView default in the image (18 PASS, 0 FAIL, 1 WARNING); the device report recognises each
  first-boot failure by its own log line; `phhsu_daemon` (TrebleDroid's permissive domain) is
  now reported as a warning with its name instead of a generic failure.
- Static results only for revision 2. Nothing of it has run on the phone.

### First install attempt by the owner: "Install failed" (nothing installed)
- Cause, from the phone's log: `dsu_install_failed: java.io.FileNotFoundException:
  /storage/emulated/0/Download/system_raw.gz: open failed: ENOENT`, three times. The archive
  was not on the phone. Correction to the first reading of this ("push skipped"): the owner had
  run the push, in Git Bash, and it failed with `remote secure_mkdirs() failed` because the
  shell rewrote `/storage/...` into `C:/Program Files/Git/storage/...`. The documented commands
  lacked `MSYS_NO_PATHCONV=1`; that was a gap in the instructions, now closed in TESTING.md and
  in the commands `dsu-preflight.sh` prints. `gsi_tool status` is `normal`,
  no DSU key directory was created, free space unchanged. Not an image or compatibility fault.
- `dsu-preflight.sh` no longer prints the install command until the archive is on the phone
  and its SHA-256 matches (exit status 2 until then), and it shows the installer's last error
  from the event log. TESTING.md: push step spelled out, failure table extended.

### Final checks before the first DSU boot (no rebuild, image unchanged)
- **Security patch level, corrected.** DSU_READINESS.md said nothing compares the image's
  level (2025-06-05) with stock's (2026-06-01). That was wrong. The stock first-stage `init`
  has AOSP's `IsStandaloneImageRollback`: it compares the two AVB properties, reports the
  image as a rollback, and continues only if `androidboot.verifiedbootstate` is `orange`;
  locked, the guest's `/system` is refused. Established from the disassembly of the stock
  binary (`check_stock_init.py`, report `reports/vantage/stock-init.json`) and from the phone
  (`orange`; vbmeta digest equal to the stock package's, so the "vbmeta disabled" shortcut is
  not what happens). No other component compares the levels. The image's level was not changed.
- **Image composition verified from the image file** (`check_image_composition.py`, report
  `reports/vantage/image-composition.md`, 14 PASS / 0 FAIL / 1 WARNING): `/system_ext` and
  `/product` are inside the image; `skip_mount.cfg` removes the stock fstab entries for both
  and the stock first-stage `init` is shown to read it; all 31 stock files are byte-identical,
  the IMS app differs from stock only in its signature; source-built apps, the three overlays
  (every value), both permission allowlists and the SELinux entries are the intended ones. The
  warning is TrebleDroid's runtime-selectable IMS overlays (known, TELEPHONY_PORT.md 1.1).
- **Artifact and command.** `out/vantage_td-20261010/system.img` and the content of
  `system_raw.gz` re-hashed on the Windows side: `c27ba0e9...`, 2,556,280,832 bytes. The install
  command now passes `--ez KEY_ONE_SHOT true` (also the stock installer's default, read from its
  code). New `dsu-preflight.sh`: read-only check of the local archive and the phone's state
  that prints the commands for exactly this build and runs none.
- Device report: new `boot.partition_composition` (from `/proc/mounts`), `boot.overlays_active`,
  `boot.spl_rollback` (kernel log, informational); the recorder now saves both.
- `validate-image.sh` runs the two new static checks. Nothing has run on the phone.

### DSU readiness review and call-audio bridge fix
- **Image to test:** 2,556,280,832 bytes, SHA-256 `c27ba0e97d4b5e93bc6e85235fede03cbf3662ea477f79641d2bd345d2fd0154`
  (`out/vantage_td-20261010/`, replacing the earlier export). Validators: preflight 27 PASS / 0 FAIL / 3 WARNING, telephony 14 PASS / 0 FAIL / 2 WARNING / 7 UNKNOWN, camera 10 PASS / 0 FAIL / 3 WARNING / 6 UNKNOWN.
  Nothing has run on the phone.
- **DSU_READINESS.md** (new): the image's AVB descriptor is found under the name first-stage
  init looks for; the unknown signing key is accepted on the unlocked phone; stock first-stage
  init, installer and gsid carry the DSU logic; the guest mounts this image's `system_ext` and
  `product`; free space covers gsid's reserve (size of `super`); this image's init refuses data
  wipe requests while running as DSU. Assessment: ready for one controlled DSU boot. Not
  checkable beforehand: extent fragmentation, and the boot itself.
- **Call-audio bridge (TrebleDroid QcRilAm) fixed** after comparing it with the stock client:
  it shared one response interface between both SIM slots (responses for slot 1 went to the
  RIL of slot 2), never waited for or re-registered with the RIL, and never reported
  audioserver restarts. Kept as `patches/packages/apps/QcRilAm/0001-...patch`, applied by
  `sync-to-tree.sh`. New checks `audio.bridge_recovery`, `audio.bridge_single_owner`. The
  stock client was evaluated as an alternative (links cleanly) and not chosen; reasons in
  TELEPHONY_PORT.md section 3.
- **Automated diagnostics:** `device-session.sh` records one session read-only (boot log,
  full snapshots, live log; saves the audio routing when a call becomes active and the camera
  state when Motorola Camera is in front) and `analyze_device_evidence.py` turns a capture into
  `report.md` with PASS / FAIL / WARNING / UNKNOWN per area. Tried against the stock phone
  (dry run) and against the old GSI crash log, where it reports the audioserver abort.
- TESTING.md: new section "First test" (install, diagnostics first, five actions done once,
  way back, what to do if it fails).

### After the owner's review (decisions of 2026-10-10)
- Image at that point (superseded by the one above): 2,556,272,640 bytes, SHA-256
  `c353881ad3ec482aef7b02d19028f8d423d4c14aa8be085934326469a84da56b`. Validators: preflight 27 PASS / 0 FAIL / 3 WARNING, telephony 12 PASS / 0 FAIL / 2 WARNING / 7 UNKNOWN, camera 10 PASS / 0 FAIL / 3 WARNING / 6 UNKNOWN.
  Nothing has run on the phone.
- **Wi-Fi calling is not offered in the first release.** The vendor CNE app was analysed
  permission by permission: `PACKET_KEEPALIVE_OFFLOAD` and `MAINLINE_NETWORK_STACK` have no
  grant path without Motorola's platform key, and the owner ruled out the framework trust
  change. `carrier_wfc_ims_available_bool` is now `false` (TELEPHONY_PORT.md 4.1.1).
- **Call audio.** Stock's audio policy manager is the same AOSP implementation with six
  Motorola additions; it routes calls with the same telephony-source and hardware-bridge
  model. TrebleDroid's bridge app runs as `system_app` (its dedicated SELinux domain never
  applies because the app uses the system UID); the compiled combined policy was queried and
  lets that domain reach the RIL audio HAL in both directions. The bridge does not
  re-register after a RIL restart (stock's does); noted, not changed.
- **Prepared, not run:** a read-only in-call capture for stock
  (`WAIT_CALL=1 ... collect-device-evidence.sh incall`). It waits for a call the owner places.
- **SELinux beyond "it compiles".** New `sepolicy_diff.py` expands this ROM's compiled policy
  and the stock precompiled policy and compares what the ported app domains may do: nothing
  stock grants the IMS app on an object existing here is missing. New check
  `sepolicy.unmapped`: 126 of the 1,539 versioned attributes the vendor policy uses are empty
  here (stock-only system types); none on the telephony or camera path.
- **Native code at symbol level.** New `check_native_symbols.py`: every imported symbol of
  the 12 ported libraries and of the 47 libraries inside the camera APK resolves on this
  image. Negative test: stock `libandroid_runtime.so` fails with 5 Motorola symbols.
- **Camera dependencies traced.** The 40 framework classes (34 `com.motorola.*`) behind
  `moto-core_services` map to cover-display support, an exit performance hint, an HDR-layer
  hint for the viewfinder, a private window flag, Motorola settings keys and the stylus; no
  capture mode goes through them. **Correction:** Dolby Vision recording was listed as
  blocked by a Motorola service. That service only handles playback picture modes; recording
  depends on the app's feature flag (present for vantage), a HAL vendor tag and the vendor's
  `video/dolby-vision` encoders (declared). It is now UNKNOWN, not blocked.
- **DSU checked for this phone without installing:** first-stage DSU support, `/metadata`
  mount, installer, AVB behaviour on an unlocked device, encrypted user data, and the
  free-space rule (about 39.4 GiB needed, 67 GiB free). Whether the image boots is still
  unknown.
- Tooling: `build.sh` refuses to start without zram swap (the VM loses it on restart and the
  build then thrashes for hours; this happened once today). `validate-image.sh` now runs the
  symbol check and the policy comparison too.

### First validated `vantage_td` image
- `vantage_td-bp2a-userdebug` builds. Image at that point (with the IMS network requester,
  superseded by the one above): 2,556,272,640 bytes, SHA-256
  `f28249c20bf4fcf778f98ef89460a54f96a224c5b0a5b5d9cb4b5e9ed6ea7f0b`.
- Validators on that image: preflight 27 PASS / 0 FAIL / 2 WARNING, telephony 12 PASS /
  0 FAIL / 2 WARNING / 7 UNKNOWN, camera 9 PASS / 0 FAIL / 3 WARNING / 6 UNKNOWN. The UNKNOWN
  entries are the hardware tests.

### IMS network request (found on the stock phone before any flash)
- On stock, an IMS network request is held by the vendor CNE app (`dumpsys connectivity`:
  `RequestorPkg: com.qualcomm.qti.cne`). The capability is restricted, and CneApp only holds
  `CONNECTIVITY_USE_RESTRICTED_NETWORKS` through Motorola's platform key. Under this ROM its
  request is refused (it catches the `SecurityException`) and nobody else asks, so telephony
  would have no IMS data network of its own.
- Added `VantageImsNetwork` (`telephony/ims-network/`): a small platform-signed system app,
  built from source, that holds the same request as stock for every active subscription.
  New check `ims.network_request`.
- What this does and does not establish: the earlier GSI log shows the modem registering IMS
  two seconds before any IMS request existed, so registration itself probably does not need
  it. Handover between WWAN and WLAN and application-side IMS traffic do. Whether a voice
  call works without it is unknown. A first draft of the notes claimed "no VoLTE without it";
  the log order contradicted that and the claim was removed before it was committed.
- `IWlanService` measured: its code needs no signature permission. Wi-Fi calling moves from
  "expected to fail" to "unknown, at risk" (CNE's remaining functions). At this point it was
  left available but off by default; the section above supersedes that (not offered).
- TrebleDroid's own IMS overlays analysed: its Treble app enables the Qualcomm one with the
  same value as this ROM's overlay; its floss IMS app is not in the image.

### Fixes found by validating the first build
- **Missing native dependency.** `libdiag_system.so` (needed by the IMS video libraries)
  requires `vendor.qti.diaghal-V1-ndk.so`. Stock ships it in `/system/lib64`, AOSP does not,
  and the resolver had treated every stock `/system` library as present in AOSP. Added
  `gen_target_libs.py` and `target-system-libs.txt` (the 759 libraries the unmodified image
  provides; `/system/lib64` verified identical to the preserved baseline image), and the
  resolver now diffs against it. Exactly one file was added to the manifest.
- **Validators on the GSI layout.** `product` and `system_ext` live inside `system` in a GSI
  output tree, so APKs were attributed to `/system`; the camera validator then looked for the
  privileged and hidden-API allowlists in the wrong partition (false FAIL). Files are now
  attributed to the most specific mapped partition (`Platform.owner`/`apks`).

### Call audio: root cause of the earlier GSI crash
- The abort `connectAudioSourceToSink: a swOutput shall always be associated` came from
  TrebleDroid's `frameworks/av` branch `android-16.0.0_r1-td`, which had lost one statement
  (`sourceDesc->setSwOutput(...)` for internal sources) in `createAudioPatchInternal`.
  Evidence: the function addresses in the tombstone match the library built here except for
  a uniform 0x2c shift behind that function, and the two branches differ in exactly that
  line. The `android-16.0.0_r2-td` baseline used here has it.
- Correction: TELEPHONY_PORT.md previously attributed the abort to "newer QPR-based code".
  That was a guess and it was wrong; AOSP r1 to r4 and both QPR branches all contain the
  statement.
- New check `audio.call_rx_swoutput` (`validate-telephony.py --aosp-tree`), with a negative
  test against the r1-td file.

### Tooling
- `validate-image.sh`: one command for the three validators plus the image file itself
  (`e2fsck`, and every pinned stock file read back out of `system.img` and hashed).
- `collect-device-evidence.sh`: read-only capture of device state for the acceptance test;
  run once against the stock phone as a reference (`work/device-evidence/`, not in git).
- The stock phone's live service bindings were read as a cross-check of the overlays:
  cellular data/network service in `com.android.phone`, WLAN and qualified-networks service
  in `vendor.qti.iwlan`, `ImsService` in `org.codeaurora.ims`.

### Measured
- `qti-telephony-common.jar` (Qualcomm's telephony component factory) against the built
  framework: 8 classes, 25 methods and 4 fields it uses exist on stock but not in AOSP. It
  cannot be transplanted; the decision not to port it stands on a measurement now.

## 2026-10-09

### Environment and baseline
- Created the dedicated WSL2 build distro `moto-aosp` on the project drive; `.wslconfig` with
  24 GB RAM / 40 GB swap; `wsl-zram.sh` after Soong's analysis (about 38 GB) thrashed on disk swap.
- Synced AOSP `android-16.0.0_r2` with TrebleDroid `treble_manifest` `android-16.0` (974
  projects); pinned every revision in `manifests/pinned-android-16.0.0_r2-td.xml`; started
  branch `vantage-baseline` in all projects.
- `build.sh`: fixed `set -u` incompatibility with `envsetup.sh`; removed ccache (Soong's
  sandbox makes paths outside `out/` read-only).
- Baseline build (`treble_arm64_bvN-bp2a-userdebug`) started; not finished at the time of
  this entry.

### Stock firmware analysis (W2WVS36.55-95-5-1)
- Verified all 44 package images against `flashfile.xml`; recorded SHA-256.
- Wrote a pure-Python sparse + dynamic-partition extractor; dumped and extracted all seven
  logical partitions (EROFS), four boot images and 47 APEX payloads.
- Built the inventory (12,523 files, 106 signing certificates, 143 HALs, 410 init services,
  150 overlays) and the per-area reports.
- Established from the device (read-only adb): stock build, unlocked bootloader, Virtual A/B,
  SIM operator 313390.

### Integration layer (`vendor/motorola/vantage`, `device/motorola/vantage`)
- Product `vantage_td` on top of TrebleDroid `treble_arm64_bvN`.
- Telephony: stock Qualcomm IMS service with its five shared libraries and eleven
  video-telephony natives; stock RIL audio bridge (`QtiTelephonyService`); overlays for the
  MMTel service binding, IWLAN bindings and eUICC values; stock APN database; carrier-config
  overlay for 313390; privileged-permission allowlist.
- Camera: Motorola Camera 10.0.56.61 and `MotoSignatureApp` with original signatures,
  `com.motorola.motosignature` library, feature and hidden-API allowlist files, privileged
  allowlist.
- SELinux: public types `vendor_qtelephony`, `moto_camera_app` and four shared attributes so
  the stock 202504 vendor rules bind; private rules and `seapp_contexts` mirrored from stock.
- No AOSP or TrebleDroid project has been modified.

### Tooling
- Dependency-free parsers (AXML, APK signing block, ELF, DEX incl. bytecode reference scan,
  VINTF, init.rc, permission XML, CIL).
- `check_java_linkage.py`, `resolve_components.py`, `setup_makefiles.py`,
  `extract-firmware.sh`, `sync-to-tree.sh`, `preflight.py`, `validate-telephony.py`,
  `validate-camera.py`, `sepolicy_slice.py`, `resdump.py`, `dump_overlays.py`.
- Validators self-tested against stock; two false positives fixed.

### Corrections after the baseline build
- Removed the stock `QtiTelephonyService` from the port. TrebleDroid's `QcRilAm` already
  implements the AIDL `IQcRilAudio` interface, and the owner's earlier GSI log shows its
  `call_state`/`vsid` parameters reaching the audio HAL. The earlier claim that it was
  HIDL-only was wrong.
- Integration layer is inherited before the TrebleDroid product so the stock APN database wins
  the `/product/etc/apns-conf.xml` destination.
- `dex_import` modules no longer carry a `dex_preopt` block (rejected by Soong).
- Validators: byte-identity check for verbatim-installed files; HAL clients are recognised by
  the generated proxy class instead of a string match; modified-UTF-8 fix in the DEX reader.

### Measured after the baseline build
- Baseline `treble_arm64_bvN` image built (2 h 30 min); its policy compiles together with the
  stock vendor policy; radio HAL versions are within the framework matrix.
- Java linkage against the AOSP 16 framework: IMS stack resolves except three narrow gaps;
  Motorola Camera resolves completely but runs on bundled throwing stubs of Motorola's
  optional libraries (24 of 40 call sites not locally guarded).

### Decisions
- Keep AOSP's telephony core; do not inject Qualcomm's `QtiTelephonyComponentFactory`.
- Do not install Motorola's optional `moto-core_services`/`moto-settings`/`moto-active-stylus`
  libraries: they need classes that exist only in Motorola's `framework.jar`.
- No signature bypasses; platform-dependent stock apps are re-signed by the build.
