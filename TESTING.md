# Testing

Two stages: automated host-side checks that must be clean before anything is flashed, and a
short, scripted acceptance test on the phone. The tooling never flashes, wipes or unlocks.

## First test: one controlled DSU boot

The readiness review is in [DSU_READINESS.md](DSU_READINESS.md). Nothing in this section is
run by a script on its own: the two install commands are the owner's. They write only into
free space of user data; `super`, `boot`, `vendor`, modem, persist and the stock user data are
not touched.


### Before the next test: remove the previous guest

1. Restart the phone. The one-shot boot is used up, so it starts stock.
2. On stock, open the "Dynamic System Updates" notification and tap **Discard**. The installer
   does not install over an existing guest, and this frees about 11 GB. The preflight of step A.2
   says `gsi_tool status: normal` when it is gone.

### What revision 4 is meant to change, and how to see it

| Try this | Expected | Report entry |
|---|---|---|
| Have the other phone send an SMS to this one (any time after the boot has settled) | it arrives within seconds. Messages sent to the phone while it was running an earlier revision may arrive too, late | `sms.receive` PASS; `sms.ril_ready` PASS ("the RIL was told that telephony is ready", accepted) |
| (nothing to do) | everything of the fourth session as before: calls, SMS sending, six cameras, video | the other entries as in FOURTH_BOOT_REPORT.md |
| Optional, if not done yet: in video mode take a screenshot (Power + Volume down), then press Home | the phone carries on | no `display.screenshot_lut` entry |

If `sms.ril_ready` is FAIL, do not wait for a message: send the report.

### A. On stock, before installing (about 5 minutes)

1. Battery above 50 %, the lock-screen PIN at hand, a second phone nearby.
2. Run the read-only preflight. It unpacks `system_raw.gz` and compares it with the validated
   image (`efe1b630...`, 2,556,506,112 bytes), reads the phone's state (stock build, verified
   boot state `orange`, no DSU installed, battery, free space) and prints the commands of
   section B for exactly this build. It installs nothing:

   ```bash
   ADB=/h/androidtools/platform-tools/adb.exe bash vendor/motorola/vantage/scripts/dsu-preflight.sh
   ```
3. Recommended once: the in-call reference of stock (section 2). It is the comparison point if
   call audio misbehaves on the ROM.

### B. Install and boot (the only steps that change anything)

First the archive (1.2 GB). Wait until adb prints `1 file pushed`; the installer reads this file,
and without it the notification says "Install failed" within a second.

**Git Bash:** every adb command with a device path needs `MSYS_NO_PATHCONV=1` in front. Without
it the shell rewrites `/storage/...` into `C:/Program Files/Git/storage/...` and the push ends
with `remote secure_mkdirs() failed` although it prints a transfer speed (this is what made the
first attempt on 2026-10-10 fail).

```bash
MSYS_NO_PATHCONV=1 adb push out/vantage_td-20261011-r4/system_raw.gz /storage/emulated/0/Download/
```

Run the preflight of step A.2 again. It now compares the copy on the phone with the validated
archive, and only then prints the install command:

```bash
MSYS_NO_PATHCONV=1 adb shell am start-activity -n com.android.dynsystem/com.android.dynsystem.VerificationActivity -a android.os.image.action.START_INSTALL -d file:///storage/emulated/0/Download/system_raw.gz --el KEY_SYSTEM_SIZE 2556506112 --el KEY_USERDATA_SIZE 8589934592 --ez KEY_ONE_SHOT true
```

`KEY_SYSTEM_SIZE` is the size of the validated image, so the command fits only this build
(SHA-256 `efe1b630cfdeda6f655112825d6df01aece2e0cc7fdf762b97a5296809dd9b3e`). `KEY_ONE_SHOT true`
selects the one-shot mode explicitly; it is also the stock installer's default.

Confirm with the PIN, wait for the "Dynamic System Update" notification to finish, tap
**Restart**. If the activity does not start on this user build, enable it once with
`adb shell setprop persist.sys.fflag.override.settings_dynamic_system true` or use Developer
options > DSU Loader.

### C. Diagnostics first, then the minimal real tests, in one recording

Start this as soon as the phone has restarted; it waits for the boot to finish. The image is a
userdebug build with adb enabled, so the recording works even if the screen never gets past
the boot animation.

```bash
ADB=/h/androidtools/platform-tools/adb.exe bash vendor/motorola/vantage/scripts/device-session.sh
```

1. The script saves the boot log, takes a full snapshot and prints a first report: boot
   completed, SELinux enforcing, crashes, SELinux denials, SIM, registration, IMS service, IMS
   network, call-audio bridge, camera devices; and for the DSU questions: nothing mounted over
   the image's `/system_ext` and `/product` (`boot.partition_composition`), this ROM's overlays
   active (`boot.overlays_active`), and what first-stage `init` logged about the older security
   patch level (`boot.spl_rollback`, informational). **Read it before doing anything else.** A FAIL
   there (a crash loop, no IMS service) will not get better by placing calls.
2. If the first report is acceptable, do the five actions it lists, each once: mobile data,
   one SMS each way, one outgoing call with a switch to the speaker, one incoming call, the
   camera with each lens and a short video. The script notices the calls and the camera by
   itself and saves the audio routing and camera state at the right moments.
3. Press Enter. It takes a final snapshot and writes `report.md` in
   `work/device-evidence/<time>-session/`. That directory is everything needed to diagnose a
   failure; there is no need to repeat a call for a second look.

What only the tester can add: whether both sides were audible on the earpiece and on the
speaker, and whether the photos and the video look right.

### D. Back to stock

Restart the phone (power menu or `adb reboot`). The DSU boot is one-shot: the next start is
stock. On stock a notification offers **Discard** (frees about 11 GB) or **Restart** (boots
the guest once more without reinstalling).

### E. If it does not go as planned

| What you see | What to do | Why this is safe |
|---|---|---|
| "Install failed" right after the PIN or fingerprint | run `dsu-preflight.sh`: it prints the installer's own error from the phone's log. `FileNotFoundException ... system_raw.gz` means the archive is not on the phone: the push failed (Git Bash without `MSYS_NO_PATHCONV=1`, seen 2026-10-10) or was skipped | nothing was installed; `gsi_tool status` stays `normal` |
| The installer reports an error later, during the progress | run `dsu-preflight.sh` and keep its output | nothing is activated; the installer removes what it had written |
| Boot animation for more than 10 minutes, or a reboot loop | run the recorder anyway (adb is usually up), then hold Power until the phone restarts | the single DSU boot attempt is already used up; the restart goes to stock |
| A recovery screen saying the system cannot be loaded | choose **Try again**. Do **not** choose "Factory data reset" | that entry would erase the stock user data. The guest never asks for it (its `init` refuses wipe requests while running as DSU), so the screen is not expected |
| Back on stock after a failed boot | `adb bugreport` right away | the report contains the kernel log of the failed boot |
| The guest should go away | the **Discard** button of the notification | removes the DSU images from user data |
| Anything worse | section "Rollback to stock" below | flashing stock `super` restores the system partitions; it needs a data wipe |

## 1. Automated checks (host)

All scripts are in `vendor/motorola/vantage/scripts/`, write JSON + Markdown to `reports/`,
and classify each result as PASS (verified by the check), FAIL (confirmed incompatibility),
WARNING (potential issue) or UNKNOWN (needs hardware or the carrier).

| Script | What it establishes |
|---|---|
| `firmware_hashes.py` | Stock package integrity (MD5 vs `flashfile.xml`, SHA-256 manifest) |
| `extract-firmware.sh` | Unpack, inventory, and copy the pinned stock files (aborts on any SHA-256 mismatch) |
| `analyze_firmware.py`, `dump_overlays.py`, `sepolicy_slice.py` | Inventory of packages, certificates, HALs, init services, overlays, policy |
| `check_java_linkage.py` | Every class/method/field a ported APK or JAR references exists in the image's class-loading context |
| `elf_closure.py` | DT_NEEDED closure of native libraries |
| `preflight.py` | File placement, signatures, privileged-permission allowlist (boot-critical under `enforce`), shared libraries, Java linkage, native dependencies, overlay targets, IMS binding, SELinux inputs / mapping / **combined policy compile with `secilc` as `init` does it**, radio HAL versions vs framework matrix, image size vs super group |
| `validate-telephony.py` | Radio HALs, vendor daemons, Qualcomm HAL clients (IMS, RIL audio), IMS package, IMS network requester, APN database, carrier-config overlay, OEM-signed vendor apps, and with `--aosp-tree` the call-audio patch code of the source tree |
| `validate-camera.py` | Provider HAL, app + certificate, shared/native libraries, permission sources, hidden-API and privileged allowlists, SELinux app context |
| `validate-image.sh` | Runs the three validators, then checks the image file: filesystem consistency, the content of every pinned stock file inside it, its composition and the stock first-stage `init` (next two rows) |
| `check_image_composition.py` | From the loop-mounted image: `/system_ext` and `/product` live inside it, `skip_mount.cfg` removes the stock fstab entries for both, every stock file / source-built app / overlay value / permission allowlist / SELinux entry is the intended one, and no other overlay outranks ours |
| `check_stock_init.py` | From the disassembly of the stock first-stage `init`: it reads `skip_mount.cfg`, compares security patch levels of a standalone image, and allows an older one only for verified boot state `orange` |
| `dsu-preflight.sh` | Read-only, before installing: local archive equals the validated image, phone state fits; prints the install commands |
| `device-session.sh`, `analyze_device_evidence.py` | Device side: read-only recording of one test session and its consolidated report (section "First test") |
| `collect-device-evidence.sh` | Not a check: read-only capture of device state for the acceptance test (section 4) |

All of them in one step, including the checks on the image file itself (`e2fsck`, and every
pinned stock file read back out of `system.img` and compared with its SHA-256):

```bash
wsl -d moto-aosp -u root -e bash /proj/vendor/motorola/vantage/scripts/validate-image.sh
```

The individual invocations, against an image tree (TrebleDroid output directory):

```bash
OUT=/work/aosp/out/target/product/tdgsi_arm64_ab; FW=/work/fw/W2WVS36.55-95-5-1
S=/proj/vendor/motorola/vantage/scripts
MAPS="--map /system=$OUT/system --map /system_ext=$OUT/system/system_ext --map /product=$OUT/system/product \
      --map /apex=$OUT/apex --map /vendor=$FW/root/vendor --map /odm=$FW/root/odm"
BASE="--baseline-map /system=$FW/root/system/system --baseline-map /system_ext=$FW/root/system_ext \
      --baseline-map /product=$FW/root/product --baseline-map /apex=$FW/apex"
python3 -I $S/preflight.py $MAPS $BASE --manifest /proj/vendor/motorola/vantage/proprietary-files.txt \
    --inventory /proj/reports/inventory --reports /proj/reports/vantage --secilc /work/aosp/out/host/linux-x86/bin/secilc \
    --expect-mapped vendor_qtelephony --expect-mapped moto_camera_app \
    --overlay-package com.android.phone.overlay.vantage --overlay-package android.overlay.vantage.telephony \
    --overlay-package com.android.carrierconfig.overlay.vantage \
    --system-img $OUT/system.img --super-layout $FW/super_layout.json
python3 -I $S/validate-telephony.py $MAPS --aosp-tree /work/aosp --reports /proj/reports/vantage
python3 -I $S/validate-camera.py $MAPS --inventory /proj/reports/inventory --reports /proj/reports/vantage
```

Run them as root inside the build distro: the extracted stock `vendor/build.prop` is mode 0600.

Result for the image of 2026-10-10 (`reports/vantage/`):

| Validator | PASS | FAIL | WARNING | UNKNOWN |
|---|---|---|---|---|
| `preflight.py` | 27 | 0 | 3 (the three documented linkage gaps in `ims.apk` / `moto-telephony.jar`; one vendor-labelled HIDL service type without a mapping, `sepolicy.unmapped`) | 0 |
| `validate-telephony.py` | 14 | 0 | 2 (no AOSP `radio.ims` HAL, by design of the vendor; OEM-signed vendor apps, TELEPHONY_PORT.md section 4.1) | 7 (hardware) |
| `validate-camera.py` | 10 | 0 | 3 (optional Motorola libraries absent by design; 17 vendor-private libraries, same on stock; 6 permissions whose definers are not ported) | 6 (hardware) |

The image file itself (`validate-image.sh`): `e2fsck -fn` is clean, and every stock file that
is installed unmodified was read back out of `system.img` and has its pinned SHA-256;
`ims.apk` and `VantageImsNetwork.apk` carry the build's platform certificate. The same script
checks native linkage at symbol level (12 ported libraries, 47 libraries inside the camera APK:
no unresolved import) and compares the compiled SELinux policy with the stock one for the two
ported app domains (needs `apt install setools` in the build distro).

Self-test of the validators against the **stock** firmware (results in
`reports/selftest-stock/`): preflight 0 FAIL, telephony 0 FAIL apart from the overlay that
only exists in this ROM, camera 0 FAIL. Two false positives found this way were fixed
(allowlist enforcement only applies to platform-defined permissions; HALs without a
`<version>` are version 1).

**Gate:** no image goes to the device while any check reports FAIL.

## 2. Reference captures on stock (once, before flashing, about 5 minutes)

These give the ground truth that later failures are compared against. With stock running:

```bash
adb shell dumpsys telephony.registry   > ref-telephony-registry.txt
adb shell dumpsys carrier_config       > ref-carrier-config.txt
adb shell dumpsys media.audio_policy   > ref-audio-policy-idle.txt
adb shell dumpsys media.camera         > ref-camera.txt
# place a call, and while it is connected:
adb shell dumpsys media.audio_policy   > ref-audio-policy-incall.txt
adb shell dumpsys media.audio_flinger  > ref-audio-flinger-incall.txt
adb logcat -b radio -d                 > ref-radio-incall.txt
```

Already captured by the owner or during analysis: carrier config, telephony state, radio log
(`stock-*.txt`), idle audio policy/flinger (`work/device-stock/`), and a full idle snapshot
taken with the evidence script (`work/device-evidence/...-stock-idle`).

**Still missing, and the one capture worth doing on stock before testing: the in-call audio
state.** It is prepared as a single command. It does not dial, answer or change anything; it
waits (polling the call state) until you place or answer a call yourself, then reads:

```bash
WAIT_CALL=1 ADB=/h/androidtools/platform-tools/adb.exe bash vendor/motorola/vantage/scripts/collect-device-evidence.sh incall
```

Start it, place a call, and once it prints "call active" keep the call up for about 25
seconds; switch to the speaker after the first few seconds so the second snapshot records
that route too. The result (`work/device-evidence/<time>-incall/audio-policy.txt` and
`audio-policy-second.txt`) shows the telephony audio sources, the software output each is
attached to and the patches stock creates. Run the same command on this ROM during the
acceptance test; the two are then compared line by line.

## 3. Deployment (manual; not performed by any script)

Artifacts of the validated build are in `out/vantage_td-20261011-r4/` (not in git):

| File | Use | Size |
|---|---|---|
| `system.img` | raw ext4 image for `fastboot flash system` | 2,556,506,112 bytes, SHA-256 `efe1b630cfdeda6f655112825d6df01aece2e0cc7fdf762b97a5296809dd9b3e` |
| `system_raw.gz` | the same image gzip-compressed, for DSU | see `SIZES`, `SHA256SUMS` |

Check them before use: `sha256sum -c SHA256SUMS` (Git Bash) or `Get-FileHash system.img`.
The image is signed with the public AOSP test keys and is a `userdebug` build: fine for a
test boot, not for daily use.

Facts this procedure is based on, all read from the firmware or the device:

- Bootloader already unlocked; A/B with Virtual A/B; active slot `_a`.
- `system` is a logical partition in `super` (group `mot_dp_group_a`, about 18 GB free without
  the stock system); `system`, `system_ext`, `product` are verified through
  `vbmeta` -> `vbmeta_system`; the first-stage fstab accepts `erofs` or `ext4` for `system`.
- The image carries `skip_mount.cfg`, so stock `system_ext`/`product` stay on the device,
  unmounted and untouched. `vendor`, `odm`, `boot`, `init_boot`, `vendor_boot`, `dtbo`,
  modem, persist and all calibration partitions are never written.
- Stock user data is encrypted for the stock system (metadata encryption, wrapped keys) and
  its settings databases belong to Motorola's framework. A different system cannot reuse it.

Not verified by me on this device: the exact fastboot behaviour of this bootloader
(`fastboot reboot fastboot`). The owner has flashed GSIs on this phone before; where the
steps of option B differ from what worked then, prefer what worked.

### Option A: Dynamic System Update (no wipe, recommended for the first boot test)

DSU installs the image into free space in `userdata` and boots it with its own, separate
user data. Stock stays intact; a normal reboot returns to it.

What was verified for this phone, without installing anything:

| Requirement | Evidence | Result |
|---|---|---|
| DSU is booted by first-stage `init`, not by the bootloader | the stock `init` in `init_boot` contains the DSU logic (`/metadata/gsi/dsu/booted`, `install_status`, `lp_names`, `avb_enforce`) and honours the image's `skip_mount.cfg` | present |
| `/metadata` mounted in the first stage | stock first-stage `fstab.qcom`: `/dev/block/by-name/metadata /metadata f2fs ... first_stage_mount` | present |
| System-side installer | `com.android.dynsystem` is installed, its `VerificationActivity` answers `START_INSTALL`, `gsi_tool status` reports `normal` (read from the running phone) | present |
| A system image signed with a key the device does not know | first-stage `init` (`fs_avb.cpp`): on an unlocked device verification errors, including an unknown public key, are allowed unless `/metadata/gsi/dsu/avb_enforce` exists; the phone reports `verifiedbootstate=orange` | allowed |
| Metadata-encrypted `userdata` | the installer maps the image files through device-mapper below `dm-default-key` (`fiemap_writer.cpp`), and DSU user data gets its own key directory | supported |
| Free space | on a Virtual A/B device `gsid` keeps free space equal to the size of `super` (29.0 GiB here): about 39.4 GiB must be free for this image plus 8 GiB of DSU user data | 67 GiB free |

What this does not establish: that the image boots. That needs the install, which only the
owner starts. If the install is refused or the DSU system does not come up, the phone falls
back to stock on the next reboot (one-shot boot); nothing on `super` is touched.

```bash
# from out/vantage_td-20261011-r4/ ; system_raw.gz is the gzip of the raw (non-sparse) system.img
export MSYS_NO_PATHCONV=1   # Git Bash: keep /storage/... from being rewritten into a Windows path
adb push system_raw.gz /storage/emulated/0/Download/
adb shell am start-activity -n com.android.dynsystem/com.android.dynsystem.VerificationActivity \
    -a android.os.image.action.START_INSTALL -d file:///storage/emulated/0/Download/system_raw.gz \
    --el KEY_SYSTEM_SIZE 2556506112 --el KEY_USERDATA_SIZE 8589934592 --ez KEY_ONE_SHOT true
# confirm on the phone, wait for the notification, tap "Restart"
```

`KEY_SYSTEM_SIZE` is the size of the uncompressed image in bytes.

If the activity refuses to start on the user build, enable it first with
`adb shell setprop persist.sys.fflag.override.settings_dynamic_system true` or use Developer
options > DSU Loader. If DSU cannot be used at all, option B is the alternative; it needs a
data wipe and is therefore the owner's deliberate step.

Leave it with a reboot (or `adb shell gsi_tool disable` then reboot). Caveat: under DSU the
SIM, modem and vendor are the real ones, so telephony and camera tests are meaningful, but
it is a temporary install.

### Option B: flash `system` (destructive: requires wiping user data)

```bash
adb reboot bootloader
fastboot getvar snapshot-update-status          # must be "none"
fastboot flash vbmeta --disable-verity --disable-verification vbmeta.img   # stock vbmeta from the package
fastboot reboot fastboot                        # userspace fastboot (fastbootd)
fastboot flash system system.img
fastboot -w                                     # WIPES ALL USER DATA: only after a backup and a deliberate decision
fastboot reboot
```

### Rollback to stock

From the stock package directory, with the phone in the bootloader: flash `vbmeta.img` and
`vbmeta_system.img` without flags, then every `super.img_sparsechunk.N` in order to `super`
(exactly the `flashfile.xml` steps for those partitions), then wipe user data. Motorola's
Software Fix tool does the same. The stock package's hashes are in
`reports/stock-firmware.sha256`. Never flash `bootloader.img`/`radio.img` from an older
package (anti-rollback, security version 6).

## 4. Acceptance test on the device

Start a full log before each session: `adb logcat -b all > session-N.log` and stop it after.
Record every line as PASS / FAIL with the log file; a FAIL plus its log is enough to act on.

Most of the evidence listed below can be captured in one step, from Git Bash in this folder:

```bash
ADB=/h/androidtools/platform-tools/adb.exe bash vendor/motorola/vantage/scripts/collect-device-evidence.sh boot
```

Use a label per moment (`boot` once the SIM has registered, `incall` while a call is connected,
`camera` after the camera session). The script only reads state (properties, `dumpsys`,
`logcat -d`, tombstone list) and writes to `work/device-evidence/<time>-<label>/`, which git
ignores because it contains personal data. It was run once against the stock phone
(`...-stock-idle`) as a reference.

### Session 1: boot and cellular (about 20 minutes, needs a second phone)

| # | Step | Evidence to capture |
|---|---|---|
| 1 | Boots to the launcher; `adb shell getenforce` | `Enforcing`; `adb shell dmesg | grep -i avc | head` |
| 2 | SIM detected, operator name shown | `adb shell dumpsys telephony.registry | grep -E "mServiceState|mSignalStrength"` |
| 3 | LTE / 5G registration | same dump: `mDataRegState=0`, RAT |
| 4 | Mobile data with Wi-Fi off: open a web page | `adb shell ping -c 3 8.8.8.8` |
| 4a | IMS network requested and connected | `adb shell dumpsys connectivity | grep -E "Capabilities: IMS"` shows a `REQUEST` from `vantage.telephony.imsnetwork` and a `NetworkAgentInfo` with `extra: ims`; `adb logcat -d -s VantageImsNetwork` |
| 5 | IMS service bound and registered | `adb shell dumpsys telephony.registry | grep -i ims`; `adb shell cmd phone ims get-ims-service -s 0 -c`; `adb shell dumpsys activity services org.codeaurora.ims | head` |
| 6 | Send an SMS to the second phone; receive a reply | both arrive |
| 7 | Outgoing call: both directions audible on the earpiece | during the call: `adb shell dumpsys media.audio_policy > incall-audio-policy.txt` |
| 8 | Same call: speakerphone, then mute/unmute | audible / silent as expected |
| 9 | Incoming call: rings, answer, audio both ways | |
| 10 | Call over a Bluetooth headset (if available) | audio on the headset |
| 11 | Call type | `adb logcat -b radio -d | grep -E "ImsPhone|GsmCdma" | tail` shows IMS (VoLTE) or CS |
| 12 | Wi-Fi calling is not offered in this release (TELEPHONY_PORT.md section 4.1.1): the setting should be absent. Optional experiment, last: `adb shell cmd phone cc set-value -p carrier_wfc_ims_available_bool true`, enable it in the SIM settings with Wi-Fi connected, place a call | Record `adb shell dumpsys telephony.registry | grep -iE "ims|iwlan"` and the log, then `adb shell cmd phone cc clear-values`. |
| 13 | Second SIM slot (if a second SIM is available) | repeat 2, 6, 7 on slot 2 |

Before starting: in *Settings > Phh Treble Settings > IMS features* leave everything off and do
not install "PHH IMS" (TELEPHONY_PORT.md section 1.1). The ROM requests the IMS network and
binds Qualcomm's IMS service by itself; those options would only blur the result.

If step 7 has no audio or crashes: stop there, keep `incall-audio-policy.txt`, the full log
and `MSYS_NO_PATHCONV=1 adb shell ls /data/tombstones`.

### Session 2: camera (about 15 minutes)

| # | Step | Evidence |
|---|---|---|
| 1 | Motorola Camera opens to a live preview | on failure: `adb logcat -d | grep -E "AndroidRuntime|camera5|avc: denied"` |
| 2 | Photo with the main camera is saved and viewable | file in DCIM |
| 3 | Switch to ultrawide, telephoto, front; photo with each | `adb shell dumpsys media.camera | grep -E "Camera ID|Facing"` |
| 4 | HDR scene, Night mode, Portrait, Macro, Pro mode: one photo each | photos + any error toast |
| 5 | High-resolution mode | |
| 6 | Video 4K 30 s with stabilisation; playback has audio | |
| 7 | Slow motion / high frame rate | |
| 8 | Dolby Vision option | expected absent (not ported); record |
| 9 | Zoom through the full range | lens hand-over works |

### Session 3 (optional, same day): the rest

Wi-Fi, Bluetooth pairing and media audio, GPS fix, fingerprint enrolment, NFC tag read,
auto-rotate/proximity/light sensors, 120 Hz setting, hardware video playback. These rely on
standard HALs and TrebleDroid's handling; none has device-specific work in this repository yet.
