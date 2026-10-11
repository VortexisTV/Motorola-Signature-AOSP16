#!/usr/bin/env python3
"""Static Java linkage check of APKs/JARs against a platform image tree.

For every subject it rebuilds the class-loading context the device would use
(BOOTCLASSPATH from etc/classpaths fragments incl. APEXes, plus the shared libraries
the manifest requests and their declared dependencies) and reports references to
classes, methods or fields that do not exist there.

    check_java_linkage.py --map /system=DIR --map /system_ext=DIR --map /product=DIR \
        --map /apex=DIR [--map ... (later maps for the same prefix are searched first)] \
        --subject /system_ext/priv-app/ims/ims.apk [--subject ...] --out report.json

A static check proves that a reference CAN be linked; it never proves that a feature
works on hardware. Unresolved references are only fatal if that code path executes.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from motofw import apk, axml, dexlink, fsmeta  # noqa: E402

ALIASES = (("/system/system_ext/", "/system_ext/"), ("/system/product/", "/product/"),
           ("/system/vendor/", "/vendor/"), ("/system/apex/", "/apex/"))


class Platform:
    def __init__(self, maps):
        self.maps = []  # (device_prefix, host_dir), most specific + latest first
        for item in maps:
            prefix, _, host = item.partition("=")
            self.maps.append((prefix.rstrip("/"), Path(host)))
        self.maps.reverse()
        self.maps.sort(key=lambda m: -len(m[0]))
        self.bootclasspath = []
        self.libraries = {}
        self._load()

    def host(self, device_path):
        for old, new in ALIASES:
            if device_path.startswith(old):
                device_path = new + device_path[len(old):]
        for prefix, host in self.maps:
            if device_path == prefix or device_path.startswith(prefix + "/"):
                cand = host / device_path[len(prefix):].lstrip("/")
                if cand.exists():
                    return cand
        return None

    def _roots(self, prefix):
        return [host for p, host in self.maps if p == prefix]

    def owner(self, host_path):
        """Device prefix of the most specific mapped root containing host_path.

        A GSI keeps system_ext and product inside system, so a file below the /system root can
        belong to another partition."""
        best = None
        for prefix, host in self.maps:
            if host not in host_path.parents:
                continue
            if best is None or len(host.parts) > len(best[1].parts):
                best = (prefix, host)
        return best[0] if best else None

    def apks(self, prefixes):
        """(path, device prefix) of every APK below the given prefixes, attributed to its real partition."""
        seen = set()
        for prefix in prefixes:
            for root in self._roots(prefix):
                for path in sorted(root.rglob("*.apk")):
                    if path in seen or self.owner(path) != prefix:
                        continue
                    seen.add(path)
                    yield path, prefix

    def _load(self):
        seen = set()
        fragment_dirs = []
        for prefix in ("/system", "/system_ext", "/product"):
            fragment_dirs += [(prefix, r / "etc" / "classpaths") for r in self._roots(prefix)]
        for apex_root in self._roots("/apex"):
            for sub in sorted(p for p in apex_root.iterdir() if p.is_dir()):
                fragment_dirs.append((f"/apex/{sub.name}", sub / "etc" / "classpaths"))
        for _, cdir in fragment_dirs:
            if not cdir.is_dir():
                continue
            for pb in sorted(cdir.glob("*.pb")):
                for jar in fsmeta.read_classpath_pb(pb):
                    if jar["classpath"] == "BOOTCLASSPATH" and jar["path"] not in seen:
                        seen.add(jar["path"])
                        self.bootclasspath.append(jar["path"])
        for prefix in ("/system", "/system_ext", "/product", "/vendor", "/odm"):
            for root in self._roots(prefix):
                for lib in fsmeta.read_permission_xmls(root / "etc")["libraries"]:
                    if lib["name"] and lib["file"]:
                        self.libraries.setdefault(lib["name"], lib)
        for apex_root in self._roots("/apex"):
            for sub in sorted(p for p in apex_root.iterdir() if p.is_dir()):
                for lib in fsmeta.read_permission_xmls(sub / "etc")["libraries"]:
                    if lib["name"] and lib["file"]:
                        self.libraries.setdefault(lib["name"], lib)

    def boot_index(self):
        index, missing = dexlink.ClassIndex(), []
        for dev in self.bootclasspath:
            host = self.host(dev)
            if host is None:
                missing.append(dev)
            else:
                index.add(host, dev)
        return index, missing

    def library_closure(self, names):
        """Resolve library names (+ declared dependencies) to [(name, device_path, host_path|None)]."""
        out, seen, queue = [], set(), list(names)
        while queue:
            name = queue.pop(0)
            if name in seen:
                continue
            seen.add(name)
            lib = self.libraries.get(name)
            if lib is None:
                out.append((name, None, None))
                continue
            out.append((name, lib["file"], self.host(lib["file"])))
            if lib.get("dependency"):
                queue.extend(lib["dependency"].split(":"))
        return out


def requested_libraries(host_path):
    """(required, optional) shared-library names from an APK manifest; ([], []) for plain jars."""
    info = apk.inspect(str(host_path))
    required, optional = [], []
    for lib in info.get("uses_libraries", []):
        (required if lib.get("required", True) is not False else optional).append(lib["name"])
    return required, optional, info.get("package")


def check(platform, boot, subject, extra_libs, limit, dump_refs=False):
    host = platform.host(subject) if subject.startswith("/") and not Path(subject).exists() else Path(subject)
    entry = {"subject": subject, "tests": []}
    if host is None or not Path(host).exists():
        entry.update(status="FAIL", reason="subject not found in platform tree")
        return entry
    required, optional, package = requested_libraries(host)
    entry["package"] = package
    closure = platform.library_closure(required + optional + extra_libs)
    index = boot.copy()
    libs_report, status = [], "PASS"
    for name, dev, lib_host in closure:
        state = "ok"
        if dev is None:
            state = "undeclared"
        elif lib_host is None:
            state = "declared-but-file-missing"
        else:
            index.add(lib_host, dev)
        needed = name in required or name in extra_libs
        libs_report.append({"name": name, "file": dev, "state": state, "required": needed})
        if state != "ok" and needed:
            status = "FAIL"
    entry["shared_libraries"] = libs_report
    res = dexlink.check_subject(str(host), index, collect_refs=dump_refs)
    if dump_refs:
        entry["external_refs"] = res["external_refs"]
        entry["external_classes"] = res["external_classes"]
    counts = {k: len(res[k]) for k in ("missing_classes", "missing_methods", "missing_fields", "unknown_hierarchy")}
    entry["counts"] = counts
    entry["providers"] = res["providers"]
    entry["classes_defined"] = res["classes_defined"]
    entry["shadowed_by_platform"] = len(res["shadowed_by_platform"])
    for key in counts:
        items = list(res[key].items())
        entry[key] = {k: v[:limit] for k, v in items}
    if counts["missing_classes"] or counts["missing_methods"] or counts["missing_fields"]:
        status = "FAIL" if status == "FAIL" else "WARNING"
    entry["status"] = status
    return entry


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", action="append", required=True, metavar="/prefix=DIR")
    ap.add_argument("--subject", action="append", default=[], help="device path or host path of an APK/JAR")
    ap.add_argument("--subjects-file", help="text file with one subject per line")
    ap.add_argument("--with-lib", action="append", default=[], help="extra shared library name to add")
    ap.add_argument("--users-limit", type=int, default=6, help="max referencing classes kept per symbol")
    ap.add_argument("--dump-refs", action="store_true", help="record every resolved external symbol per provider")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    subjects = list(args.subject)
    if args.subjects_file:
        subjects += [s.strip() for s in Path(args.subjects_file).read_text().splitlines()
                     if s.strip() and not s.startswith("#")]
    platform = Platform(args.map)
    boot, missing_boot = platform.boot_index()
    report = {
        "bootclasspath": platform.bootclasspath,
        "bootclasspath_missing_files": missing_boot,
        "boot_classes": len(boot.classes),
        "shared_libraries_known": len(platform.libraries),
        "results": [],
    }
    print(f"bootclasspath: {len(platform.bootclasspath)} jars ({len(missing_boot)} not found), "
          f"{len(boot.classes)} classes; {len(platform.libraries)} shared libraries declared")
    for subject in subjects:
        entry = check(platform, boot, subject, args.with_lib, args.users_limit, args.dump_refs)
        report["results"].append(entry)
        c = entry.get("counts", {})
        print(f"[{entry['status']:<7}] {subject}  classes={entry.get('classes_defined')} "
              f"missing: classes={c.get('missing_classes')} methods={c.get('missing_methods')} "
              f"fields={c.get('missing_fields')} unknown={c.get('unknown_hierarchy')}")
        for lib in entry.get("shared_libraries", []):
            if lib["state"] != "ok":
                print(f"          library {lib['name']}: {lib['state']} (required={lib['required']})")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", newline="\n") as f:
            json.dump(report, f, indent=1)
    return 0 if all(r["status"] == "PASS" for r in report["results"]) else 1


if __name__ == "__main__":
    sys.exit(main())
