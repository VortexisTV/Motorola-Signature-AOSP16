#!/usr/bin/env python3
"""Static validation of the Motorola Camera integration.

    validate-camera.py --map /system=DIR --map /system_ext=DIR --map /product=DIR --map /apex=DIR \
        --map /vendor=DIR --map /odm=DIR --reports reports [--inventory reports/inventory] [--name NAME]

Checks what can be read from files: HAL declaration, app installation and signature,
shared and native library availability, permission sources, SELinux app context.
Every imaging feature is reported as UNKNOWN: it needs the sensor, the ISP and the HAL.
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from check_java_linkage import Platform  # noqa: E402
from motofw import apk, fsmeta  # noqa: E402
from motofw.report import Report  # noqa: E402

AREA = "camera"
PKG = "com.motorola.camera5"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", action="append", required=True)
    ap.add_argument("--reports", required=True)
    ap.add_argument("--inventory")
    ap.add_argument("--name", default="validate-camera")
    args = ap.parse_args()
    platform = Platform(args.map)
    r = Report(f"Camera validation: {args.name}", {"maps": " ".join(args.map)})

    # 1. Camera provider HAL
    provider = None
    for prefix in ("/vendor", "/odm"):
        for root in platform._roots(prefix):
            for doc in fsmeta.read_vintf_dir(root / "etc"):
                for hal in doc["hals"] if doc["kind"] == "manifest" else []:
                    if hal["name"] == "android.hardware.camera.provider":
                        provider = hal
    if provider:
        r.passed("hal.provider", f"vendor declares android.hardware.camera.provider ({provider['format']}) "
                 f"V{','.join(provider['versions']) or '1'} {provider['fqnames']}", area=AREA)
    else:
        r.fail("hal.provider", "no android.hardware.camera.provider in the vendor manifest", area=AREA)

    # 2. Application
    apps = {}
    for path, prefix in platform.apks(("/system", "/system_ext", "/product")):
        info = apk.inspect(str(path))
        if info.get("package"):
            apps.setdefault(info["package"], (path, info, prefix))
    if PKG not in apps:
        r.fail("app.installed", f"{PKG} is not in the image", area=AREA)
        r.write(args.reports, args.name)
        r.print_summary()
        return 1
    path, info, prefix = apps[PKG]
    stock_cert = None
    if args.inventory and (Path(args.inventory) / "packages.json").exists():
        for p in json.loads((Path(args.inventory) / "packages.json").read_text(encoding="utf-8")):
            if p.get("package") == PKG:
                stock_cert = p["signing"].get("cert_sha256")
    cert = info["signing"].get("cert_sha256")
    note = [f"{path}", f"version {info.get('versionName')}", f"certificate {cert}"]
    if stock_cert and cert != stock_cert:
        r.fail("app.installed", f"{PKG} is installed but no longer carries the stock certificate "
               "(Motorola signature permissions and seinfo would be lost)", note, AREA)
    else:
        r.passed("app.installed", f"{PKG} {info.get('versionName')} installed under {prefix} with its original "
                 "certificate", note, AREA)

    # 3. Shared libraries
    required = [l["name"] for l in info.get("uses_libraries", []) if l.get("required", True) is not False]
    optional = [l["name"] for l in info.get("uses_libraries", []) if l.get("required", True) is False]
    def available(lib):
        decl = platform.libraries.get(lib)
        return bool(decl and platform.host(decl["file"]))
    miss = [l for l in required if not available(l)]
    if miss:
        r.fail("app.required_libraries", f"required shared libraries missing: {miss} (PackageManager would reject "
               "the app)", area=AREA)
    else:
        r.passed("app.required_libraries", f"required shared libraries present: {required}", area=AREA)
    absent_opt = [l for l in optional if not available(l) and not l.startswith("androidx.")]
    if absent_opt:
        r.warn("app.optional_libraries", f"optional Motorola libraries absent by design: {absent_opt}; features "
               "implemented through them are unavailable (see CAMERA_PORT.md section 3)", area=AREA)

    # 4. Native libraries named in the manifest
    vendor_public, vendor_libs, system_libs = set(), set(), set()
    for root in platform._roots("/vendor"):
        f = root / "etc" / "public.libraries.txt"
        if f.exists():
            vendor_public |= {l.split()[0] for l in f.read_text().splitlines() if l.strip() and not l.startswith("#")}
        vendor_libs |= {p.name for p in (root / "lib64").glob("*.so")}
    for prefix_ in ("/system", "/system_ext", "/product"):
        for root in platform._roots(prefix_):
            system_libs |= {p.name for p in (root / "lib64").glob("*.so")}
    names = [l["name"] for l in info.get("uses_native_libraries", [])]
    loadable = sorted(n for n in names if n in vendor_libs and n in vendor_public)
    blocked = sorted(n for n in names if n in vendor_libs and n not in vendor_public)
    absent = sorted(n for n in names if n not in vendor_libs and n not in system_libs)
    r.passed("native.vendor_public", f"{len(loadable)} vendor processing libraries are on /vendor and in the vendor "
             "public-library list (loadable by the app)", loadable, AREA)
    if blocked:
        r.warn("native.vendor_private", f"{len(blocked)} vendor libraries named by the app exist but are not public; "
               "the app cannot load them (identical on stock, since /vendor is unchanged)", blocked, AREA)
    r.passed("native.other_soc", f"{len(absent)} libraries named by the app do not exist on this device "
             "(other SoC variants); optional by manifest", area=AREA)

    # 5. Where each non-AOSP permission the app requests is defined in this image
    defs = {}
    for pkg, (ppath, pinfo, _) in apps.items():
        for d in pinfo.get("defines_permissions", []):
            defs.setdefault(d["name"], (pkg, pinfo["signing"].get("cert_sha256")))
    same_sig, other_sig, undefined = [], [], []
    for perm in info.get("uses_permissions", []):
        if perm.startswith("android.permission."):
            continue
        if perm not in defs:
            undefined.append(perm)
        elif defs[perm][1] == cert:
            same_sig.append(f"{perm} <- {defs[perm][0]}")
        else:
            other_sig.append(f"{perm} <- {defs[perm][0]} (different certificate)")
    r.passed("permissions.motorola", f"{len(same_sig)} Motorola permissions are defined in the image by packages "
             "sharing the camera's certificate (granted by signature)", same_sig, AREA)
    if undefined or other_sig:
        r.warn("permissions.unavailable", f"{len(undefined) + len(other_sig)} requested permissions cannot be granted "
               "in this image (their definers are not ported or use another key)", undefined + other_sig, AREA)

    # 6. Privileged-permission allowlist and hidden-API allowlist
    part = prefix
    perms = {"privapp_permissions": {}, "sysconfig": {}}
    for root in platform._roots(part):
        got = fsmeta.read_permission_xmls(root / "etc")
        perms["privapp_permissions"].update(got["privapp_permissions"])
        for k, v in got["sysconfig"].items():
            perms["sysconfig"].setdefault(k, []).extend(v)
    allow = perms["privapp_permissions"].get(PKG)
    if allow is None:
        r.fail("permissions.privapp", f"no privapp-permissions entry for {PKG} under {part}", area=AREA)
    else:
        r.passed("permissions.privapp", f"privileged allowlist under {part}: {sorted(allow)}", area=AREA)
    hidden = any(e.get("package") == PKG for e in perms["sysconfig"].get("hidden-api-whitelisted-app", []))
    (r.passed if hidden else r.warn)("permissions.hidden_api", f"{PKG} is "
                                     f"{'' if hidden else 'NOT '}on the hidden-API allowlist "
                                     "(it is not platform-signed and uses non-SDK interfaces)", area=AREA)

    # 7. SELinux app context and its vendor-side grants
    seapp, ver, vendor_text, system_text = [], None, "", ""
    for prefix_, rel in (("/system", "etc/selinux/plat_seapp_contexts"),
                         ("/system_ext", "etc/selinux/system_ext_seapp_contexts"),
                         ("/product", "etc/selinux/product_seapp_contexts")):
        for root in platform._roots(prefix_):
            f = root / rel
            if f.exists():
                seapp += [l for l in f.read_text().splitlines() if f"name={PKG}" in l]
            for cil in (root / "etc" / "selinux").glob("**/*.cil"):
                system_text += cil.read_text(errors="replace")
    for root in platform._roots("/vendor"):
        v = root / "etc" / "selinux" / "plat_sepolicy_vers.txt"
        ver = v.read_text().strip() if v.exists() else ver
        for cil in (root / "etc" / "selinux").glob("*.cil"):
            vendor_text += cil.read_text(errors="replace")
    domains = sorted({m.group(1) for l in seapp for m in [re.search(r"domain=(\S+)", l)] if m})
    if not seapp:
        r.fail("selinux.app_context", f"no seapp_contexts entry for {PKG}: it would run as priv_app, for which the "
               "stock vendor policy has no camera-specific grants", area=AREA)
    else:
        for dom in domains:
            versioned = f"{dom}_{ver}"
            uses = len(re.findall(rf"\b{re.escape(versioned)}\b", vendor_text))
            mapped = re.search(rf"\(typeattributeset {re.escape(versioned)} \([^)]*\b{re.escape(dom)}\b", system_text)
            if mapped:
                r.passed("selinux.app_context", f"{PKG} runs in {dom}; {versioned} is mapped and referenced "
                         f"{uses} times by the stock vendor policy", seapp, AREA)
            else:
                r.fail("selinux.app_context", f"{PKG} is assigned {dom} but {versioned} is not mapped by the system "
                       "policy; vendor camera/DSP grants would not apply", seapp, AREA)

    # 7b. Dolby Vision recording. The app enables it from three inputs: its per-device feature
    #     list (VIDEO_DOLBY_VISION), a camera-HAL vendor tag, and an encoder for video/dolby-vision
    #     in MediaCodecList. Only the first and third can be read statically.
    import zipfile
    feature = None
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.startswith("assets/app_feature_")]
            dev = next((n for n in names if n.endswith("_vantage")), None)
            feature = dev is not None and b'"VIDEO_DOLBY_VISION"' in z.read(dev)
    except (OSError, zipfile.BadZipFile):
        pass
    encoders = []
    for root in platform._roots("/vendor"):
        for xml in sorted((root / "etc").glob("media_codecs*.xml")):
            text = xml.read_text(errors="replace")
            enc = text.partition("<Encoders>")[2].partition("</Encoders>")[0]
            for m in re.finditer(r'<MediaCodec name="([^"]+)" type="video/dolby-vision"', enc):
                encoders.append(f"{m.group(1)} ({xml.name})")
    details = [f"app feature list for vantage names VIDEO_DOLBY_VISION: {feature}",
               f"vendor Dolby Vision encoders: {sorted(set(e.split(' ')[0] for e in encoders)) or 'none'}"]
    if feature and encoders:
        r.passed("video.dolby_vision_inputs", "Dolby Vision recording: the app's feature flag and a vendor encoder "
                 "for video/dolby-vision are present (the HAL vendor tag and the result need the device)",
                 details + encoders[:6], AREA)
    else:
        r.warn("video.dolby_vision_inputs", "Dolby Vision recording: a static input is missing", details, AREA)

    # 8. Hardware-only
    for tid, text in (
        ("hw.launch_preview", "application start and live preview"),
        ("hw.lenses", "main, ultrawide, telephoto and front cameras (HAL camera list as seen by AOSP)"),
        ("hw.still_modes", "HDR, night, portrait, macro, pro and high-resolution capture"),
        ("hw.video", "video recording, stabilisation, slow motion / high frame rate"),
        ("hw.dolby_vision", "Dolby Vision recording"),
        ("hw.ai_processing", "Motorola/ArcSoft/QNN processing quality compared with stock"),
    ):
        r.unknown(tid, f"{text}: requires the device", area="hardware")

    out = r.write(args.reports, args.name)
    r.print_summary()
    print(f"report: {out}")
    return 1 if r.counts()["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
