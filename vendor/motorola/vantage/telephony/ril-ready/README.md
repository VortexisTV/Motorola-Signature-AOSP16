# VantageRilReady: tell the RIL that Android telephony is ready

## Why

The Qualcomm RIL of this phone runs with "power-on optimisation": its own property database
(`/vendor/etc/qcril_database`, `persist.vendor.radio.poweron_opt`, default `1` since upgrade
script 0010) enables it without any Android property. In that mode the modem may attach and
register for IMS before Android is up, and the RIL keeps incoming SMS in a buffer until it is
told that the telephony side can take them
(`SmsModule::qcril_sms_mt_sms_ind_hdlr` asks `is_power_opt_enabled`, then `get_ui_status`).

On stock the teller is Qualcomm's telephony service, `QtiTelephony.apk`
(`com.qti.phone.powerupoptimization.PowerUpOptimization`): it sends the OEM hook request
`QCRIL_EVT_HOOK_SET_ATEL_UI_STATUS` with the value 1 for each SIM slot. AOSP telephony has no
such step, and that service is not part of this ROM. Result on the phone, four sessions long:
SMS could be sent and none arrived, without one line in any log.

Proof (2026-10-11, running guest, root): the same 17 bytes sent by hand to
`vendor.qti.hardware.radio.qcrilhook.IQtiOemHook/oemhook0`, and 10 ms later

    QImsService: ImsSenderRxr : [UNSL]< UNSOL_INCOMING_IMS_SMS[SUB0]
    GsmInboundSmsHandler: Delivering SMS to: ...

a message that had been waiting in the RIL for a quarter of an hour.

## What it does

A persistent system-UID app without UI. For each slot it sends the request once when, as on
stock:

- the RIL's OEM hook service for the slot is registered,
- and either the slot has no SIM,
- or its subscription exists, the radio is not unavailable and the IMS stack of that
  subscription is up (stock polls the IMS state for 120 s and then goes ahead; so does this).

It sends again after the RIL process dies or the radio becomes unavailable and returns (a modem
restart forgets the state). It also registers the two OEM hook callbacks, for one purpose: the
RIL's answer to the request appears in the log (`... answered request 1 with error 0`).

The message, as the stock client builds it: `"QOEMHOOK"`, request id `0x8001A` (int), payload
length `1` (int), payload `01`; `oemHookRawRequest(serial, bytes)` is method 2 of the frozen
AIDL interface version 1. The app talks to the binder directly instead of carrying a copy of
Qualcomm's interface definition.

## Tried on the phone (2026-10-11, revision 3 guest, the build that is in revision 4)

    VantageRilReady: slot 0: waiting for the IMS stack of subscription 1
    VantageRilReady: slot 1: told the RIL that telephony is ready (request 1, SIM state 1)
    VantageRilReady: slot 0: told the RIL that telephony is ready (request 2, SIM state 5)
    VantageRilReady: slot 0: the RIL answered request 2 with error 0 (accepted)

and, after the RIL daemon was killed:

    VantageRilReady: slot 0: the RIL died, the signal will be sent again
    VantageRilReady: slot 0: told the RIL that telephony is ready (request 3, SIM state 5)
    VantageRilReady: slot 0: the RIL answered request 3 with error 0 (accepted)

Installed with adb the app is not persistent and Android freezes its idle process; it then
reacts to a RIL death only when woken. As part of the image it is persistent and not frozen.

## What it does not need

No SELinux rule: the stock vendor policy lets `system_app` find
`vendor_hal_telephony_service2` and call `rild`, the same path TrebleDroid's audio bridge uses
(`validate-image.sh` queries both). No permission entry: it runs as the system UID.

## Alternatives that were not taken

- `persist.vendor.radio.poweron_opt=0` as an Android property would switch the buffering off.
  Not tested on the phone, and it would make the vendor RIL run in a mode stock does not use.
- Porting `QtiTelephony.apk` brings the stock sender and a great deal more of Qualcomm's
  telephony extension with it. Kept as the fallback if more of that service turns out to be
  needed.
