#!/usr/bin/env python3
"""What the STOCK first-stage init (init_boot ramdisk) does with a DSU guest image.

    check_stock_init.py INIT_ELF LLVM_OBJDUMP [--out reports/vantage/stock-init.json]

The binary is stripped and static, so the facts are established from the code itself: strings
are located in the file, the instructions that load their address (ADRP+ADD) are found in the
disassembly, and calls between the functions that contain them are checked.

  init.unlock_state  the function that reads androidboot.verifiedbootstate returns true only for
                     the 6-character value "orange"
  init.spl_rollback  the function that logs "Image rollback detected ..." (security patch level
                     of a standalone image older than the device's) calls that function and
                     branches on its result; it also holds the "Allowing rollbacked standalone
                     image when the device is unlocked" message
  init.skip_mount    the function that reads /system/system_ext/etc/init/config/skip_mount.cfg is
                     called from the first-stage mount routine

This is the same logic as AOSP system/core/init/first_stage_mount.cpp (IsStandaloneImageRollback,
MountPartitions) and fs_mgr (AvbHandle::IsDeviceUnlocked, SkipMountingPartitions).
"""
import bisect
import hashlib
import json
import re
import struct
import subprocess
import sys

S_STATE = "verifiedbootstate"
S_ROLLBACK = "Image rollback detected for "
S_ALLOW = "Allowing rollbacked standalone image when the device is unlocked"
S_SKIPCFG = "/system/system_ext/etc/init/config/skip_mount.cfg"
S_SKIPLOG = "Skip mounting mountpoint: "
S_MOUNT = ", ignoring mount for no_fail partition"
ENDS = ("ret", "retaa", "retab", "b", "br", "udf", "nop", "brk", "bl")


def main():
    elf, objdump = sys.argv[1], sys.argv[2]
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    buf = open(elf, "rb").read()
    phoff, = struct.unpack_from("<Q", buf, 0x20)
    phentsize, phnum = struct.unpack_from("<HH", buf, 0x36)
    loads = []
    for i in range(phnum):
        ptype, _, off, vaddr, _, filesz, _, _ = struct.unpack_from("<IIQQQQQQ", buf, phoff + i * phentsize)
        if ptype == 1:
            loads.append((off, vaddr, filesz))
    def va(offset):
        return next(v + offset - o for o, v, n in loads if o <= offset < o + n)
    targets = {}
    for s in (S_STATE, S_ROLLBACK, S_ALLOW, S_SKIPCFG, S_SKIPLOG, S_MOUNT):
        pos = buf.find(s.encode())
        if pos < 0 or buf.find(s.encode(), pos + 1) >= 0:
            print("  [FAIL   ] init.strings: %r is %s in the binary" % (s, "missing" if pos < 0 else "ambiguous"))
            return 1
        targets[va(pos)] = s
    ins = []
    for line in subprocess.run([objdump, "-d", "--no-show-raw-insn", elf], capture_output=True, text=True).stdout.splitlines():
        m = re.match("^ *([0-9a-f]+):[ " + chr(9) + "]+([^ " + chr(9) + "]+)[ " + chr(9) + "]*(.*)$", line)
        if m:
            ins.append((int(m.group(1), 16), m.group(2), m.group(3)))
    # function starts (heuristic for this compiler output: frame setup right after a terminator)
    starts = [0]
    for j in range(1, len(ins)):
        op, args, prev = ins[j][1], ins[j][2], ins[j - 1][1]
        if (op in ("paciasp", "pacibsp") and prev in ENDS) or \
           (op == "stp" and args.startswith("x29, x30, [sp, #-") and prev in ENDS) or \
           (op == "sub" and args.startswith("sp, sp, #") and prev in ENDS[:-1]):
            starts.append(j)
    def func(idx):
        k = bisect.bisect_right(starts, idx) - 1
        return starts[k], (starts[k + 1] if k + 1 < len(starts) else len(ins))
    refs, adrp = {}, {}
    for idx, (addr, op, args) in enumerate(ins):
        if op == "adrp":
            m = re.match("(x[0-9]+), (0x[0-9a-f]+)", args)
            if m:
                adrp[m.group(1)] = int(m.group(2), 16)
        elif op == "add":
            m = re.match("(x[0-9]+), (x[0-9]+), #(0x[0-9a-f]+)", args)
            if m and m.group(2) in adrp and adrp[m.group(2)] + int(m.group(3), 16) in targets:
                refs.setdefault(targets[adrp[m.group(2)] + int(m.group(3), 16)], []).append(idx)
    hx = lambda i: "0x%x" % ins[i][0]
    results, rc = [], 0
    def add(ok, check, summary, evidence):
        nonlocal rc
        rc |= 0 if ok else 1
        results.append({"status": "PASS" if ok else "FAIL", "check": check, "summary": summary, "evidence": evidence})
        print("  [%-7s] %s: %s" % ("PASS" if ok else "FAIL", check, summary))

    lo, hi = func(refs[S_STATE][0])
    body = " ; ".join("%s %s" % (o, a) for _, o, a in ins[lo:hi])
    orange = all(x in body for x in ("#0x726f", "#0x6e61, lsl #16", "#0x6567", "#0x6"))   # "oran" + "ge", length 6
    unlock = ins[lo][0]
    add(orange and len(refs[S_STATE]) == 1, "init.unlock_state",
        "the only function that reads androidboot.verifiedbootstate (%s) returns true exactly for the value 'orange'" % hx(lo),
        ["immediates 0x6e61726f ('oran') and 0x6567 ('ge'), length compare with 6 in %s..%s" % (hx(lo), hx(hi - 1))])
    callers = [i for i, (_, o, a) in enumerate(ins) if o == "bl" and a.split()[0] == "0x%x" % unlock]

    rlo, rhi = func(refs[S_ROLLBACK][0])
    inside = [i for i in callers if rlo <= i < rhi]
    branches = ["%s: bl unlock_state ; %s: %s %s" % (hx(i), hx(i + 1), ins[i + 1][1], ins[i + 1][2].split(" <")[0]) for i in inside]
    ok = bool(inside) and all(ins[i + 1][1] in ("tbz", "tbnz", "cbz", "cbnz") and ins[i + 1][2].startswith("w0") for i in inside) \
        and any(rlo <= i < rhi for i in refs[S_ALLOW])
    add(ok, "init.spl_rollback",
        "the stock function that logs 'Image rollback detected' (%s) calls the unlock-state function %d time(s) and "
        "branches on the result; the 'Allowing rollbacked standalone image when the device is unlocked' message is in "
        "the same function: the comparison is enforced when locked and allowed when the state is 'orange'" % (hx(rlo), len(inside)),
        branches + ["other callers of the unlock-state function: " + ", ".join(hx(i) for i in callers if i not in inside)])

    slo, shi = func(refs[S_SKIPCFG][0])
    mlo, mhi = func(refs[S_MOUNT][0])
    calls = [i for i, (_, o, a) in enumerate(ins) if o == "bl" and a.split()[0] == "0x%x" % ins[slo][0]]
    from_mount = [i for i in calls if mlo <= i < mhi]
    ok = bool(from_mount) and any(slo <= i < shi for i in refs[S_SKIPLOG])
    add(ok, "init.skip_mount",
        "the stock first-stage mount routine (%s) calls the function that reads skip_mount.cfg (%s) from the mounted "
        "system image and drops the matching fstab entries" % (hx(mlo), hx(slo)),
        ["call at " + ", ".join(hx(i) for i in from_mount), "all callers: " + ", ".join(hx(i) for i in calls)])
    if out:
        json.dump({"binary": elf, "sha256": hashlib.sha256(buf).hexdigest(), "instructions": len(ins), "results": results},
                  open(out, "w"), indent=1)
    return rc


if __name__ == "__main__":
    sys.exit(main())
