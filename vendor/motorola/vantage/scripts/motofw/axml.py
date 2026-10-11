"""Minimal Android binary XML (AXML) parser, enough to read AndroidManifest.xml.

Resource references are reported as "@0x7f...." because resolving them would need
resources.arsc; every field the validators rely on (package, sharedUserId, SDK
levels, permissions, uses-library, components, overlay target) is a literal.
"""
import struct

RES_STRING_POOL = 0x0001
RES_XML = 0x0003
RES_XML_START_NAMESPACE = 0x0100
RES_XML_END_NAMESPACE = 0x0101
RES_XML_START_ELEMENT = 0x0102
RES_XML_END_ELEMENT = 0x0103
RES_XML_RESOURCE_MAP = 0x0180

TYPE_REFERENCE = 0x01
TYPE_ATTRIBUTE = 0x02
TYPE_STRING = 0x03
TYPE_FLOAT = 0x04
TYPE_INT_DEC = 0x10
TYPE_INT_HEX = 0x11
TYPE_INT_BOOLEAN = 0x12

# android:* attribute resource ids, used only when the string pool carries no name
ATTR_NAMES = {
    0x01010003: "name",
    0x01010006: "permission",
    0x01010009: "protectionLevel",
    0x0101000B: "sharedUserId",
    0x0101000C: "hasCode",
    0x0101000D: "persistent",
    0x0101000E: "enabled",
    0x01010010: "exported",
    0x01010011: "process",
    0x01010018: "authorities",
    0x0101001C: "priority",
    0x01010021: "targetPackage",
    0x01010024: "value",
    0x01010025: "resource",
    0x0101020C: "minSdkVersion",
    0x0101021B: "versionCode",
    0x0101021C: "versionName",
    0x01010270: "targetSdkVersion",
    0x01010271: "maxSdkVersion",
    0x0101028E: "required",
    0x010104EA: "extractNativeLibs",
}


class Element:
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag):
        self.tag = tag
        self.attrs = {}
        self.children = []

    def get(self, name, default=None):
        return self.attrs.get(name, default)

    def iter(self, tag=None):
        if tag is None or self.tag == tag:
            yield self
        for child in self.children:
            yield from child.iter(tag)

    def findall(self, tag):
        return [c for c in self.children if c.tag == tag]


def _decode_length8(data, pos):
    val = data[pos]
    pos += 1
    if val & 0x80:
        val = ((val & 0x7F) << 8) | data[pos]
        pos += 1
    return val, pos


def _parse_string_pool(data, start):
    _, header_size, _ = struct.unpack_from("<HHI", data, start)
    string_count, _, flags, strings_start, _ = struct.unpack_from("<IIIII", data, start + 8)
    utf8 = bool(flags & 0x100)
    offsets = struct.unpack_from(f"<{string_count}I", data, start + header_size)
    base = start + strings_start
    out = []
    for off in offsets:
        pos = base + off
        try:
            if utf8:
                _, pos = _decode_length8(data, pos)
                nbytes, pos = _decode_length8(data, pos)
                out.append(data[pos : pos + nbytes].decode("utf-8", "replace"))
            else:
                nchars = struct.unpack_from("<H", data, pos)[0]
                pos += 2
                if nchars & 0x8000:
                    nchars = ((nchars & 0x7FFF) << 16) | struct.unpack_from("<H", data, pos)[0]
                    pos += 2
                out.append(data[pos : pos + nchars * 2].decode("utf-16-le", "replace"))
        except (IndexError, struct.error):
            out.append("")
    return out


def _value(strings, data_type, raw):
    if data_type == TYPE_STRING:
        return strings[raw] if 0 <= raw < len(strings) else ""
    if data_type == TYPE_INT_BOOLEAN:
        return raw != 0
    if data_type == TYPE_INT_DEC:
        return raw - (1 << 32) if raw & 0x80000000 else raw
    if data_type == TYPE_INT_HEX:
        return raw
    if data_type in (TYPE_REFERENCE, TYPE_ATTRIBUTE):
        return f"@0x{raw:08x}"
    if data_type == TYPE_FLOAT:
        return struct.unpack("<f", struct.pack("<I", raw))[0]
    return raw


def parse(data):
    """Parse binary XML bytes and return the root Element."""
    rtype, _, total = struct.unpack_from("<HHI", data, 0)
    if rtype != RES_XML:
        raise ValueError("not a binary XML document")
    strings, resmap = [], []
    root, stack = None, []
    pos = 8
    end = min(total, len(data))
    while pos + 8 <= end:
        ctype, hsize, csize = struct.unpack_from("<HHI", data, pos)
        if csize < 8:
            break
        if ctype == RES_STRING_POOL:
            strings = _parse_string_pool(data, pos)
        elif ctype == RES_XML_RESOURCE_MAP:
            resmap = struct.unpack_from(f"<{(csize - hsize) // 4}I", data, pos + hsize)
        elif ctype == RES_XML_START_ELEMENT:
            body = pos + hsize
            _, name_idx, attr_start, attr_size, attr_count = struct.unpack_from("<iiHHH", data, body)
            elem = Element(strings[name_idx] if 0 <= name_idx < len(strings) else "?")
            for i in range(attr_count):
                apos = body + attr_start + i * attr_size
                _, aname, araw, _, _, dtype, adata = struct.unpack_from("<iiiHBBI", data, apos)
                name = strings[aname] if 0 <= aname < len(strings) else ""
                if not name and 0 <= aname < len(resmap):
                    name = ATTR_NAMES.get(resmap[aname], f"attr_0x{resmap[aname]:08x}")
                if dtype == TYPE_STRING and 0 <= araw < len(strings):
                    val = strings[araw]
                else:
                    val = _value(strings, dtype, adata)
                elem.attrs[name] = val
            if stack:
                stack[-1].children.append(elem)
            else:
                root = elem
            stack.append(elem)
        elif ctype == RES_XML_END_ELEMENT:
            if stack:
                stack.pop()
        pos += csize
    if root is None:
        raise ValueError("binary XML has no root element")
    return root
