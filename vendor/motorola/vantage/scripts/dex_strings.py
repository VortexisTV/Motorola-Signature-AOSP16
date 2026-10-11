#!/usr/bin/env python3
"""List string constants of an APK/JAR dex that look like runtime integration points.

    dex_strings.py <apk-or-jar> [--all] [--grep REGEX]

Categories: system properties, binder/HAL service names, intent actions, permissions,
package names, content URIs, settings keys and file paths. Useful for spotting what a
proprietary component expects to exist on the device (static evidence only).
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from motofw import dex as dexmod  # noqa: E402

CATEGORIES = [
    ("hal_interface", re.compile(r"^(vendor|android)\.(qti|hardware|hidl|frameworks|system)\.[\w.]+(@\d+\.\d+)?(::\w+|\.I\w+)(/\w+)?$")),
    ("property", re.compile(r"^(persist|ro|sys|vendor|debug|ril|gsm|telephony|net|init|service|log|config|dalvik|wifi|bluetooth|media|camera|audio)\.[a-z0-9_.\-]+$", re.I)),
    ("permission", re.compile(r"^[a-z][\w.]*\.permission\.[A-Z_0-9]+$")),
    ("action", re.compile(r"^[a-z][\w.]*\.(action|intent)\.[\w.]+$|^[a-z][\w.]+\.[A-Z][A-Z_0-9]{4,}$")),
    ("content_uri", re.compile(r"^content://")),
    ("path", re.compile(r"^/(data|vendor|system|system_ext|product|odm|dev|sys|proc|mnt|apex|sdcard|storage)/")),
    ("package_or_class", re.compile(r"^(com|org|vendor|android|motorola)\.[a-z0-9_]+(\.[A-Za-z0-9_$]+)+$")),
]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--all", action="store_true", help="print every string, uncategorised")
    ap.add_argument("--grep", default=None, help="only strings matching this regex (case-insensitive)")
    args = ap.parse_args()
    grep = re.compile(args.grep, re.I) if args.grep else None
    strings = set()
    for d in dexmod.load(args.path):
        for i in range(d.n_str):
            try:
                strings.add(d.string(i))
            except (ValueError, IndexError, UnicodeDecodeError):
                pass
    buckets = {}
    for s in sorted(strings):
        if grep and not grep.search(s):
            continue
        if args.all:
            buckets.setdefault("all", []).append(s)
            continue
        if len(s) > 200 or s.startswith(("L", "[")) and s.endswith(";"):
            continue
        for name, pat in CATEGORIES:
            if pat.match(s):
                buckets.setdefault(name, []).append(s)
                break
    for name, items in buckets.items():
        print(f"== {name} ({len(items)})")
        for s in items:
            print("   ", s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
