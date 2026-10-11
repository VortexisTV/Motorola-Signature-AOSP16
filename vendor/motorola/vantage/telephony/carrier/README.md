# Carrier data

| Item | Stock source | Here |
|---|---|---|
| APN database | `/product/etc/apns-conf.xml` (8,560 entries, version 8) plus Google Carrier Settings | The stock `apns-conf.xml` is copied to the same path (listed in `proprietary-files.txt`, component `telephony-carrier`). AOSP's TelephonyProvider prefers `/product/etc/apns-conf.xml` over `/system/etc/apns-conf.xml`. |
| Carrier configuration | Google Carrier Settings protobufs (`com.google.android.carrier`, GMS) | `VantageCarrierConfigOverlay` adds per-carrier blocks to AOSP CarrierConfig's `vendor.xml`, each transcribed from a `dumpsys carrier_config` taken on stock with that SIM inserted. |

Currently covered: Optimum Mobile US (313390). For any other SIM the ROM falls back to what
AOSP's CarrierConfig assets contain, which may leave VoLTE/Wi-Fi calling disabled. To add a
carrier: boot stock with the SIM, run `adb shell dumpsys carrier_config > stock-carrier.txt`,
and transcribe the standard keys of `mConfigFromDefaultApp` into a new `<carrier_config>` block.

Deliberately different from stock: `carrier_wfc_ims_available_bool` and the two
`carrier_default_wfc_ims_*enabled_bool` keys are `false` here, `true` on stock. Wi-Fi calling
is not offered in the first release (TELEPHONY_PORT.md section 4.1); the comment in
`vendor.xml` shows how to switch it on for an experiment without rebuilding.

Whether a block is honoured is checked statically (`validate-telephony.py`: key names exist in
`CarrierConfigManager` of the built framework). Whether the network then registers IMS is a
hardware/carrier question and is UNKNOWN until tested.
