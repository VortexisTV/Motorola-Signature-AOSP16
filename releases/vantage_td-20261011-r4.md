# vantage_td 2026-10-11 r4 (test image)

Android 16 system image for the **Motorola Signature** (codename `vantage`, product
`vantage_g`, XT2603-1) running stock firmware **W2WVS36.55-95-5-1**. AOSP `android-16.0.0_r2`
plus TrebleDroid `android-16.0`, userdebug, AOSP test keys, security patch level 2025-06-05.
Only `system` is replaced; vendor, odm, boot, modem and everything else stay stock.

Built from this repository at commit `66c9f26`.

## Files

| File | Size | SHA-256 |
|---|---|---|
| `system_raw.gz` | 1,203,842,929 bytes | `53a0ae6b3c6fea41ad31b04540431379778bd3771a86c322a9db58954947d96f` |
| `system.img` (what the archive unpacks to; not attached, it is larger than a release asset may be) | 2,556,506,112 bytes | `efe1b630cfdeda6f655112825d6df01aece2e0cc7fdf762b97a5296809dd9b3e` |

`system_raw.gz` is the gzip of the raw (non-sparse) ext4 image. It is the form the Dynamic
System Update installer takes.

## What was tested

One phone, one boot of this image as a DSU guest on 2026-10-11 (and four sessions on the three
revisions before it). "Works" means the phone logged it; the tester's summary of this session
was "It all works".

| Works | Evidence |
|---|---|
| Boot with the stock vendor, SELinux enforcing | boot completed, `getenforce`, no native crash |
| SIM, LTE registration, mobile data | in service, data network validated |
| VoLTE calls, outgoing and incoming, earpiece and speaker | call active; voice session in the vendor audio HAL; both sides audible (confirmed by ear on revision 2) |
| SMS in both directions (over IMS) | sent status; an incoming SMS delivered 12 s after the message it answers. New in this revision: before it the Qualcomm RIL kept every incoming SMS to itself |
| Motorola Camera with all six cameras | camera service lists 6 devices, the app opens a camera |
| Video mode and video recording | a 13 s HEVC recording written to the end; picture quality not assessed |

| Known issue | State |
|---|---|
| Carrier settings are included for one operator only (MCC/MNC 313390); other SIMs get AOSP defaults | by design so far |
| Wi-Fi calling | not offered |
| The vendor's connectivity app (`.qtidataservices`) crashes once at boot and restarts | located, no effect seen, not fixed |
| The idle camera process may be killed once about 30 s after boot | known, harmless, not fixed |
| SystemUI restarts for about a second right after boot | open |
| Security patch level is 2025-06-05, a year behind the stock firmware | inherent to the source baseline |

Not tested at all: Bluetooth, GNSS, NFC, fingerprint, dual SIM, eSIM (not supported), a screenshot
while the camera is in video mode (fixed in revision 3, checked in the binary only), flashing the
image to the `system` partition.

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
MSYS_NO_PATHCONV=1 adb shell am start-activity -n com.android.dynsystem/com.android.dynsystem.VerificationActivity -a android.os.image.action.START_INSTALL -d file:///storage/emulated/0/Download/system_raw.gz --el KEY_SYSTEM_SIZE 2556506112 --el KEY_USERDATA_SIZE 8589934592 --ez KEY_ONE_SHOT true
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
