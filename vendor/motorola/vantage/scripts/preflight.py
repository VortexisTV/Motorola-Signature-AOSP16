#!/usr/bin/env python3
"""Offline pre-flash validation of a system image tree against the stock vendor firmware.

    preflight.py --map /system=DIR --map /system_ext=DIR --map /product=DIR --map /apex=DIR \
                 --map /vendor=DIR --map /odm=DIR \
                 --manifest proprietary-files.txt --reports reports [--inventory reports/inventory] \
                 [--baseline-map /system=STOCK ...] [--secilc PATH] [--aapt2 PATH] \
                 [--system-img FILE --super-layout super_layout.json] [--name preflight]

The --map arguments describe the image under test (for a TrebleDroid build:
/system=$OUT/system, /system_ext=$OUT/system/system_ext, /product=$OUT/system/product,
/apex=$OUT/apex) plus the extracted stock /vendor and /odm. --baseline-map describes the
stock system side; findings that are identical on stock are reported as pre-existing.

Every check is static. Results are PASS / FAIL / WARNING / UNKNOWN (see motofw/report.py).
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from check_java_linkage import Platform, check as linkage_check  # noqa: E402
from motofw import apk, axml, elf, fsmeta  # noqa: E402
from motofw.report import Report  # noqa: E402

PRIVILEGED_FLAG = 0x10
SIGNATURE_BASE = 2


def parse_manifest(path):
    entries = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        spec, _, sha = line.partition("|")
        rel, *flags = spec.split(";")
        if any(e["rel"] == rel for e in entries):  # shared by several components
            continue
        entries.append({"rel": rel, "device": "/" + rel, "flags": flags, "sha256": sha})
    return entries


class Context:
    def __init__(self, args):
        self.args = args
        self.platform = Platform(args.map)
        self.baseline = Platform(args.baseline_map) if args.baseline_map else None
        self.manifest = parse_manifest(args.manifest)
        self.report = Report(f"Preflight: {args.name}", {"manifest": args.manifest, "maps": " ".join(args.map)})
        self.inventory = Path(args.inventory) if args.inventory else None
        self._stock_packages = None

    def stock_packages(self):
        if self._stock_packages is None:
            self._stock_packages = {}
            if self.inventory and (self.inventory / "packages.json").exists():
                for p in json.loads((self.inventory / "packages.json").read_text(encoding="utf-8")):
                    self._stock_packages[p["path"]] = p
        return self._stock_packages

    def apps(self):
        return [e for e in self.manifest if e["rel"].endswith(".apk")]

    def host(self, device_path):
        return self.platform.host(device_path)


def check_files(ctx):
    missing, present = [], 0
    for e in ctx.manifest:
        if any(f.startswith("SYMLINK=") for f in e["flags"]):
            host = ctx.platform.host(e["device"].rsplit("/", 1)[0])
            link = (host / e["device"].rsplit("/", 1)[1]) if host else None
            ok = bool(link) and (link.is_symlink() or link.exists())
        else:
            ok = ctx.host(e["device"]) is not None
        present += ok
        if not ok:
            missing.append(e["device"])
    if missing:
        ctx.report.fail("files.present", f"{len(missing)} of {len(ctx.manifest)} manifest files are not in the image",
                        missing, "placement")
    else:
        ctx.report.passed("files.present", f"all {present} manifest files are present at their stock paths",
                          area="placement")


def check_content(ctx):
    """Files the build installs verbatim must match the SHA-256 pinned in the manifest.

    Catches a different file winning the same destination (PRODUCT_COPY_FILES: first entry wins).
    Jars (re-packed by dex_import) and re-signed APKs legitimately differ and are skipped.
    """
    import hashlib
    bad, same = [], 0
    for e in ctx.manifest:
        if not e["sha256"] or e["rel"].endswith(".jar"):
            continue
        if e["rel"].endswith(".apk") and "PRESIGNED" not in e["flags"]:
            continue
        host = ctx.host(e["device"])
        if host is None:
            continue
        h = hashlib.sha256()
        with open(host, "rb") as f:
            for buf in iter(lambda: f.read(4 * 1024 * 1024), b""):
                h.update(buf)
        if h.hexdigest() == e["sha256"]:
            same += 1
        else:
            bad.append(f"{e['device']}: installed {h.hexdigest()[:16]}, stock {e['sha256'][:16]}")
    if bad:
        ctx.report.fail("files.content", f"{len(bad)} installed files differ from the pinned stock files "
                        "(another module or copy rule owns the destination, or the file was altered)", bad,
                        "placement")
    else:
        ctx.report.passed("files.content", f"{same} verbatim-installed files are byte-identical to stock",
                          area="placement")


def check_signatures(ctx):
    fw_res = ctx.host("/system/framework/framework-res.apk")
    platform_cert = apk.signing_info(str(fw_res))["cert_sha256"] if fw_res else None
    if not platform_cert:
        ctx.report.unknown("apk.signature", "framework-res.apk not found; cannot determine the platform certificate",
                           area="signing")
        return None
    problems, notes = [], [f"image platform certificate sha256={platform_cert}"]
    stock = ctx.stock_packages()
    for e in ctx.apps():
        host = ctx.host(e["device"])
        if host is None:
            continue
        cert = apk.signing_info(str(host))["cert_sha256"]
        if "PRESIGNED" in e["flags"]:
            want = (stock.get(e["device"]) or {}).get("signing", {}).get("cert_sha256")
            if want and cert != want:
                problems.append(f"{e['device']}: PRESIGNED but certificate changed ({cert} != stock {want})")
            else:
                notes.append(f"{e['device']}: keeps OEM certificate {str(cert)[:16]}")
        else:
            if cert != platform_cert:
                problems.append(f"{e['device']}: expected the image platform certificate, found {cert}")
            else:
                notes.append(f"{e['device']}: re-signed with the image platform certificate")
    if problems:
        ctx.report.fail("apk.signature", f"{len(problems)} signing problems", problems, "signing")
    else:
        ctx.report.passed("apk.signature", "app certificates match the manifest intent", notes, "signing")
    return platform_cert


def partition_of(device_path):
    return device_path.split("/")[1]


def collect_permission_definitions(ctx):
    """name -> (protectionLevel, defining package, certificate) for every APK in the image."""
    defs = {}
    ordered = []
    fw_res = ctx.host("/system/framework/framework-res.apk")
    if fw_res:
        ordered.append(fw_res)
    for prefix in ("/system", "/system_ext", "/product", "/vendor"):
        for root in ctx.platform._roots(prefix):
            ordered += sorted(root.rglob("*.apk"))
    seen = set()
    for path in ordered:
        if path in seen:
            continue
        seen.add(path)
        info = apk.inspect(str(path))
        for d in info.get("defines_permissions", []):
            level = d.get("protectionLevel", 0)
            defs.setdefault(d["name"], (level if isinstance(level, int) else 0, info.get("package"),
                                        info["signing"].get("cert_sha256")))
    return defs


def check_privapp(ctx, platform_cert):
    defs = collect_permission_definitions(ctx)
    mode = None
    for prefix, rel in (("/vendor", "build.prop"), ("/product", "etc/build.prop"), ("/system", "build.prop"),
                        ("/system_ext", "etc/build.prop")):
        for root in ctx.platform._roots(prefix):
            mode = mode or fsmeta.read_props(root / rel).get("ro.control_privapp_permissions")
    violations, notes = [], [f"ro.control_privapp_permissions={mode}", f"{len(defs)} permission definitions in image"]
    checked = 0
    for e in ctx.apps():
        if "PRIV" not in e["flags"]:
            continue
        host = ctx.host(e["device"])
        if host is None:
            continue
        info = apk.inspect(str(host))
        part = partition_of(e["device"])
        allow, deny = set(), set()
        for root in ctx.platform._roots("/" + part):
            perms = fsmeta.read_permission_xmls(root / "etc")
            allow |= set(perms["privapp_permissions"].get(info["package"], []))
            deny |= set(perms["privapp_deny"].get(info["package"], []))
        cert = info["signing"].get("cert_sha256")
        checked += 1
        for perm in info.get("uses_permissions", []):
            if perm not in defs:
                continue
            level, definer, definer_cert = defs[perm]
            # PermissionManagerService only enforces the allowlist for permissions whose source
            # package is the platform ("android"); privileged permissions defined by other apps
            # are granted to any privileged app.
            if definer != "android":
                continue
            privileged = bool(level & PRIVILEGED_FLAG) or (level & 0xF) == 3
            if not privileged:
                continue
            if cert and cert == definer_cert:
                continue  # granted by signature
            if perm in allow or perm in deny:
                continue
            violations.append(f"{info['package']} ({e['device']}): {perm} [defined by {definer}] is not allowlisted "
                              f"in /{part}/etc/permissions")
        notes.append(f"{info['package']}: allowlist={sorted(allow)}")
    if violations:
        sev = ctx.report.fail if mode == "enforce" else ctx.report.warn
        sev("privapp.allowlist", f"{len(violations)} privileged permissions lack an allowlist entry "
            f"(mode={mode}; 'enforce' makes system_server abort at boot)", violations, "permissions")
    else:
        ctx.report.passed("privapp.allowlist", f"all privileged permissions of {checked} priv-apps are allowlisted "
                          "or granted by signature", notes, "permissions")


def check_java(ctx):
    boot, missing_boot = ctx.platform.boot_index()
    if missing_boot:
        ctx.report.warn("java.bootclasspath", f"{len(missing_boot)} BOOTCLASSPATH jars not found in the image tree",
                        missing_boot, "java")
    base_boot = ctx.baseline.boot_index()[0] if ctx.baseline else None
    subjects = [e for e in ctx.manifest if e["rel"].endswith((".apk", ".jar"))]
    for e in subjects:
        if ctx.host(e["device"]) is None:
            continue
        res = linkage_check(ctx.platform, boot, e["device"], [], 4)
        tid = f"java.linkage:{e['rel'].rsplit('/', 1)[-1]}"
        libs_bad = [f"{l['name']}: {l['state']}" for l in res.get("shared_libraries", [])
                    if l["state"] != "ok" and l["required"]]
        if libs_bad:
            ctx.report.fail(f"java.libraries:{e['rel'].rsplit('/', 1)[-1]}",
                            "required shared libraries cannot be resolved in the image", libs_bad, "java")
        base = None
        if ctx.baseline and ctx.baseline.host(e["device"]) is not None:
            base = linkage_check(ctx.baseline, base_boot, e["device"], [], 4)
        new, old = [], 0
        for key in ("missing_classes", "missing_methods", "missing_fields"):
            for sym, users in res.get(key, {}).items():
                if base is not None and sym in base.get(key, {}):
                    old += 1
                    continue
                new.append(f"{key[8:]} {sym}  (used by {', '.join(users)})")
        total = sum(res.get("counts", {}).get(k, 0) for k in ("missing_classes", "missing_methods", "missing_fields"))
        if new:
            ctx.report.warn(tid, f"{len(new)} references do not resolve against this image "
                            f"({old} more are also unresolved on stock)", new, "java")
        elif res.get("status") == "FAIL" and not libs_bad:
            ctx.report.fail(tid, res.get("reason", "linkage check failed"), area="java")
        else:
            ctx.report.passed(tid, f"all external references resolve ({total} unresolved, all pre-existing on stock)"
                              if total else "all external references resolve", area="java")


def check_native(ctx):
    libs = {}
    for prefix in ("/system", "/system_ext", "/product"):
        for root in ctx.platform._roots(prefix):
            for p in (root / "lib64").glob("*.so"):
                libs.setdefault(p.name, prefix)
    for root in ctx.platform._roots("/apex"):
        for p in root.glob("*/lib64/*.so"):
            libs.setdefault(p.name, "/apex")
    vendor_public = set()
    for root in ctx.platform._roots("/vendor"):
        f = root / "etc" / "public.libraries.txt"
        if f.exists():
            vendor_public |= {l.split()[0] for l in f.read_text().splitlines() if l.strip() and not l.startswith("#")}
    problems, checked = [], 0
    for e in ctx.manifest:
        if not e["rel"].endswith(".so") or any(f.startswith("SYMLINK=") for f in e["flags"]):
            continue
        host = ctx.host(e["device"])
        if host is None:
            continue
        meta = elf.inspect(str(host))
        checked += 1
        for dep in (meta or {}).get("needed", []):
            if dep not in libs and dep not in vendor_public:
                problems.append(f"{e['device']} needs {dep}: not in /system, /system_ext, /product, an APEX "
                                "or the vendor public library list")
    if problems:
        ctx.report.fail("native.needed", f"{len(problems)} unresolved DT_NEEDED entries", problems, "native")
    else:
        ctx.report.passed("native.needed", f"DT_NEEDED of all {checked} ported native libraries resolve in the image",
                          area="native")


def image_packages(ctx):
    out = {}
    for path, prefix in ctx.platform.apks(("/system", "/system_ext", "/product", "/vendor")):
        info = apk.inspect(str(path))
        if info.get("package"):
            out.setdefault(info["package"], (path, info, prefix))
    return out


def dump_resources(aapt2, path):
    proc = subprocess.run([aapt2, "dump", "resources", str(path)], capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        return None
    res, name, buf = {}, None, []
    for line in proc.stdout.splitlines():
        m = re.match(r"^\s+resource 0x[0-9a-f]+ (\S+)", line)
        if m or re.match(r"^\s+type \S+ id=|^Package name=", line):
            if name:
                res[name] = " ".join(buf)
            name, buf = (m.group(1), []) if m else (None, [])
        elif name and line.strip():
            buf.append(line.strip())
    if name:
        res[name] = " ".join(buf)
    return res


def check_overlays(ctx, packages):
    aapt2 = ctx.args.aapt2
    if not aapt2 or not Path(aapt2).exists():
        ctx.report.unknown("overlay.targets", "aapt2 not available; overlay resources were not checked", area="overlays")
        return
    ours = set(ctx.args.overlay_package or [])
    checked = 0
    for pkg, (path, info, _) in packages.items():
        if pkg not in ours:
            continue
        checked += 1
        target = (info.get("overlay") or {}).get("targetPackage")
        tid = f"overlay.targets:{pkg}"
        if target not in packages:
            ctx.report.fail(tid, f"overlay targets {target}, which is not in the image", area="overlays")
            continue
        over, base = dump_resources(aapt2, path), dump_resources(aapt2, packages[target][0])
        if over is None or base is None:
            ctx.report.unknown(tid, "aapt2 could not dump the overlay or its target", area="overlays")
            continue
        unknown = sorted(n for n in over if n not in base)
        notes = [f"{n} = {v[:120]}" for n, v in sorted(over.items())]
        if unknown:
            ctx.report.fail(tid, f"{len(unknown)} overlaid resources do not exist in {target} (they would be ignored)",
                            unknown, "overlays")
        else:
            ctx.report.passed(tid, f"all {len(over)} overlaid resources exist in {target}", notes, "overlays")
        for name, val in over.items():
            m = re.search(r'"([a-zA-Z][\w.]+)"', val)
            if not name.startswith("string/") or not name.endswith("_package") or not m:
                continue
            ref = m.group(1)
            short = name.split("/")[1]
            if ref not in packages:
                ctx.report.fail(f"overlay.package:{short}",
                                f"{name} points at {ref}, which is not installed in the image or on /vendor",
                                area="overlays")
                continue
            rpath, rinfo, rprefix = packages[ref]
            if short == "config_ims_mmtel_package":
                ok = any("android.telephony.ims.ImsService" in s.get("actions", [])
                         and s.get("permission") == "android.permission.BIND_IMS_SERVICE"
                         for s in rinfo.get("services", []))
                verb = "declares" if ok else "does NOT declare"
                (ctx.report.passed if ok else ctx.report.fail)(
                    "telephony.ims_binding",
                    f"{ref} {verb} an android.telephony.ims.ImsService guarded by BIND_IMS_SERVICE",
                    [str(rpath)], "telephony")
            else:
                ctx.report.passed(f"overlay.package:{short}", f"{name} -> {ref} found under {rprefix}",
                                  area="overlays")
    if not checked:
        ctx.report.warn("overlay.targets", "none of the expected overlay packages were found in the image",
                        sorted(ours), "overlays")


def check_sepolicy(ctx):
    r = ctx.report

    def one(prefix, rel):
        for root in ctx.platform._roots(prefix):
            if (root / rel).exists():
                return root / rel
        return None

    vers_file = one("/vendor", "etc/selinux/plat_sepolicy_vers.txt")
    if vers_file is None:
        r.unknown("sepolicy.compile", "vendor plat_sepolicy_vers.txt not found", area="selinux")
        return
    ver = vers_file.read_text().strip()
    plan = [("/system", "etc/selinux/plat_sepolicy.cil", True), ("/system", f"etc/selinux/mapping/{ver}.cil", True),
            ("/system", f"etc/selinux/mapping/{ver}.compat.cil", False),
            ("/system_ext", "etc/selinux/system_ext_sepolicy.cil", False),
            ("/system_ext", f"etc/selinux/mapping/{ver}.cil", False),
            ("/system_ext", f"etc/selinux/mapping/{ver}.compat.cil", False),
            ("/product", "etc/selinux/product_sepolicy.cil", False),
            ("/product", f"etc/selinux/mapping/{ver}.cil", False),
            ("/vendor", "etc/selinux/plat_pub_versioned.cil", True), ("/vendor", "etc/selinux/vendor_sepolicy.cil", True),
            ("/odm", "etc/selinux/odm_sepolicy.cil", False)]
    files, missing = [], []
    for prefix, rel, required in plan:
        path = one(prefix, rel)
        if path:
            files.append(path)
        elif required:
            missing.append(f"{prefix}/{rel}")
    if missing:
        r.fail("sepolicy.inputs", f"policy inputs init needs for vendor policy version {ver} are missing "
               "(the device would fail to load SELinux policy)", missing, "selinux")
        return
    r.passed("sepolicy.inputs", f"system provides the platform policy and the {ver} mapping file",
             [str(f) for f in files], "selinux")

    texts = {f: f.read_text(errors="replace") for f in files}
    declared = set()
    for text in texts.values():
        declared |= set(re.findall(r"^\(type (\S+)\)", text, re.M))
    bad = []
    for prefix, rel in (("/system", "etc/selinux/plat_seapp_contexts"),
                        ("/system_ext", "etc/selinux/system_ext_seapp_contexts"),
                        ("/product", "etc/selinux/product_seapp_contexts")):
        path = one(prefix, rel)
        for line in path.read_text().splitlines() if path else []:
            m = re.search(r"\bdomain=(\S+)", line)
            if m and m.group(1) not in declared:
                bad.append(f"{rel}: domain {m.group(1)} is not declared by any policy file")
    if bad:
        r.fail("sepolicy.seapp_domains", f"{len(bad)} seapp_contexts entries reference undeclared domains", bad,
               "selinux")
    else:
        r.passed("sepolicy.seapp_domains", "every system-side seapp_contexts domain is declared", area="selinux")

    # Versioned attributes the vendor policy writes rules against must be populated by a system type.
    system_text = "".join(t for f, t in texts.items() if "/vendor/" not in str(f) and "/odm/" not in str(f))
    vendor_text = "".join(t for f, t in texts.items() if "/vendor/" in str(f))
    for seed in ctx.args.expect_mapped or []:
        versioned = f"{seed}_{ver}"
        used = len(re.findall(rf"\b{re.escape(versioned)}\b", vendor_text))
        mapped = re.search(rf"\(typeattributeset {re.escape(versioned)} \([^)]*\b{re.escape(seed)}\b", system_text)
        if mapped:
            r.passed(f"sepolicy.mapping:{seed}", f"{versioned} is populated by the system policy "
                     f"({used} references in the stock vendor policy bind to it)", area="selinux")
        else:
            r.fail(f"sepolicy.mapping:{seed}", f"{versioned} is used {used} times by the stock vendor policy but "
                   "no system-side type is mapped to it; those vendor rules are dead", area="selinux")

    # Every versioned attribute the vendor policy writes rules against, not only the expected ones.
    # An attribute no system type is mapped to makes those vendor rules dead. That is harmless for
    # domains nothing runs in and for labels nothing carries, but not for a label the vendor's own
    # context files assign.
    vendor_rules = "".join(t for f, t in texts.items() if str(f).endswith(("vendor_sepolicy.cil", "odm_sepolicy.cil")))
    used = {a for a in re.findall(rf"\b(\w+_{ver})\b", vendor_rules) if not a.startswith("base_typeattr_")}
    populated = {m.group(1) for m in re.finditer(rf"\(typeattributeset (\w+_{ver}) \(\s*\w", system_text)}
    empty = sorted(used - populated)
    vendor_labels = {}
    for prefix in ("/vendor", "/odm"):
        for root in ctx.platform._roots(prefix):
            for cfile in sorted((root / "etc" / "selinux").glob("*contexts")):
                for line in cfile.read_text(errors="replace").splitlines():
                    m = re.match(r"\s*(\S+)\s.*u:object_r:(\w+):s0", line)
                    if m and not line.lstrip().startswith("#"):
                        vendor_labels.setdefault(m.group(2), []).append(f"{cfile.name}: {m.group(1)}")
    labelled = [a for a in empty if a[:-len(ver) - 1] in vendor_labels]
    note = [f"{len(used)} versioned attributes referenced by vendor/odm rules, {len(used) - len(empty)} populated, "
            f"{len(empty)} empty"]
    if labelled:
        r.warn("sepolicy.unmapped", f"{len(labelled)} empty versioned attributes belong to labels the vendor's own "
               "context files assign; vendor rules on those objects are dead (review each)",
               note + [f"{a}: {'; '.join(vendor_labels[a[:-len(ver) - 1]][:3])}" for a in labelled], "selinux")
    else:
        r.passed("sepolicy.unmapped", f"{len(empty)} versioned attributes are empty here, none of them for a label "
                 "the vendor's context files assign", note + empty[:200], "selinux")

    secilc = ctx.args.secilc
    if not secilc or not Path(secilc).exists():
        r.unknown("sepolicy.compile", "secilc not available; combined policy was not compiled", area="selinux")
        return
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [secilc, "-m", "-M", "true", "-G", "-N", "-c", "30", "-o", f"{tmp}/sepolicy", "-f", "/dev/null"]
        proc = subprocess.run(cmd + [str(f) for f in files], capture_output=True, text=True)
        if proc.returncode == 0:
            size = Path(f"{tmp}/sepolicy").stat().st_size
            if ctx.args.policy_out:
                shutil.copyfile(f"{tmp}/sepolicy", ctx.args.policy_out)
            r.passed("sepolicy.compile", "secilc compiled the system policy together with the stock vendor policy "
                     f"the way init does ({len(files)} CIL files, {size} byte policy)", area="selinux")
        else:
            r.fail("sepolicy.compile", "secilc failed on the combined policy; the device would not boot",
                   (proc.stderr or proc.stdout).strip().splitlines()[-25:], "selinux")


def check_platform(ctx):
    def props(prefix, rel):
        out = {}
        for root in ctx.platform._roots(prefix):
            out.update(fsmeta.read_props(root / rel))
        return out

    system, vendor = props("/system", "build.prop"), props("/vendor", "build.prop")
    sdk, vsdk = system.get("ro.build.version.sdk"), vendor.get("ro.vendor.build.version.sdk")
    llndk, board = system.get("ro.llndk.api_level"), vendor.get("ro.board.api_level")
    notes = [f"system sdk={sdk} sdk_full={system.get('ro.build.version.sdk_full')} llndk_api={llndk} "
             f"fingerprint={system.get('ro.system.build.fingerprint')}",
             f"vendor sdk={vsdk} board_api={board} fingerprint={vendor.get('ro.vendor.build.fingerprint')}"]
    try:
        ok = int(sdk) >= int(vsdk) and int(llndk or 0) >= int(board or 0)
    except (TypeError, ValueError):
        ctx.report.unknown("platform.api_levels", "could not read API levels from build.prop (the stock vendor "
                           "build.prop is mode 0600 root: run the validators as root)", notes, "platform")
        return
    if ok:
        ctx.report.passed("platform.api_levels", f"system (SDK {sdk}, LLNDK {llndk}) is not older than the vendor "
                          f"(SDK {vsdk}, board API {board})", notes, "platform")
    else:
        ctx.report.fail("platform.api_levels", "system image is older than the vendor image it must serve", notes,
                        "platform")


def check_vintf(ctx):
    device_hals = {}
    level = None
    for prefix in ("/vendor", "/odm"):
        for root in ctx.platform._roots(prefix):
            for doc in fsmeta.read_vintf_dir(root / "etc"):
                if doc["kind"] != "manifest":
                    continue
                level = level or doc.get("target_level")
                for hal in doc["hals"]:
                    device_hals.setdefault(hal["name"], []).append(hal)
    matrix = {}
    for root in ctx.platform._roots("/system"):
        for doc in fsmeta.read_vintf_dir(root / "etc"):
            if doc["kind"] == "compatibility-matrix" and doc.get("level") == level:
                for hal in doc["hals"]:
                    matrix.setdefault(hal["name"], []).extend(hal["versions"])
    if not level or not matrix:
        ctx.report.unknown("vintf.radio", f"no framework compatibility matrix for target-level {level} in the image",
                           area="vintf")
        return
    issues, notes = [], []
    for name, hals in sorted(device_hals.items()):
        if not name.startswith("android.hardware.radio") or name not in matrix:
            continue
        have = {int(v) for h in hals for v in h["versions"] if v.isdigit()} or {1}
        ranges = []
        for spec in matrix[name] or ["1"]:  # no <version> means version 1
            lo, _, hi = spec.partition("-")
            ranges.append((int(lo), int(hi or lo)))
        fits = all(any(lo <= v <= hi for lo, hi in ranges) for v in have)
        notes.append(f"{name}: vendor V{sorted(have)} framework accepts {matrix[name]}")
        if not fits:
            issues.append(notes[-1])
    if issues:
        ctx.report.warn("vintf.radio", "vendor radio HAL versions fall outside the framework matrix range", issues,
                        "vintf")
    else:
        ctx.report.passed("vintf.radio", f"all vendor android.hardware.radio.* AIDL versions are accepted by the "
                          f"framework compatibility matrix level {level}", notes, "vintf")


def check_image_size(ctx):
    img, layout = ctx.args.system_img, ctx.args.super_layout
    if not img or not layout or not Path(img).exists():
        ctx.report.unknown("image.size", "no system image/super layout given; size was not checked", area="image")
        return
    import struct
    with open(img, "rb") as f:
        head = f.read(28)
    size = Path(img).stat().st_size
    if len(head) == 28 and struct.unpack_from("<I", head)[0] == 0xED26FF3A:
        blk, total = struct.unpack_from("<II", head, 12)
        size = blk * total
    lp = json.loads(Path(layout).read_text())
    group = next(g for g in lp["groups"] if g["name"].endswith("_a"))
    others = sum(p["size"] for p in lp["partitions"] if p["group"] == group["name"] and p["name"] != "system_a")
    free = group["maximum_size"] - others
    note = [f"system image {size} bytes; group {group['name']} max {group['maximum_size']}; "
            f"other stock partitions {others}; available for system {free}"]
    if size <= free:
        ctx.report.passed("image.size", f"system image ({size / 2**20:.0f} MiB) fits the dynamic partition group "
                          f"with {((free - size) / 2**30):.1f} GiB to spare", note, "image")
    else:
        ctx.report.fail("image.size", "system image does not fit the super partition group", note, "image")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", action="append", required=True)
    ap.add_argument("--baseline-map", action="append")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--reports", required=True)
    ap.add_argument("--inventory")
    ap.add_argument("--secilc")
    ap.add_argument("--policy-out", help="keep the compiled combined policy here (input of sepolicy_diff.py)")
    ap.add_argument("--aapt2", default="/work/aosp/prebuilts/sdk/tools/linux/bin/aapt2")
    ap.add_argument("--overlay-package", action="append", help="package name of an overlay expected in the image")
    ap.add_argument("--expect-mapped", action="append", help="system type that must be mapped for the vendor policy")
    ap.add_argument("--system-img")
    ap.add_argument("--super-layout")
    ap.add_argument("--name", default="preflight")
    ap.add_argument("--skip", default="", help="comma-separated checks to skip (java,native,overlays,...)")
    args = ap.parse_args()
    skip = set(args.skip.split(","))

    ctx = Context(args)
    check_platform(ctx)
    check_files(ctx)
    check_content(ctx)
    platform_cert = check_signatures(ctx)
    check_privapp(ctx, platform_cert)
    if "native" not in skip:
        check_native(ctx)
    if "overlays" not in skip:
        check_overlays(ctx, image_packages(ctx))
    check_sepolicy(ctx)
    check_vintf(ctx)
    check_image_size(ctx)
    if "java" not in skip:
        check_java(ctx)
    path = ctx.report.write(args.reports, args.name)
    ctx.report.print_summary()
    print(f"report: {path}")
    return 1 if ctx.report.counts()["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
