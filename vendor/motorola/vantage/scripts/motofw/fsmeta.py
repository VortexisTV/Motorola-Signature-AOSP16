"""Parsers for the configuration files found on Android system/vendor partitions."""
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path


def read_props(path):
    """Parse a build.prop style file into an ordered dict (later assignments win)."""
    props = {}
    try:
        text = Path(path).read_text(errors="replace")
    except OSError:
        return props
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("import ") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        props[key.strip()] = val.strip()
    return props


def _xml_root(path):
    try:
        return ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None


def read_permission_xmls(etc_dir):
    """Aggregate etc/permissions + etc/sysconfig XML of one partition.

    Returns dict with libraries, privapp allowlists/denylists, features and assorted sysconfig tags.
    """
    out = {
        "libraries": [],
        "privapp_permissions": {},
        "privapp_deny": {},
        "signature_permissions": {},
        "features": [],
        "unavailable_features": [],
        "sysconfig": {},
        "files": [],
    }
    for sub in ("permissions", "sysconfig"):
        base = Path(etc_dir) / sub
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.xml")):
            root = _xml_root(path)
            if root is None:
                out["files"].append({"file": f"{sub}/{path.name}", "error": "unparseable"})
                continue
            out["files"].append({"file": f"{sub}/{path.name}"})
            for el in root.iter():
                tag = el.tag
                if tag == "library":
                    out["libraries"].append(
                        {
                            "name": el.get("name"),
                            "file": el.get("file"),
                            "dependency": el.get("dependency"),
                            "min_device_sdk": el.get("min-device-sdk"),
                            "max_device_sdk": el.get("max-device-sdk"),
                            "on_bootclasspath_since": el.get("on-bootclasspath-since"),
                            "declared_in": f"{sub}/{path.name}",
                        }
                    )
                elif tag in ("privapp-permissions", "signature-permissions"):
                    pkg = el.get("package")
                    key = "privapp_permissions" if tag == "privapp-permissions" else "signature_permissions"
                    grant = out[key].setdefault(pkg, [])
                    for child in el:
                        if child.tag == "permission":
                            grant.append(child.get("name"))
                        elif child.tag == "deny-permission":
                            out["privapp_deny"].setdefault(pkg, []).append(child.get("name"))
                elif tag == "feature":
                    out["features"].append(el.get("name"))
                elif tag == "unavailable-feature":
                    out["unavailable_features"].append(el.get("name"))
                elif tag in (
                    "allow-in-power-save",
                    "allow-in-power-save-except-idle",
                    "allow-in-data-usage-save",
                    "system-user-whitelisted-app",
                    "hidden-api-whitelisted-app",
                    "allow-implicit-broadcast",
                    "allow-association",
                    "default-enabled-vr-app",
                    "disabled-until-used-preinstalled-carrier-app",
                    "disabled-until-used-preinstalled-carrier-associated-app",
                    "component-override",
                    "backup-transport-whitelisted-service",
                    "app-link",
                    "install-in-user-type",
                    "named-actor",
                    "allowed-oem-apex",
                    "allow-ignore-location-settings",
                    "bugreport-whitelisted",
                    "allow-unthrottled-location",
                ):
                    out["sysconfig"].setdefault(tag, []).append(dict(el.attrib))
    return out


def _read_varint(buf, pos):
    result = shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7


def read_classpath_pb(path):
    """Decode etc/classpaths/*.pb (ExportedClasspathsJars) -> list of {path, classpath}."""
    kinds = {0: "UNKNOWN", 1: "BOOTCLASSPATH", 2: "SYSTEMSERVERCLASSPATH", 3: "DEX2OATBOOTCLASSPATH",
             4: "STANDALONE_SYSTEMSERVER_JARS"}
    jars = []
    try:
        buf = Path(path).read_bytes()
    except OSError:
        return jars
    pos = 0
    while pos < len(buf):
        key, pos = _read_varint(buf, pos)
        if key & 7 != 2:
            break
        length, pos = _read_varint(buf, pos)
        msg, pos = buf[pos : pos + length], pos + length
        jar, mpos = {"path": None, "classpath": "UNKNOWN"}, 0
        while mpos < len(msg):
            mkey, mpos = _read_varint(msg, mpos)
            field, wire = mkey >> 3, mkey & 7
            if wire == 2:
                mlen, mpos = _read_varint(msg, mpos)
                val, mpos = msg[mpos : mpos + mlen], mpos + mlen
                if field == 1:
                    jar["path"] = val.decode("utf-8", "replace")
                elif field == 3:
                    jar["min_sdk_version"] = val.decode("utf-8", "replace")
                elif field == 4:
                    jar["max_sdk_version"] = val.decode("utf-8", "replace")
            elif wire == 0:
                val, mpos = _read_varint(msg, mpos)
                if field == 2:
                    jar["classpath"] = kinds.get(val, str(val))
            else:
                break
        jars.append(jar)
    return jars


def read_vintf_file(path):
    """Parse one VINTF manifest or compatibility-matrix XML into a list of HAL dicts."""
    root = _xml_root(path)
    if root is None:
        return None
    doc = {
        "file": str(path),
        "kind": root.tag,
        "type": root.get("type"),
        "version": root.get("version"),
        "target_level": root.get("target-level"),
        "level": root.get("level"),
        "hals": [],
        "sepolicy": None,
        "kernel": [],
        "vendor_ndk": [],
        "system_sdk": [],
    }
    for hal in root.findall("hal"):
        entry = {
            "name": (hal.findtext("name") or "").strip(),
            "format": hal.get("format", "hidl"),
            "optional": hal.get("optional"),
            "updatable_via_apex": hal.get("updatable-via-apex"),
            "transport": (hal.findtext("transport") or "").strip() or None,
            "versions": [v.text.strip() for v in hal.findall("version") if v.text],
            "fqnames": [f.text.strip() for f in hal.findall("fqname") if f.text],
            "interfaces": [],
        }
        for iface in hal.findall("interface"):
            entry["interfaces"].append(
                {
                    "name": (iface.findtext("name") or "").strip(),
                    "instances": [i.text.strip() for i in iface.findall("instance") if i.text],
                    "regex_instances": [i.text.strip() for i in iface.findall("regex-instance") if i.text],
                }
            )
        doc["hals"].append(entry)
    sep = root.find("sepolicy")
    if sep is not None:
        doc["sepolicy"] = {
            "version": sep.findtext("version"),
            "kernel_sepolicy_version": sep.findtext("kernel-sepolicy-version"),
            "sepolicy_versions": [v.text for v in sep.findall("sepolicy-version")],
        }
    for k in root.findall("kernel"):
        doc["kernel"].append({"version": k.get("version"), "target_level": k.get("target-level")})
    for v in root.findall("vendor-ndk"):
        doc["vendor_ndk"].append(v.findtext("version"))
    for v in root.findall("system-sdk"):
        doc["system_sdk"].extend(x.text for x in v.findall("version"))
    return doc


def read_vintf_dir(etc_dir):
    """Read etc/vintf/** of one partition (manifests, fragments and compatibility matrices)."""
    docs = []
    base = Path(etc_dir) / "vintf"
    if base.is_dir():
        for path in sorted(base.rglob("*.xml")):
            doc = read_vintf_file(path)
            if doc:
                doc["file"] = str(path.relative_to(etc_dir))
                docs.append(doc)
    return docs


_SERVICE_RE = re.compile(r"^service\s+(\S+)\s+(\S+)(.*)$")


def read_init_rc(path):
    """Extract service definitions from an init .rc file."""
    services, current = [], None
    try:
        lines = Path(path).read_text(errors="replace").splitlines()
    except OSError:
        return services
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _SERVICE_RE.match(line)
        if m:
            current = {
                "name": m.group(1),
                "exec": m.group(2),
                "args": m.group(3).strip(),
                "class": [],
                "user": None,
                "group": [],
                "interfaces": [],
                "flags": [],
                "seclabel": None,
            }
            services.append(current)
            continue
        if line.startswith(("on ", "import ")):
            current = None
            continue
        if current is None:
            continue
        word, _, rest = line.partition(" ")
        rest = rest.strip()
        if word == "class":
            current["class"] = rest.split()
        elif word == "user":
            current["user"] = rest
        elif word == "group":
            current["group"] = rest.split()
        elif word == "interface":
            current["interfaces"].append(rest)
        elif word == "seclabel":
            current["seclabel"] = rest
        elif word in ("disabled", "oneshot", "override", "critical", "updatable"):
            current["flags"].append(word)
    return services


def read_init_dir(etc_dir):
    out = []
    base = Path(etc_dir) / "init"
    if base.is_dir():
        for path in sorted(base.rglob("*.rc")):
            for svc in read_init_rc(path):
                svc["rc"] = str(path.relative_to(etc_dir))
                out.append(svc)
    return out


def walk_files(root):
    """Yield (relative_path, absolute_path) for regular files under root, never following symlinks."""
    root = str(root)
    for dirpath, _, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full) or not os.path.isfile(full):
                continue
            yield os.path.relpath(full, root), full
