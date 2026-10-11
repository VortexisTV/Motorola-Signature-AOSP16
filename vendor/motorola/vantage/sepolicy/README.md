# vantage system-side SELinux policy

The stock vendor policy (`/vendor/etc/selinux`, policy version **202504**) is used unmodified.
It contains rules for system-side domains that Motorola's own `system_ext`/`product` policy
normally declares. A generic AOSP/TrebleDroid system has none of them, so those vendor rules
would bind to nothing. This directory re-declares the minimum set:

| Symbol | Stock declaration | Used by |
|---|---|---|
| `vendor_qtelephony` (type) | system_ext public | `org.codeaurora.ims` |
| `moto_camera_app` (type) | product public | `com.motorola.camera5` |
| `vendor_hal_atfwd_client`, `vendor_hal_imsvthal_client` (attributes) | system_ext public | IMS |
| `motoappdomain`, `moto_qcxdsp_domain` (attributes) | system_ext public | Camera |

Because they are **public** types, the build emits `(typeattributeset <type>_202504 (<type>))`
into the system_ext mapping file and the stock vendor rules attach automatically.

`seinfo` values are not defined here: the stock `/vendor/etc/selinux/vendor_mac_permissions.xml`
already maps Motorola's certificates (`common`, `common2`, `release`, `platform`) and is merged
at boot. The ROM's own platform key maps to `platform` through the regular platform policy.

Regenerate the evidence with:

    scripts/sepolicy_slice.py <fw_out_dir> reports/sepolicy-slice.json --seed vendor_qtelephony \
        --seed moto_camera_app --te reports/sepolicy-slice

`scripts/preflight.py` compiles the resulting system policy together with the stock vendor
policy using `secilc`, exactly as `init` does on the device, before anything is flashed.

## How the result is verified (2026-10-10)

Compiling is necessary and not sufficient, so three further checks run on the image:

1. `preflight.py`: `sepolicy.compile` builds the policy from the same inputs `init` uses
   (this ROM's CIL and mapping files plus the stock `plat_pub_versioned.cil`,
   `vendor_sepolicy.cil`, `odm_sepolicy.cil`) with the tree's `secilc`.
2. `preflight.py`: `sepolicy.unmapped` looks at every versioned attribute the stock vendor
   policy writes rules against, not only the two this layer was built for. Of 1,539, this ROM
   populates 1,413. The 126 empty ones are stock `system_ext`/`product` public types: 52
   domains of stock-only processes, 30 property types, 19 service types, 22 file types, 3 that
   stock itself never defines. None of the object types is assigned by the vendor's own
   context files (their labels come from stock's system-side files, which do not exist here),
   with one exception, the HIDL `IAtCmdFwd` service, whose stock server is a system app that
   is not ported. Consequence: the vendor rules on those 126 attributes are dead, as on any
   GSI on this vendor; what a vendor process loses is access to objects that stock would have
   labelled with those types and that here carry a default label (for example the
   `persist.mot_bt.*` properties or `/data/adspd`). None of them is on the telephony or
   camera path. Restoring them would mean re-declaring stock's public object types and their
   label files; that is listed as later hardening work, not done.
3. `sepolicy_diff.py` expands both the compiled policy of this ROM and the stock precompiled
   policy to plain (source, target, class, permission) tuples and compares what the two ported
   app domains may do. `vendor_qtelephony`: nothing stock grants on an object that exists here
   is missing. `moto_camera_app`: two service lookups (`recovery_service`,
   `vr_manager_service`) that stock grants to every Motorola app through an attribute; the
   camera's bytecode references neither, so they were not added. The same tool answers single
   questions, for example whether the call-audio bridge's domain may reach the RIL audio HAL.

## A property only the camera HAL may read

`ro.vendor.qti.va_aosp.support` is Qualcomm's "vendor-enhanced framework" flag. Stock sets it
to 1 and labels it `vendor_exported_system_prop`, readable by every vendor process. Here it is
`vantage_vendor_framework_prop` (`private/property.te`, `private/property_contexts`), readable
by `hal_camera_server` and `shell` only:

- the camera HAL needs it to expose all six cameras (CAMERA_PORT.md section 4.2);
- the other readers (audio HAL, Bluetooth HAL, `cnd`, the IMS and RTP daemons, `qcc-vendor`,
  the GNSS XTRA daemon) take it as a promise that Qualcomm's system-side services exist. In the
  one boot where they saw it, the XTRA daemon gave up and stayed down
  (THIRD_BOOT_REPORT.md section 4).

A process that may not read a property finds no property, so those components behave as on a
system that never set the flag. `validate-image.sh` asks the compiled policy both ways: the
camera HAL domain is allowed, seven other vendor domains are refused. The stock vendor and odm
`property_contexts` do not name the property; a second exact entry would be an error.
