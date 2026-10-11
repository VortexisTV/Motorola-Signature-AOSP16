"""APK / APEX metadata: manifest summary, signing certificate digest, bundled native libs."""
import hashlib
import struct
import zipfile

from . import axml

EOCD_MAGIC = 0x06054B50
SIG_BLOCK_MAGIC = b"APK Sig Block 42"
SCHEME_IDS = {0x7109871A: "v2", 0xF05368C0: "v3", 0x1B93AD61: "v3.1"}


def _u32(buf, off):
    return struct.unpack_from("<I", buf, off)[0]


def _lp(buf, off):
    """Read a u32 length-prefixed field; return (bytes, next_offset)."""
    n = _u32(buf, off)
    return buf[off + 4 : off + 4 + n], off + 4 + n


def _first_cert_from_scheme(value):
    signers, _ = _lp(value, 0)
    signer, _ = _lp(signers, 0)
    signed_data, _ = _lp(signer, 0)
    _, off = _lp(signed_data, 0)  # digests
    certs, _ = _lp(signed_data, off)
    cert, _ = _lp(certs, 0)
    return cert


def _der_tlv(buf, off):
    """Return (tag, header_len, content_len) of the DER element at off."""
    tag = buf[off]
    first = buf[off + 1]
    if first < 0x80:
        return tag, 2, first
    n = first & 0x7F
    return tag, 2 + n, int.from_bytes(buf[off + 2 : off + 2 + n], "big")


def _first_cert_from_pkcs7(der):
    # ContentInfo ::= SEQ { OID, [0] EXPLICIT SignedData }
    _, h, _ = _der_tlv(der, 0)
    off = h
    _, h, n = _der_tlv(der, off)  # contentType OID
    off += h + n
    _, h, _ = _der_tlv(der, off)  # [0]
    off += h
    _, h, _ = _der_tlv(der, off)  # SignedData SEQ
    off += h
    for _ in range(3):  # version, digestAlgorithms, encapContentInfo
        _, h, n = _der_tlv(der, off)
        off += h + n
    tag, h, _ = _der_tlv(der, off)
    if tag != 0xA0:
        return None
    off += h
    _, h, n = _der_tlv(der, off)
    return der[off : off + h + n]


def signing_info(path):
    """Return {'scheme': ..., 'cert_sha256': ...} for the first signer, or scheme 'none'."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            tail_len = min(size, 65557)
            f.seek(size - tail_len)
            tail = f.read(tail_len)
            idx = tail.rfind(struct.pack("<I", EOCD_MAGIC))
            found = {}
            if idx >= 0:
                cd_offset = _u32(tail, idx + 16)
                if cd_offset >= 32:
                    f.seek(cd_offset - 24)
                    footer = f.read(24)
                    if footer[8:] == SIG_BLOCK_MAGIC:
                        block_size = struct.unpack_from("<Q", footer, 0)[0]
                        f.seek(cd_offset - block_size - 8)
                        block = f.read(block_size + 8)
                        pos, limit = 8, len(block) - 24
                        while pos + 12 <= limit:
                            plen = struct.unpack_from("<Q", block, pos)[0]
                            pid = _u32(block, pos + 8)
                            if pid in SCHEME_IDS:
                                found[SCHEME_IDS[pid]] = block[pos + 12 : pos + 8 + plen]
                            pos += 8 + plen
            for scheme in ("v3.1", "v3", "v2"):
                if scheme in found:
                    cert = _first_cert_from_scheme(found[scheme])
                    return {
                        "scheme": "+".join(sorted(found)),
                        "cert_sha256": hashlib.sha256(cert).hexdigest(),
                    }
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                upper = name.upper()
                if upper.startswith("META-INF/") and upper.endswith((".RSA", ".DSA", ".EC")):
                    cert = _first_cert_from_pkcs7(z.read(name))
                    if cert:
                        return {"scheme": "v1", "cert_sha256": hashlib.sha256(cert).hexdigest()}
    except (OSError, struct.error, IndexError, zipfile.BadZipFile):
        return {"scheme": "error", "cert_sha256": None}
    return {"scheme": "none", "cert_sha256": None}


def _component(elem):
    actions = sorted(
        {a.get("name", "") for f in elem.findall("intent-filter") for a in f.findall("action")}
    )
    meta = {m.get("name", ""): m.get("value", m.get("resource")) for m in elem.findall("meta-data")}
    out = {"name": elem.get("name", "")}
    for key in ("permission", "exported", "process", "enabled", "authorities", "directBootAware"):
        if elem.get(key) is not None:
            out[key] = elem.get(key)
    if actions:
        out["actions"] = actions
    if meta:
        out["meta"] = meta
    return out


def manifest_summary(root):
    """Flatten the parsed AndroidManifest root Element into a JSON-friendly dict."""
    info = {
        "package": root.get("package"),
        "versionCode": root.get("versionCode"),
        "versionName": root.get("versionName"),
        "sharedUserId": root.get("sharedUserId"),
        "coreApp": root.get("coreApp"),
    }
    sdk = next(iter(root.findall("uses-sdk")), None)
    if sdk is not None:
        info["minSdkVersion"] = sdk.get("minSdkVersion")
        info["targetSdkVersion"] = sdk.get("targetSdkVersion")
    info["uses_permissions"] = sorted(
        {e.get("name", "") for t in ("uses-permission", "uses-permission-sdk-23") for e in root.findall(t)}
    )
    info["defines_permissions"] = [
        {"name": e.get("name", ""), "protectionLevel": e.get("protectionLevel", 0)}
        for e in root.findall("permission")
    ]
    overlay = next(iter(root.findall("overlay")), None)
    if overlay is not None:
        info["overlay"] = {k: overlay.get(k) for k in ("targetPackage", "targetName", "priority", "isStatic")}
    app = next(iter(root.findall("application")), None)
    if app is not None:
        info["application"] = {
            k: app.get(k)
            for k in ("name", "process", "persistent", "directBootAware", "hasCode", "extractNativeLibs")
            if app.get(k) is not None
        }
        for tag, key in (
            ("uses-library", "uses_libraries"),
            ("uses-native-library", "uses_native_libraries"),
            ("uses-static-library", "uses_static_libraries"),
            ("library", "provides_libraries"),
            ("static-library", "provides_static_libraries"),
        ):
            items = [{"name": e.get("name", ""), "required": e.get("required", True)} for e in app.findall(tag)]
            if items:
                info[key] = items
        for tag, key in (
            ("service", "services"),
            ("receiver", "receivers"),
            ("provider", "providers"),
            ("activity", "activities"),
        ):
            comps = [_component(e) for e in app.findall(tag)]
            if tag == "activity":
                info["activity_count"] = len(comps)
                comps = [c for c in comps if c.get("actions")]
            if comps:
                info[key] = comps
        meta = {m.get("name", ""): m.get("value", m.get("resource")) for m in app.findall("meta-data")}
        if meta:
            info["app_meta"] = meta
    return info


def inspect(path):
    """Return manifest summary + signing info + native libs for an APK/APEX file."""
    out = {"signing": signing_info(path)}
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            out["native_libs"] = sorted(n for n in names if n.startswith("lib/") and n.endswith(".so"))
            out["dex_count"] = sum(1 for n in names if n.endswith(".dex") and "/" not in n)
            out["has_apex_payload"] = "apex_payload.img" in names or "original_apex" in names
            out.update(manifest_summary(axml.parse(z.read("AndroidManifest.xml"))))
    except (zipfile.BadZipFile, KeyError, ValueError, struct.error, IndexError) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out
