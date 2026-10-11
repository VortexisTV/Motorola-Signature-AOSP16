"""Static Java linkage checking: do the classes/methods/fields a dex references exist?

A ClassIndex is built from the jars that will be visible at run time (boot classpath,
APEX jars, declared shared libraries). check_subject() then resolves every external
reference made by an APK/JAR, walking superclasses and interfaces the way ART does.
"""
from collections import defaultdict

from . import dex as dexmod

SIGNATURE_POLYMORPHIC = {"Ljava/lang/invoke/MethodHandle;", "Ljava/lang/invoke/VarHandle;"}


class ClassIndex:
    def __init__(self):
        self.classes = {}  # descriptor -> info dict (first definition wins, like a class loader)
        self.provider = {}  # descriptor -> source label
        self.duplicates = defaultdict(list)

    def add(self, path, label=None):
        label = label or str(path)
        count = 0
        for d in dexmod.load(path):
            for info in d.classes():
                name = info["name"]
                if name in self.classes:
                    self.duplicates[name].append(label)
                    continue
                self.classes[name] = info
                self.provider[name] = label
                count += 1
        return count

    def copy(self):
        other = ClassIndex()
        other.classes = dict(self.classes)
        other.provider = dict(self.provider)
        return other

    def _walk(self, cls):
        """Yield (class_name, info_or_None) for cls and all its ancestors (BFS, deduplicated)."""
        seen, queue = set(), [cls]
        while queue:
            cur = queue.pop(0)
            if cur in seen or cur is None:
                continue
            seen.add(cur)
            info = self.classes.get(cur)
            yield cur, info
            if info:
                queue.append(info["super"])
                queue.extend(info["interfaces"])

    def resolve(self, kind, cls, name, sig):
        """Return ('ok', provider) | ('noclass', None) | ('missing', None) | ('unknown', ancestor)."""
        if cls.startswith("["):
            return ("ok", "array") if kind == "methods" else ("missing", None)
        if cls not in self.classes:
            return "noclass", None
        unknown = None
        for cur, info in self._walk(cls):
            if info is None:
                unknown = unknown or cur
                continue
            if kind == "methods":
                if (name, sig) in info["methods"]:
                    return "ok", self.provider[cur]
                if cur in SIGNATURE_POLYMORPHIC and any(m[0] == name for m in info["methods"]):
                    return "ok", self.provider[cur]
            elif (name, sig) in info["fields"]:
                return "ok", self.provider[cur]
        if unknown:
            return "unknown", unknown
        return "missing", None


def check_subject(path, index, own_label="self", collect_refs=False):
    """Resolve all external references of the APK/JAR at path against index (+ its own classes)."""
    dexes = dexmod.load(path)
    merged = index.copy()
    own, scanned = set(), []
    for d in dexes:
        for info in d.classes(scan_code=True):
            own.add(info["name"])
            if info["name"] not in merged.classes:  # platform classes win over app classes, as in ART
                merged.classes[info["name"]] = info
                merged.provider[info["name"]] = own_label
            scanned.append((d, info))

    result = {
        "dex_files": len(dexes),
        "classes_defined": len(own),
        "providers": defaultdict(int),
        "missing_classes": defaultdict(set),
        "missing_methods": defaultdict(set),
        "missing_fields": defaultdict(set),
        "unknown_hierarchy": defaultdict(set),
        "shadowed_by_platform": sorted(n for n in own if n in index.classes),
        "external_refs": defaultdict(set),
        "external_classes": defaultdict(set),
    }
    cache = {}
    for d, info in scanned:
        user = info["name"]
        refs = info["refs"]
        deps = {info["super"], *info["interfaces"]} - {None}
        for tidx in refs["types"]:
            deps.add(d.type(tidx))
        for t in deps:
            t = t.lstrip("[")
            if t.startswith("L") and t not in merged.classes:
                result["missing_classes"][t].add(user)
            elif collect_refs and t.startswith("L") and merged.provider[t] != own_label:
                result["external_classes"][merged.provider[t]].add(t)
        for kind, getter in (("methods", d.method), ("fields", d.field)):
            for idx in refs[kind]:
                cls, name, sig = getter(idx)
                if collect_refs and cls in merged.classes and merged.provider[cls] != own_label:
                    result["external_classes"][merged.provider[cls]].add(cls)
                key = (kind, cls, name, sig)
                if key not in cache:
                    cache[key] = merged.resolve(kind, cls, name, sig)
                status, where = cache[key]
                if status == "ok":
                    if where != own_label:
                        result["providers"][where] += 1
                        if collect_refs:
                            sep = "" if kind == "methods" else ":"
                            result["external_refs"][where].add(f"{cls}->{name}{sep}{sig}")
                elif status == "noclass":
                    if cls.startswith("L"):
                        result["missing_classes"][cls].add(user)
                elif status == "unknown":
                    result["unknown_hierarchy"][f"{cls}->{name}{sig} (needs {where})"].add(user)
                else:
                    sep = "" if kind == "methods" else ":"
                    result[f"missing_{kind}"][f"{cls}->{name}{sep}{sig}"].add(user)
    for key in ("missing_classes", "missing_methods", "missing_fields", "unknown_hierarchy"):
        result[key] = {k: sorted(v) for k, v in sorted(result[key].items())}
    result["providers"] = dict(sorted(result["providers"].items(), key=lambda kv: -kv[1]))
    result["external_refs"] = {k: sorted(v) for k, v in sorted(result["external_refs"].items())}
    result["external_classes"] = {k: sorted(v) for k, v in sorted(result["external_classes"].items())}
    return result
