# Telephony validation: validate-telephony

Generated: 2026-10-11T02:51:20

**PASS 14 / FAIL 0 / WARNING 2 / UNKNOWN 7**

Static analysis only. PASS means the checked property holds in the files; it does not prove that the feature works on hardware.

- maps: `/system=/work/aosp/out/target/product/tdgsi_arm64_ab/system /system_ext=/work/aosp/out/target/product/tdgsi_arm64_ab/system/system_ext /product=/work/aosp/out/target/product/tdgsi_arm64_ab/system/product /apex=/work/aosp/out/target/product/tdgsi_arm64_ab/apex /vendor=/work/fw/W2WVS36.55-95-5-1/root/vendor /odm=/work/fw/W2WVS36.55-95-5-1/root/odm`
- sim: `313390`

| Status | Area | Test | Result |
|---|---|---|---|
| WARNING | telephony | `radio.hal.aosp_ims` | vendor does not implement android.hardware.radio.ims; IMS is only available through vendor.qti.hardware.radio.ims and Qualcomm's IMS service |
| WARNING | telephony | `vendor.oem_signed_apps` | 4 vendor apps are signed with the OEM platform certificate; under this ROM they lose platform-signature permissions (TELEPHONY_PORT.md section 4.1) |
| UNKNOWN | hardware | `hw.call_audio` | microphone, earpiece, speaker and Bluetooth audio during a call: requires the device, a SIM and a network |
| UNKNOWN | hardware | `hw.data` | mobile data on the default APN: requires the device, a SIM and a network |
| UNKNOWN | hardware | `hw.dual_sim` | dual-SIM behaviour: requires the device, a SIM and a network |
| UNKNOWN | hardware | `hw.ims_registration` | IMS registration / VoLTE with the carrier: requires the device, a SIM and a network |
| UNKNOWN | hardware | `hw.registration` | SIM detection and network registration (LTE/NR): requires the device, a SIM and a network |
| UNKNOWN | hardware | `hw.sms` | SMS send and receive: requires the device, a SIM and a network |
| UNKNOWN | hardware | `hw.voice` | outgoing and incoming voice calls: requires the device, a SIM and a network |
| PASS | telephony | `audio.bridge_recovery` | the call-audio bridge keeps a response interface per slot, waits for the HAL, re-registers on RIL death and reports audioserver state |
| PASS | telephony | `audio.bridge_single_owner` | exactly one package in the image registers RIL audio callbacks |
| PASS | telephony | `audio.call_rx_swoutput` | createAudioPatchInternal attaches a software output to internal (call) sources |
| PASS | telephony | `carrier.apn` | APN database has default, ims and mms APNs for 313/390 |
| PASS | telephony | `carrier.config_keys` | every carrier-config overlay key exists in this framework |
| PASS | telephony | `carrier.config_overlay` | carrier-config overlay installed (/work/aosp/out/target/product/tdgsi_arm64_ab/system/product/overlay/VantageCarrierConfigOverlay.apk) |
| PASS | telephony | `carrier.volte_flag` | carrier_volte_available_bool is set for 313/390 |
| PASS | telephony | `features.telephony` | android.hardware.telephony and .ims features are declared |
| PASS | telephony | `ims.network_request` | vantage.telephony.imsnetwork is platform-signed, persistent and may request restricted networks (holds the IMS network request, as the vendor CNE app does on stock) |
| PASS | telephony | `ims.package` | org.codeaurora.ims is installed with its ImsService and all required libraries |
| PASS | telephony | `qti.client:am` | RIL audio bridge (voice-session audio): vendor serves ['IQcRilAudio/slot1', 'IQcRilAudio/slot2']; system-side client present |
| PASS | telephony | `qti.client:ims` | IMS radio (VoLTE/VoWiFi signalling): vendor serves ['IImsRadio/imsradio0', 'IImsRadio/imsradio1']; system-side client present |
| PASS | telephony | `radio.hal.standard` | vendor declares all 7 android.hardware.radio.* AIDL HALs |
| PASS | telephony | `radio.vendor_daemons` | vendor RIL/IMS daemons are defined and present |

## Details

### WARNING: `vendor.oem_signed_apps`

4 vendor apps are signed with the OEM platform certificate; under this ROM they lose platform-signature permissions (TELEPHONY_PORT.md section 4.1)

- vendor.qti.hardware.cacert.server (CACertService.apk) uid=android.uid.datacacert needs no signature permissions
- com.qualcomm.qti.cne (CneApp.apk) uid=com.qualcomm.qti.qtidataservices needs ['CONNECTIVITY_USE_RESTRICTED_NETWORKS', 'INTERACT_ACROSS_USERS', 'MAINLINE_NETWORK_STACK', 'READ_PRIVILEGED_PHONE_STATE']
- vendor.qti.iwlan (IWlanService.apk) uid=com.qualcomm.qti.qtidataservices needs no signature permissions
- vendor.qti.data.txpwradmin (TxPwrAdmin.apk) uid=com.qualcomm.qti.qmsdataservices needs ['CONNECTIVITY_USE_RESTRICTED_NETWORKS', 'INTERACT_ACROSS_USERS', 'INTERACT_ACROSS_USERS_FULL', 'MAINLINE_NETWORK_STACK', 'READ_PRIVILEGED_PHONE_STATE', 'UPDATE_DEVICE_STATS', 'WRITE_SECURE_SETTINGS']

### PASS: `audio.bridge_recovery`

the call-audio bridge keeps a response interface per slot, waits for the HAL, re-registers on RIL death and reports audioserver state

- /work/aosp/packages/apps/QcRilAm/src/me/phh/qcrilam/QcRilAmService.kt

### PASS: `audio.bridge_single_owner`

exactly one package in the image registers RIL audio callbacks

- me.phh.qcrilam (/work/aosp/out/target/product/tdgsi_arm64_ab/system/app/QcRilAm/QcRilAm.apk)

### PASS: `audio.call_rx_swoutput`

createAudioPatchInternal attaches a software output to internal (call) sources

- /work/aosp/frameworks/av/services/audiopolicy/managerdefault/AudioPolicyManager.cpp

### PASS: `carrier.apn`

APN database has default, ims and mms APNs for 313/390

- /work/aosp/out/target/product/tdgsi_arm64_ab/system/product/etc/apns-conf.xml: 8560 APNs; types for 313/390: ['default', 'dun', 'emergency', 'ia', 'ims', 'mms']

### PASS: `carrier.config_keys`

every carrier-config overlay key exists in this framework

- 1 carrier blocks, 33 keys; 33 for 313/390

### PASS: `ims.network_request`

vantage.telephony.imsnetwork is platform-signed, persistent and may request restricted networks (holds the IMS network request, as the vendor CNE app does on stock)

- path /work/aosp/out/target/product/tdgsi_arm64_ab/system/system_ext/app/VantageImsNetwork/VantageImsNetwork.apk
- application {'name': '.ImsNetworkApp', 'persistent': True, 'directBootAware': True, 'extractNativeLibs': True}

### PASS: `ims.package`

org.codeaurora.ims is installed with its ImsService and all required libraries

- path /work/aosp/out/target/product/tdgsi_arm64_ab/system/system_ext/priv-app/ims/ims.apk
- persistent=True
- required libraries ['qti-telephony-hidl-wrapper', 'qti-telephony-utils', 'ims-ext-common', 'moto-telephony', 'moto-ims-ext']

### PASS: `qti.client:am`

RIL audio bridge (voice-session audio): vendor serves ['IQcRilAudio/slot1', 'IQcRilAudio/slot2']; system-side client present

- me.phh.qcrilam (/work/aosp/out/target/product/tdgsi_arm64_ab/system/app/QcRilAm/QcRilAm.apk)

### PASS: `qti.client:ims`

IMS radio (VoLTE/VoWiFi signalling): vendor serves ['IImsRadio/imsradio0', 'IImsRadio/imsradio1']; system-side client present

- org.codeaurora.ims (/work/aosp/out/target/product/tdgsi_arm64_ab/system/system_ext/priv-app/ims/ims.apk)

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

