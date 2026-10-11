# Telephony port

Scope: SIM/eSIM, registration, LTE/5G data, APN and carrier configuration, SMS, voice, IMS
(VoLTE, VoWiFi), call audio, dual SIM. Evidence is static unless a line says otherwise;
**no telephony function has been tested on the device with this ROM yet.**

## 1. Design

```
AOSP telephony framework (unmodified: RIL.java, ServiceStateTracker, data stack, ImsResolver)
   |  android.hardware.radio.* AIDL V4 (slot1/slot2)             standard Treble interface
   |  ImsService binding -> org.codeaurora.ims (stock, re-signed)   config_ims_mmtel_package overlay
   |        '-- vendor.qti.hardware.radio.ims.IImsRadio/imsradio0,1 (V20)
   |  IMS NetworkRequest per subscription <- VantageImsNetwork (stock: the vendor CNE app)
   |  IQcRilAudio callbacks <- me.phh.qcrilam (TrebleDroid's QcRilAm, already in the baseline)
   v
stock vendor: qcrilNrd, imsdaemon, ims_rtp_daemon, cnd, IWlanService, audio HAL -> modem
```

What is taken from stock, and why each piece is needed:

| Piece | Why it is required | How it is integrated |
|---|---|---|
| `org.codeaurora.ims` | The vendor implements IMS only through Qualcomm's `IImsRadio`; it does not register AOSP's `android.hardware.radio.ims`. AOSP's telephony therefore has no IMS backend of its own (RILJ on a GSI: "service IMS is not available"). | `android_app_import`, re-signed with the ROM platform key, privileged, system_ext |
| `ims-ext-common`, `qti-telephony-utils`, `qti-telephony-hidl-wrapper`, `moto-telephony`, `moto-ims-ext` | `<uses-library required=true>` of `ims.apk`; a missing one makes PackageManager refuse the app. | `dex_import` + the stock permission XML at the stock paths |
| IMS video natives (11 libraries) | `libimsmedia_jni.so`/`libimscamera_jni.so` are loaded by the IMS app (video calling) and pull the rest in through DT_NEEDED and `dlopen("lib-imsvt.so")`. | `cc_prebuilt_library_shared` + the two JNI symlinks in the app directory |
| `config_ims_mmtel_package` | Stock compiles `org.codeaurora.ims` into its own `TeleService.apk`; AOSP's value is empty, so `ImsResolver` would bind nothing. | RRO `VantageTelephonyOverlay` -> `com.android.phone` |
| IMS network request | AOSP telephony creates its IMS data network (the application-processor side of the IMS PDN) only while an app holds a `NetworkRequest` for the restricted capability `IMS`. On stock that app is the vendor's `com.qualcomm.qti.cne` (read from `dumpsys connectivity` on the stock phone). Under this ROM it lacks `CONNECTIVITY_USE_RESTRICTED_NETWORKS`, which it only holds through Motorola's platform key. The earlier GSI log shows the modem registering IMS two seconds *before* any such request existed, so registration itself does not appear to need it; WWAN/WLAN handover and application-side IMS traffic do, and whether a voice call works without it is unknown (the one successful call had it, via TrebleDroid's manual option). | `VantageImsNetwork`: a small platform-signed system app built from source (`telephony/ims-network/`, with the evidence in its README) that holds the same request as stock for every active subscription |
| IWLAN service bindings, eUICC capabilities | Stock sets them in `/product` overlays, which are not mounted. | RRO `VantageFrameworkTelephonyOverlay` -> `android` |
| APN database | AOSP's list lacks the carrier's IMS/MMS/emergency APNs (the earlier GSI run had to inject a "PHH IMS" APN). | stock `/product/etc/apns-conf.xml` |
| Carrier configuration | Stock gets `carrier_volte_available_bool` etc. from Google Carrier Settings (GMS). | RRO `VantageCarrierConfigOverlay` -> `com.android.carrierconfig` |
| SELinux domain `vendor_qtelephony` | The stock vendor policy grants the IMS RTP HAL, vendor radio/IMS properties etc. to `vendor_qtelephony_202504`. Without a system-side type mapped to it the IMS app would run as `platform_app` and be denied `find` on `vendor_hal_telephony_service2`. | `sepolicy/public` + `sepolicy/private`, mirrored `seapp_contexts` |

What is deliberately **not** taken:

| Stock piece | Reason |
|---|---|
| `QtiTelephonyComponentFactory` injection (16 jars replacing RIL, ServiceStateTracker, GsmCdmaPhone, the data stack, ...) | Subclasses AOSP-internal classes of Qualcomm's own `telephony-common`; the vendor already speaks the standard radio AIDL V4, so AOSP's stack can drive it. Replacing a working upstream subsystem needs a demonstrated incompatibility first. Measured (section 2.2): it does not link against AOSP's `telephony-common`, so it could not be transplanted even if wanted. |
| `com.qualcomm.qti.telephonyservice` (`QtiTelephonyService`) | Stock's receiver for the RIL audio HAL `vendor.qti.hardware.radio.am.IQcRilAudio`. TrebleDroid's `QcRilAm` implements the same AIDL interface (`setRequestInterface` on `IQcRilAudio/slotN`), and the owner's earlier GSI log shows its `setParameters("call_state=2;call_type=LTE;crs_call=false;vsid=297816064")` reaching the audio HAL on this phone. An earlier revision of this port added the stock app on the wrong assumption that QcRilAm was HIDL-only; it was removed again, since two clients would compete for one callback slot. |
| `com.qti.phone` (ExtTelephonyService), `qcrilmsgtunnel`, `datastatusnotification` | Extra Qualcomm features (5G icon variants, smart DDS, OEM hook tunnel). Not on the path for registration, data, SMS, calls. Candidate for a later iteration if a concrete gap shows up. |
| `ImsRcsService`, `uceShimService`, `rcsConfigService` | RCS/presence. Out of scope until basic IMS is confirmed. |
| Motorola `motoexttelephony` / `moto_ext_telephony.registry` services | Live in Motorola's `services.jar`/`TeleService`. `MotoExtTelephonyManager` (in `moto-telephony.jar`) null-checks the binder and catches `RemoteException`/`NullPointerException` in every method the IMS app calls (`listen`, `getAndResetInTestEmergencyCall`, `get/setVoiceDomainSetting`, `vendorInvokeOemRilRequestRawSync`), so their absence degrades to defaults. Verified in the disassembly. |
| Google Carrier Settings, Motorola CarrierConfig apps | GMS / Motorola-signed; replaced by the two overlays above. |

### 1.1 Interaction with TrebleDroid's own IMS handling

TrebleDroid ships six runtime-enabled overlays for `config_ims_mmtel_package` and its Treble app
(`Ims.startup`, read from the disassembly of the APK in this image) enables at most one at boot:
the "floss" one if the package `me.phh.ims` is installed, otherwise for a Qualcomm vendor (it
looks up `vendor.qti.hardware.radio.ims.IImsRadio/...`) the one whose value is
`org.codeaurora.ims`. `me.phh.ims` is not in this image, so TrebleDroid's choice and this
ROM's static overlay agree.

For the tester this means, in *Settings > Phh Treble Settings > IMS features*:

- do **not** install "PHH IMS" / the floss IMS APK: a runtime-enabled overlay can take
  precedence over a static one, and the Treble app would then bind `me.phh.ims` instead of
  Qualcomm's service;
- "Request IMS network" and "Create IMS APN" are not needed (the request is held by
  `VantageImsNetwork`, the IMS APN comes from the stock APN database). Leave them off so the
  test shows what the ROM does by itself.

## 2. Evidence per requirement

| Requirement | Static evidence | Status |
|---|---|---|
| Radio HAL compatibility | Vendor registers `android.hardware.radio.{config,data,messaging,modem,network,sim,voice}` V4, AIDL, `slot1`/`slot2`. Android 16's framework matrix level 202504 accepts them (`preflight.py`: `vintf.radio`, run on the vantage image). | PASS statically; UNKNOWN on hardware |
| SIM detection, registration, data, SMS over standard RIL | Same interfaces a TrebleDroid GSI uses. The owner's earlier GSI run on this device (older vendor build) shows SIM loaded, LTE registered on 310260, default data call up (`rmnet_data2`), IMS PDN up. | Observed on a different system image; UNKNOWN for this ROM |
| IMS service binding | Overlay value -> package present, declares `android.telephony.ims.ImsService` guarded by `BIND_IMS_SERVICE` (`preflight.py`: `telephony.ims_binding`, run on the vantage image). | PASS statically; binding itself UNKNOWN on hardware |
| IMS app can start | Required libraries resolve. Java linkage against the AOSP framework built here: all references resolve except three (section 2.1). On the vantage image `preflight.py` reports the privileged-permission allowlist complete, the app in domain `vendor_qtelephony`, `vendor_qtelephony_202504` populated (23 vendor rules bind to it) and the combined policy compiling. | PASS statically with 3 documented linkage gaps; UNKNOWN on hardware |
| Telephony service bindings | Running stock phone (`dumpsys activity services`, 2026-10-10): cellular data and network service in `com.android.phone` (AOSP's own), WLAN data / network / qualified-networks service in `vendor.qti.iwlan`, `ImsService` in `org.codeaurora.ims`. This ROM configures the same bindings; nothing Qualcomm-specific replaces the cellular services on stock either. | Same configuration as stock; UNKNOWN on hardware |
| IMS network request | `validate-telephony.py`: `ims.network_request` (requester installed, platform-signed, persistent, requests the restricted-network permission). | PASS statically; UNKNOWN on hardware |
| Native code of the IMS app | `check_native_symbols.py`: all 12 ported libraries resolve every imported symbol inside their DT_NEEDED closure on this image (1,276 imports). The checker was shown to fail on stock libraries that do need Motorola's framework (`libandroid_runtime.so`: 5 symbols). | PASS statically |
| JNI of the IMS app | The app declares 42 native methods (`ImsMedia` 29, `ImsCamera` 13) and loads `imsmedia_jni` / `imscamera_jni`. Both libraries export `JNI_OnLoad` and contain every one of those method names in their registration tables. | PASS statically |
| SELinux for the IMS app | `sepolicy_diff.py`, compiled combined policy against the stock precompiled policy: of the 8,585 permissions stock gives `vendor_qtelephony`, 869 are missing here, and every one of them targets a type this ROM does not define or a label nothing here carries (stock-only apps and services). None concerns an object that exists in this ROM. | PASS statically |
| IMS registration, VoLTE call | Needs modem, network and carrier provisioning. | UNKNOWN (hardware + carrier) |
| VoWiFi | Analysed permission by permission in section 4.1.1: no clean substitute for two of the vendor CNE app's signature permissions. | **Not offered in the first release** |
| eSIM | `ro.vendor.hw.esim=false` on this unit although the product overlay declares slot 1 non-removable; LPA is Google's `EuiccGoogle` (GMS). No AOSP LPA is added. | Not supported in this iteration |
| Dual SIM | `persist.radio.multisim.config=dsds` comes from the vendor; AOSP handles DSDS natively. `IImsRadio` and `IQcRilAudio` exist per slot. | UNKNOWN (hardware) |

### 2.1 Java linkage against the AOSP 16 framework (measured)

`check_java_linkage.py` against the baseline build (45 boot jars, 60,309 classes) plus the ported
libraries; report `reports/linkage-aosp-baseline.json`:

| Subject | Unresolved | Where it is used | Consequence |
|---|---|---|---|
| `ims.apk` | `ImsConfigImpl.resetProvisionedCacheValue()` (a Motorola addition to `ImsConfigImplBase`) | `ImsConfigImplOem.refreshImsConfigCache()`, only when the active subscription of a slot **changes after it was first seen**; runs inside an `ExecutorService.submit` task | No crash (the error stays in the Future). After hot-swapping to a different SIM the IMS provisioning cache is not reset: reboot after a SIM swap. |
| `ims.apk` | `ImsExternalCallState.<init>(String, Uri, Uri, boolean, int, int, boolean, boolean)` (Qualcomm 8-argument overload) | `ImsViceParser.getCallPullInfo()`: multi-endpoint "call pull" dialog info | Only if the network sends VICE dialog events; that feature is unavailable. |
| `moto-telephony.jar` | field `android.os.Build.SOC_MANUFACTURER_IS_MTK` | `MotoExtTelephonyManager.setBlockNrinWfcCall`, `DiagnosisEventProxy.listenDiagnosisEvent` | Neither is called by the IMS app. |
| `ims-ext-common`, `moto-ims-ext`, `qti-telephony-utils`, `qti-telephony-hidl-wrapper` | none | | |

No framework patch is made for these; each is a named, narrow gap rather than a start-up blocker.
The same three references are the only linkage warnings `preflight.py` reports on the vantage
image (`reports/vantage/preflight.md`).

### 2.2 Qualcomm's telephony component factory does not fit AOSP (measured, not ported)

Stock replaces large parts of the telephony stack through `qti-telephony-common.jar`
(`QtiTelephonyComponentFactory`). Its linkage against the framework built here, compared with
its linkage against stock (`reports/vantage/linkage-qti-telephony-common.json`): **8 classes,
25 methods and 4 fields that exist on stock are missing in AOSP**, among them
`Phone.getSmartTempDdsSwitchSupported()`, `Phone.getSubscriberUriNumber()`,
`ServiceStateTracker.issuePollCommands()`, `DataNetworkController.onDataEnabledChanged(boolean, int)`,
`DataNetwork.updateQosBearerSessions(List)`, `OperatorInfo.getCagInfo()`,
`android.telephony.CagInfo`/`SnpnInfo`, the constructor of
`CellularNetworkService.CellularNetworkServiceProvider`, and Motorola's `ExtTelephonyUtils`.
201 of its 500 classes also shadow platform classes. It is written against Qualcomm's and
Motorola's modified `telephony-common`, so it cannot be dropped onto AOSP's. This confirms the
design choice above: AOSP's own stack drives the standard radio AIDL, and only the IMS service
is taken from stock.

## 3. In-call audio

This is the one area with real failure data from the device. During the owner's earlier test
of a TrebleDroid-based GSI (vendor build `W2WV36V.55-65-ST2.4`, logs in
`call_audio_fail_full.txt` / `tombstone_audio.txt`):

- the SIM registered, the IMS PDN came up and an IMS call reached `ACTIVE`;
- from the moment the call started, `audioserver` aborted on every `setPhoneState`:
  `AudioPolicyManager::connectAudioSourceToSink: a swOutput shall always be associated`
  (call chain `setPhoneState -> updateCallRouting -> connectTelephonyRxAudioSource ->
  startAudioSourceInternal -> connectAudioSource -> connectAudioSourceToSink`), restarting in
  a loop (11 restarts in the captured window). No call audio was possible.

Findings:

1. The vendor audio HAL is Qualcomm's AIDL HAL (`AHAL_Module_QTI`, config source "AIDL HAL").
   Its module configuration (`/vendor/etc/audio/audio_module_config_primary.xml`) declares the
   attached devices `telephony_rx` (IN_TELEPHONY_RX) and `telephony_tx` (OUT_TELEPHONY_TX) and
   **device-to-device routes**: `telephony_rx` is a source for `earpiece`, `speaker`,
   `usb_device_out`, `usb_headset`, `bt_sco_*`, `bt_ble_*`; the microphones are sources for
   `telephony_tx`. That is AOSP's "hardware bridge" call model: the policy manager creates
   `telephony_rx -> <sink>` and `<mic> -> telephony_tx` patches and the HAL runs the voice
   session in the DSP.
2. The stock audio policy manager reports the same model (`dumpsys media.audio_policy` taken
   from the stock device: same ports and routes, "Config source: AIDL HAL"). An in-call dump
   from stock has not been captured yet; it is step 0 of the acceptance test because it shows
   the exact patches stock creates.
3. **Root cause of that abort** (established from the tombstone, the built library and the
   sources; an earlier revision of this document wrongly blamed "newer QPR code"):
   - The crashing `libaudiopolicymanagerdefault.so` (BuildId `239e9295...`) has
     `updateCallRouting`, `connectAudioSource` and `connectAudioSourceToSink` at exactly the
     addresses of the library built here (`0x2f270`, `0x35e9c`, `0x36c6c`), and every frame
     that lies behind `createAudioPatchInternal` (`0x373f8` here) exactly `0x2c` bytes lower
     (`updateCallRoutingInternal`, `connectTelephonyRxAudioSource`, `startAudioSourceInternal`,
     `setPhoneState`). It is the same code with one small statement missing inside
     `createAudioPatchInternal`.
   - TrebleDroid's `frameworks/av` branch `android-16.0.0_r1-td` differs from the
     `android-16.0.0_r2-td` branch used here in exactly one line of `AudioPolicyManager.cpp`:
     r1-td lost `sourceDesc->setSwOutput(outputDesc, /* closeOutput= */ false);` in the
     "internal source" branch of `createAudioPatchInternal` (a slip in TrebleDroid's
     "restore legacy telephony audio behaviour" patch; AOSP itself has the line in
     android-15, 16.0.0_r1..r4 and both QPR branches).
   - The telephony RX source is internal (`startAudioSourceInternal(..., internal=true,
     isCallRx=true)`). Without that line the HAL still creates the hardware patch (the log
     shows `setAudioPatch: created [telephony_rx -> speaker]` 1 ms before the abort), then
     `connectAudioSourceToSink` finds no software output. Its `ALOG_ASSERT` is live in
     production builds because the file defines `LOG_NDEBUG 0`. Result: a deterministic abort
     on every call, repeated on each `audioserver` restart while the call is up, which is the
     loop in the log.
   - This baseline contains the statement. `validate-telephony.py --aosp-tree` checks it
     (`audio.call_rx_swoutput`; it reports FAIL on the r1-td file), so a later rebase cannot
     bring the defect back unnoticed.

   Consequence: the known crash cause is absent from this build. Whether call audio is
   audible in both directions is still **UNKNOWN** until tested. What the old log does show
   is that the HAL accepted the `telephony_rx -> speaker` patch and set its RX device.
3a. The transmit side follows the same code path with `telephony_tx` as sink, where the
   software output is "any opened mix that reaches the sink". The stock policy dump shows two
   such outputs opened at start-up on this HAL configuration (`voice_tx`, flags NONE, and
   `in_call_music`), and route 20 lists the microphones as sources of `telephony_tx`. So the
   internal TX patch has an output to attach to; nothing indicates the "no output available
   for internal patch sink" error path. UNKNOWN until tested.
4. Independently of routing, `qcrilNrd` sends voice-session parameters (`vsid`, `call_state`,
   `call_type`) through `IQcRilAudio`. TrebleDroid's `QcRilAm` answers that HAL: the earlier GSI
   log shows those parameters arriving at the audio HAL (`AHAL_Telephony_QTI: updateCalls ...`).
   So the session-control half already worked; the failure was the policy-manager abort alone.

5. **Stock audio policy manager versus this build.** Stock ships Motorola's build of the same
   AOSP `libaudiopolicymanagerdefault.so`, not a Qualcomm replacement. Its exported methods
   contain the whole call-patch path this build uses (`updateCallRoutingInternal`,
   `connectTelephonyRxAudioSource`, `connectTelephonyTxAudioSource`, `startAudioSourceInternal`,
   `connectAudioSourceToSink`) and the same messages ("using HW Bridge", "a swOutput shall
   always be associated", "no output available for internal patch sink"). Six methods exist
   only on stock: `chkDpConnAndAllowedForVoice`, `disableLhdcBluetoothDevice`,
   `disableLhdcRouteToRawOutput`, `isInvalidationOfMusicStreamNeeded`,
   `isOffloadSupportedInternal`, `setScreenRecordHandle`; stock also links `libmotosecure.so`.
   One exists only here: TrebleDroid's `createTelephonyPatch` (legacy path, not taken on this
   device because `ro.vndk.version` is unset). So stock routes calls with the same model:
   telephony RX/TX audio sources and a hardware bridge in the HAL. The Motorola additions
   concern DisplayPort outputs, LHDC Bluetooth, offload and screen recording; none is on the
   earpiece/speaker call path. This is a comparison of code, not of behaviour.
6. **The call-audio bridge in this image** (`me.phh.qcrilam`, TrebleDroid's QcRilAm; stock uses
   `com.qualcomm.qti.telephonyservice`):
   - installed as `/system/app/QcRilAm`, platform-signed, persistent, direct-boot aware,
     started by `LOCKED_BOOT_COMPLETED`/`BOOT_COMPLETED`;
   - it declares `sharedUserId="android.uid.system"`, so it runs in the SELinux domain
     `system_app`. TrebleDroid's `seapp_contexts` line for a dedicated `qcrilam_app` domain is
     written for `user=_app` and therefore never applies. That looked like a defect, so the
     combined policy (this ROM + stock vendor) was compiled and queried: `system_app` may
     `find` `vendor_hal_telephony_service2` (the label of `IQcRilAudio/slot1,2`), call `rild`,
     and be called back by `rild`. The bridge can reach the HAL under enforcing;
   - interface: the vendor serves `vendor.qti.hardware.radio.am` V1 (hash `7807b67b...`, the
     same hash the stock bridge embeds). QcRilAm is built from an unfrozen copy of the
     interface (hash "notfrozen") with the same methods in the same order. The earlier GSI
     log, taken under enforcing SELinux, shows its `call_state`/`vsid` parameters arriving at
     the audio HAL, so the RIL does not reject the client;
   - **who owns the callbacks:** the vendor RIL (`qcrilNrd`, one process per slot) serves
     `IQcRilAudio/slotN` and keeps one request interface per slot
     (`QcrilAudioSAidlService::setRequestInterface`, with its own death notifier for the
     client). The client hands that interface over and receives the slot's response interface.
     In this image exactly one package does that, `me.phh.qcrilam`
     (`audio.bridge_single_owner`); the stock client is not installed, so nothing competes;
   - **defects found by reading it next to the stock client** (disassembly of
     `com.qualcomm.qti.telephonyservice`) and fixed in
     `patches/packages/apps/QcRilAm/0001-per-slot-aidl-response-and-recovery.patch`:
     1. it kept a single response interface in a file-level variable. This vendor serves two
        slots, so the second registration overwrote the first and every response for slot 1
        went to the RIL process of slot 2, while slot 1's RIL waited for answers that never
        came (`QcrilAudioResponseCallback::setParametersResponse` completes a pending
        message there). Now one connection object per slot;
     2. it looked the service up once at boot, without waiting, and never again. Now it uses
        `ServiceManager.waitForDeclaredService` on a per-slot thread, links a death recipient
        and registers again when the RIL comes back, as the stock client does;
     3. it never told the RIL about audioserver. The stock client registers an
        `AudioServerStateCallback` and calls `setError(STATUS_SERVER_DIED)` / `setError(STATUS_OK)`,
        and answers `GENERIC_FAILURE` instead of blocking while audioserver is down. Same now.
     Start-up order: the service still starts on `LOCKED_BOOT_COMPLETED`; if the RIL registers
     later, the wait covers it. Duplicate start: the second boot broadcast starts an already
     created service, which does not register twice. `audio.bridge_recovery` checks that the
     built source is the patched one. Not tested on the phone;
   - a remaining difference that does not affect the wire format: TrebleDroid's copy of the
     interface declares `AudioError` without a backing type (so `byte`), Qualcomm's uses
     `int`; both are written as a 32-bit value.
6a. **Why TrebleDroid's bridge and not the stock app.** Both were evaluated. The stock app
   links cleanly against this image (44 classes, nothing missing) and its SELinux domain
   exists here, so it remains a fallback. It was not chosen because: it is built to live in
   the shared UID and process of Qualcomm's `com.qti.phone` family (`android.uid.qtiphone`),
   none of which is ported; TrebleDroid's bridge is already part of the baseline and would
   have to be removed to avoid two clients; it is the only bridge with evidence on this phone
   under AOSP (its parameters reached the audio HAL in the earlier run); and being open
   source, its defects could be fixed in one small patch that can go upstream, instead of adding
   another proprietary package.
7. **Reference capture on stock** (read-only; nothing is dialled): see TESTING.md section 2.
   The in-call `dumpsys media.audio_policy` of stock shows which software output each
   telephony source is attached to and the exact patches, which is the comparison point if
   this ROM routes differently.

None of this proves audible call audio. It establishes that the known crash cause is absent,
that stock uses the same routing model, and that the bridge is installed, permitted and
interface-compatible.

No change has been made to `frameworks/av`. If the acceptance test shows wrong routing, the
in-call `dumpsys media.audio_policy` of stock versus this ROM pinpoints the difference, and
the fix belongs in a small, reviewable `frameworks/av` patch on top of `vantage-baseline`.

Bluetooth call audio: the HAL routes `telephony_rx` to `bt_sco_*`/`bt_ble_*` sinks directly.
TrebleDroid's system-side Bluetooth audio HAL (`sysbta`) is an opt-in property; the stock
vendor Bluetooth audio HAL is declared in the vendor manifest and is what should be used.
UNKNOWN until tested.

### 3.8 Found on and after the first boot (2026-10-10)

Three things in this section were incomplete; details and evidence in FIRST_BOOT_REPORT.md.

| Finding | Status |
|---|---|
| The analysis above stops at `AudioManager.setParameters()`. With this phone's **AIDL** audio HAL the key=value string (`vsid`, `call_state`) reaches the HAL only through `android.media.audio.IHalAdapterVendorExtension`; without that service the client library drops it. Stock implements it in `/system_ext/lib64/libaudiohalvendorextn.so`, loaded by Motorola's `audioserver` | **Ported** (static): the stock library, hosted by AOSP's own audio parameter parser service. `vendor/motorola/vantage/audio/vendorext/README.md` |
| On the first boot the bridge found both `IQcRilAudio` services and then neither registered nor failed: its two threads wait inside a binder call | **Cause unknown.** Revision 2 of the patch logs each step and warns after 10 s. The RIL's callback interface is one-way, so the bridge's own lock is not the cause |
| No call could be placed on the first boot (no service) | **Second boot (image revision 2): hardware-tested.** Outgoing and incoming VoLTE call, voice session in the vendor HAL opened, started, switched to the speaker and stopped with status 0; the owner confirms both sides audible on earpiece and speaker. SMS over IMS sent and received by the other phone. Incoming SMS: not received, cause open (SECOND_BOOT_REPORT.md 5.3). All of this was with Qualcomm's vendor-enhanced flag off; it must be repeated with the flag on |

## 3.9 Incoming SMS: the RIL waits for a "telephony ready" signal (2026-10-11)

For four sessions SMS could be sent and none arrived. No log line anywhere: the messages never
left the Qualcomm RIL.

| Piece | Evidence |
|---|---|
| The RIL runs with power-on optimisation and buffers incoming SMS until the "UI status" is ready | stock `libqcrilNrSmsModule.so`: `SmsModule::qcril_sms_mt_sms_ind_hdlr` calls `qcril_qmi_sms_external_query_is_power_opt_enabled`, then `qcril_qmi_sms_external_get_ui_status`; the buffer functions are `qcril_qmi_sms_update_mt_sms_with_ack_needed_power_opt_buffer` and `..._notify_..._to_atel` |
| The mode is on by default | `/vendor/etc/qcril_database/upgrade/config/0010.0_config.sql`: `UPDATE qcril_properties_table SET def_val="1" WHERE property="persist.vendor.radio.poweron_opt"`. No Android property is involved, so a `getprop` comparison shows nothing |
| On stock the signal comes from Qualcomm's telephony service | `QtiTelephony.apk`, `com.qti.phone.powerupoptimization.PowerUpOptimization`: reads the property through the RIL, then `QtiMsgTunnelClient.sendAtelReadyStatus` = OEM hook request `0x8001A` (`QCRIL_EVT_HOOK_SET_ATEL_UI_STATUS`), payload one byte |
| AOSP has no sender | the request id appears nowhere in the tree; the Qualcomm service is not part of this ROM (section 2.2 covers its sibling, the telephony component factory) |
| **Proven on the phone** | the request sent by hand on the running guest released a held SMS within 10 ms (FOURTH_BOOT_REPORT.md section 3) |

**Fix:** `VantageRilReady` (`telephony/ril-ready/`), built from source, sends the request per
slot under the stock conditions and repeats it after a RIL or modem restart. It needs no
SELinux rule and no permission entry.

Open: the stock service sends the RIL other things as well (it is the server behind
`com.qti.extphone`). Only this one request has been shown to be needed.

## 4. Open blockers

### 4.1 Wi-Fi calling: vendor apps signed with Motorola's platform key

`/vendor/app/IWlanService` (`vendor.qti.iwlan`, the IWLAN `DataService`/`NetworkService`/
`QualifiedNetworksService`) and `/vendor/app/CneApp` (`com.qualcomm.qti.cne`) share the UID
`com.qualcomm.qti.qtidataservices` and are signed with Motorola's platform certificate. They
sit in `/vendor/app` (not privileged), so on stock they receive `READ_PRIVILEGED_PHONE_STATE`,
`CONNECTIVITY_USE_RESTRICTED_NETWORKS`, `MAINLINE_NETWORK_STACK`, `PACKET_KEEPALIVE_OFFLOAD`
etc. purely because their certificate equals the platform certificate. Under this ROM the
platform certificate is different, so those signature permissions are not granted.

What each app actually depends on (measured 2026-10-10 from the disassembly and the phone):

- `IWlanService` requests only `WAKE_LOCK`, and its code calls nothing that needs a privileged
  permission: `TelephonyManager.getPhoneCount()` and the `DataService` / `NetworkService` /
  `QualifiedNetworksService` base classes. It is a shim between telephony and the vendor IWLAN
  HAL. Nothing found that would stop it from working when telephony binds it.
- `CneApp` is the one that loses function. **On stock it holds the IMS network request**
  (`dumpsys connectivity`). Its `requestNetwork` calls are wrapped in
  `catch (SecurityException)`, so under this ROM it keeps running without that network.
  The request is now held by `VantageImsNetwork` (section 1). Telephony needs that data
  network to hand IMS over between WWAN and WLAN, so Wi-Fi calling could not work without it;
  how much plain VoLTE needs it is not known (`telephony/ims-network/README.md`).
- Still unknown: whether CNE's remaining work for Wi-Fi calling (telling the modem about
  Wi-Fi availability and quality) functions without `READ_PRIVILEGED_PHONE_STATE`,
  `MAINLINE_NETWORK_STACK` and `PACKET_KEEPALIVE_OFFLOAD`.

- Their SELinux domain is unaffected: the vendor's `vendor_mac_permissions.xml` still maps
  Motorola's certificate to `seinfo=platform`.
- AOSP and TrebleDroid have no generic "vendor platform certificate" mechanism (checked in
  `frameworks/base` of this tree; TrebleDroid only special-cases its own maintainer key).
- Not acceptable here: treating a foreign certificate as the platform certificate.

Options analysed:

1. *ROM-signed copies in `/system/app`* (PackageManager scans `/system` before `/vendor` and
   skips later duplicates). **Not viable**: `CneApp` loads `libCneAppJni.so` and `IWlanService`
   loads `libWlanServiceJni.so` from `/vendor/lib64`; neither is in
   `/vendor/etc/public.libraries.txt`. They only load because apps installed on `/vendor` get
   the vendor linker namespace. Copies on `/system` could not load them, and moving the JNI
   libraries with their vendor-only dependencies (`libcne`, `libcneapiclient`, QMI libraries)
   to the system side is not a clean port.
2. *Framework change: treat the vendor's platform certificate as a platform signer for apps
   that are installed on `/vendor` or `/odm` only.* The certificate is already identified by
   the vendor itself (`vendor_mac_permissions.xml`, seinfo `platform`). This restores exactly
   the stock trust relationship for vendor-partition apps and nothing else, but it is a change
   to signature policy in `frameworks/base`. **Not implemented: it needs the owner's decision.**
3. *Leave the vendor apps as they are* and supply only what stock visibly has and this ROM
   would lack. This is the current state: `VantageImsNetwork` holds the IMS request. AOSP also has a per-UID allowlist
   for restricted networks (`ConnectivitySettingsManager.setUidsAllowedOnRestrictedNetworks`,
   honoured by `enforceNetworkRequestPermissions`) that could let CneApp place its own request
   again; it is not used because it does not restore CneApp's other permissions.

### 4.1.1 Precise findings and the decision for the first release

Owner's instruction (2026-10-10): no `frameworks/base` trust change; find the exact problem;
if it cannot be solved cleanly, ship without Wi-Fi calling.

| | `IWlanService` | `CneApp` |
|---|---|---|
| Package, location | `vendor.qti.iwlan`, `/vendor/app` | `com.qualcomm.qti.cne`, `/vendor/app` |
| Certificate | Motorola platform (`e0a42da2...`) | same |
| Shared UID / process / domain | `com.qualcomm.qti.qtidataservices` / `.qtidataservices` / `vendor_qtidataservices_app`, a vendor-defined type, so its policy does not depend on this ROM | same |
| Native code | vendor JNI through the vendor linker namespace (works because the app stays on `/vendor`) | same |
| How it is started | bound by telephony as WLAN data, network and qualified-networks service (the overlay names it; the binder holds the BIND permissions) | own boot receiver |
| Permissions it needs from its signature | none (only `WAKE_LOCK`; code calls `getPhoneCount()` and the service base classes) | see below |

`CneApp`, permission by permission (protection levels and the gated APIs were read from this
source tree, the uses from the app's bytecode):

| Permission | Level | Use found in the app | Effect of not holding it | Grant path without the platform key |
|---|---|---|---|---|
| `CONNECTIVITY_USE_RESTRICTED_NETWORKS` | signature, privileged | two `requestNetwork` sites, both inside `catch (SecurityException)` | the IMS request is refused | **yes**: the ROM's own requester (`VantageImsNetwork`, done), or AOSP's per-UID allowlist for restricted networks |
| `PACKET_KEEPALIVE_OFFLOAD` | signature, privileged | `ConnectivityManager.createNattKeepalive`: offloaded NAT-T keepalives for the ePDG IPsec tunnel | no keepalive offload for the Wi-Fi calling tunnel | none |
| `MAINLINE_NETWORK_STACK` | signature | `WifiManager.stopSoftAp()`; it is also what exempts a caller from the location check that redacts SSID/BSSID in `WifiInfo` (`LocationPermissionChecker`) | no soft-AP control; the app sees a redacted BSSID/SSID | none |
| `READ_PRIVILEGED_PHONE_STATE` | signature, privileged | no call found that strictly needs it (the telephony calls present work with `READ_PHONE_STATE`, which the vendor's default-permissions file grants) | probably nothing | none |
| `INTERACT_ACROSS_USERS`, `PACKAGE_USAGE_STATS` | signature, privileged | `NetworkStatsManager.querySummary` | per-UID traffic statistics unavailable | none |

No failed service binding was found: the three IWLAN services resolve to `vendor.qti.iwlan`
(checked by `preflight.py`, `overlay.package:*`), and CneApp is not bound by the framework.

**Can it be resolved without widening signature trust?** Only in part. The restricted-network
request has a sanctioned substitute. For `PACKET_KEEPALIVE_OFFLOAD` and
`MAINLINE_NETWORK_STACK` Android offers no route to a non-privileged app on `/vendor` except the
platform signature: the app cannot be made privileged without changing the vendor partition,
ROM-signed copies cannot load the vendor JNI (option 1), and the remaining route is option 2.
Whether Wi-Fi calling would work with a redacted BSSID and without keepalive offload cannot be
decided statically (carriers commonly require the access point's BSSID in the IMS
registration, which is a reason to expect trouble).

**Decision:** Wi-Fi calling is **not offered in the first release**.
`carrier_wfc_ims_available_bool` is `false` in the carrier-config overlay, so the setting does
not appear and nothing switches IMS to WLAN. The vendor IWLAN services stay bound as on stock;
with Wi-Fi calling unavailable they have nothing to hand over. For an experiment on a userdebug
build, `adb shell cmd phone cc set-value -p carrier_wfc_ims_available_bool true` makes the
setting appear without a rebuild (`cc clear-values` undoes it). Option 2 remains the complete
fix and remains the owner's decision.

### 4.2 Carrier coverage

Only the owner's current carrier is covered by `VantageCarrierConfigOverlay`. Other SIMs fall
back to AOSP CarrierConfig assets.

### 4.3 Signing

The image is built with AOSP test keys so far (see BUILDING.md). Because the IMS app and the
RIL audio bridge are re-signed with the build's platform key, switching to private release
keys later does not change the integration, only the key.

## 5. Permissions

| Package | Placement | Certificate in image | Privileged permissions | Source of the grant |
|---|---|---|---|---|
| `org.codeaurora.ims` | `/system_ext/priv-app/ims` | ROM platform | `MODIFY_PHONE_STATE`, `READ_PRECISE_PHONE_STATE`, `READ_PRIVILEGED_PHONE_STATE`, `INTERACT_ACROSS_USERS`, `SUBSTITUTE_NOTIFICATION_APP_NAME`, `WRITE_SECURE_SETTINGS`, `READ_NETWORK_USAGE_HISTORY` | platform signature; also listed in `privapp-permissions-vantage-telephony.xml`, same set as stock |
| `vantage.telephony.imsnetwork` | `/system_ext/app/VantageImsNetwork` (not privileged) | ROM platform | `CONNECTIVITY_USE_RESTRICTED_NETWORKS`, `READ_PRIVILEGED_PHONE_STATE` | platform signature only; built from source in this repository, so no allowlist entry is involved |

Permissions the IMS app requests but that no package in this ROM defines
(`com.qti.permission.RECEIVE_ESSENTIAL_RECORDS_LOADED`,
`com.motorola.permission.RECEIVE_MSIM_VOICE_CAPABILITY`, `com.motorola.permission.ACCESS_CHECKIN`)
are defined on stock by Motorola's modified `TeleService`/`MotoSignatureApp`. They guard
broadcasts that AOSP never sends; their absence is expected and harmless to the app's start.

## 6. Next actions

Done: baseline build and validation; `vantage_td` build; all three validators without FAIL
(`reports/vantage/`); linkage of the Qualcomm component factory measured (section 2.2); root
cause of the earlier call-audio abort (section 3).

Open:

1. Acceptance test on the device (TESTING.md), including the stock in-call audio capture.
   Everything marked UNKNOWN in section 2 is decided there.
2. Wi-Fi calling: owner's decision on the approach in section 4.1.
3. Release signing keys (section 4.3).
