#!/usr/bin/env python3
"""Check what a single GSI/DSU system image really contains, read from the image itself.

    check_image_composition.py --root MNT --manifest proprietary-files.txt --repo /proj
        --stock FW/root --fstab FW/.../fstab.qcom --stock-overlays reports/inventory/overlays.json
        --hostbin AOSP/out/host/linux-x86/bin --out reports/vantage

MNT is the image mounted read-only (validate-image.sh does that). The questions answered:

  layout    is /system_ext and /product content inside the image, and does skip_mount.cfg remove
            every stock fstab entry that would otherwise be mounted on top of it?
  stock     is every file of the blob manifest in the image, byte-identical to the stock file
            (or, for the re-signed IMS app, identical apart from the signature)?
  built     are the source-built apps, overlays, permission allowlists and SELinux entries in the
            image what the repository says?
  overlays  can another overlay (in the image, or on the stock /vendor and /odm that stay mounted)
            still win over a value our overlays set?

Static evidence about the image file. Whether the phone then mounts it this way is a boot-time
fact: analyze_device_evidence.py checks /proc/mounts of the running guest.
"""
import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NL = chr(10)
# OverlayConfig: partitions in increasing precedence; within one partition, android:priority.
PARTITION_ORDER = ["system", "vendor", "odm", "oem", "product", "system_ext"]
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
RESULTS = []


def add(status, check, summary, evidence=()):
    RESULTS.append({"status": status, "check": check, "summary": summary, "evidence": [str(e) for e in evidence]})
    print("  [%-7s] %s: %s" % (status, check, summary))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def run(*cmd):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, errors="replace").stdout


def image_path(root, rel):
    """manifest path '<partition>/<sub>' -> path inside the mounted GSI image"""
    part, sub = rel.split("/", 1)
    return root / "system" / sub if part == "system" else root / "system" / part / sub


def stock_path(stock, rel):
    part, sub = rel.split("/", 1)
    return stock / "system" / "system" / sub if part == "system" else stock / part / sub


class Tools:
    def __init__(self, hostbin):
        self.aapt2 = Path(hostbin) / "aapt2"
        self.apksigner = Path(hostbin) / "apksigner"

    def signer(self, apk):
        m = re.search(r"Signer #1 certificate SHA-256 digest: ([0-9a-f]{64})", run(self.apksigner, "verify", "--print-certs", apk))
        return m.group(1) if m else None

    def manifest(self, apk):
        """{'package':..., 'overlay': {attr: value}} from the binary manifest"""
        out = {"package": None, "overlay": None, "uses": []}
        element = None
        for line in run(self.aapt2, "dump", "xmltree", "--file", "AndroidManifest.xml", apk).splitlines():
            s = line.strip()
            if s.startswith("E: "):
                element = s[3:].split(" ")[0]
                if element == "overlay":
                    out["overlay"] = {}
            elif s.startswith("A: "):
                m = re.match(r"A: (?:[^ =]*:)?([A-Za-z]+)(?:[(]0x[0-9a-f]+[)])?=(.*)$", s)
                if not m:
                    continue
                key, val = m.group(1), m.group(2)
                val = val[1:].split(chr(34))[0] if val.startswith(chr(34)) else val.split(" ")[0]
                if element == "manifest" and key == "package":
                    out["package"] = val
                elif element == "overlay":
                    out["overlay"][key] = val
                elif element in ("uses-library", "uses-permission") and key == "name":
                    out["uses"].append((element, val))
        return out

    def resources(self, apk):
        """{'type/name': 'default-configuration value text'}"""
        res, name = {}, None
        for line in run(self.aapt2, "dump", "resources", apk).splitlines():
            m = re.match(r"^ +resource 0x[0-9a-f]+ ([^ ]+)", line)
            if m:
                name = m.group(1)
                res[name] = ""
            elif name and re.match(r"^ +type ", line):
                name = None
            elif name:
                s = line.strip()
                if s.startswith("() "):
                    res[name] = s[3:]
                elif s.startswith("[") and res[name].startswith("(array)"):
                    res[name] = s
        return res

    def xmltree(self, apk, member):
        """[(depth, tag, {attr: value}, text)] of a compiled XML file inside an APK"""
        out = []
        for line in run(self.aapt2, "dump", "xmltree", "--file", member, apk).splitlines():
            s = line.strip()
            depth = (len(line) - len(line.lstrip())) // 2
            if s.startswith("E: "):
                out.append([depth, s[3:].split(" ")[0], {}, ""])
            elif s.startswith("A: ") and out:
                key, val = s[3:].split("=", 1)
                val = val[1:].split(chr(34))[0] if val.startswith(chr(34)) else val.split(" ")[0]
                out[-1][2][key.split(":")[-1].split("(")[0]] = val
            elif s.startswith("T: ") and out:
                out[-1][3] = s[3:].strip().strip(chr(39))
        return [(t, a, x) for _, t, a, x in out]


def check_layout(root, fstab):
    bad = []
    for name in ("system_ext", "product"):
        link, inner = root / name, root / "system" / name
        target = os.readlink(link) if link.is_symlink() else None
        if target != "/system/" + name:
            bad.append("/%s is %s, expected a symlink to /system/%s" % (name, target or "not a symlink", name))
        if inner.is_symlink() or not inner.is_dir():
            bad.append("/system/%s is not a real directory" % name)
    counts = {n: sum(len(f) for _, _, f in os.walk(root / "system" / n)) for n in ("system_ext", "product")}
    add("FAIL" if bad else "PASS", "layout.single_image",
        "; ".join(bad) if bad else "/system_ext and /product are symlinks into the image; content lives in "
        "/system/system_ext (%d files) and /system/product (%d files)" % (counts["system_ext"], counts["product"]))

    cfg = root / "system/system_ext/etc/init/config/skip_mount.cfg"
    if not cfg.is_file():
        add("FAIL", "layout.skip_mount", "skip_mount.cfg is missing: stock /system_ext and /product would be mounted over the image")
        return
    patterns = [l for l in cfg.read_text().split(NL) if l and not l.startswith("#")]
    entries = []
    for line in Path(fstab).read_text().split(NL):
        f = line.split()
        if len(f) >= 4 and not line.startswith("#"):
            entries.append((f[0], f[1], f[2]))
    skipped = sorted({(d, m) for d, m, _ in entries if any(fnmatch.fnmatchcase(m, p) for p in patterns)})
    kept = sorted({m for _, m, _ in entries} - {m for _, m in skipped})
    must = {m for _, m, _ in entries if m in ("/system_ext", "/product")}
    missing = must - {m for _, m in skipped}
    # Anything else the stock fstab would put on or under the image's system_ext/product trees.
    shadow = [m for m in kept if m.startswith(("/system_ext", "/product", "/system/"))]
    ok = must == {"/system_ext", "/product"} and not missing and not shadow
    add("PASS" if ok else "FAIL", "layout.skip_mount",
        "skip_mount.cfg removes the stock fstab entries %s; no remaining entry mounts on or under /system, "
        "/system_ext or /product" % ", ".join("%s (%s)" % (m, d) for d, m in skipped) if ok else
        "stock fstab entries not neutralised: %s" % ", ".join(sorted(missing) + shadow),
        ["patterns: " + " ".join(patterns), "still mounted from the stock fstab: " + " ".join(kept)])


def check_stock(root, stock, manifest, tools):
    plain = links = 0
    bad = []
    resigned = []
    for line in Path(manifest).read_text().split(NL):
        if not line or line.startswith("#"):
            continue
        spec, _, pinned = line.partition("|")
        rel, flags = spec.split(";")[0], spec.split(";")[1:]
        img = image_path(root, rel)
        link = [f.split("=", 1)[1] for f in flags if f.startswith("SYMLINK=")]
        if link:
            links += 1
            got = os.readlink(img) if img.is_symlink() else None
            # resolve inside the image: /system_ext/... -> <root>/system/system_ext/...
            inner = root / "system" / link[0].lstrip("/") if not link[0].startswith("/system/") else root / link[0].lstrip("/")
            if got != link[0] or not inner.is_file():
                bad.append("%s: link is %s, expected %s (target present: %s)" % (rel, got, link[0], inner.is_file()))
            continue
        if not img.is_file():
            bad.append("%s: missing in the image" % rel)
            continue
        if any(f.startswith("CERT=") for f in flags):
            resigned.append((rel, pinned))
            continue
        plain += 1
        got, ref = sha256(img), sha256(stock_path(stock, rel))
        if not (got == pinned == ref):
            bad.append("%s: image %s, manifest %s, stock %s" % (rel, got[:16], pinned[:16], ref[:16]))
    add("FAIL" if bad else "PASS", "stock.files",
        "%d problems" % len(bad) if bad else "%d stock files in the image are byte-identical to the manifest hash and to "
        "the stock firmware; %d JNI links point at files inside the image" % (plain, links), bad)

    platform = tools.signer(root / "system/framework/framework-res.apk")
    for rel, pinned in resigned:
        img, ref = image_path(root, rel), stock_path(stock, rel)
        problems = []
        if sha256(ref) != pinned:
            problems.append("stock file does not match the manifest hash")
        a, b = zipfile.ZipFile(img), zipfile.ZipFile(ref)
        payload = lambda z: {i.filename: (i.CRC, i.file_size) for i in z.infolist() if not i.filename.startswith("META-INF/")}
        pa, pb = payload(a), payload(b)
        if pa != pb:
            diff = sorted(set(pa) ^ set(pb)) + sorted(k for k in set(pa) & set(pb) if pa[k] != pb[k])
            problems.append("payload differs from stock: " + ", ".join(diff[:8]))
        signer = tools.signer(img)
        if signer != platform:
            problems.append("signer %s is not this build's platform certificate %s" % (signer, platform))
        add("FAIL" if problems else "PASS", "stock.resigned",
            "; ".join(problems) if problems else "%s: all %d payload entries equal the stock APK (name, size, CRC-32); "
            "only the signature differs, signer = the certificate of this image's framework-res.apk" % (rel, len(pa)),
            ["stock signer %s" % tools.signer(ref), "image signer %s" % signer])
    return platform


def norm(value):
    """aapt2 value text -> comparable form"""
    v = value.strip()
    if v.startswith("["):
        return [i.strip().strip(chr(34)) for i in v.strip("[]").split(", ")]
    return v.strip(chr(34))


def source_values(res_dir):
    """{'type/name': expected} from res/values/*.xml"""
    out = {}
    for f in sorted((res_dir / "values").glob("*.xml")) if (res_dir / "values").is_dir() else []:
        for e in ET.parse(f).getroot():
            if e.tag.endswith("-array"):
                out["array/" + e.get("name")] = [(i.text or "").strip() for i in e.findall("item")]
            else:
                out[e.tag + "/" + e.get("name")] = (e.text or "").strip()
    return out


def source_xml(path):
    out = []
    def walk(e):
        out.append((e.tag, dict(e.attrib), (e.text or "").strip()))
        for c in e:
            walk(c)
    walk(ET.parse(path).getroot())
    return out


def check_built(root, repo, tools, platform):
    v = repo / "vendor/motorola/vantage"
    # Apps built from source.
    apps = [("system/system_ext/app/VantageImsNetwork/VantageImsNetwork.apk",
             ET.parse(v / "telephony/ims-network/AndroidManifest.xml").getroot().get("package")),
            ("system/system_ext/app/VantageRilReady/VantageRilReady.apk",
             ET.parse(v / "telephony/ril-ready/AndroidManifest.xml").getroot().get("package")),
            ("system/app/QcRilAm/QcRilAm.apk", "me.phh.qcrilam")]
    for rel, package in apps:
        apk = root / rel
        if not apk.is_file():
            add("FAIL", "built.app", "%s is missing" % rel)
            continue
        got, signer = tools.manifest(apk)["package"], tools.signer(apk)
        ok = got == package and signer == platform
        add("PASS" if ok else "FAIL", "built.app", "/%s: package %s, signed with %s" % (
            rel, got, "this image's platform certificate" if signer == platform else "ANOTHER certificate " + str(signer)))
    # The telephony-ready sender: system UID (the domain the vendor policy lets reach the RIL's OEM
    # hook service), persistent, and carrying the request the stock client sends.
    apk = root / "system/system_ext/app/VantageRilReady/VantageRilReady.apk"
    if apk.is_file():
        tree = run(tools.aapt2, "dump", "xmltree", "--file", "AndroidManifest.xml", apk)
        with zipfile.ZipFile(apk) as z:
            dex = b"".join(z.read(n) for n in z.namelist() if n.endswith(".dex"))
        problems = []
        if "android.uid.system" not in tree:
            problems.append("not in the system UID")
        if not re.search(r"persistent[^=]*=(true|.*0xffffffff)", tree):
            problems.append("not persistent")
        for literal in (b"QOEMHOOK", b"vendor.qti.hardware.radio.qcrilhook.IQtiOemHook", b"/oemhook"):
            if literal not in dex:
                problems.append("code lacks %s" % literal.decode())
        add("FAIL" if problems else "PASS", "built.ril_ready",
            "VantageRilReady: " + "; ".join(problems) if problems else
            "VantageRilReady runs in the system UID, is persistent and carries the OEM hook request for the RIL")
    # The RIL audio bridge must be the patched one: look for literals the patch adds.
    patch = repo / "patches/packages/apps/QcRilAm/0001-per-slot-aidl-response-and-recovery.patch"
    apk = root / "system/app/QcRilAm/QcRilAm.apk"
    if patch.is_file() and apk.is_file():
        code, perms, current = [], [], ""
        for l in patch.read_text(errors="replace").split(NL):
            if l.startswith("+++ "):
                current = l
            elif current.endswith((".kt", ".java")):
                code.append(l)
            elif current.endswith("AndroidManifest.xml") and l.startswith("+") and "uses-permission" in l:
                perms += re.findall("android:name=" + chr(34) + "([^" + chr(34) + "]+)", l)
        lit = lambda lines: {m for l in lines for m in re.findall(chr(34) + "([^" + chr(34) + "$]{14,})" + chr(34), l)}
        added = lit(l for l in code if l.startswith("+")) - lit(l for l in code if l.startswith("-"))
        z = zipfile.ZipFile(apk)
        dex = b"".join(z.read(n) for n in z.namelist() if n.endswith(".dex"))
        found = sorted(s for s in added if s.encode() in dex)
        declared = {n for kind, n in tools.manifest(apk)["uses"] if kind == "uses-permission"}
        ok = bool(dex) and added and len(found) == len(added) and set(perms) <= declared
        add("PASS" if ok else "FAIL", "built.qcrilam_patched",
            "QcRilAm.apk in the image contains all %d string literals that only the reliability patch adds, and "
            "declares the permission it adds (%s)" % (len(added), ", ".join(perms))
            if ok else "QcRilAm.apk does not look patched: %d of %d patch-only literals found, permissions %s" % (
                len(found), len(added), sorted(set(perms) - declared) or "ok"),
            found[:6] + ["not found: " + s for s in sorted(added - set(found))])

    # Overlays: manifest and every value against the source.
    for manifest in sorted(v.glob("*/*/*/AndroidManifest.xml")):
        src = ET.parse(manifest).getroot()
        ov = src.find("overlay")
        if ov is None:
            continue
        name = manifest.parent.name
        apk = root / "system/product/overlay" / (name + ".apk")
        if not apk.is_file():
            add("FAIL", "built.overlay", "%s.apk is missing from /product/overlay" % name)
            continue
        got = tools.manifest(apk)
        problems = []
        if got["package"] != src.get("package"):
            problems.append("package %s" % got["package"])
        for key in ("targetPackage", "isStatic", "priority"):
            if (got["overlay"] or {}).get(key) != ov.get(ANDROID_NS + key):
                problems.append("%s=%s, source says %s" % (key, (got["overlay"] or {}).get(key), ov.get(ANDROID_NS + key)))
        want = source_values(manifest.parent / "res")
        have = {k: norm(x) for k, x in tools.resources(apk).items() if not k.startswith("xml/")}
        if want != have:
            problems.append("values differ: " + ", ".join(sorted(k for k in set(want) | set(have) if want.get(k) != have.get(k))))
        xml_count = 0
        for xf in sorted((manifest.parent / "res/xml").glob("*.xml")) if (manifest.parent / "res/xml").is_dir() else []:
            a, b = source_xml(xf), tools.xmltree(apk, "res/xml/" + xf.name)
            xml_count += len(a)
            if a != b:
                first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
                problems.append("res/xml/%s differs from the source at element %d (%d vs %d elements)" % (xf.name, first, len(a), len(b)))
        add("FAIL" if problems else "PASS", "built.overlay",
            "%s: %s" % (name, "; ".join(problems)) if problems else
            "%s -> %s, static, priority %s: %d values and %d XML elements equal the source" % (
                name, ov.get(ANDROID_NS + "targetPackage"), ov.get(ANDROID_NS + "priority"), len(want), xml_count),
            ["%s = %s" % (k, x) for k, x in sorted(have.items())])

    # Files copied by vantage.mk (permission allowlists) are the repository files.
    copies = re.findall(r"(vendor/motorola/vantage/[^ :]+):[$][(]TARGET_COPY_OUT_([A-Z_]+)[)]/([^ " + NL + "]+)", (v / "vantage.mk").read_text())
    bad = []
    for src, part, dest in copies:
        img = root / "system" / part.lower() / dest
        if not img.is_file() or sha256(img) != sha256(repo / src):
            bad.append("/%s/%s" % (part.lower(), dest))
    add("FAIL" if bad or not copies else "PASS", "built.permissions",
        "differs or missing: " + ", ".join(bad) if bad else "%d privileged-permission allowlists in the image equal the "
        "repository files: %s" % (len(copies), ", ".join("/%s/%s" % (p.lower(), d) for _, p, d in copies)))
    # Each privileged stock app has its allowlist on its own partition (PackageManager requires that).
    for line in (v / "proprietary-files.txt").read_text().split(NL):
        spec = line.partition("|")[0]
        if ";PRIV" not in spec:
            continue
        rel = spec.split(";")[0]
        part, package = rel.split("/")[0], tools.manifest(image_path(root, rel))["package"]
        holders = [f.name for f in (root / "system" / part / "etc/permissions").glob("*.xml")
                   if "privapp-permissions package=" + chr(34) + package + chr(34) in f.read_text(errors="replace")]
        add("PASS" if holders else "FAIL", "built.privapp_partition",
            "%s (/%s) has its allowlist on the same partition: %s" % (package, rel, ", ".join(holders) or "NONE"))

    # SELinux: our seapp_contexts lines and types are in the image's system_ext policy.
    sel = root / "system/system_ext/etc/selinux"
    have_lines = {frozenset(l.split()) for l in (sel / "system_ext_seapp_contexts").read_text().split(NL) if l.strip()}
    want_lines = [l for l in (v / "sepolicy/private/seapp_contexts").read_text().split(NL) if l.strip() and not l.startswith("#")]
    missing = [l for l in want_lines if frozenset(l.split()) not in have_lines]
    types = re.findall(r"^type ([a-z0-9_]+)", (v / "sepolicy/public/vantage_public.te").read_text(), re.M)
    cil = (sel / "system_ext_sepolicy.cil").read_text()
    no_type = [t for t in types if "(type %s)" % t not in cil]
    add("FAIL" if missing or no_type else "PASS", "built.sepolicy",
        "missing: " + "; ".join(missing + no_type) if missing or no_type else
        "system_ext policy in the image declares %s and carries all %d seapp_contexts entries" % (", ".join(types), len(want_lines)))


def read_props(path):
    out = {}
    if path.is_file():
        for line in path.read_text(errors="replace").split(NL):
            if "=" in line and not line.startswith("#"):
                k, _, val = line.partition("=")
                out[k.strip()] = val.strip()   # a later line of the same file wins, as in init
    return out


def check_properties(root, repo, tools):
    """properties.mk -> the build.prop of the partition it names; identity; audio vendor extension."""
    v = repo / "vendor/motorola/vantage"
    files = {"SYSTEM": root / "system/build.prop", "SYSTEM_EXT": root / "system/system_ext/etc/build.prop",
             "PRODUCT": root / "system/product/etc/build.prop"}
    have = {k: read_props(f) for k, f in files.items()}
    want, part = [], None
    for line in (v / "properties.mk").read_text().split(NL):
        m = re.match(r"^PRODUCT_(SYSTEM_EXT|SYSTEM|PRODUCT)_PROPERTIES [+]=", line)
        if m:
            part = m.group(1)
        elif part and re.match(r"^ +[A-Za-z0-9_.]+=", line):
            k, _, val = line.strip().rstrip(chr(92)).strip().partition("=")
            want.append((part, k, val))
        elif not line.strip():
            part = None
    bad = ["%s: %s=%s, image has %s" % (p_.lower(), k, val, have[p_].get(k)) for p_, k, val in want if have[p_].get(k) != val]
    add("FAIL" if bad or not want else "PASS", "built.properties",
        "; ".join(bad) if bad else "all %d stock properties of properties.mk are in the build.prop of the partition stock uses" % len(want), bad)

    # What init will make of the identity: base properties set in /product win; brand, model and
    # manufacturer are derived from ro.product.product.* (default source order starts with product).
    prod = have["PRODUCT"]
    ident = {"device": prod.get("ro.product.device"), "name": prod.get("ro.product.name"),
             "brand": prod.get("ro.product.brand") or prod.get("ro.product.product.brand"),
             "manufacturer": prod.get("ro.product.manufacturer") or prod.get("ro.product.product.manufacturer"),
             "model": prod.get("ro.product.model") or prod.get("ro.product.product.model")}
    stock = {"device": "vantage", "name": "vantage_g", "brand": "motorola", "manufacturer": "motorola", "model": "motorola signature"}
    add("PASS" if ident == stock else "FAIL", "built.identity",
        "ro.product.device/name/brand/manufacturer/model will be %s: the stock values" % "/".join(ident[k] or "?" for k in stock)
        if ident == stock else "identity differs from stock: %s" % ident)

    # Audio vendor extension: host service, loader, stock library, labels, properties.
    ext = root / "system/system_ext"
    problems = []
    for rel in ("bin/hw/android.hardware.audio.parameter_parser.example_service",
                "etc/init/android.hardware.audio.parameter_parser.example_service.rc",
                "lib64/libvantage_audiohalvendorext.so", "lib64/libaudiohalvendorextn.so", "lib64/qti-audio-types-aidl-V1-ndk.so"):
        if not (ext / rel).is_file():
            problems.append("missing /system_ext/" + rel)
    loader = ext / "lib64/libvantage_audiohalvendorext.so"
    if loader.is_file() and b"createIHalAdapterVendorExtension" not in loader.read_bytes():
        problems.append("the loader does not export createIHalAdapterVendorExtension")
    stocklib = ext / "lib64/libaudiohalvendorextn.so"
    if stocklib.is_file() and b"registerInterface" not in stocklib.read_bytes():
        problems.append("the stock library has no registerInterface")
    sel = ext / "etc/selinux"
    if "android.media.audio.IHalAdapterVendorExtension/default" not in (sel / "system_ext_service_contexts").read_text():
        problems.append("service name not in system_ext_service_contexts")
    if "audio_vendor_parameter_parser_exec" not in (sel / "system_ext_file_contexts").read_text():
        problems.append("service binary not labelled in system_ext_file_contexts")
    if "(type audio_vendor_parameter_parser)" not in (sel / "system_ext_sepolicy.cil").read_text():
        problems.append("domain not in the system_ext policy")
    se = have["SYSTEM_EXT"]
    if se.get("ro.audio.ihaladaptervendorextension_enabled") != "true" or             se.get("ro.audio.ihaladaptervendorextension_libname") != "libvantage_audiohalvendorext.so":
        problems.append("extension properties not set")
    add("FAIL" if problems else "PASS", "built.audio_vendor_extension",
        "; ".join(problems) if problems else "audio parameter parser service, loader, stock library and its dependency, "
        "service and file labels, policy domain and both properties are in the image")

    # WebView: Android 16 uses the first availableByDefault provider and nothing else.
    best = None
    for part in ("product", "system_ext"):
        for apk in sorted((root / "system" / part / "overlay").rglob("*.apk")):
            with zipfile.ZipFile(apk) as z:
                if "res/xml/config_webview_packages.xml" not in z.namelist():
                    continue
            m = tools.manifest(apk)
            o = m["overlay"] or {}
            if o.get("targetPackage") == "android" and o.get("isStatic") == "true":
                rank = (PARTITION_ORDER.index(part), int(o.get("priority", "0")))
                if best is None or rank > best[0]:
                    best = (rank, apk, m["package"])
    src = best[1] if best else root / "system/framework/framework-res.apk"
    default = next((a.get("packageName") for t, a, _ in tools.xmltree(src, "res/xml/config_webview_packages.xml")
                    if t == "webviewprovider" and a.get("availableByDefault") == "true"), None)
    installed = [str(a.relative_to(root)) for a in (root / "system").rglob("*.apk")
                 if "webview" in a.name.lower() and tools.manifest(a)["package"] == default]
    add("PASS" if installed else "FAIL", "built.webview_default",
        "the effective WebView provider list (%s) has %s as its default, which is /%s" % (
            best[2] if best else "framework-res", default, installed[0]) if installed else
        "the effective WebView provider list (%s) has %s as its default and no such package is in the image" % (
            best[2] if best else "framework-res", default))


def check_media_and_flag(root, stock):
    """Camcorder profile selection and the vendor-framework flag that only the camera HAL may read."""
    ext = root / "system/system_ext"
    rc = ext / "etc/init/init.vantage.media.rc"
    text = rc.read_text() if rc.is_file() else ""
    problems = []
    wanted = ("on property:ro.media.xml_variant.codecs=*",
              "setprop ro.media.xml_variant.profiles ${ro.media.xml_variant.codecs}")
    if not all(w in text for w in wanted):
        problems.append("/system_ext/etc/init/init.vantage.media.rc is missing or has no trigger")
    # Every variant the vendor script can choose on this platform needs a profile file, as on stock.
    script = stock / "vendor/bin/init.qti.media.sh"
    variants = sorted(set(re.findall(r'target_variant "(_canoe[a-z0-9_]*)"', script.read_text()))) if script.is_file() else []
    missing = [v for v in variants if not (stock / "vendor/etc" / ("media_profiles%s.xml" % v)).is_file()]
    if not variants:
        problems.append("no canoe variants found in the stock init.qti.media.sh")
    if missing:
        problems.append("no /vendor/etc/media_profiles<variant>.xml for " + ", ".join(missing))
    for d in ("product/etc", "odm/etc"):  # searched before /vendor/etc by libmedia
        early = [f.name for f in (stock / d).glob("media_profiles*.xml")] if (stock / d).is_dir() else []
        if early:
            problems.append("stock %s also has %s, which libmedia would prefer" % (d, ", ".join(early)))
    add("FAIL" if problems else "PASS", "built.media_profiles",
        "; ".join(problems) if problems else "init copies the vendor's media variant to ro.media.xml_variant.profiles; "
        "the stock vendor image has a profile file for each of %s" % ", ".join(variants))

    name, label = "ro.vendor.qti.va_aosp.support", "vantage_vendor_framework_prop"
    sel = ext / "etc/selinux"
    problems = []
    if read_props(root / "system/build.prop").get(name) != "1":
        problems.append("%s=1 is not in /system/build.prop" % name)
    ctx = [l.split() for l in (sel / "system_ext_property_contexts").read_text().split(NL) if l.startswith(name)]
    if ctx != [[name, "u:object_r:%s:s0" % label, "exact", "bool"]]:
        problems.append("system_ext_property_contexts does not label it %s (%s)" % (label, ctx))
    cil = (sel / "system_ext_sepolicy.cil").read_text()
    if not re.search(r"\(allow hal_camera_server %s \(file \(" % label, cil):
        problems.append("no allow rule for hal_camera_server in the system_ext policy")
    others = []
    for f in list((stock / "vendor/etc/selinux").glob("*property_contexts")) + list((stock / "odm/etc/selinux").glob("*property_contexts")):
        if any(l.split()[:1] == [name] for l in f.read_text().split(NL)):
            others.append(f.name)
    if others:
        problems.append("the stock %s label the same property: a duplicate exact entry" % ", ".join(others))
    add("FAIL" if problems else "PASS", "built.vendor_framework_flag",
        "; ".join(problems) if problems else "%s=1 is set, has its own type %s, hal_camera_server may read it, "
        "and no stock vendor or odm property_contexts names it" % (name, label))


def load_props(files):
    props = {}
    for f in files:
        if f.is_file():
            for line in f.read_text(errors="replace").split(NL):
                if "=" in line and not line.startswith("#"):
                    k, _, val = line.partition("=")
                    props.setdefault(k.strip(), val.strip())
    return props


def gate(overlay, props):
    """'on' / 'off' / 'unknown' for android:requiredSystemPropertyName/Value (value '+x' = regex)"""
    name, value = overlay.get("requiredSystemPropertyName"), overlay.get("requiredSystemPropertyValue")
    if not name:
        return "on"
    names, values = name.split(","), (value or "").split(",")
    if len(names) != len(values):
        return "off"
    state = "on"
    for n, val in zip(names, values):
        if n not in props:
            state = "unknown"   # set at run time (or not at all); cannot be decided from the files
        elif val.startswith("+"):
            # TrebleDroid's FrameworkParsingPackageUtils: '+' = pattern, '*' means '.*', find()
            if not re.search(val[1:].replace("*", ".*"), props[n]):
                return "off"
        elif props[n] != val:
            return "off"
    return state


def check_precedence(root, stock, repo, stock_overlays, tools):
    v = repo / "vendor/motorola/vantage"
    ours = {}
    for manifest in sorted(v.glob("*/*/*/AndroidManifest.xml")):
        if ET.parse(manifest).getroot().find("overlay") is not None:
            apk = root / "system/product/overlay" / (manifest.parent.name + ".apk")
            m = tools.manifest(apk)
            ours[m["package"]] = (m["overlay"]["targetPackage"], int(m["overlay"]["priority"]), tools.resources(apk))
    targets = {t for t, _, _ in ours.values()}
    props = load_props([stock / "vendor/build.prop", stock / "odm/etc/build.prop", root / "system/build.prop",
                        root / "system/product/etc/build.prop", root / "system/system_ext/etc/build.prop"])
    others = []   # (where, partition, package, target, static, priority, gate, resources)
    scanned = 0
    for part in ("product", "system_ext"):
        for apk in sorted((root / "system" / part / "overlay").rglob("*.apk")):
            scanned += 1
            m = tools.manifest(apk)
            o = m["overlay"] or {}
            if m["package"] in ours or o.get("targetPackage") not in targets:
                continue
            others.append(("image", part, m["package"], o["targetPackage"], o.get("isStatic") == "true",
                           int(o.get("priority", "0")), gate(o, props), tools.resources(apk)))
    for o in json.loads(Path(stock_overlays).read_text()):
        if o["partition"] in ("vendor", "odm") and o["target"] in targets:
            others.append(("stock", o["partition"], o["package"], o["target"], bool(o["static"]),
                           int(o["priority"] or 0), "on", o["resources"]))
    rank = lambda part, prio: (PARTITION_ORDER.index(part), prio)
    wins, maybe, lower, same = [], [], [], []
    for package, (target, prio, res) in sorted(ours.items()):
        for where, part, opkg, otarget, static, oprio, g, ores in others:
            if otarget != target:
                continue
            for key in sorted(set(res) & set(ores)):
                row = "%s %s: also set by %s (%s /%s, %s, priority %d, property gate %s) = %s" % (
                    target, key, opkg, where, part, "static" if static else "mutable", oprio, g, str(ores[key])[:60])
                if norm(str(ores[key])) == norm(res[key]):
                    same.append(row)
                elif g == "off":
                    lower.append(row + "  [inactive: property condition is false on this device]")
                elif not static:
                    maybe.append(row + "  [mutable: applies only if something enables it at run time]")
                elif g == "unknown":
                    maybe.append(row + "  [property not known statically]")
                elif rank(part, oprio) > rank("product", prio):
                    wins.append(row)
                else:
                    lower.append(row + "  [lower precedence than ours]")
    n = sum(len(r) for _, _, r in ours.values())
    status = "FAIL" if wins else "WARNING" if maybe else "PASS"
    add(status, "overlays.precedence",
        "%d values set by our %d overlays; %d overlays in the image and the stock /vendor and /odm overlays for the same "
        "targets were compared: %d active overlay(s) with higher precedence set a different value, %d could at run time, "
        "%d are overridden by ours or inactive, %d set the same value" % (
            n, len(ours), scanned, len(wins), len(maybe), len(lower), len(same)),
        wins + maybe + lower + same)


def main():
    ap = argparse.ArgumentParser()
    for a in ("--root", "--manifest", "--repo", "--stock", "--fstab", "--stock-overlays", "--hostbin", "--out"):
        ap.add_argument(a, required=True)
    ap.add_argument("--image", help="image file, recorded in the report with its SHA-256")
    args = ap.parse_args()
    root, repo, stock = Path(args.root), Path(args.repo), Path(args.stock)
    tools = Tools(args.hostbin)
    check_layout(root, args.fstab)
    platform = check_stock(root, stock, args.manifest, tools)
    check_built(root, repo, tools, platform)
    check_properties(root, repo, tools)
    check_media_and_flag(root, stock)
    check_precedence(root, stock, repo, args.stock_overlays, tools)
    counts = {s: sum(1 for r in RESULTS if r["status"] == s) for s in ("PASS", "FAIL", "WARNING", "UNKNOWN")}
    header = {"image": args.image or "", "sha256": sha256(args.image) if args.image else "",
              "platform_certificate_sha256": platform}
    out = Path(args.out)
    (out / "image-composition.json").write_text(json.dumps({"header": header, "counts": counts, "results": RESULTS}, indent=1) + NL)
    md = ["# Image composition", "", "Image `%s`" % header["image"], "", "SHA-256 `%s`" % header["sha256"], "",
          "PASS %(PASS)d / FAIL %(FAIL)d / WARNING %(WARNING)d / UNKNOWN %(UNKNOWN)d" % counts, "",
          "| Status | Check | Finding |", "|---|---|---|"]
    md += ["| %s | `%s` | %s |" % (r["status"], r["check"], r["summary"]) for r in RESULTS]
    for r in RESULTS:
        if r["evidence"]:
            md += ["", "## `%s`" % r["check"], "", "```"] + r["evidence"] + ["```"]
    (out / "image-composition.md").write_text(NL.join(md) + NL)
    print("  composition: PASS %(PASS)d / FAIL %(FAIL)d / WARNING %(WARNING)d / UNKNOWN %(UNKNOWN)d" % counts)
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
