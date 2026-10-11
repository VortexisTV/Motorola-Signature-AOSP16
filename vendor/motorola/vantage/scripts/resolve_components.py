#!/usr/bin/env python3
"""Expand components.json into proprietary-files.txt using the firmware inventory.

    resolve_components.py <report_dir> <components.json> <proprietary-files.txt> [--target-system-libs FILE]

For every seed app the closure contains: the APK, the files in its lib/ directory, each
shared library it requests (jar + the permission XML that declares it, following declared
library dependencies), and native libraries reachable through DT_NEEDED that are not part of
the target system image. Each line is pinned with the SHA-256 of the stock file:

    <partition>/<path>[;FLAG...]|<sha256>

Flags: PRESIGNED (keep OEM signature), CERT=platform (re-sign with the ROM platform key),
       PRIV (privileged app), SYMLINK=<target> (recreate a symlink instead of copying).
"""
import argparse
import json
import sys
from pathlib import Path

NATIVE_PORT_PARTITIONS = ("system_ext", "product")
AOSP_LIB_PREFIXES = ("android.", "androidx.", "org.apache.", "com.android.")


def canon(path):
    for old, new in (("/system/system_ext/", "/system_ext/"), ("/system/product/", "/product/")):
        if path.startswith(old):
            return new + path[len(old):]
    return path


class Inventory:
    def __init__(self, report_dir, target_libs_file=None):
        inv = report_dir / "inventory"
        files = json.loads((inv / "files.json").read_text(encoding="utf-8"))
        self.files = {f["path"]: f for f in files["files"]}
        self.symlinks = {s["path"]: s["target"] for s in files["symlinks"]}
        self.packages = {p["path"]: p for p in json.loads((inv / "packages.json").read_text(encoding="utf-8"))}
        self.elfs = {e["path"]: e for e in json.loads((inv / "elf.json").read_text(encoding="utf-8"))}
        self.libraries = {}
        for part, data in json.loads((inv / "permissions.json").read_text(encoding="utf-8")).items():
            for lib in data["libraries"]:
                if lib["name"] and lib["file"]:
                    self.libraries.setdefault(lib["name"], dict(lib, xml=f"/{part}/etc/{lib['declared_in']}"))
        self.soname_paths = {}
        for path, e in self.elfs.items():
            if e["bits"] == 64 and "/lib64/" in path:
                self.soname_paths.setdefault(e.get("soname") or path.rsplit("/", 1)[-1], []).append(path)
        self.target_libs = None
        if target_libs_file:
            self.target_libs = {l.strip() for l in target_libs_file.read_text().splitlines() if l.strip()}


class Closure:
    def __init__(self, inv, name, problems):
        self.inv, self.name, self.problems = inv, name, problems
        self.entries = {}  # path -> (flags, reason)

    def add(self, path, reason, flags=()):
        path = canon(path)
        if path in self.entries:
            return
        if path in self.inv.symlinks:
            target = self.inv.symlinks[path]
            self.entries[path] = ((f"SYMLINK={target}",) + tuple(flags), reason)
            self.add_native(target, f"target of the {path.rsplit('/', 1)[-1]} symlink")
        elif path in self.inv.files:
            self.entries[path] = (tuple(flags), reason)
        else:
            self.problems.append(f"{self.name}: {path} ({reason}) not found in stock firmware")

    def add_native(self, path, reason):
        path = canon(path)
        inv = self.inv
        if path not in inv.elfs:
            self.problems.append(f"{self.name}: native {path} ({reason}) not in inventory")
            return
        self.add(path, reason)
        for dep in inv.elfs[path]["needed"]:
            if inv.target_libs is not None and dep in inv.target_libs:
                continue
            cands = inv.soname_paths.get(dep, [])
            in_system = next((c for c in cands if c.startswith("/system/")), None)
            if inv.target_libs is None and in_system:
                continue  # also shipped in stock /system: assumed AOSP until a target lib list is given
            port = next((c for c in cands if c.split("/")[1] in NATIVE_PORT_PARTITIONS), None) or in_system
            if port and canon(port) not in self.entries:
                self.add_native(port, f"DT_NEEDED of {path.rsplit('/', 1)[-1]}")
        for dep in inv.elfs[path].get("so_refs", []):
            cands = inv.soname_paths.get(dep, [])
            if any(c.startswith("/system/") for c in cands) or (inv.target_libs and dep in inv.target_libs):
                continue
            port = next((c for c in cands if c.split("/")[1] in NATIVE_PORT_PARTITIONS), None)
            if port and canon(port) not in self.entries:
                self.add_native(port, f"named in {path.rsplit('/', 1)[-1]} (dlopen candidate)")

    def add_app(self, app, skip_libs):
        inv = self.inv
        apk = app["path"]
        pkg = inv.packages.get(apk)
        if pkg is None:
            self.problems.append(f"{self.name}: app {apk} not in inventory")
            return
        flags = ["PRESIGNED"] if app["sign"] == "presigned" else [f"CERT={app['sign']}"]
        if pkg["kind"] == "priv-app":
            flags.append("PRIV")
        self.add(apk, f"seed app {pkg['package']}", flags)
        app_lib = apk.rsplit("/", 1)[0] + "/lib/"
        for path in sorted(set(inv.files) | set(inv.symlinks)):
            if path.startswith(app_lib):
                if path in inv.symlinks:
                    self.add(path, f"JNI library link of {pkg['package']}")
                else:
                    self.add_native(path, f"JNI library of {pkg['package']}")
        queue = [(l["name"], l.get("required", True) is not False) for l in pkg.get("uses_libraries", [])]
        seen = set()
        while queue:
            lib, required = queue.pop(0)
            if lib in seen or lib.endswith(".so"):
                continue
            seen.add(lib)
            if not required and lib in skip_libs:
                continue
            decl = inv.libraries.get(lib)
            if decl is None:
                if required:
                    self.problems.append(f"{self.name}: required library {lib} of {pkg['package']} undeclared on stock")
                continue
            jar = canon(decl["file"])
            if jar.startswith("/apex/") or lib.startswith(AOSP_LIB_PREFIXES):
                continue  # provided by AOSP itself
            kind = "required" if required else "optional"
            self.add(jar, f"shared library {lib} ({kind}) of {pkg['package']}")
            self.add(decl["xml"], f"declares shared library {lib}")
            for dep in (decl.get("dependency") or "").split(":"):
                if dep:
                    queue.append((dep, True))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report_dir", type=Path)
    ap.add_argument("components", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--target-system-libs", type=Path,
                    help="sonames present in the target /system/lib64, one per line (enables exact native diffing)")
    args = ap.parse_args()

    inv = Inventory(args.report_dir, args.target_system_libs)
    spec = json.loads(args.components.read_text(encoding="utf-8"))
    problems, lines, total = [], [], 0
    for name, comp in spec.items():
        if name.startswith("_"):
            continue
        closure = Closure(inv, name, problems)
        for app in comp.get("apps", []):
            closure.add_app(app, set(comp.get("skip_optional_libraries", [])))
        for path in comp.get("native", []):
            closure.add_native(path, "native library listed in components.json")
        for path in comp.get("config", []):
            closure.add(path, "configuration listed in components.json")
        lines.append(f"# === {name}: {comp.get('description', '')}")
        for path in sorted(closure.entries):
            flags, reason = closure.entries[path]
            sha = inv.files.get(path, {}).get("sha256", "")
            lines.append(f"# {reason}")
            lines.append(path.lstrip("/") + "".join(f";{f}" for f in flags) + (f"|{sha}" if sha else ""))
            total += 1
        lines.append("")
    header = [
        "# Generated by scripts/resolve_components.py from components.json and the firmware inventory.",
        "# Stock build: motorola/vantage_g W2WVS36.55-95-5-1. Edit components.json, not this file.",
        "# Format: <partition>/<path>[;FLAG...]|<sha256 of the stock file>",
        "",
    ]
    with args.out.open("w", newline="\n") as f:
        f.write("\n".join(header + lines))
    print(f"{total} files -> {args.out}")
    for p in problems:
        print("PROBLEM:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
