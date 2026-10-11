#!/usr/bin/env python3
"""Dump the resource values of every runtime resource overlay (RRO) in an extracted firmware.

    python3 dump_overlays.py <fw_out_dir> <report_dir> [--aapt2 PATH]

Reads  <report_dir>/inventory/packages.json (from analyze_firmware.py) to find overlay APKs.
Writes <report_dir>/inventory/overlays.json:
    [{package, path, partition, target, target_name, priority, static, cert_label,
      resources: {"type/name": "value text"}}]
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

PARTITION_DIRS = {
    "/system/": "system/system/",
    "/system_ext/": "system_ext/",
    "/product/": "product/",
    "/vendor/": "vendor/",
    "/odm/": "odm/",
}
RES_RE = re.compile(r"^\s+resource 0x[0-9a-f]+ (\S+)")
SKIP_RE = re.compile(r"^\s+type \S+ id=|^Package name=|^Binary APK")


def host_path(fw, device_path):
    for prefix, sub in PARTITION_DIRS.items():
        if device_path.startswith(prefix):
            return fw / "root" / sub / device_path[len(prefix):]
    return None


def dump(aapt2, apk):
    proc = subprocess.run([aapt2, "dump", "resources", str(apk)], capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        return None, proc.stderr.strip()[-200:]
    resources, name, buf = {}, None, []
    for line in proc.stdout.splitlines():
        m = RES_RE.match(line)
        if m:
            if name:
                resources[name] = " ".join(buf).strip()
            name, buf = m.group(1), []
        elif name and not SKIP_RE.match(line):
            text = line.strip()
            if text:
                buf.append(text)
        elif SKIP_RE.match(line) and name:
            resources[name] = " ".join(buf).strip()
            name, buf = None, []
    if name:
        resources[name] = " ".join(buf).strip()
    return resources, None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fw_dir", type=Path)
    ap.add_argument("report_dir", type=Path)
    ap.add_argument("--aapt2", default="/work/aosp/prebuilts/sdk/tools/linux/bin/aapt2")
    args = ap.parse_args()

    packages = json.loads((args.report_dir / "inventory" / "packages.json").read_text())
    out, errors = [], 0
    for pkg in packages:
        overlay = pkg.get("overlay")
        if not overlay:
            continue
        apk = host_path(args.fw_dir, pkg["path"])
        resources, err = dump(args.aapt2, apk) if apk and apk.exists() else (None, "file not found")
        entry = {
            "package": pkg.get("package"),
            "path": pkg["path"],
            "partition": pkg["partition"],
            "target": overlay.get("targetPackage"),
            "target_name": overlay.get("targetName"),
            "priority": overlay.get("priority"),
            "static": overlay.get("isStatic"),
            "cert_label": pkg.get("cert_label"),
            "resources": resources or {},
        }
        if err:
            entry["error"] = err
            errors += 1
        out.append(entry)
    out.sort(key=lambda e: (e["target"] or "", e["path"]))
    dest = args.report_dir / "inventory" / "overlays.json"
    with dest.open("w", newline="\n") as f:
        json.dump(out, f, indent=1)
    total = sum(len(e["resources"]) for e in out)
    print(f"{len(out)} overlays, {total} resource values, {errors} errors -> {dest}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
