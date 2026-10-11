#!/usr/bin/env python3
"""Symbol-level linkage check of ported native libraries against an image tree.

DT_NEEDED resolution (preflight: native.needed) only proves that the named libraries exist.
A stock library built against Qualcomm's or Motorola's framework can still fail to load on
AOSP with "cannot locate symbol". This check takes every strong undefined dynamic symbol of a
subject library and looks for a definition in its DT_NEEDED closure, the way the Android
linker does (versions are ignored, weak undefined symbols are allowed to stay unresolved).

    check_native_symbols.py --map /system=DIR --map /system_ext=DIR --map /product=DIR \
        --map /apex=DIR [--map /vendor=DIR] --manifest proprietary-files.txt \
        [--apk /product/priv-app/X/X.apk ...] [--baseline-map ...] --out report.json

--apk adds the arm64 libraries bundled in an APK; they may also use the APK's other libraries.
With --baseline-map (the stock system) symbols that are unresolved on stock as well are
reported separately: those are resolved some other way at run time (or never used).

Static: it proves that a library can be linked, not that the code works on hardware.
"""
import argparse
import json
import struct
import sys
import zipfile
from pathlib import Path

SHT_DYNAMIC, SHT_DYNSYM = 6, 11
DT_NEEDED, DT_SONAME = 1, 14


def parse_elf(buf):
    """(soname, needed, defined, undefined_strong) of a little-endian ELF64, or None."""
    if buf[:4] != bytes([0x7F, 0x45, 0x4C, 0x46]) or buf[4] != 2 or buf[5] != 1:
        return None
    shoff, = struct.unpack_from("<Q", buf, 0x28)
    shentsize, shnum = struct.unpack_from("<HH", buf, 0x3A)
    secs = []
    for i in range(shnum):
        off = shoff + i * shentsize
        if off + 64 > len(buf):
            return None
        _, stype, _, _, soff, ssize, slink, _, _, sent = struct.unpack_from("<IIQQQQIIQQ", buf, off)
        secs.append((stype, soff, ssize, slink, sent))

    def cstr(table, idx):
        base = table[1] + idx
        end = buf.find(bytes(1), base)
        return buf[base:end].decode("utf-8", "replace")

    soname, needed, defined, undefined = None, [], set(), set()
    for stype, soff, ssize, slink, sent in secs:
        if stype == SHT_DYNAMIC and slink < len(secs):
            for pos in range(soff, soff + ssize, 16):
                tag, val = struct.unpack_from("<qQ", buf, pos)
                if tag == DT_NEEDED:
                    needed.append(cstr(secs[slink], val))
                elif tag == DT_SONAME:
                    soname = cstr(secs[slink], val)
                elif tag == 0:
                    break
        elif stype == SHT_DYNSYM and slink < len(secs):
            for pos in range(soff + 24, soff + ssize, 24):
                name, info, other, shndx = struct.unpack_from("<IBBH", buf, pos)
                if not name:
                    continue
                bind = info >> 4
                sym = cstr(secs[slink], name)
                if shndx == 0:
                    if bind == 1:
                        undefined.add(sym)
                elif bind in (1, 2) and (other & 3) in (0, 3):
                    defined.add(sym)
    return soname, needed, defined, undefined


class Libs:
    """Library name -> parsed ELF for one image (system-side search path, APEXes, optionally vendor)."""

    def __init__(self, maps):
        self.index = {}
        self.cache = {}
        order = ("/system_ext", "/system", "/product", "/vendor", "/odm")
        by_prefix = {}
        for item in maps:
            prefix, _, host = item.partition("=")
            by_prefix.setdefault(prefix.rstrip("/"), []).append(Path(host))
        for prefix in order:
            for root in by_prefix.get(prefix, []):
                self._add_dir(root / "lib64")
        for root in by_prefix.get("/apex", []):
            if root.is_dir():
                for apex in sorted(p for p in root.iterdir() if p.is_dir()):
                    self._add_dir(apex / "lib64")
                    self._add_dir(apex / "lib64" / "bionic")

    def _add_dir(self, d):
        if not d.is_dir():
            return
        for f in d.iterdir():
            if f.name.endswith(".so") and f.is_file():  # is_file() is False for dangling bionic symlinks
                self.index.setdefault(f.name, f)

    def get(self, name, extra=None):
        if extra and name in extra:
            return extra[name]
        if name not in self.cache:
            path = self.index.get(name)
            self.cache[name] = parse_elf(path.read_bytes()) if path else None
        return self.cache[name]

    def unresolved(self, subject, extra=None):
        """(missing libraries, unresolved strong symbols) for a parsed subject."""
        _, needed, _, undefined = subject
        seen, queue, missing, provided = set(), list(needed), [], set()
        while queue:
            name = queue.pop(0)
            if name in seen:
                continue
            seen.add(name)
            lib = self.get(name, extra)
            if lib is None:
                missing.append(name)
                continue
            provided |= lib[2]
            queue.extend(lib[1])
        return missing, sorted(undefined - provided - subject[2])


def subjects_from_manifest(manifest, maps):
    hosts = {}
    for item in maps:
        prefix, _, host = item.partition("=")
        hosts.setdefault(prefix.strip("/"), Path(host))
    for line in manifest.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        spec = line.partition("|")[0]
        rel = spec.partition(";")[0]
        if "SYMLINK=" in spec or not rel.endswith(".so") or "/lib64/" not in f"/{rel}":
            continue
        part, _, sub = rel.partition("/")
        path = hosts.get(part, Path("/nonexistent")) / sub
        if path.is_file():
            yield f"/{rel}", parse_elf(path.read_bytes()), None


def subjects_from_apk(device_path, maps):
    best = None
    for item in maps:
        prefix, _, host = item.partition("=")
        prefix = prefix.rstrip("/")
        if device_path.startswith(prefix + "/") and (best is None or len(prefix) > len(best[0])):
            best = (prefix, Path(host))
    if not best:
        return
    apk = best[1] / device_path[len(best[0]):].lstrip("/")
    if not apk.is_file():
        return
    bundled = {}
    with zipfile.ZipFile(apk) as z:
        for n in z.namelist():
            if n.startswith("lib/arm64-v8a/") and n.endswith(".so"):
                parsed = parse_elf(z.read(n))
                if parsed:
                    bundled[n.rsplit("/", 1)[-1]] = parsed
    for name, parsed in sorted(bundled.items()):
        yield f"{device_path}!{name}", parsed, bundled


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", action="append", required=True)
    ap.add_argument("--baseline-map", action="append", default=[])
    ap.add_argument("--manifest", type=Path)
    ap.add_argument("--apk", action="append", default=[])
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    libs = Libs(args.map)
    base = Libs(args.baseline_map) if args.baseline_map else None
    todo = list(subjects_from_manifest(args.manifest, args.map)) if args.manifest else []
    for apk in args.apk:
        todo.extend(subjects_from_apk(apk, args.map))

    results, bad = [], 0
    for name, parsed, extra in todo:
        if parsed is None:
            continue
        missing, unresolved = libs.unresolved(parsed, extra)
        also_stock = []
        if base is not None and unresolved:
            _, stock_unres = base.unresolved(parsed, extra)
            also_stock = sorted(set(unresolved) & set(stock_unres))
        new = [s for s in unresolved if s not in also_stock]
        bad += bool(new or missing)
        results.append({"subject": name, "needed": parsed[1], "missing_libraries": missing,
                        "unresolved_new": new, "unresolved_also_on_stock": also_stock,
                        "undefined_total": len(parsed[3])})
        flag = "FAIL" if new or missing else "ok  "
        print(f"{flag} {name}: {len(parsed[3])} imported symbols, {len(new)} unresolved here"
              + (f" ({len(also_stock)} more unresolved on stock too)" if also_stock else "")
              + (f", missing libraries {missing}" if missing else ""))
        for s in new[:12]:
            print(f"       {s}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"subjects": results}, indent=1) + chr(10), encoding="utf-8")
    print(f"{len(results)} libraries checked, {bad} with unresolved symbols or missing libraries")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
