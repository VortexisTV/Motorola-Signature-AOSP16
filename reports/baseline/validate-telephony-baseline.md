# Telephony validation: validate-telephony-baseline

Generated: 2026-10-09T23:53:07

**PASS 6 / FAIL 2 / WARNING 4 / UNKNOWN 7**

Static analysis only. PASS means the checked property holds in the files; it does not prove that the feature works on hardware.

- maps: `/system=/work/aosp/out/target/product/tdgsi_arm64_ab/system /system_ext=/work/aosp/out/target/product/tdgsi_arm64_ab/system/system_ext /product=/work/aosp/out/target/product/tdgsi_arm64_ab/system/product /apex=/work/aosp/out/target/product/tdgsi_arm64_ab/apex /vendor=/work/fw/W2WVS36.55-95-5-1/root/vendor /odm=/work/fw/W2WVS36.55-95-5-1/root/odm`
- sim: `313390`

| Status | Area | Test | Result |
|---|---|---|---|
| FAIL | telephony | `carrier.config_overlay` | VantageCarrierConfigOverlay is not installed in the image |
| FAIL | telephony | `ims.package` | org.codeaurora.ims is not in the image |
| WARNING | telephony | `carrier.apn` | APN database has no entry for 313/390 |
| WARNING | telephony | `carrier.config_keys` | 1 overlay keys are not string constants of this framework (they would be ignored) |
| WARNING | telephony | `radio.hal.aosp_ims` | vendor does not implement android.hardware.radio.ims; IMS is only available through vendor.qti.hardware.radio.ims and Qualcomm's IMS service |
| WARNING | telephony | `vendor.oem_signed_apps` | 10 vendor apps are signed with the OEM platform certificate; under this ROM they lose platform-signature permissions (Wi-Fi calling / CNE blocker) |
| UNKNOWN | hardware | `hw.call_audio` | microphone, earpiece, speaker and Bluetooth audio during a call: requires the device, a SIM and a network |
| UNKNOWN | hardware | `hw.data` | mobile data on the default APN: requires the device, a SIM and a network |
| UNKNOWN | hardware | `hw.dual_sim` | dual-SIM behaviour: requires the device, a SIM and a network |
| UNKNOWN | hardware | `hw.ims_registration` | IMS registration / VoLTE with the carrier: requires the device, a SIM and a network |
| UNKNOWN | hardware | `hw.registration` | SIM detection and network registration (LTE/NR): requires the device, a SIM and a network |
| UNKNOWN | hardware | `hw.sms` | SMS send and receive: requires the device, a SIM and a network |
| UNKNOWN | hardware | `hw.voice` | outgoing and incoming voice calls: requires the device, a SIM and a network |
| PASS | telephony | `carrier.volte_flag` | carrier_volte_available_bool is set for 313/390 |
| PASS | telephony | `features.telephony` | android.hardware.telephony and .ims features are declared |
| PASS | telephony | `qti.client:am` | RIL audio bridge (voice-session audio): vendor serves ['IQcRilAudio/slot1', 'IQcRilAudio/slot2']; system-side client present |
| PASS | telephony | `qti.client:ims` | IMS radio (VoLTE/VoWiFi signalling): vendor serves ['IImsRadio/imsradio0', 'IImsRadio/imsradio1']; system-side client present |
| PASS | telephony | `radio.hal.standard` | vendor declares all 7 android.hardware.radio.* AIDL HALs |
| PASS | telephony | `radio.vendor_daemons` | vendor RIL/IMS daemons are defined and present |

## Details

### WARNING: `carrier.apn`

APN database has no entry for 313/390

- /work/aosp/out/target/product/tdgsi_arm64_ab/system/product/etc/apns-conf.xml: 3667 APNs; types for 313/390: []

### WARNING: `carrier.config_keys`

1 overlay keys are not string constants of this framework (they would be ignored)

- allow_video_call_in_low_battery

### WARNING: `vendor.oem_signed_apps`

10 vendor apps are signed with the OEM platform certificate; under this ROM they lose platform-signature permissions (Wi-Fi calling / CNE blocker)

- vendor.qti.hardware.cacert.server (CACertService.apk) uid=android.uid.datacacert needs no signature permissions
- com.qualcomm.qti.cne (CneApp.apk) uid=com.qualcomm.qti.qtidataservices needs ['CONNECTIVITY_USE_RESTRICTED_NETWORKS', 'INTERACT_ACROSS_USERS', 'MAINLINE_NETWORK_STACK', 'READ_PRIVILEGED_PHONE_STATE']
- vendor.qti.iwlan (IWlanService.apk) uid=com.qualcomm.qti.qtidataservices needs no signature permissions
- com.qualcomm.timeservice (TimeService.apk) uid=None needs no signature permissions
- vendor.qti.data.txpwradmin (TxPwrAdmin.apk) uid=com.qualcomm.qti.qmsdataservices needs ['CONNECTIVITY_USE_RESTRICTED_NETWORKS', 'INTERACT_ACROSS_USERS', 'INTERACT_ACROSS_USERS_FULL', 'MAINLINE_NETWORK_STACK', 'READ_PRIVILEGED_PHONE_STATE', 'UPDATE_DEVICE_STATS', 'WRITE_SECURE_SETTINGS']
- com.android.se.overlay.target (SecureElementResTarget_Vendor.apk) uid=None needs no signature permissions
- com.android.uwb.overlay (ServiceUwbResVantageOverlayGsi.apk) uid=None needs no signature permissions
- com.android.wifi.resources.overlay.WifiRes6GhzEnable (WifiRes6GhzEnable.apk) uid=None needs no signature permissions
- com.android.wifi.resources.overlay.WifiResDualStaEnable (WifiResDualStaEnablePRC.apk) uid=None needs no signature permissions
- com.android.wifi.resources.overlay.WifiResDualStaEnableROW (WifiResDualStaEnableROW.apk) uid=None needs no signature permissions

### PASS: `qti.client:am`

RIL audio bridge (voice-session audio): vendor serves ['IQcRilAudio/slot1', 'IQcRilAudio/slot2']; system-side client present

- me.phh.qcrilam (/work/aosp/out/target/product/tdgsi_arm64_ab/system/app/QcRilAm/QcRilAm.apk)

### PASS: `qti.client:ims`

IMS radio (VoLTE/VoWiFi signalling): vendor serves ['IImsRadio/imsradio0', 'IImsRadio/imsradio1']; system-side client present

- me.phh.treble.app (/work/aosp/out/target/product/tdgsi_arm64_ab/system/priv-app/TrebleApp/TrebleApp.apk)

### PASS: `radio.hal.standard`

vendor declares all 7 android.hardware.radio.* AIDL HALs

- android.hardware.radio.config V4: ['IRadioConfig/default']
- android.hardware.radio.data V4: ['IRadioData/slot1', 'IRadioData/slot2']
- android.hardware.radio.messaging V4: ['IRadioMessaging/slot1', 'IRadioMessaging/slot2']
- android.hardware.radio.modem V4: ['IRadioModem/slot1', 'IRadioModem/slot2']
- android.hardware.radio.network V4: ['IRadioNetwork/slot1', 'IRadioNetwork/slot2']
- android.hardware.radio.sim V4: ['IRadioSim/slot1', 'IRadioSim/slot2']
- android.hardware.radio.voice V4: ['IRadioVoice/slot1', 'IRadioVoice/slot2']

### PASS: `radio.vendor_daemons`

vendor RIL/IMS daemons are defined and present

- vendor.qcrild: /vendor/bin/hw/qcrilNrd (present)
- vendor.qcrild2: /vendor/bin/hw/qcrilNrd (present)
- vendor.imsdaemon: /vendor/bin/imsdaemon (present)
- vendor.ims_rtp_daemon: /vendor/bin/ims_rtp_daemon (present)

