"""Pure-Python DEX reader: class definitions and outgoing references (with per-class attribution).

Supports classic DEX (035-040) and container DEX (041), where several logical dex
files share one data section and offsets are relative to the container start.
"""
import struct
import zipfile

NO_INDEX = 0xFFFFFFFF


def _uleb(buf, pos):
    result = shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7


# code-unit length per opcode (Dalvik instruction formats)
_LEN = [1] * 256
for _op, _n in (
    (0x02, 2), (0x03, 3), (0x05, 2), (0x06, 3), (0x08, 2), (0x09, 3), (0x13, 2), (0x14, 3), (0x15, 2),
    (0x16, 2), (0x17, 3), (0x18, 5), (0x19, 2), (0x1A, 2), (0x1B, 3), (0x1C, 2), (0x1F, 2), (0x20, 2),
    (0x22, 2), (0x23, 2), (0x24, 3), (0x25, 3), (0x26, 3), (0x29, 2), (0x2A, 3), (0x2B, 3), (0x2C, 3),
    (0xFA, 4), (0xFB, 4), (0xFC, 3), (0xFD, 3), (0xFE, 2), (0xFF, 2),
):
    _LEN[_op] = _n
for _lo, _hi, _n in (
    (0x2D, 0x3D, 2), (0x44, 0x6D, 2), (0x6E, 0x72, 3), (0x74, 0x78, 3), (0x90, 0xAF, 2), (0xD0, 0xE2, 2),
):
    for _op in range(_lo, _hi + 1):
        _LEN[_op] = _n

_TYPE_OPS = {0x1C, 0x1F, 0x20, 0x22, 0x23, 0x24, 0x25}
_FIELD_OPS = set(range(0x52, 0x6E))
_METHOD_OPS = set(range(0x6E, 0x73)) | set(range(0x74, 0x79)) | {0xFA, 0xFB}


class Dex:
    """One logical dex file."""

    def __init__(self, buf, header_off=0, source=""):
        self.buf = buf
        self.source = source
        magic = buf[header_off : header_off + 8]
        if magic[:4] != b"dex\n":
            raise ValueError("not a dex file")
        self.version = int(magic[4:7])
        self.base = 0 if self.version >= 41 else header_off
        self.file_size = struct.unpack_from("<I", buf, header_off + 0x20)[0]
        (
            self.n_str, o_str, self.n_type, o_type, self.n_proto, o_proto,
            self.n_field, o_field, self.n_method, o_method, self.n_class, o_class,
        ) = struct.unpack_from("<12I", buf, header_off + 0x38)
        b = self.base
        self._str_off = struct.unpack_from(f"<{self.n_str}I", buf, b + o_str) if self.n_str else ()
        self._type = struct.unpack_from(f"<{self.n_type}I", buf, b + o_type) if self.n_type else ()
        self._o_proto, self._o_field, self._o_method, self._o_class = (
            b + o_proto, b + o_field, b + o_method, b + o_class,
        )
        self._strings = {}
        self._protos = {}

    def string(self, idx):
        s = self._strings.get(idx)
        if s is None:
            pos = self.base + self._str_off[idx]
            _, pos = _uleb(self.buf, pos)
            end = self.buf.index(0, pos)
            raw = self.buf[pos:end]
            try:
                s = raw.decode("utf-8", "surrogatepass")
            except UnicodeDecodeError:
                # Modified UTF-8: an embedded NUL is encoded as C0 80.
                s = raw.replace(bytes([0xC0, 0x80]), bytes(1)).decode("utf-8", "replace")
            self._strings[idx] = s
        return s

    def type(self, idx):
        return self.string(self._type[idx])

    def proto(self, idx):
        sig = self._protos.get(idx)
        if sig is None:
            _, ret, params_off = struct.unpack_from("<III", self.buf, self._o_proto + idx * 12)
            params = ""
            if params_off:
                pos = self.base + params_off
                n = struct.unpack_from("<I", self.buf, pos)[0]
                params = "".join(self.type(t) for t in struct.unpack_from(f"<{n}H", self.buf, pos + 4))
            sig = f"({params}){self.type(ret)}"
            self._protos[idx] = sig
        return sig

    def field(self, idx):
        cls, typ, name = struct.unpack_from("<HHI", self.buf, self._o_field + idx * 8)
        return self.type(cls), self.string(name), self.type(typ)

    def method(self, idx):
        cls, proto, name = struct.unpack_from("<HHI", self.buf, self._o_method + idx * 8)
        return self.type(cls), self.string(name), self.proto(proto)

    def classes(self, scan_code=False):
        """Yield dicts describing each class_def (optionally with the ids its bytecode references)."""
        buf = self.buf
        for i in range(self.n_class):
            cls, access, sup, ifaces_off, _, _, data_off, _ = struct.unpack_from(
                "<8I", buf, self._o_class + i * 32
            )
            info = {
                "name": self.type(cls),
                "access": access,
                "super": self.type(sup) if sup != NO_INDEX else None,
                "interfaces": [],
                "fields": set(),
                "methods": set(),
            }
            if ifaces_off:
                pos = self.base + ifaces_off
                n = struct.unpack_from("<I", buf, pos)[0]
                info["interfaces"] = [self.type(t) for t in struct.unpack_from(f"<{n}H", buf, pos + 4)]
            refs = {"types": set(), "fields": set(), "methods": set()} if scan_code else None
            if data_off:
                pos = self.base + data_off
                counts = []
                for _ in range(4):
                    v, pos = _uleb(buf, pos)
                    counts.append(v)
                for group in range(2):
                    idx = 0
                    for _ in range(counts[group]):
                        diff, pos = _uleb(buf, pos)
                        _, pos = _uleb(buf, pos)
                        idx += diff
                        _, name, typ = self.field(idx)
                        info["fields"].add((name, typ))
                for group in range(2, 4):
                    idx = 0
                    for _ in range(counts[group]):
                        diff, pos = _uleb(buf, pos)
                        _, pos = _uleb(buf, pos)
                        code_off, pos = _uleb(buf, pos)
                        idx += diff
                        _, name, sig = self.method(idx)
                        info["methods"].add((name, sig))
                        if scan_code and code_off:
                            self._scan(self.base + code_off, refs)
            if scan_code:
                info["refs"] = refs
            yield info

    def _scan(self, code_off, refs):
        buf = self.buf
        insns_size = struct.unpack_from("<I", buf, code_off + 12)[0]
        start = code_off + 16
        try:
            insns = struct.unpack_from(f"<{insns_size}H", buf, start)
        except struct.error:
            return
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
                    count = insns[pc + 2] | (insns[pc + 3] << 16)
                    pc += (count * insns[pc + 1] + 1) // 2 + 4
                else:
                    pc += 1
                continue
            if pc + 1 < insns_size:
                if op in _METHOD_OPS:
                    refs["methods"].add(insns[pc + 1])
                elif op in _FIELD_OPS:
                    refs["fields"].add(insns[pc + 1])
                elif op in _TYPE_OPS:
                    refs["types"].add(insns[pc + 1])
            pc += _LEN[op]


def iter_dex(buf, source=""):
    """Yield every logical Dex contained in a dex buffer (handles v41 containers)."""
    pos = 0
    while pos + 0x70 <= len(buf) and buf[pos : pos + 4] == b"dex\n":
        dex = Dex(buf, pos, source)
        yield dex
        if dex.file_size <= 0:
            break
        pos += dex.file_size
        if dex.version < 41:
            break


def load(path):
    """Return every Dex found in an APK/JAR/APEX zip (classes*.dex) or in a raw .dex file."""
    out = []
    path = str(path)
    if path.endswith(".dex"):
        with open(path, "rb") as f:
            out.extend(iter_dex(f.read(), path))
        return out
    try:
        with zipfile.ZipFile(path) as z:
            names = sorted(
                (n for n in z.namelist() if n.startswith("classes") and n.endswith(".dex") and "/" not in n),
                key=lambda n: (len(n), n),
            )
            for name in names:
                out.extend(iter_dex(z.read(name), f"{path}!{name}"))
    except (zipfile.BadZipFile, OSError):
        pass
    return out
