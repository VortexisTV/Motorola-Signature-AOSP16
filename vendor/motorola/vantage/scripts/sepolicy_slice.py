#!/usr/bin/env python3
"""Slice the stock SELinux policy around given domains.

For each seed type it reports, per partition policy file:
  * where the type is declared and which attributes it is a member of,
  * the rules where it is the source or the target,
  * the versioned attribute the vendor policy uses for it (e.g. vendor_qtelephony_202504),
  * every other type/attribute those rules mention and which partition declares it.

    sepolicy_slice.py <fw_out_dir> <out.json> --seed vendor_qtelephony [--seed ...] [--te DIR]

With --te a human-reviewable .te rendering of the system-side rules is written per seed.
This is static analysis of the stock policy; it does not prove a ported policy is sufficient.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from motofw import cil  # noqa: E402

FILES = {
    "plat": "system/system/etc/selinux/plat_sepolicy.cil",
    "system_ext": "system_ext/etc/selinux/system_ext_sepolicy.cil",
    "product": "product/etc/selinux/product_sepolicy.cil",
    "vendor_pub": "vendor/etc/selinux/plat_pub_versioned.cil",
    "vendor": "vendor/etc/selinux/vendor_sepolicy.cil",
    "odm": "odm/etc/selinux/odm_sepolicy.cil",
}
MAPPINGS = {
    "plat": "system/system/etc/selinux/mapping/{v}.cil",
    "system_ext": "system_ext/etc/selinux/mapping/{v}.cil",
    "product": "product/etc/selinux/mapping/{v}.cil",
}
SYSTEM_SIDE = ("plat", "system_ext", "product")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fw_dir", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--seed", action="append", required=True)
    ap.add_argument("--te", type=Path, help="directory for .te renderings")
    args = ap.parse_args()

    root = args.fw_dir / "root"
    vers_file = root / "vendor/etc/selinux/plat_sepolicy_vers.txt"
    version = vers_file.read_text().strip() if vers_file.exists() else None
    policies = {}
    for label, rel in FILES.items():
        path = root / rel
        if path.exists():
            policies[label] = cil.Policy(label, path.read_text(errors="replace"))
    mappings = {}
    for label, rel in MAPPINGS.items():
        path = root / rel.format(v=version)
        if path.exists():
            mappings[label] = cil.Policy(f"{label}-mapping", path.read_text(errors="replace"))

    def declared_in(name):
        where = []
        for label, pol in policies.items():
            if name in pol.types:
                where.append(f"{label}:type")
            elif name in pol.attributes:
                where.append(f"{label}:attribute")
        return where

    report = {"vendor_policy_version": version, "seeds": {}}
    for seed in args.seed:
        versioned = f"{seed}_{version}" if version else None
        entry = {
            "declared_in": declared_in(seed),
            "versioned_attribute": versioned,
            "mapping": {},
            "partitions": {},
            "referenced_symbols": {},
        }
        for label, pol in mappings.items():
            hits = [a for a, expr in pol.attr_sets if cil.is_plain_list(expr) and seed in expr]
            if hits:
                entry["mapping"][label] = hits
        symbols = set()
        for label, pol in policies.items():
            names = [seed] + ([versioned] if versioned and label in ("vendor", "vendor_pub", "odm") else [])
            part = {"attributes": [], "source_rules": [], "target_rules": []}
            for name in names:
                part["attributes"] += pol.memberships(name)
                src, tgt = pol.rules_for(name)
                for bucket, stmts in (("source_rules", src), ("target_rules", tgt)):
                    for stmt in stmts:
                        if stmt[0].startswith("neverallow"):
                            continue
                        te = cil.to_te(stmt)
                        part[bucket].append(te or " ".join(cil.flat_names(stmt)))
                        symbols.update(x for x in (stmt[1], stmt[2]) if isinstance(x, str))
            part["attributes"] = sorted(set(part["attributes"]))
            symbols.update(part["attributes"])
            if any(part.values()):
                entry["partitions"][label] = part
        symbols.discard(seed)
        symbols.discard(versioned)
        for sym in sorted(symbols):
            entry["referenced_symbols"][sym] = declared_in(sym) or ["UNDECLARED"]
        report["seeds"][seed] = entry

        print(f"## {seed}: declared in {entry['declared_in']}, mapping {entry['mapping']}")
        for label, part in entry["partitions"].items():
            print(f"   [{label}] attrs={len(part['attributes'])} src_rules={len(part['source_rules'])} "
                  f"tgt_rules={len(part['target_rules'])}")
        if args.te:
            args.te.mkdir(parents=True, exist_ok=True)
            lines = [f"# Stock rules for {seed} (rendered from CIL by sepolicy_slice.py; review before use)", ""]
            for label in SYSTEM_SIDE + ("vendor", "odm"):
                part = entry["partitions"].get(label)
                if not part:
                    continue
                lines.append(f"### from {label} policy")
                lines += [f"# typeattribute {seed} {a};" if label not in SYSTEM_SIDE else f"typeattribute {seed} {a};"
                          for a in part["attributes"]]
                for bucket in ("source_rules", "target_rules"):
                    prefix = "" if label in SYSTEM_SIDE else "# (vendor side, applies via mapping) "
                    lines += [prefix + r for r in part[bucket]]
                lines.append("")
            with (args.te / f"{seed}.te.txt").open("w", newline="\n") as f:
                f.write("\n".join(lines) + "\n")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="\n") as f:
        json.dump(report, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
