#!/usr/bin/env python3
"""Build a machine-readable inventory of an extracted Motorola stock firmware.

Input : the <fw_out_dir> produced by extract_firmware.py + extract_filesystems.sh
        (contains root/<partition>/ trees and super_layout.json).
Output: <report_dir>/inventory/{summary,props,files,packages,elf,vintf,init,permissions,classpath}.json

The firmware trees are only read. Run as root when the trees were extracted with
preserved ownership, otherwise some 0600 files are skipped (they are counted).

Usage:
    python3 analyze_firmware.py <fw_out_dir> <report_dir> [--no-hash]
"""
import argparse
import hashlib
import json
import os
import stat
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from motofw import apk, elf, fsmeta  # noqa: E402

# partition name -> (sub-path of the extracted tree, mount point on device)
PARTITIONS = {
    "system": ("system/system", "/system"),
    "system_ext": ("system_ext", "/system_ext"),
    "product": ("product", "/product"),
    "vendor": ("vendor", "/vendor"),
    "odm": ("odm", "/odm"),
    "vendor_dlkm": ("vendor_dlkm", "/vendor_dlkm"),
    "system_dlkm": ("system_dlkm", "/system_dlkm"),
}
PROP_FILES = ("build.prop", "etc/build.prop", "default.prop", "etc/default.prop", "odm_dlkm/etc/build.prop")
PACKAGE_EXT = (".apk", ".apex", ".capex")
ELF_DIRS = ("bin/", "lib/", "lib64/", "xbin/", "apex/", "firmware/")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for buf in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(buf)
    return h.hexdigest()


def package_kind(rel):
    parts = rel.split("/")
    if rel.endswith((".apex", ".capex")):
        return "apex"
    if parts[0] == "overlay" or "/overlay/" in rel:
        return "overlay"
    if parts[0] == "priv-app":
        return "priv-app"
    if parts[0] == "app":
        return "app"
    if parts[0] == "framework":
        return "framework"
    return parts[0]


def scan_partition(name, root, mount, do_hash):
    result = {
        "files": [],
        "packages": [],
        "elf": [],
        "unreadable": 0,
        "symlinks": [],
        "bytes": 0,
    }
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for entry in list(dirnames) + filenames:
            full = os.path.join(dirpath, entry)
            if os.path.islink(full):
                result["symlinks"].append(
                    {"path": f"{mount}/{os.path.relpath(full, root)}", "target": os.readlink(full)}
                )
        for fname in filenames:
            full = os.path.join(dirpath, fname)
            if os.path.islink(full):
                continue
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            try:
                st = os.stat(full)
            except OSError:
                result["unreadable"] += 1
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            rec = {
                "path": f"{mount}/{rel}",
                "size": st.st_size,
                "mode": oct(stat.S_IMODE(st.st_mode)),
                "uid": st.st_uid,
                "gid": st.st_gid,
            }
            result["bytes"] += st.st_size
            try:
                if do_hash:
                    rec["sha256"] = sha256_file(full)
                if rel.endswith(PACKAGE_EXT):
                    info = apk.inspect(full)
                    info.update({"partition": name, "path": rec["path"], "size": st.st_size,
                                 "kind": package_kind(rel), "sha256": rec.get("sha256")})
                    result["packages"].append(info)
                elif rel.startswith(ELF_DIRS) or rel.endswith(".so"):
                    meta = elf.inspect(full)
                    if meta:
                        meta.update({"partition": name, "path": rec["path"]})
                        result["elf"].append(meta)
                        rec["elf"] = True
            except (OSError, ValueError) as exc:
                result["unreadable"] += 1
                rec["error"] = str(exc)
            result["files"].append(rec)
    return result


def label_certificates(packages):
    """Name signing certificates by the well-known package that anchors each key."""
    anchors = [
        ("platform", ("android",)),
        ("media", ("com.android.providers.media", "com.android.providers.downloads")),
        ("shared", ("com.android.contacts", "com.android.providers.contacts")),
        ("networkstack", ("com.android.networkstack.tethering", "com.android.networkstack")),
        ("bluetooth", ("com.android.bluetooth",)),
        ("nfc", ("com.android.nfc",)),
        ("sdk_sandbox", ("com.android.sdksandbox",)),
    ]
    by_pkg = {p.get("package"): p for p in packages if p.get("package") and p["kind"] != "apex"}
    labels = {}
    for label, names in anchors:
        for n in names:
            cert = (by_pkg.get(n) or {}).get("signing", {}).get("cert_sha256")
            if cert and cert not in labels:
                labels[cert] = label
                break
    counts = Counter(p["signing"].get("cert_sha256") for p in packages)
    groups = []
    for cert, count in counts.most_common():
        members = sorted(p.get("package") or p["path"] for p in packages if p["signing"].get("cert_sha256") == cert)
        groups.append(
            {
                "cert_sha256": cert,
                "label": labels.get(cert) or (f"key-{cert[:8]}" if cert else "unsigned-or-unknown"),
                "count": count,
                "sample": members[:12],
            }
        )
    for p in packages:
        cert = p["signing"].get("cert_sha256")
        p["cert_label"] = labels.get(cert) or (f"key-{cert[:8]}" if cert else "unsigned-or-unknown")
    return groups


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fw_dir", type=Path)
    ap.add_argument("report_dir", type=Path)
    ap.add_argument("--no-hash", action="store_true", help="skip per-file SHA-256 (much faster)")
    args = ap.parse_args()

    out_dir = args.report_dir / "inventory"
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    props, perms, vintf, init, classpath = {}, {}, {}, {}, {}
    files, packages, elfs, symlinks = [], [], [], []
    summary = {"firmware": args.fw_dir.name, "partitions": {}}

    for name, (sub, mount) in PARTITIONS.items():
        root = args.fw_dir / "root" / sub
        if not root.is_dir():
            summary["partitions"][name] = {"present": False}
            continue
        print(f"[scan] {name} ({root})", flush=True)
        merged = {}
        for pf in PROP_FILES:
            merged.update(fsmeta.read_props(root / pf))
        props[name] = merged
        etc = root / "etc"
        perms[name] = fsmeta.read_permission_xmls(etc)
        vintf[name] = fsmeta.read_vintf_dir(etc)
        init[name] = fsmeta.read_init_dir(etc)
        jars = []
        for pb in sorted((etc / "classpaths").glob("*.pb")) if (etc / "classpaths").is_dir() else []:
            for jar in fsmeta.read_classpath_pb(pb):
                jar["fragment"] = pb.name
                jars.append(jar)
        classpath[name] = jars

        scan = scan_partition(name, str(root), mount, not args.no_hash)
        files.extend(scan["files"])
        packages.extend(scan["packages"])
        elfs.extend(scan["elf"])
        symlinks.extend(scan["symlinks"])
        kinds = Counter(p["kind"] for p in scan["packages"])
        summary["partitions"][name] = {
            "present": True,
            "mount": mount,
            "files": len(scan["files"]),
            "symlinks": len(scan["symlinks"]),
            "bytes": scan["bytes"],
            "unreadable": scan["unreadable"],
            "packages": dict(kinds),
            "elf_objects": len(scan["elf"]),
            "init_services": len(init[name]),
            "vintf_files": len(vintf[name]),
            "shared_libraries": len(perms[name]["libraries"]),
            "privapp_allowlisted_packages": len(perms[name]["privapp_permissions"]),
            "fingerprint": next((v for k, v in merged.items() if k.endswith("build.fingerprint")), None),
        }

    cert_groups = label_certificates(packages)
    summary["certificates"] = cert_groups
    summary["package_parse_errors"] = [
        {"path": p["path"], "error": p["error"]} for p in packages if p.get("error")
    ]
    layout = args.fw_dir / "super_layout.json"
    if layout.exists():
        lp = json.loads(layout.read_text())
        summary["super"] = {
            "size": lp["source"]["image_size"],
            "lp_version": lp["header"]["version"],
            "header_flags": lp["header"]["flags"],
            "metadata_slots": lp["geometry"]["metadata_slot_count"],
            "groups": lp["groups"],
            "partitions": [
                {k: p.get(k) for k in ("name", "size", "group", "attributes", "filesystem", "sha256")}
                for p in lp["partitions"]
            ],
        }
    summary["elapsed_seconds"] = round(time.time() - started, 1)

    outputs = {
        "summary": summary,
        "props": props,
        "files": {"files": files, "symlinks": symlinks},
        "packages": packages,
        "elf": elfs,
        "vintf": vintf,
        "init": init,
        "permissions": perms,
        "classpath": classpath,
    }
    for key, data in outputs.items():
        with (out_dir / f"{key}.json").open("w", newline="\n") as f:
            json.dump(data, f, indent=1, sort_keys=False, default=str)
    print(json.dumps({k: v for k, v in summary["partitions"].items()}, indent=1))
    print(f"certificate groups: {len(cert_groups)}; parse errors: {len(summary['package_parse_errors'])}")
    print(f"wrote {out_dir} in {summary['elapsed_seconds']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
