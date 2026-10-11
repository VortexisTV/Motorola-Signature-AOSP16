# Building

How to get from a clone of this repository to an installable `system.img`. Every command below
was run on the development machine between 2026-10-09 and 2026-10-11; results are stated as
observed, and section 10 is the log of every build made so far.

The order matters: environment, source tree, stock firmware, build, validation, export.

## 1. What you need

| | |
|---|---|
| The phone's stock firmware package | build **W2WVS36.55-95-5-1** for the Motorola Signature (XT2603-1, `vantage_g`): the folder that contains `flashfile.xml`, here `VANTAGE_G_W2WVS36.55_95_5_1_subsidy_DEFAULT_regulatory_DEFAULT_cid50_CFC.xml`. It is not part of this repository. The build copies 34 files out of it and checks each against the SHA-256 in `vendor/motorola/vantage/proprietary-files.txt`; with any other firmware build that check stops the build |
| Disk | about 300 GB on a Linux filesystem (measured: 29 GB `.repo`, 112 GB build output, 31 GB extracted firmware, 272 GB in total) |
| Memory | 32 GB. Soong's analysis of Android 16 peaked at about 38 GB virtual; see the zram step |
| Time | source sync 29 minutes, first build 2 h 30 min on 16 threads, every later build 7 to 9 minutes |
| Network | android.googlesource.com and github.com (TrebleDroid) |

## 2. Host and build environment

What was used:

| Item | Value |
|---|---|
| Host OS | Windows 11 (10.0.26100), Ryzen 7 9800X3D (16 threads), 31 GB RAM |
| Project drive | `H:` USB SSD, **exFAT** |
| Build environment | Dedicated WSL2 distro `moto-aosp` (Ubuntu 24.04.5), its VHDX in `wsl\moto-aosp` next to the repository |

exFAT cannot hold an Android tree (no symlinks, case-insensitive), so sources, the extracted
firmware and build output live on ext4 inside the distro's VHDX. The repository itself may sit
on any filesystem.

The scripts assume three paths inside the build environment and nothing else about the host:

| Path | What |
|---|---|
| `/proj` | this repository |
| `/stockfw` | the stock firmware folder (read only) |
| `/work` | sources (`/work/aosp`), extracted firmware (`/work/fw`), created by the bootstrap |

Host changes made on the development machine (all reversible):

- `C:\Users\<user>\.wslconfig`: `memory=24GB`, `processors=16`, `swap=40GB`, swap file on the
  project drive. Delete the file and run `wsl --shutdown` to revert.
- WSL distro `moto-aosp` registered (`wsl --unregister moto-aosp` removes it and its disk).
- `git config --global --add safe.directory '<path of the repository>'`, needed on exFAT
  because it records no file ownership.

Create the distro (PowerShell or cmd; adjust the location):

```bash
wsl --install Ubuntu-24.04 --name moto-aosp --location "H:\androidtools\platform-tools\CUSTOM ROM\wsl\moto-aosp" --no-launch
```

Inside the distro, as root, point the two links at your clone and at your firmware folder, then
run the bootstrap:

```bash
ln -sfn "/mnt/h/androidtools/platform-tools/CUSTOM ROM" /proj
```

```bash
ln -sfn "/mnt/h/AndroidRoms/VANTAGE_G_W2WVS36.55_95_5_1_subsidy_DEFAULT_regulatory_DEFAULT_cid50_CFC.xml" /stockfw
```

```bash
bash /proj/vendor/motorola/vantage/scripts/wsl-bootstrap.sh
```

`wsl-bootstrap.sh` installs the AOSP build prerequisites, OpenJDK 21, the firmware tools
(`erofs-utils`, `android-sdk-libsparse-utils`, `aapt`, `apktool`, `setools`), the `repo`
launcher, creates the user `builder` and the `/work` tree. It is idempotent.

Compressed RAM swap. With 24 GB for the VM and the overflow on a USB disk swap, `soong_build`
sat at 70-80 % I/O wait and made no progress in 20 minutes. zram fixes that. Run it as root
after every start of the VM; `build.sh` refuses to start without it:

```bash
wsl -d moto-aosp -u root -e bash /proj/vendor/motorola/vantage/scripts/wsl-zram.sh
```

The WSL VM shuts down after about a minute without a running command and then loses its zram
device. Keep one command running during a work session, for example
`wsl -d moto-aosp -e tail -f /dev/null` in a second terminal.

On a native Ubuntu 24.04 machine the same scripts should work without the `wsl -d moto-aosp -u
<user> -e` prefix, given the three paths above. That has not been tried.

## 3. Source tree

| Component | Revision | Why |
|---|---|---|
| AOSP | tag `android-16.0.0_r2` (build id `BP2A.250605.031.A3`, SDK 36.0) | Matches the stock framework level (`ro.build.version.sdk_full=36.0`) and is the tag TrebleDroid's Android 16 forks are based on |
| TrebleDroid manifest | `treble_manifest` branch `android-16.0` @ `e218100` ("Up to r2", 2025-06-22) | Replaces 27 AOSP projects with TrebleDroid forks at `android-16.0.0_r2-td` (patches already applied in-tree) |
| `device_phh_treble` | branch `android-16.0` @ `9103196` (2026-07-26) | One of seven TrebleDroid projects that follow a branch instead of a tag (another is the RIL audio bridge `QcRilAm`, which this repository patches); all are pinned in the manifest below |
| Release config | `bp2a` | The android-16.0.0_r2 release configuration |

The exact commit of each of the 974 projects is recorded in
[`manifests/pinned-android-16.0.0_r2-td.xml`](manifests/pinned-android-16.0.0_r2-td.xml).
To get the tree the released images were built from:

```bash
wsl -d moto-aosp -u builder -e env PINNED=1 bash /proj/vendor/motorola/vantage/scripts/sync-source.sh
```

Without `PINNED=1` the script takes the AOSP tag plus TrebleDroid's manifest at the revision
above, which brings whatever those seven branches hold that day, and then rewrites the pinned
manifest with what it fetched. That is the way to move the baseline, not to reproduce an image;
the patches in `patches/` are only known to apply to the pinned revisions.

Observed (unpinned run of 2026-10-09): `repo sync` (shallow, `-c --no-tags`) finished in 29
minutes; one transient HTTP 500 from android.googlesource.com was retried automatically.
`.repo` is 29 GB. The pinned mode was checked up to the point where `repo` has read the
manifest (974 projects, all named by commit); a full pinned sync has not been run.

Upstream state checked on 2026-10-09: TrebleDroid's last CI release is `ci-20250617`
(android_16.0.0_r1); `ponces/treble_aosp` is archived (last push 2025-07-25) and was used as a
reference for the lunch target and sync flags only. No Android 15 patches are involved.

## 4. Stock firmware

One command unpacks the package, inventories it and checks it. Run it as root (ownership and
modes of the extracted trees are preserved) and after the source sync (it takes
`unpack_bootimg.py` from the tree):

```bash
wsl -d moto-aosp -u root -e bash /proj/vendor/motorola/vantage/scripts/extract-firmware.sh
```

What it does, in three stages (`STAGES="unpack inventory blobs"` selects them):

| Stage | Result |
|---|---|
| `unpack` | verifies every image against the MD5 in `flashfile.xml`, writes `reports/stock-firmware.sha256`; dumps the logical partitions of `super`, extracts the EROFS/ext4 trees to `/work/fw/W2WVS36.55-95-5-1/root/<partition>/`, the boot images and their ramdisks to `.../boot/`, the APEX payloads to `.../apex/` |
| `inventory` | `reports/inventory/*.json`. Three of them (`files.json`, `elf.json`, `packages.json`) are large, are needed by the validators and are not committed: this stage is what creates them in a fresh clone. Keep `packages.json` out of git; it lists the API keys the stock apps carry |
| `blobs` | copies the 34 pinned files into `vendor/motorola/vantage/proprietary/` (ignored by git), each checked against its SHA-256, and generates `Android.bp` and `vantage-vendor.mk` |

The package is only read. Nothing from it is committed.

## 5. Build

```bash
wsl -d moto-aosp -u builder -e bash /proj/vendor/motorola/vantage/scripts/sync-to-tree.sh
```

copies `vendor/motorola/vantage` and `device/motorola/vantage` into the tree, applies the
patches of `patches/` (section 5.1) and repeats the `blobs` stage inside the tree. The
repository is the source of truth; run it again after every change here.

```bash
wsl -d moto-aosp -u builder -e env TARGET=vantage_td bash /proj/vendor/motorola/vantage/scripts/build.sh
```

builds `vantage_td-bp2a-userdebug`, goal `systemimage`. The image is
`/work/aosp/out/target/product/tdgsi_arm64_ab/system.img`: raw ext4 with an AVB hashtree
footer, system, system_ext and product in one image, signed with the AOSP test keys.

Without `TARGET` the script builds the unmodified TrebleDroid product `treble_arm64_bvN`, which
was done once as a baseline. `vantage_td` inherits it and keeps `PRODUCT_DEVICE=tdgsi_arm64_ab`,
so both share one output directory and switching between them is an incremental build.

Environment overrides of `build.sh`: `TARGET`, `RELEASE` (default `bp2a`), `VARIANT` (default
`userdebug`), `GOALS` (default `systemimage`), `JOBS` (default 10; 24 GB of RAM is tight for
more). ccache is deliberately not used: the Soong sandbox mounts everything outside `out/`
read-only.

### 5.1 Source patches

Changes to projects of the tree live in `patches/<project path>/*.patch`. `sync-to-tree.sh`
applies each with `git apply` inside its project, skips one that is already applied and stops
if one no longer applies. At present there are three:

| Patch | Project | Why |
|---|---|---|
| `patches/packages/apps/QcRilAm/0001-per-slot-aidl-response-and-recovery.patch` | TrebleDroid's RIL audio bridge | one response interface was shared by both SIM slots; no wait for the HAL and no re-registration after a RIL restart; no audioserver state reporting (TELEPHONY_PORT.md section 3) |
| `patches/system/core/0001-init-export-ro.carrier-from-the-boot-parameters.patch` | init | Motorola's bootloader passes the sales channel as `androidboot.carrier` and the vendor expects init to have set `ro.carrier` from it; one entry in init's existing table |
| `patches/frameworks/native/0001-surfaceflinger-keep-the-layer-lut-descriptor-open-in-screenshots.patch` | surfaceflinger | `android-16.0.0_r2` closes the LUT descriptor of an HDR layer twice when taking a screenshot and aborts; one expression, identical to upstream `android-16.0.0_r3` |

The last two are the only changes to AOSP projects. Each patch file starts with its reason and
evidence. Everything else of this ROM lives in `vendor/motorola/vantage` and
`device/motorola/vantage`.

## 6. Validate

```bash
wsl -d moto-aosp -u root -e bash /proj/vendor/motorola/vantage/scripts/validate-image.sh
```

Run as root (it loop-mounts the image and reads stock files of mode 0600). It runs every static
check against the built image and the extracted stock vendor: the combined SELinux policy
compiled as `init` would, VINTF, native and Java linkage of the ported files, what the policy
lets the ported domains do compared with stock, the image's filesystem and content, each source
patch in the image's binaries, and what the stock first-stage `init` will do with the image.
Reports go to `reports/vantage/`. Exit status 0 means no FAIL; the last line prints the
image's size and SHA-256. For the current image the counts were preflight 27 PASS / 0 FAIL,
telephony 14 / 0, camera 10 / 0, composition 22 / 0.

A static PASS says the files and the configuration are consistent. It does not say the image
works on a phone.

## 7. Export and install

```bash
wsl -d moto-aosp -u builder -e bash /proj/vendor/motorola/vantage/scripts/export-image.sh vantage_td-mybuild
```

writes `out/vantage_td-mybuild/` in the repository: `system.img`, `system_raw.gz` (its gzip,
the form the Dynamic System Update installer takes), `SHA256SUMS`, `SIZES`, and prints the
image's SHA-256 and size.

Installing is described in [TESTING.md](TESTING.md): as a DSU guest, which leaves stock
untouched, on a phone with an unlocked bootloader. `dsu-preflight.sh` checks archive and phone
first and prints the install commands. It is pinned to the released image; two builds of the
same sources do not give the same bytes, so for your own image pass the two printed values:

```bash
IMAGE_SHA256=<sha256 of system.img> IMAGE_SIZE=<bytes> bash vendor/motorola/vantage/scripts/dsu-preflight.sh out/vantage_td-mybuild
```

## 8. After changing the source baseline

`target-system-libs.txt` (the libraries the unmodified AOSP image provides, generated from the
baseline build output) is an input of `resolve_components.py`, which computes the closure of
stock files in `proprietary-files.txt`. Regenerate both after moving to another AOSP revision,
inside the distro:

```bash
S=/proj/vendor/motorola/vantage/scripts; V=/proj/vendor/motorola/vantage; OUT=/work/aosp/out/target/product/tdgsi_arm64_ab
python3 -I $S/gen_target_libs.py --system $OUT/system --manifest $V/proprietary-files.txt > $V/target-system-libs.txt
python3 -I $S/resolve_components.py /proj/reports $V/components.json $V/proprietary-files.txt --target-system-libs $V/target-system-libs.txt
```

## 9. Signing

The build uses the AOSP test keys. Those keys are public, so an image for daily use must be
signed with private keys (`PRODUCT_DEFAULT_DEV_CERTIFICATE`); this is an open item in
[COMPATIBILITY.md](COMPATIBILITY.md). Stock apps that need platform-signature permissions are
re-signed by the build with whatever platform key the build uses; OEM-signed apps are installed
unmodified. The system security patch level (2025-06-05) is older than the vendor's
(2026-06-01); the stock first-stage `init` accepts that only on an unlocked phone
(DSU_READINESS.md section 1.1).

## 10. Build log

Every build made so far, failures included. `vantage_td` builds after the first are incremental.

| Date | Target | Result |
|---|---|---|
| 2026-10-09 20:46 | `treble_arm64_bvN-bp2a-userdebug` | Script error: `build/envsetup.sh` is not `set -u` clean. Fixed in `build.sh`. |
| 2026-10-09 20:47 | same | Aborted by hand after 20 min: Soong analysis thrashing on disk swap (see section 2). |
| 2026-10-09 21:14 | same, with zram | Soong analysis completed in about 4 minutes; then failed: `ccache: error: Read-only file system` (sandbox). ccache removed from `build.sh`. |
| 2026-10-09 21:20 | same | **Success** in 2 h 30 min (187,304 steps). `system.img` 2,211,053,568 bytes, ext4, SHA-256 `8bd6cd2e185c9b95e3a89dda62fe7ff08b197c411c6e52ebe9c9e5e813004aa6`, kept as `/work/out/baseline/system-treble_arm64_bvN.img`. Fingerprint `google/treble_arm64_bvN/tdgsi_arm64_ab:16/BP2A.250605.031.A3/...:userdebug/test-keys`, security patch 2025-06-05. |
| 2026-10-09 23:55 | `vantage_td-bp2a-userdebug` | Failed in 13 s at Soong parse: `dex_import` has no `dex_preopt` property in this tree. Generator fixed. |
| 2026-10-09 23:57 | same | **Built** in 8 min 26 s (incremental on the baseline output). `preflight.py` then reported one FAIL: `libdiag_system.so` needs `vendor.qti.diaghal-V1-ndk.so`, which stock ships in `/system/lib64` and AOSP does not. The resolver had assumed every stock `/system` library exists in AOSP; it now diffs against `target-system-libs.txt`. Image discarded. |
| 2026-10-10 00:12 | same | **Success** in 7 min 19 s. `system.img` 2,556,227,584 bytes, ext4 with an AVB hashtree footer (test key), SHA-256 `477c32e737b8b6d9cad30c7a6598107ee5dc68ae999c90fd696c10db24514a5a`. Fingerprint `google/vantage_td/tdgsi_arm64_ab:16/BP2A.250605.031.A3/...:userdebug/test-keys`. `e2fsck -fn` clean; files read back out of the image match the stock hashes. Validators: no FAIL. Superseded by the next entry. |
| 2026-10-10 | same, plus `VantageImsNetwork` and Wi-Fi calling off by default (two incremental builds; the second only changed comments and one defensive `catch`) | **Success**. `system.img` 2,556,272,640 bytes, SHA-256 `f28249c20bf4fcf778f98ef89460a54f96a224c5b0a5b5d9cb4b5e9ed6ea7f0b`, kept as `/work/out/vantage/system-vantage_td.img` and exported to `out/vantage_td-20261010/`. `e2fsck -fn` clean. Validators: no FAIL. Superseded by the next entry. |
| 2026-10-10 | same, Wi-Fi calling withdrawn from the carrier overlay (first attempt killed after 12 min of swap thrashing: the WSL VM had restarted and lost its zram device; `build.sh` now checks) | **Success**. `system.img` 2,556,272,640 bytes, SHA-256 `c353881ad3ec482aef7b02d19028f8d423d4c14aa8be085934326469a84da56b`, kept as `/work/out/vantage/system-vantage_td.img` and exported to `out/vantage_td-20261010/`. Validators: no FAIL. Superseded by the next entry. |
| 2026-10-10 | same, with the call-audio bridge patch (`patches/packages/apps/QcRilAm`) | **Success**. `system.img` 2,556,280,832 bytes, SHA-256 `c27ba0e97d4b5e93bc6e85235fede03cbf3662ea477f79641d2bd345d2fd0154`, kept as `/work/out/vantage/system-vantage_td.img` and exported to `out/vantage_td-20261010/`. Validators: no FAIL. Booted in the first DSU session (CHANGELOG.md). |
| 2026-10-10 16:00 | same, after the first DSU boot: stock system-side properties and identity (`properties.mk`), `VantageFrameworkOverlay` (WebView), audio vendor extension (`audio/vendorext`, AOSP's parameter parser service, 2 more stock files), bridge patch revision 2 | **Success** in 7 min 29 s. `system.img` 2,556,428,288 bytes, SHA-256 `af0101848774ef963763cb558ad0f1a2f908de004bb33d9e66c78a47560d3faf`. `validate-image.sh`: no FAIL (preflight 27/0/3/0, telephony 14/0/2/7, camera 10/0/3/6, composition 18/0/1/0). Exported to `out/vantage_td-20261010-r2/`. Booted in the second and third DSU session (CHANGELOG.md). |
| 2026-10-10 20:07 | same, after the third DSU session: `init/init.vantage.media.rc` (camcorder profile file), the vendor-framework flag with its own SELinux type (`sepolicy/private/property.te`), and for the first time two patches to AOSP projects (`patches/frameworks/native`: surfaceflinger screenshot fix from upstream `_r3`; `patches/system/core`: `ro.carrier`) | **Success** in 8 min 52 s. `system.img` 2,556,448,768 bytes, SHA-256 `6698676f9b43d42a43de6eee1a11a5a5d5de5a2b1bf7df6f5b26333f34a1bea1`. `validate-image.sh`: no FAIL (preflight 27/0/3/0, telephony 14/0/2/7, camera 10/0/3/6, composition 20/0/1/0; policy: camera HAL may read the flag, seven other vendor domains may not; all three patches found in the image's binaries). Exported to `out/vantage_td-20261010-r3/`. Booted in the fourth DSU session (CHANGELOG.md). |
| 2026-10-11 02:43 | same, after the fourth DSU session: `VantageRilReady` (`telephony/ril-ready/`), the telephony-ready signal for the Qualcomm RIL (first attempt 9 minutes earlier failed at `javac`: a final field used in a field initialiser) | **Success** in 7 min 19 s. `system.img` 2,556,506,112 bytes, SHA-256 `efe1b630cfdeda6f655112825d6df01aece2e0cc7fdf762b97a5296809dd9b3e`. `validate-image.sh`: no FAIL (preflight 27/0/3/0, telephony 14/0/2/7, camera 10/0/3/6, composition 22/0/1/0). The app from this build was tried on the running revision 3 guest: both slots signalled, the RIL answered both with error 0. Exported to `out/vantage_td-20261011-r4/`. Booted in the fifth DSU session (CHANGELOG.md): incoming SMS arrive. **This is the released image.** |

Baseline validation against the stock vendor (`reports/baseline/`): the combined SELinux policy
compiles with the tree's own `secilc`, radio HAL V4 is inside the framework matrix range (3-4),
the image fits `super` with 14.7 GiB to spare. As expected for an unmodified image, the vendor's
`vendor_qtelephony_202504` / `moto_camera_app_202504` rules are dead, there is no IMS service and
the AOSP APN list has no entry for 313390.
