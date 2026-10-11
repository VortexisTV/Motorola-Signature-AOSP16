"""Tiny ELF reader: SONAME, DT_NEEDED, machine and class of shared objects/executables."""
import re
import struct

PT_LOAD, PT_DYNAMIC = 1, 2
DT_NULL, DT_NEEDED, DT_STRTAB, DT_SONAME, DT_STRSZ = 0, 1, 5, 14, 10
_SO_NAME = re.compile(rb"(?<![A-Za-z0-9_.+@/-])[A-Za-z0-9_][A-Za-z0-9_.+@-]{2,90}\.so(?![A-Za-z0-9_.])")
MACHINES = {3: "x86", 40: "arm", 62: "x86_64", 183: "arm64", 243: "riscv"}


def is_elf(path):
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


def inspect(path):
    """Return {'bits', 'machine', 'soname', 'needed'} or None when not a little-endian ELF."""
    with open(path, "rb") as f:
        ident = f.read(16)
        if ident[:4] != b"\x7fELF" or ident[5] != 1:
            return None
        is64 = ident[4] == 2
        if is64:
            hdr = f.read(48)
            _, machine, _, _, phoff, _, _, _, phentsize, phnum = struct.unpack_from("<HHIQQQIHHH", hdr)
        else:
            hdr = f.read(36)
            _, machine, _, _, phoff, _, _, _, phentsize, phnum = struct.unpack_from("<HHIIIIIHHH", hdr)
        loads, dyn = [], None
        for i in range(phnum):
            f.seek(phoff + i * phentsize)
            ph = f.read(phentsize)
            if is64:
                ptype, _, offset, vaddr, _, filesz, _, _ = struct.unpack_from("<IIQQQQQQ", ph)
            else:
                ptype, offset, vaddr, _, filesz, _, _, _ = struct.unpack_from("<IIIIIIII", ph)
            if ptype == PT_LOAD:
                loads.append((vaddr, offset, filesz))
            elif ptype == PT_DYNAMIC:
                dyn = (offset, filesz)
        out = {"bits": 64 if is64 else 32, "machine": MACHINES.get(machine, str(machine)), "soname": None, "needed": []}
        if not dyn:
            return out
        f.seek(dyn[0])
        raw = f.read(dyn[1])
        fmt, step = ("<qQ", 16) if is64 else ("<iI", 8)
        needed, soname, strtab, strsz = [], None, None, 0
        for off in range(0, len(raw) - step + 1, step):
            tag, val = struct.unpack_from(fmt, raw, off)
            if tag == DT_NULL:
                break
            if tag == DT_NEEDED:
                needed.append(val)
            elif tag == DT_SONAME:
                soname = val
            elif tag == DT_STRTAB:
                strtab = val
            elif tag == DT_STRSZ:
                strsz = val
        if strtab is None:
            return out
        file_off = None
        for vaddr, offset, filesz in loads:
            if vaddr <= strtab < vaddr + filesz:
                file_off = offset + (strtab - vaddr)
                break
        if file_off is None:
            return out
        f.seek(file_off)
        table = f.read(strsz)

        def name(idx):
            end = table.find(bytes(1), idx)
            return table[idx:end].decode("ascii", "replace")

        out["needed"] = [name(n) for n in needed]
        out["soname"] = name(soname) if soname is not None else None
        # Library names mentioned as plain strings but not linked: dlopen() candidates.
        f.seek(0)
        known = set(out["needed"]) | {out["soname"]}
        refs = {m.decode("ascii") for m in _SO_NAME.findall(f.read())}
        out["so_refs"] = sorted(refs - known)
        return out
