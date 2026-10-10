# vantage_td 2026-10-10 r2 (test image)

Android 16 system image for the **Motorola Signature** (codename `vantage`, product
`vantage_g`, XT2603-1) running stock firmware **W2WVS36.55-95-5-1**. AOSP `android-16.0.0_r2`
plus TrebleDroid `android-16.0`, userdebug, AOSP test keys, security patch level 2025-06-05.
Only `system` is replaced; vendor, odm, boot, modem and everything else stay stock.

Built from this repository at commit `f3906bf`.

## Files

| File | Size | SHA-256 |
|---|---|---|
| `system_raw.gz` | 1,203,837,883 bytes | `0be57d38c90fd2a256e276909a97b03932204c2dcf034e0c1312cb329233712d` |
| `system.img` (what the xz archive unpacks to) | 2,556,428,288 bytes | `af0101848774ef963763cb558ad0f1a2f908de004bb33d9e66c78a47560d3faf` |

`system_raw.gz` is the gzip of the raw (non-sparse) ext4 image. It is the form the Dynamic
System Update installer takes.

## What was tested

One phone, booted twice as a DSU guest on 2026-10-10. "Works" means the phone logged it and,
where it can be heard or seen, the tester confirmed it.

| Works | Evidence |
|---|---|
| Boot with the stock vendor, SELinux enforcing | boot completed, `getenforce` |
| SIM, LTE registration, mobile data | in service, data network validated |
| VoLTE calls, outgoing and incoming, earpiece and speaker | call active; voice session in the vendor audio HAL; both sides audible |
| SMS sending (over IMS) | sent status; received by the other phone |
| Motorola Camera on the main and front camera | preview seen; photo captures logged by the camera HAL (picture quality not assessed); see known issues |

| Known issue | State |
|---|---|
| Motorola Camera says "Multiple cameras aren't working" (70400001): ultra-wide and telephoto are missing | cause found (Qualcomm's `ro.vendor.qti.va_aosp.support` flag is not set in this image); fixed in the next revision |
| An SMS sent to the phone did not arrive in one test | cause open |
| Carrier settings are included for one operator only (MCC/MNC 313390); other SIMs get AOSP defaults | by design so far |
| Wi-Fi calling | not offered |
| `ro.carrier` reads `unknown` | fixed in the next revision |
| SystemUI restarts for about a second right after boot | open |
| Security patch level is 2025-06-05, a year behind the stock firmware | inherent to the source baseline |

Not tested at all: Bluetooth, GNSS, NFC, fingerprint, video recording, eSIM (not supported),
flashing the image to the `system` partition.

## Before you install

- **This is a test build.** It is a userdebug image signed with the public AOSP test keys and
  has adb enabled with root available. Do not use it as a daily system.
- It is for this model and this stock firmware build only.
- The bootloader must be unlocked (verified boot state `orange`). The stock first-stage `init`
  refuses a test-keyed image with an older patch level on a locked phone.
- About 41 GiB of free user data is needed (the installer keeps a reserve the size of `super`).
- A DSU guest lives in free space of user data with its own data; stock is not modified, and a
  reboot returns to it.

## Install (Dynamic System Update)

In Git Bash every adb command with a device path needs `MSYS_NO_PATHCONV=1` in front;
otherwise the shell rewrites the path and the push fails.

```bash
MSYS_NO_PATHCONV=1 adb push system_raw.gz /storage/emulated/0/Download/
```

```bash
MSYS_NO_PATHCONV=1 adb shell am start-activity -n com.android.dynsystem/com.android.dynsystem.VerificationActivity -a android.os.image.action.START_INSTALL -d file:///storage/emulated/0/Download/system_raw.gz --el KEY_SYSTEM_SIZE 2556428288 --el KEY_USERDATA_SIZE 8589934592 --ez KEY_ONE_SHOT true
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
