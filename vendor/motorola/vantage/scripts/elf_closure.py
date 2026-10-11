#!/usr/bin/env python3
"""Compute the DT_NEEDED closure of ELF objects using the firmware inventory.

    elf_closure.py <report_dir> <device-path> [<device-path> ...] [--target-system-libs FILE]

<report_dir>/inventory/elf.json comes from analyze_firmware.py. For every root the tool walks
DT_NEEDED and reports which partition provides each dependency on stock. With
--target-system-libs (a text file listing the sonames present in OUR system image, one per
line) it also classifies each dependency as: provided-by-target, must-port, or vendor-only.

Namespace model used (bundled system/system_ext/product apps and executables):
  search order /system/lib64, /system_ext/lib64, /product/lib64; vendor libraries are only
  reachable when listed in /vendor/etc/public.libraries.txt (or as LL-NDK, which lives in /system).
"""
import argparse
import json
import sys
from pathlib import Path

ORDER = ("system", "system_ext", "product", "vendor", "odm")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report_dir", type=Path)
    ap.add_argument("roots", nargs="+")
    ap.add_argument("--bits", type=int, default=64)
    ap.add_argument("--target-system-libs", type=Path)
    ap.add_argument("--vendor-public", type=Path, help="copy of /vendor/etc/public.libraries.txt")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    elfs = json.loads((args.report_dir / "inventory" / "elf.json").read_text())
    by_path = {e["path"]: e for e in elfs}
    providers = {}
    for e in elfs:
        if e["bits"] != args.bits:
            continue
        name = e.get("soname") or e["path"].rsplit("/", 1)[-1]
        libdir = "/lib64/" if args.bits == 64 else "/lib/"
        # only top-level lib dirs are on the default search path
        if libdir in e["path"] and e["path"].count("/") <= 3 + (1 if e["path"].startswith("/system/") else 0):
            providers.setdefault(name, []).append(e["partition"])
        providers.setdefault("@any:" + name, []).append(e["path"])
    target = None
    if args.target_system_libs:
        target = {l.strip() for l in args.target_system_libs.read_text().splitlines() if l.strip()}
    vendor_public = set()
    if args.vendor_public and args.vendor_public.exists():
        vendor_public = {l.split()[0] for l in args.vendor_public.read_text().splitlines()
                         if l.strip() and not l.startswith("#")}

    report = {}
    for root in args.roots:
        if root not in by_path:
            print(f"!! {root}: not in inventory")
            continue
        seen, queue, rows = set(), list(by_path[root]["needed"]), []
        while queue:
            lib = queue.pop(0)
            if lib in seen:
                continue
            seen.add(lib)
            parts = sorted(set(providers.get(lib, [])), key=lambda p: ORDER.index(p) if p in ORDER else 9)
            chosen = parts[0] if parts else None
            if target is not None:
                if lib in target:
                    status = "provided-by-target"
                elif chosen in ("system", "system_ext", "product"):
                    status = "must-port"
                elif chosen in ("vendor", "odm"):
                    status = "vendor-public" if lib in vendor_public else "vendor-only-UNREACHABLE"
                else:
                    status = "MISSING"
            else:
                status = chosen or "MISSING"
            rows.append({"lib": lib, "stock_partitions": parts, "status": status})
            if chosen:
                path = next((p for p in providers.get("@any:" + lib, []) if p.startswith(f"/{chosen}/")), None)
                if path and path in by_path:
                    queue.extend(by_path[path]["needed"])
        report[root] = rows
        counts = {}
        for r in rows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        print(f"## {root}: {len(rows)} transitive deps  {counts}")
        for r in rows:
            if r["status"] not in ("system", "provided-by-target"):
                print(f"   {r['status']:<26} {r['lib']}  {r['stock_partitions']}")
    if args.json:
        with args.json.open("w", newline="\n") as f:
            json.dump(report, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
