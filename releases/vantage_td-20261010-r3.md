# vantage_td 2026-10-10 r3 (test image)

Android 16 system image for the **Motorola Signature** (codename `vantage`, product
`vantage_g`, XT2603-1) running stock firmware **W2WVS36.55-95-5-1**. AOSP `android-16.0.0_r2`
plus TrebleDroid `android-16.0`, userdebug, AOSP test keys, security patch level 2025-06-05.
Only `system` is replaced; vendor, odm, boot, modem and everything else stay stock.

Built from this repository at commit `31ab1e0`.

## Files

| File | Size | SHA-256 |
|---|---|---|
| `system_raw.gz` | 1,203,829,324 bytes | `b7718a00627e4d56a824ae478cd8030197bf4e854404c23f3241c9de6b5ce68b` |
| `system.img` (what the archive unpacks to; not attached, it is larger than a release asset may be) | 2,556,448,768 bytes | `6698676f9b43d42a43de6eee1a11a5a5d5de5a2b1bf7df6f5b26333f34a1bea1` |

`system_raw.gz` is the gzip of the raw (non-sparse) ext4 image. It is the form the Dynamic
System Update installer takes.

## Status: built and statically validated, not booted

**This image has not run on a phone yet.** The table says what each change rests on.

| Change since r2 | What it rests on |
|---|---|
| All six cameras: Qualcomm's `ro.vendor.qti.va_aosp.support=1` is set | seen on the phone with r2 and the property added by hand (6 devices, the logical multi-camera opens) |
| ...and only the camera HAL can read it (own SELinux type) | with the property visible to every vendor process the GNSS assistance daemon gave up and stayed down; the audio HAL, Bluetooth HAL and IMS daemons read it too. The restricted form is checked in the compiled policy, not on the phone |
| Motorola Camera no longer stops when switched to video: the camcorder profiles come from the file stock reads | cause proven on the phone (r2 guest with the stock file loaded: video mode opens). Recording itself has not been tried |
| A screenshot of the video viewfinder no longer aborts the display server | the abort was captured on the phone; the cause is an AOSP `android-16.0.0_r2` bug fixed upstream in `_r3`; the same change is applied here and checked in the image's binary |
| `ro.carrier` is taken from the bootloader's `androidboot.carrier`, as Motorola's init does | static; the vendor reads it (RIL, thermal, modem scripts) |

Carried over from r2, where the phone logged them and the tester confirmed what can be heard
or seen: boot with the stock vendor under enforcing SELinux; SIM, LTE registration, mobile
data; VoLTE calls in both directions with audio on earpiece and speaker; SMS sending.

| Known issue | State |
|---|---|
| An SMS sent to the phone did not arrive in one test | cause open |
| The idle camera process is killed once about 30 s after boot (a broadcast of the TrebleDroid app that Motorola Camera does not expect) | known, harmless, not fixed |
| Carrier settings are included for one operator only (MCC/MNC 313390); other SIMs get AOSP defaults | by design so far |
| Wi-Fi calling | not offered |
| SystemUI restarts for about a second right after boot | open |
| Security patch level is 2025-06-05, a year behind the stock firmware | inherent to the source baseline |

Not tested at all: video recording, Bluetooth, GNSS, NFC, fingerprint, eSIM (not supported),
flashing the image to the `system` partition.

## Before you install

- **This is a test build.** It is a userdebug image signed with the public AOSP test keys and
  has adb enabled with root available. Do not use it as a daily system.
- It is for this model and this stock firmware build only.
- The bootloader must be unlocked (verified boot state `orange`). The stock first-stage `init`
  refuses a test-keyed image with an older patch level on a locked phone.
- About 41 GiB of free user data is needed (the installer keeps a reserve the size of `super`).
- A DSU guest lives in free space of user data with its own data; stock is not modified, and a
  reboot returns to it. An earlier guest has to be discarded first (notification on stock).

## Install (Dynamic System Update)

In Git Bash every adb command with a device path needs `MSYS_NO_PATHCONV=1` in front;
otherwise the shell rewrites the path and the push fails.

```bash
MSYS_NO_PATHCONV=1 adb push system_raw.gz /storage/emulated/0/Download/
```

```bash
MSYS_NO_PATHCONV=1 adb shell am start-activity -n com.android.dynsystem/com.android.dynsystem.VerificationActivity -a android.os.image.action.START_INSTALL -d file:///storage/emulated/0/Download/system_raw.gz --el KEY_SYSTEM_SIZE 2556448768 --el KEY_USERDATA_SIZE 8589934592 --ez KEY_ONE_SHOT true
```

Confirm on the phone, wait for the notification to finish, tap **Restart**. To go back: reboot.
On stock the notification offers **Discard**, which removes the guest.

`vendor/motorola/vantage/scripts/dsu-preflight.sh` in the repository checks the archive and the
phone first and prints these commands; `TESTING.md` has the full procedure.

## What is inside

Everything is built from source except 34 files taken from the stock firmware (the
Qualcomm IMS service and its libraries, Motorola Camera and its signature library, the APN
database, the audio vendor-extension library); the list with hashes is
`vendor/motorola/vantage/proprietary-files.txt`. 33 are byte-identical to stock; the IMS app is
re-signed with this image's platform key and otherwise unchanged. Those files belong to Motorola and
Qualcomm and are not covered by this repository's own terms.

Three source patches are applied to the tree (`patches/`): TrebleDroid's RIL audio bridge, one
table entry in `init`, one expression in surfaceflinger. Each patch file starts with its reason
and evidence.
