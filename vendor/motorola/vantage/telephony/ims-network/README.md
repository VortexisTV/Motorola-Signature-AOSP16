# IMS network request (`VantageImsNetwork`)

AOSP telephony creates its IMS data network (the application-processor side of the IMS PDN)
only while some app holds a `NetworkRequest` for `NET_CAPABILITY_IMS`. Who holds it is left to
the device:

| System | Requester | Evidence |
|---|---|---|
| Stock | `com.qualcomm.qti.cne` (CneApp on `/vendor/app`) | `dumpsys connectivity` on the stock phone, 2026-10-10: one `REQUEST` with `Transports: CELLULAR Capabilities: IMS ... Specifier: <TelephonyNetworkSpecifier [mSubId = 1]> ... RequestorPkg: com.qualcomm.qti.cne` |
| Owner's earlier TrebleDroid GSI | `me.phh.treble.app`, through its manual option "Request IMS network" | radio log of that run: `RequestorPkg: me.phh.treble.app` |
| This ROM without this module | nobody | see below |

Why CneApp cannot do it here: the capability is restricted, so `ConnectivityService`
(`enforceNetworkRequestPermissions`) demands `CONNECTIVITY_USE_RESTRICTED_NETWORKS`
(`signature|privileged`). CneApp is a non-privileged `/vendor` app that holds the permission
on stock only because it is signed with Motorola's platform key. Under a ROM with another
platform key the request throws `SecurityException`; CneApp catches it and carries on (its
ordinary INTERNET request is visible in the earlier GSI log, an IMS one is not).

## What is and is not known about the consequence

- **IMS registration itself does not appear to need it.** In the earlier GSI log the modem
  reported IMS registered over WWAN at 01:21:26.046, two seconds before the first IMS network
  request existed (01:21:28.257). When that request arrived, `SETUP_DATA_CALL` for the IMS APN
  completed in 19 ms, which fits a PDN the modem already had up. The Qualcomm modem evidently
  brings up its own IMS PDN.
- The only successful call in that run (ACTIVE at 01:21:54) took place **with** the
  application-processor side of the network present. Whether a voice call works without it
  is not known.
- What certainly depends on it: everything on the application processor that talks over the
  IMS APN (the video RTP daemon, XCAP/Ut supplementary-service settings, RCS), and every
  WWAN/WLAN handover, because telephony performs a handover on that data network. So Wi-Fi
  calling cannot work without it.

The module therefore reproduces the stock condition instead of leaving it to a manual
TrebleDroid option: a platform-signed system app (no UI, no exported component, persistent,
direct-boot aware) that keeps the same request as stock alive for every active subscription
and releases it when the subscription goes away. It does not touch the vendor apps, and it
stays correct if CneApp later regains its permissions (two requests for the same network are
satisfied by the same data network).

Status: builds and is checked statically (`validate-telephony.py`: `ims.network_request`).
Its effect on the device is **UNKNOWN** until the device test.
