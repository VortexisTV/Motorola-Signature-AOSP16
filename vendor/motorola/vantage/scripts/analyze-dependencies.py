#!/usr/bin/env python3
"""Dependency analysis of the integration components (single entry point).

    analyze-dependencies.py <report_dir> <vendor_dir> [--map /system=DIR ...] [--target-system-libs FILE]

1. Re-resolves components.json into proprietary-files.txt (APK + shared-library jars and
   their permission XML + JNI links + DT_NEEDED / dlopen-candidate native libraries).
2. Regenerates Android.bp and vantage-vendor.mk from it.
3. With --map (same convention as preflight.py), runs the Java linkage check of every ported
   APK/JAR against that image tree and writes <report_dir>/dependency-linkage.json.

Steps 1 and 2 only need the firmware inventory (reports/inventory); step 3 needs an extracted
or built image tree.
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(*cmd):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([sys.executable, "-I", *map(str, cmd)]).returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report_dir", type=Path)
    ap.add_argument("vendor_dir", type=Path)
    ap.add_argument("--map", action="append", default=[])
    ap.add_argument("--target-system-libs", type=Path)
    args = ap.parse_args()

    manifest = args.vendor_dir / "proprietary-files.txt"
    cmd = [HERE / "resolve_components.py", args.report_dir, args.vendor_dir / "components.json", manifest]
    if args.target_system_libs:
        cmd += ["--target-system-libs", args.target_system_libs]
    rc = run(*cmd)
    rc |= run(HERE / "setup_makefiles.py", args.vendor_dir)
    if args.map:
        subjects = []
        for line in manifest.read_text(encoding="utf-8").splitlines():
            rel = line.split("|")[0].split(";")[0].strip()
            if rel and not line.startswith("#") and rel.endswith((".apk", ".jar")) and "/" + rel not in subjects:
                subjects.append("/" + rel)
        cmd = [HERE / "check_java_linkage.py", "--out", args.report_dir / "dependency-linkage.json"]
        for m in args.map:
            cmd += ["--map", m]
        for s in subjects:
            cmd += ["--subject", s]
        rc |= run(*cmd)
    return 1 if rc else 0


if __name__ == "__main__":
    sys.exit(main())
