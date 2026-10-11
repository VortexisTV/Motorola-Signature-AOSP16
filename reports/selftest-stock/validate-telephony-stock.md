# Telephony validation: validate-telephony-stock

Generated: 2026-10-09T21:29:11

**PASS 9 / FAIL 1 / WARNING 2 / UNKNOWN 7**

Static analysis only. PASS means the checked property holds in the files; it does not prove that the feature works on hardware.

- maps: `/system=/work/fw/W2WVS36.55-95-5-1/root/system/system /system_ext=/work/fw/W2WVS36.55-95-5-1/root/system_ext /product=/work/fw/W2WVS36.55-95-5-1/root/product /apex=/work/fw/W2WVS36.55-95-5-1/apex /vendor=/work/fw/W2WVS36.55-95-5-1/root/vendor /odm=/work/fw/W2WVS36.55-95-5-1/root/odm`
- sim: `313390`

| Status | Area | Test | Result |
|---|---|---|---|
| FAIL | telephony | `carrier.config_overlay` | VantageCarrierConfigOverlay is not installed in the image |
| WARNING | telephony | `carrier.config_keys` | 2 overlay keys are not string constants of this framework (they would be ignored) |
| WARNING | telephony | `radio.hal.aosp_ims` | vendor does not implement android.hardware.radio.ims; IMS is only available through vendor.qti.hardware.radio.ims and Qualcomm's IMS service |
| UNKNOWN | hardware | `hw.call_audio` | microphone, earpiece, speaker and Bluetooth audio during a call: requires the device, a SIM and a network |
| UNKNOWN | hardware | `hw.data` | mobile data on the default APN: requires the device, a SIM and a network |
| UNKNOWN | hardware | `hw.dual_sim` | dual-SIM behaviour: requires the device, a SIM and a network |
| UNKNOWN | hardware | `hw.ims_registration` | IMS registration / VoLTE with the carrier: requires the device, a SIM and a network |
| UNKNOWN | hardware | `hw.registration` | SIM detection and network registration (LTE/NR): requires the device, a SIM and a network |
| UNKNOWN | hardware | `hw.sms` | SMS send and receive: requires the device, a SIM and a network |
| UNKNOWN | hardware | `hw.voice` | outgoing and incoming voice calls: requires the device, a SIM and a network |
| PASS | telephony | `carrier.apn` | APN database has default, ims and mms APNs for 313/390 |
| PASS | telephony | `carrier.volte_flag` | carrier_volte_available_bool is set for 313/390 |
| PASS | telephony | `features.telephony` | android.hardware.telephony and .ims features are declared |
| PASS | telephony | `ims.package` | org.codeaurora.ims is installed with its ImsService and all required libraries |
| PASS | telephony | `qti.client:am` | RIL audio bridge (voice-session audio): vendor serves ['IQcRilAudio/slot1', 'IQcRilAudio/slot2']; system-side client present |
| PASS | telephony | `qti.client:ims` | IMS radio (VoLTE/VoWiFi signalling): vendor serves ['IImsRadio/imsradio0', 'IImsRadio/imsradio1']; system-side client present |
| PASS | telephony | `radio.hal.standard` | vendor declares all 7 android.hardware.radio.* AIDL HALs |
| PASS | telephony | `radio.vendor_daemons` | vendor RIL/IMS daemons are defined and present |
| PASS | telephony | `vendor.oem_signed_apps` | image platform certificate equals the vendor's (stock system) |

## Details

### WARNING: `carrier.config_keys`

2 overlay keys are not string constants of this framework (they would be ignored)

- allow_video_call_in_low_battery
- display_in_call_notification_wifi_icon_bool

### PASS: `carrier.apn`

APN database has default, ims and mms APNs for 313/390

- /work/fw/W2WVS36.55-95-5-1/root/product/etc/apns-conf.xml: 8560 APNs; types for 313/390: ['default', 'dun', 'emergency', 'ia', 'ims', 'mms']

### PASS: `ims.package`

org.codeaurora.ims is installed with its ImsService and all required libraries

- path /work/fw/W2WVS36.55-95-5-1/root/system_ext/priv-app/ims/ims.apk
- persistent=True
- required libraries ['qti-telephony-hidl-wrapper', 'qti-telephony-utils', 'ims-ext-common', 'moto-telephony', 'moto-ims-ext']

### PASS: `qti.client:am`

RIL audio bridge (voice-session audio): vendor serves ['IQcRilAudio/slot1', 'IQcRilAudio/slot2']; system-side client present

- com.qualcomm.qti.telephonyservice (/work/fw/W2WVS36.55-95-5-1/root/system_ext/app/QtiTelephonyService/QtiTelephonyService.apk)

### PASS: `qti.client:ims`

IMS radio (VoLTE/VoWiFi signalling): vendor serves ['IImsRadio/imsradio0', 'IImsRadio/imsradio1']; system-side client present

- org.codeaurora.ims (/work/fw/W2WVS36.55-95-5-1/root/system_ext/priv-app/ims/ims.apk)

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

