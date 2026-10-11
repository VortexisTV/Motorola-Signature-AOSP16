#!/usr/bin/env python3
"""List the 64-bit shared libraries the target (AOSP) system image provides on its own.

    gen_target_libs.py --system OUT/system [--manifest proprietary-files.txt] > target-system-libs.txt

resolve_components.py uses the list to decide which DT_NEEDED entries of a stock binary have to
be ported: a library that stock ships in /system is only "already there" if the AOSP build ships
it too. Files installed by this integration layer (everything named in the manifest) are left
out, so the list describes the unmodified baseline even when it is taken from a vantage build.
"""
import argparse
import sys
from pathlib import Path

# linker search path of the default (system) namespace, relative to the system root
LIB_DIRS = ("lib64", "system_ext/lib64", "product/lib64")


def manifest_paths(manifest):
    owned = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rel = line.partition("|")[0].partition(";")[0]
        part, _, sub = rel.partition("/")
        owned.add(sub if part == "system" else f"{part}/{sub}")
    return owned


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--system", type=Path, required=True, help="system root of a built tree (contains lib64/)")
    ap.add_argument("--manifest", type=Path, help="proprietary-files.txt; files it installs are excluded")
    args = ap.parse_args()

    owned = manifest_paths(args.manifest) if args.manifest else set()
    names = set()
    for d in LIB_DIRS:
        base = args.system / d
        if not base.is_dir():
            continue
        for f in base.iterdir():
            if f.name.endswith(".so") and f"{d}/{f.name}" not in owned:
                names.add(f.name)
    if not names:
        sys.exit(f"no libraries found under {args.system}")
    sys.stdout.write("".join(n + chr(10) for n in sorted(names)))


if __name__ == "__main__":
    main()
