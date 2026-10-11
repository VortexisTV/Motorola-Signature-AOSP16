#!/usr/bin/env python3
"""For calls into a set of classes, report whether each call site is inside a try block.

    dex_guard_scan.py <apk-or-jar> --target-prefix Lmotorola/core_services/ [--target-prefix ...]
                      [--catches Ljava/lang/RuntimeException;] [--json out.json]

Use case: an app bundles throwing stubs of an optional OEM library. Where the real library is
absent the stubs run, so a call is only safe if something catches what the stub throws.
A site counts as guarded when an enclosing try in the SAME method has a catch-all or catches
one of the --catches types or their supertypes. Guards further up the call stack are not
visible to this scan, so "unguarded" means "not locally guarded", not "will crash".
"""
import argparse
import json
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from motofw import dex as dexmod  # noqa: E402
from motofw.dex import _LEN, _METHOD_OPS, _uleb  # noqa: E402

SUPERS = {
    "Ljava/lang/RuntimeException;": ["Ljava/lang/RuntimeException;", "Ljava/lang/Exception;", "Ljava/lang/Throwable;"],
    "Ljava/lang/NoClassDefFoundError;": ["Ljava/lang/NoClassDefFoundError;", "Ljava/lang/LinkageError;",
                                         "Ljava/lang/Error;", "Ljava/lang/Throwable;"],
}


def _sleb(buf, pos):
    result = shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            if b & 0x40:
                result -= 1 << shift
            return result, pos


def method_sites(d, code_off, prefixes):
    """Yield (pc, target_method, [catch types incl. '<any>']) for matching invokes in one method."""
    buf = d.buf
    _, _, _, tries_size, _, insns_size = struct.unpack_from("<HHHHII", buf, code_off)
    start = code_off + 16
    insns = struct.unpack_from(f"<{insns_size}H", buf, start)
    tries = []
    if tries_size:
        pos = start + insns_size * 2
        if insns_size % 2:
            pos += 2
        items = [struct.unpack_from("<IHH", buf, pos + i * 8) for i in range(tries_size)]
        hbase = pos + tries_size * 8
        for addr, count, hoff in items:
            p = hbase + hoff
            size, p = _sleb(buf, p)
            types = []
            for _ in range(abs(size)):
                tidx, p = _uleb(buf, p)
                _, p = _uleb(buf, p)
                types.append(d.type(tidx))
            if size <= 0:
                types.append("<any>")
            tries.append((addr, addr + count, types))
    pc = 0
    while pc < insns_size:
        unit = insns[pc]
        op = unit & 0xFF
        if op == 0 and unit != 0:
            if unit == 0x0100 and pc + 1 < insns_size:
                pc += insns[pc + 1] * 2 + 4
            elif unit == 0x0200 and pc + 1 < insns_size:
                pc += insns[pc + 1] * 4 + 2
            elif unit == 0x0300 and pc + 3 < insns_size:
                pc += ((insns[pc + 2] | (insns[pc + 3] << 16)) * insns[pc + 1] + 1) // 2 + 4
            else:
                pc += 1
            continue
        if op in _METHOD_OPS and pc + 1 < insns_size:
            cls, name, sig = d.method(insns[pc + 1])
            if cls.startswith(prefixes):
                caught = [t for lo, hi, types in tries if lo <= pc < hi for t in types]
                yield pc, f"{cls}->{name}", caught
        pc += _LEN[op]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--target-prefix", action="append", required=True)
    ap.add_argument("--catches", default="Ljava/lang/RuntimeException;")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    prefixes = tuple(args.target_prefix)
    accept = set(SUPERS.get(args.catches, [args.catches, "Ljava/lang/Throwable;"])) | {"<any>"}

    sites = []
    for d in dexmod.load(args.path):
        buf = d.buf
        for i in range(d.n_class):
            cls_idx, _, _, _, _, _, data_off, _ = struct.unpack_from("<8I", buf, d._o_class + i * 32)
            owner = d.type(cls_idx)
            if owner.startswith(prefixes) or not data_off:
                continue
            pos = d.base + data_off
            counts = []
            for _ in range(4):
                v, pos = _uleb(buf, pos)
                counts.append(v)
            for _ in range(counts[0] + counts[1]):
                _, pos = _uleb(buf, pos)
                _, pos = _uleb(buf, pos)
            for group in (2, 3):
                idx = 0
                for _ in range(counts[group]):
                    diff, pos = _uleb(buf, pos)
                    _, pos = _uleb(buf, pos)
                    code_off, pos = _uleb(buf, pos)
                    idx += diff
                    if not code_off:
                        continue
                    _, mname, _ = d.method(idx)
                    for pc, target, caught in method_sites(d, d.base + code_off, prefixes):
                        sites.append({"caller": f"{owner}->{mname}", "target": target,
                                      "guarded": bool(accept & set(caught)), "catches": sorted(set(caught))})
    guarded = sum(s["guarded"] for s in sites)
    print(f"{len(sites)} call sites into {list(prefixes)}: {guarded} locally guarded, {len(sites) - guarded} not")
    by_target = defaultdict(lambda: [0, 0])
    for s in sites:
        by_target[s["target"].split("->")[0]][0 if s["guarded"] else 1] += 1
    for cls, (g, u) in sorted(by_target.items(), key=lambda kv: -sum(kv[1])):
        print(f"   {cls:<78} guarded={g:<4} unguarded={u}")
    callers = Counter(s["caller"].split("->")[0] for s in sites if not s["guarded"])
    print("classes with the most locally-unguarded calls:")
    for cls, n in callers.most_common(12):
        print(f"   {n:>4} {cls}")
    if args.json:
        with args.json.open("w", newline="\n") as f:
            json.dump(sites, f, indent=0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
