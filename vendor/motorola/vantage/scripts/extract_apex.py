#!/usr/bin/env python3
"""Unpack the payload of every APEX/CAPEX found in an extracted firmware tree.

    python3 extract_apex.py <fw_out_dir>

Reads  <fw_out_dir>/root/<partition>/apex/*.{apex,capex}
Writes <fw_out_dir>/apex/<apex-name>/...   (payload contents, e.g. javalib/*.jar)
       <fw_out_dir>/apex/index.json        (name, version, source file, payload fs, jars)

Needs erofs-utils (fsck.erofs) and e2fsprogs (debugfs); run it inside the build distro.
"""
import io
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

PARTS = {"system": "system/system", "system_ext": "system_ext", "product": "product", "vendor": "vendor"}


def varint(buf, pos):
    result = shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7


def manifest_name_version(pb):
    name, version, pos = None, None, 0
    try:
        while pos < len(pb):
            key, pos = varint(pb, pos)
            field, wire = key >> 3, key & 7
            if wire == 2:
                n, pos = varint(pb, pos)
                if field == 1:
                    name = pb[pos : pos + n].decode("utf-8", "replace")
                pos += n
            elif wire == 0:
                val, pos = varint(pb, pos)
                if field == 2:
                    version = val
            elif wire == 1:
                pos += 8
            elif wire == 5:
                pos += 4
            else:
                break
    except IndexError:
        pass
    return name, version


def payload_fs(path):
    with open(path, "rb") as f:
        head = f.read(2048)
    if len(head) >= 1028 and struct.unpack_from("<I", head, 1024)[0] == 0xE0F5E1E2:
        return "erofs"
    if len(head) >= 1082 and struct.unpack_from("<H", head, 1080)[0] == 0xEF53:
        return "ext4"
    return "unknown"


def unpack(apex_path, out_root, partition):
    with zipfile.ZipFile(apex_path) as outer:
        names = outer.namelist()
        compressed = "original_apex" in names
        inner = zipfile.ZipFile(io.BytesIO(outer.read("original_apex"))) if compressed else outer
        name, version = manifest_name_version(inner.read("apex_manifest.pb"))
        entry = {
            "name": name,
            "version": version,
            "source": f"/{partition}/apex/{apex_path.name}",
            "compressed": compressed,
        }
        if "apex_payload.img" not in inner.namelist():
            entry["error"] = "no apex_payload.img"
            return entry
        dest = out_root / (name or apex_path.stem)
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        with tempfile.NamedTemporaryFile(suffix=".img", dir=out_root) as tmp:
            with inner.open("apex_payload.img") as src:
                shutil.copyfileobj(src, tmp, 4 * 1024 * 1024)
            tmp.flush()
            fs = payload_fs(tmp.name)
            entry["payload_fs"] = fs
            if fs == "erofs":
                cmd = ["fsck.erofs", f"--extract={dest}", "--overwrite", "--no-preserve", tmp.name]
            elif fs == "ext4":
                cmd = ["debugfs", "-R", f"rdump / {dest}", tmp.name]
            else:
                entry["error"] = "unknown payload filesystem"
                return entry
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                entry["error"] = (proc.stderr or proc.stdout).strip()[-300:]
        entry["dir"] = dest.name
        entry["jars"] = sorted(str(p.relative_to(dest)) for p in dest.rglob("*.jar"))
        entry["apks"] = sorted(str(p.relative_to(dest)) for p in dest.rglob("*.apk"))
        return entry


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    fw = Path(sys.argv[1])
    out_root = fw / "apex"
    out_root.mkdir(exist_ok=True)
    index = []
    for partition, sub in PARTS.items():
        apex_dir = fw / "root" / sub / "apex"
        if not apex_dir.is_dir():
            continue
        for path in sorted(apex_dir.iterdir()):
            if path.suffix not in (".apex", ".capex"):
                continue
            try:
                entry = unpack(path, out_root, partition)
            except (zipfile.BadZipFile, KeyError, OSError) as exc:
                entry = {"source": f"/{partition}/apex/{path.name}", "error": f"{type(exc).__name__}: {exc}"}
            index.append(entry)
            print(f"{entry.get('name')}: v{entry.get('version')} fs={entry.get('payload_fs')} "
                  f"jars={len(entry.get('jars', []))} {entry.get('error', '')}", flush=True)
    (out_root / "index.json").write_text(json.dumps(index, indent=1))
    errors = [e for e in index if e.get("error")]
    print(f"{len(index)} apexes, {len(errors)} with errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
