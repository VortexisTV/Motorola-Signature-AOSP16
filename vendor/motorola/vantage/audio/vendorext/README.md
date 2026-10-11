# Call audio: vendor parameters for the AIDL audio HAL

## Why this exists

This phone's audio HAL is AIDL (`vendor.audio-hal-aidl`). Key=value parameters set with
`AudioManager.setParameters()` reach an AIDL HAL only through
`android.media.audio.IHalAdapterVendorExtension`: the audio client library
(`frameworks/av/media/libaudiohal/impl`) asks that service to turn the string into
`VendorParameter` objects and passes those to the HAL. Without the service the string is
dropped (`HalAdapterVendorExtensionWrapper` returns OK with no parameters).

The call path depends on it: the RIL asks the audio side, through the RIL audio bridge, to set
`vsid=...;call_state=...`. Those are vendor parameters.

| | Stock | This ROM before | This ROM now |
|---|---|---|---|
| Implementation | `/system_ext/lib64/libaudiohalvendorextn.so` (Qualcomm) | none | the same stock file |
| Who hosts it | Motorola's `audioserver` loads it (`dlopen`, `registerInterface`) | nobody | AOSP's `audio_parameter_parser_service` (`frameworks/av/services/audioparameterparser`, unmodified) |
| `ro.audio.ihaladaptervendorextension_enabled` | `true` (stock `/system_ext/etc/build.prop`) | unset | `true` |

Evidence: the source of the client library as built here; strings and imports of the stock
`audioserver` and of the stock library; the stock property; the guest's property dump from the
first boot (property missing).

## Pieces

- `loader.cpp` -> `libvantage_audiohalvendorext.so`: AOSP's service looks for
  `createIHalAdapterVendorExtension` in the library named by
  `ro.audio.ihaladaptervendorextension_libname`; the stock library exports `registerInterface`.
  The loader bridges the two names and nothing else.
- Stock files (blob manifest, component `audio-call-parameters`): `libaudiohalvendorextn.so`
  and its dependency `qti-audio-types-aidl-V1-ndk.so`.
- SELinux (`sepolicy/private/audio_vendor_parameter_parser.te`): the domain, service type and
  rules Android's own reference device (Cuttlefish) uses for this service. The stock code
  therefore runs in a small domain of its own instead of inside audioserver.

## Failure behaviour

- Stock library missing or not loadable: the loader returns an error, AOSP's service registers
  its built-in parser, audioserver is not blocked, vendor parameters are ignored (the state
  before this change).
- Registration refused by the service manager: the stock code aborts and init restarts the
  service. With the property enabled audioserver would then wait on its first vendor parameter.
  `validate-telephony.py` (`audio.vendor_extension`) and `validate-image.sh` check the policy
  for exactly these permissions before an image is tested.

Static compatibility only. Whether calls have audio is a hardware test.
