#!/usr/bin/env python3
"""Dump an APK's compiled resource values to JSON (via aapt2) and optionally query/diff them.

    resdump.py dump  <apk> <out.json> [--aapt2 PATH]
    resdump.py show  <dump.json> <regex> [--types string,bool,...]
    resdump.py diff  <stock.json> <ours.json> [<regex>] [--types string,bool,integer,array,xml]

"diff" lists resources whose default-configuration value differs (or exists on one side only);
it is how values that the OEM baked into framework-res.apk at build time are found.
"""
import argparse
import json
import re
import subprocess
import sys

RES_RE = re.compile(r"^\s+resource 0x[0-9a-f]+ (\S+)")
TYPE_RE = re.compile(r"^\s+type \S+ id=|^Package name=|^Binary APK")
DEFAULT_AAPT2 = "/work/aosp/prebuilts/sdk/tools/linux/bin/aapt2"


def parse(text):
    res, name, buf = {}, None, []
    for line in text.splitlines():
        m = RES_RE.match(line)
        if m or TYPE_RE.match(line):
            if name:
                res[name] = " ".join(buf).strip()
            name, buf = (m.group(1), []) if m else (None, [])
        elif name and line.strip():
            buf.append(line.strip())
    if name:
        res[name] = " ".join(buf).strip()
    return res


def default_value(text):
    """Value for the default configuration: the part following the leading '()' marker."""
    if not text.startswith("()"):
        return None
    m = re.search(r"\s\((?!array\)|style\)|plurals\)|attr\)|file\)|styleable\))[A-Za-z0-9][^()]*\)\s", text[2:])
    return (text[2 : 2 + m.start()] if m else text[2:]).strip()


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump")
    d.add_argument("apk")
    d.add_argument("out")
    d.add_argument("--aapt2", default=DEFAULT_AAPT2)
    s = sub.add_parser("show")
    s.add_argument("dump")
    s.add_argument("regex")
    s.add_argument("--types", default="")
    s.add_argument("--width", type=int, default=220)
    f = sub.add_parser("diff")
    f.add_argument("stock")
    f.add_argument("ours")
    f.add_argument("regex", nargs="?", default=".")
    f.add_argument("--types", default="string,bool,integer,array,xml,dimen,fraction")
    f.add_argument("--width", type=int, default=200)
    args = ap.parse_args()

    if args.cmd == "dump":
        proc = subprocess.run([args.aapt2, "dump", "resources", args.apk], capture_output=True, text=True,
                              errors="replace")
        if proc.returncode != 0:
            sys.exit(f"aapt2 failed: {proc.stderr[-300:]}")
        res = parse(proc.stdout)
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(res, fh, indent=0, ensure_ascii=False)
        print(f"{len(res)} resources -> {args.out}")
        return 0

    types = {t for t in args.types.split(",") if t}
    pat = re.compile(args.regex, re.I)
    if args.cmd == "show":
        for name, val in sorted(load(args.dump).items()):
            if pat.search(name) and (not types or name.split("/")[0] in types):
                print(f"{name} = {val[:args.width]}")
        return 0

    stock, ours = load(args.stock), load(args.ours)
    changed = added = 0
    for name in sorted(set(stock) | set(ours)):
        if not pat.search(name) or (types and name.split("/")[0] not in types):
            continue
        a, b = stock.get(name), ours.get(name)
        if a is not None and b is None:
            added += 1
            print(f"STOCK-ONLY {name} = {a[:args.width]}")
        elif a is not None and b is not None and default_value(a) != default_value(b):
            changed += 1
            print(f"DIFFERS    {name}\n   stock: {str(default_value(a))[:args.width]}\n   ours : {str(default_value(b))[:args.width]}")
    print(f"-- {changed} differing, {added} stock-only (within filter)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
