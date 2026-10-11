#!/usr/bin/env python3
"""Unpack the dynamic partitions of a Motorola stock firmware package.

Pure Python, read-only with respect to the firmware directory:

  * reads the Android sparse super.img_sparsechunk.N files in flashfile.xml order
    (no intermediate 30 GB raw super image is written),
  * parses the liblp ("dynamic partitions") metadata,
  * writes each populated logical partition to <out>/images/<name>.img,
  * records the layout in <out>/super_layout.json.

Filesystem contents are extracted separately (extract_filesystems.sh), because that
step needs erofs-utils and a case-sensitive, symlink-capable filesystem.

Usage:
    python3 extract_firmware.py <stock_firmware_dir> <out_dir> [--slot a] [--only name,name]
"""
import argparse
import bisect
import hashlib
import json
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SPARSE_MAGIC = 0xED26FF3A
CHUNK_RAW, CHUNK_FILL, CHUNK_DONT_CARE, CHUNK_CRC32 = 0xCAC1, 0xCAC2, 0xCAC3, 0xCAC4

LP_SECTOR = 512
LP_RESERVED = 4096
LP_GEOMETRY_MAGIC = 0x616C4467
LP_GEOMETRY_SIZE = 4096
LP_HEADER_MAGIC = 0x414C5030
LP_TARGET_LINEAR, LP_TARGET_ZERO = 0, 1

COPY = 16 * 1024 * 1024
NUL = bytes(1)


class SparseSet:
    """Random-access view over one or more Android sparse images targeting one partition."""

    def __init__(self, paths):
        self.extents = []  # (start_byte, length, kind, file_index, file_offset_or_fill)
        self.files = []
        self.block_size = None
        self.total_bytes = 0
        self.info = []
        for path in paths:
            self._index(Path(path))
        self.extents.sort(key=lambda e: e[0])
        self.starts = [e[0] for e in self.extents]
        prev_end = 0
        for start, length, *_ in self.extents:
            if start < prev_end:
                raise ValueError(f"overlapping sparse data at byte {start}")
            prev_end = start + length

    def _index(self, path):
        fidx = len(self.files)
        f = path.open("rb")
        self.files.append(f)
        hdr = f.read(28)
        magic, major, minor, file_hdr_sz, chunk_hdr_sz, blk_sz, total_blks, total_chunks, _ = struct.unpack(
            "<IHHHHIIII", hdr
        )
        if magic != SPARSE_MAGIC:
            raise ValueError(f"{path.name}: not an Android sparse image")
        if major != 1:
            raise ValueError(f"{path.name}: unsupported sparse version {major}.{minor}")
        if self.block_size is None:
            self.block_size = blk_sz
        elif self.block_size != blk_sz:
            raise ValueError("sparse block size differs between chunks")
        self.total_bytes = max(self.total_bytes, total_blks * blk_sz)
        f.seek(file_hdr_sz)
        out_blk = raw_blocks = 0
        for _ in range(total_chunks):
            chdr = f.read(chunk_hdr_sz)
            ctype, _, nblk, total_sz = struct.unpack("<HHII", chdr[:12])
            data_sz = total_sz - chunk_hdr_sz
            pos = f.tell()
            if ctype == CHUNK_RAW:
                if data_sz != nblk * blk_sz:
                    raise ValueError(f"{path.name}: bad RAW chunk size")
                self.extents.append((out_blk * blk_sz, nblk * blk_sz, "raw", fidx, pos))
                raw_blocks += nblk
            elif ctype == CHUNK_FILL:
                fill = f.read(4)
                self.extents.append((out_blk * blk_sz, nblk * blk_sz, "fill", fidx, fill))
            elif ctype == CHUNK_DONT_CARE:
                pass
            elif ctype == CHUNK_CRC32:
                nblk = 0
            else:
                raise ValueError(f"{path.name}: unknown chunk type {ctype:#x}")
            f.seek(pos + data_sz)
            out_blk += nblk
        self.info.append(
            {"file": path.name, "total_blocks": total_blks, "chunks": total_chunks, "raw_blocks": raw_blocks}
        )

    def read(self, offset, length):
        """Return length bytes at offset; holes read as zero."""
        out = bytearray(length)
        end = offset + length
        i = max(bisect.bisect_right(self.starts, offset) - 1, 0)
        while i < len(self.extents):
            start, elen, kind, fidx, ref = self.extents[i]
            if start >= end:
                break
            lo, hi = max(start, offset), min(start + elen, end)
            if lo < hi:
                if kind == "raw":
                    f = self.files[fidx]
                    f.seek(ref + (lo - start))
                    out[lo - offset : hi - offset] = f.read(hi - lo)
                else:
                    n = hi - lo
                    phase = (lo - start) % 4
                    pat = (ref * (n // 4 + 2))[phase : phase + n]
                    out[lo - offset : hi - offset] = pat
            i += 1
        return bytes(out)

    def close(self):
        for f in self.files:
            f.close()


def cstr(raw):
    return raw.split(NUL, 1)[0].decode("ascii", "replace")


def parse_lp(src):
    geo = src.read(LP_RESERVED, LP_GEOMETRY_SIZE)
    magic, struct_size = struct.unpack_from("<II", geo, 0)
    if magic != LP_GEOMETRY_MAGIC:
        raise ValueError("LP geometry magic not found at offset 4096; not a super image")
    checksum = geo[8:40]
    blank = bytearray(geo[:struct_size])
    blank[8:40] = bytes(32)
    geometry_ok = hashlib.sha256(bytes(blank)).digest() == checksum
    metadata_max_size, metadata_slot_count, logical_block_size = struct.unpack_from("<III", geo, 40)

    meta_off = LP_RESERVED + 2 * LP_GEOMETRY_SIZE
    hdr = src.read(meta_off, 256)
    hmagic, major, minor, header_size = struct.unpack_from("<IHHI", hdr, 0)
    if hmagic != LP_HEADER_MAGIC:
        raise ValueError("LP metadata header magic mismatch")
    tables_size = struct.unpack_from("<I", hdr, 44)[0]
    desc = struct.unpack_from("<12I", hdr, 80)
    (p_off, p_num, p_sz, e_off, e_num, e_sz, g_off, g_num, g_sz, b_off, b_num, b_sz) = desc
    header_flags = struct.unpack_from("<I", hdr, 128)[0] if header_size >= 132 else 0
    tables = src.read(meta_off + header_size, tables_size)
    tables_ok = hashlib.sha256(tables).digest() == hdr[48:80]

    groups = []
    for i in range(g_num):
        raw = tables[g_off + i * g_sz : g_off + (i + 1) * g_sz]
        flags, max_size = struct.unpack_from("<IQ", raw, 36)
        groups.append({"name": cstr(raw[:36]), "flags": flags, "maximum_size": max_size})

    block_devices = []
    for i in range(b_num):
        raw = tables[b_off + i * b_sz : b_off + (i + 1) * b_sz]
        first_logical_sector, alignment, alignment_offset, size = struct.unpack_from("<QIIQ", raw, 0)
        block_devices.append(
            {
                "partition_name": cstr(raw[24:60]),
                "first_logical_sector": first_logical_sector,
                "alignment": alignment,
                "alignment_offset": alignment_offset,
                "size": size,
                "flags": struct.unpack_from("<I", raw, 60)[0],
            }
        )

    extents = []
    for i in range(e_num):
        raw = tables[e_off + i * e_sz : e_off + (i + 1) * e_sz]
        num_sectors, target_type, target_data, target_source = struct.unpack_from("<QIQI", raw, 0)
        extents.append(
            {
                "num_sectors": num_sectors,
                "target_type": target_type,
                "target_data": target_data,
                "target_source": target_source,
            }
        )

    partitions = []
    for i in range(p_num):
        raw = tables[p_off + i * p_sz : p_off + (i + 1) * p_sz]
        attributes, first_extent, num_extents, group_index = struct.unpack_from("<IIII", raw, 36)
        pext = extents[first_extent : first_extent + num_extents]
        partitions.append(
            {
                "name": cstr(raw[:36]),
                "attributes": attributes,
                "group": groups[group_index]["name"] if group_index < len(groups) else None,
                "size": sum(e["num_sectors"] for e in pext) * LP_SECTOR,
                "extents": pext,
            }
        )

    return {
        "geometry": {
            "checksum_ok": geometry_ok,
            "metadata_max_size": metadata_max_size,
            "metadata_slot_count": metadata_slot_count,
            "logical_block_size": logical_block_size,
        },
        "header": {
            "version": f"{major}.{minor}",
            "header_size": header_size,
            "flags": header_flags,
            "tables_checksum_ok": tables_ok,
        },
        "groups": groups,
        "block_devices": block_devices,
        "partitions": partitions,
    }


def fs_type(head):
    if len(head) >= 1028 and struct.unpack_from("<I", head, 1024)[0] == 0xE0F5E1E2:
        return "erofs"
    if len(head) >= 1082 and struct.unpack_from("<H", head, 1080)[0] == 0xEF53:
        return "ext4"
    if len(head) >= 1028 and struct.unpack_from("<I", head, 1024)[0] == 0xF2F52010:
        return "f2fs"
    return "unknown"


def dump_partition(src, part, dest):
    sha = hashlib.sha256()
    head = bytes()
    with dest.open("wb") as out:
        for ext in part["extents"]:
            remaining = ext["num_sectors"] * LP_SECTOR
            if ext["target_type"] == LP_TARGET_ZERO:
                zero = bytes(min(COPY, remaining))
                while remaining:
                    n = min(len(zero), remaining)
                    out.write(zero[:n])
                    sha.update(zero[:n])
                    remaining -= n
                continue
            pos = ext["target_data"] * LP_SECTOR
            while remaining:
                n = min(COPY, remaining)
                buf = src.read(pos, n)
                if len(head) < 4096:
                    head += buf[: 4096 - len(head)]
                out.write(buf)
                sha.update(buf)
                pos += n
                remaining -= n
    return sha.hexdigest(), fs_type(head)


def super_chunks(fw_dir):
    flashfile = fw_dir / "flashfile.xml"
    names = []
    if flashfile.exists():
        for step in ET.parse(flashfile).getroot().iter("step"):
            if step.get("operation") == "flash" and step.get("partition") == "super":
                names.append(step.get("filename"))
    if not names:
        names = sorted(
            (p.name for p in fw_dir.glob("super.img_sparsechunk.*")), key=lambda n: int(n.rsplit(".", 1)[1])
        )
    if not names and (fw_dir / "super.img").exists():
        names = ["super.img"]
    if not names:
        raise SystemExit("no super image found in firmware directory")
    return [fw_dir / n for n in names]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("firmware_dir", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--slot", default="a", help="slot suffix to extract (default: a)")
    ap.add_argument("--only", default="", help="comma-separated partition base names to extract")
    ap.add_argument("--layout-only", action="store_true", help="write super_layout.json and stop")
    args = ap.parse_args()

    chunks = super_chunks(args.firmware_dir)
    src = SparseSet(chunks)
    lp = parse_lp(src)
    lp["source"] = {
        "firmware_dir": args.firmware_dir.name,
        "sparse_files": src.info,
        "sparse_block_size": src.block_size,
        "image_size": src.total_bytes,
    }

    images = args.out_dir / "images"
    images.mkdir(parents=True, exist_ok=True)
    only = {n for n in args.only.split(",") if n}
    suffix = f"_{args.slot}"
    for part in lp["partitions"]:
        base = part["name"][: -len(suffix)] if part["name"].endswith(suffix) else part["name"]
        part["base_name"] = base
        wanted = part["size"] > 0 and part["name"].endswith(suffix) and (not only or base in only)
        if args.layout_only or not wanted:
            continue
        dest = images / f"{base}.img"
        sha256, fstype = dump_partition(src, part, dest)
        part["image"] = dest.name
        part["sha256"] = sha256
        part["filesystem"] = fstype
        print(f"{part['name']:<16} {part['size']:>12} bytes  {fstype:<7} sha256={sha256[:16]}...", flush=True)

    (args.out_dir / "super_layout.json").write_text(json.dumps(lp, indent=2))
    src.close()
    g, h = lp["geometry"], lp["header"]
    print(
        f"LP v{h['version']} geometry_ok={g['checksum_ok']} tables_ok={h['tables_checksum_ok']} "
        f"slots={g['metadata_slot_count']} super_size={src.total_bytes}"
    )
    for grp in lp["groups"]:
        used = sum(p["size"] for p in lp["partitions"] if p["group"] == grp["name"])
        print(f"group {grp['name']:<28} max={grp['maximum_size']:>12} used={used:>12}")
    return 0 if g["checksum_ok"] and h["tables_checksum_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
