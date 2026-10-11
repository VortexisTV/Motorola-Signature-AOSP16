#!/usr/bin/env python3
"""Hash every file of a Motorola stock firmware package and verify it against flashfile.xml.

Read-only with respect to the firmware directory.

Usage:
    python3 firmware_hashes.py <stock_firmware_dir> <report_dir>

Outputs:
    <report_dir>/stock-firmware-hashes.json
    <report_dir>/stock-firmware-hashes.md
    <report_dir>/stock-firmware.sha256      (sha256sum-compatible)
"""
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

CHUNK = 8 * 1024 * 1024


def digest(path: Path):
    sha256, md5 = hashlib.sha256(), hashlib.md5()
    with path.open("rb") as f:
        while True:
            buf = f.read(CHUNK)
            if not buf:
                break
            sha256.update(buf)
            md5.update(buf)
    return sha256.hexdigest(), md5.hexdigest()


def natural_key(name: str):
    head, _, tail = name.rpartition(".")
    return (head, int(tail)) if tail.isdigit() else (name, -1)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    fw_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    expected = {}
    header = {}
    flashfile = fw_dir / "flashfile.xml"
    if flashfile.exists():
        root = ET.parse(flashfile).getroot()
        hdr = root.find("header")
        if hdr is not None:
            for child in hdr:
                header[child.tag] = dict(child.attrib)
        for step in root.iter("step"):
            name, md5 = step.get("filename"), step.get("MD5")
            if name and md5:
                expected[name] = {"md5": md5.lower(), "partition": step.get("partition")}

    files = sorted((p for p in fw_dir.iterdir() if p.is_file()), key=lambda p: natural_key(p.name))
    results, ok, bad = [], 0, 0
    for p in files:
        sha256, md5 = digest(p)
        entry = {"name": p.name, "size": p.stat().st_size, "sha256": sha256, "md5": md5}
        exp = expected.get(p.name)
        if exp:
            entry["partition"] = exp["partition"]
            entry["flashfile_md5"] = exp["md5"]
            entry["md5_matches_flashfile"] = exp["md5"] == md5
            ok += entry["md5_matches_flashfile"]
            bad += not entry["md5_matches_flashfile"]
        results.append(entry)
        print(f"{sha256}  {p.name}", flush=True)

    missing = sorted(set(expected) - {p.name for p in files})
    summary = {
        "firmware_dir": fw_dir.name,
        "flashfile_header": header,
        "files": results,
        "flashfile_entries": len(expected),
        "md5_verified": ok,
        "md5_mismatch": bad,
        "missing_from_disk": missing,
        "status": "PASS" if expected and not bad and not missing else "FAIL",
    }
    (out_dir / "stock-firmware-hashes.json").write_text(json.dumps(summary, indent=2))
    with (out_dir / "stock-firmware.sha256").open("w", newline="\n") as f:
        f.writelines(f"{r['sha256']}  {r['name']}\n" for r in results)

    lines = [
        "# Stock firmware hashes",
        "",
        f"- Package: `{fw_dir.name}`",
        f"- flashfile.xml entries with MD5: {len(expected)}",
        f"- MD5 verified against flashfile.xml: {ok}",
        f"- MD5 mismatches: {bad}",
        f"- Listed in flashfile.xml but missing on disk: {len(missing)}",
        f"- Integrity status: **{summary['status']}**",
        "",
        "| File | Partition | Size (bytes) | SHA-256 | flashfile MD5 |",
        "|---|---|---:|---|---|",
    ]
    for r in results:
        state = {True: "match", False: "MISMATCH", None: "n/a"}[r.get("md5_matches_flashfile")]
        lines.append(
            f"| `{r['name']}` | {r.get('partition', '')} | {r['size']} | `{r['sha256']}` | {state} |"
        )
    with (out_dir / "stock-firmware-hashes.md").open("w", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nstatus={summary['status']} verified={ok} mismatch={bad} missing={len(missing)}")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
