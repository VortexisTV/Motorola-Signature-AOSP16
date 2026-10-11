#!/usr/bin/env python3
"""Source patches (patches/<project>/*.patch): applied in the tree, and present in the image.

    check_source_patches.py --repo REPO --aosp TREE --product-out OUT --root MOUNTED_IMAGE
                            --toolbin DIR_WITH_LLVM_TOOLS [--out REPORT_DIR]

"Applied in the tree" says nothing about the binaries of an image that was built earlier, so
each patch also names something that can be read out of the image itself.
"""
import argparse, json, pathlib, re, subprocess, sys, zipfile

results = []


def add(status, check, summary):
    results.append({"status": status, "check": check, "summary": summary})
    print("  [%-7s] %s: %s" % (status, check, summary))


def run(*cmd):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True)


def build_id(toolbin, path):
    m = re.search(r"Build ID: ([0-9a-f]+)", run(toolbin / "llvm-readelf", "-n", path).stdout)
    return m.group(1) if m else None


def probe_surfaceflinger(args):
    """The screenshot path must not duplicate the LUT descriptor into a temporary any more."""
    image = args.root / "system/bin/surfaceflinger"
    syms = args.product_out / "symbols/system/bin/surfaceflinger"
    a, b = build_id(args.toolbin, image), build_id(args.toolbin, syms)
    if not a or a != b:
        return "UNKNOWN", "Build ID of the image binary (%s) and of the unstripped copy (%s) differ" % (a, b)
    want = "ScreenCaptureOutput33generateClientCompositionRequests"
    names = [l.split()[2] for l in run(args.toolbin / "llvm-nm", "--defined-only", syms).stdout.splitlines()
             if want in l and len(l.split()) == 3]
    if len(names) != 1:
        return "UNKNOWN", "function not found in the unstripped surfaceflinger"
    dis = run(args.toolbin / "llvm-objdump", "-d", "--no-show-raw-insn", "--disassemble-symbols=" + names[0], syms).stdout
    calls = re.findall(r"bl\s+0x[0-9a-f]+ <([^>]+)>", dis)
    if not calls:
        return "UNKNOWN", "no disassembly for the function"
    if any(c.startswith("dup@") for c in calls):
        return "FAIL", "surfaceflinger %s still calls dup() in ScreenCaptureOutput::generateClientCompositionRequests" % a
    return "PASS", ("surfaceflinger in the image (Build ID %s): ScreenCaptureOutput::generateClientCompositionRequests "
                    "has %d calls, none to dup(); the LUT descriptor is moved, not copied into a temporary" % (a, len(calls)))


def probe_bytes(path, needle, what):
    if not path.is_file():
        return "FAIL", "%s is not in the image" % what
    data = path.read_bytes()
    if path.suffix == ".apk":
        with zipfile.ZipFile(path) as z:
            data = b"".join(z.read(n) for n in z.namelist() if n.endswith(".dex"))
    if needle.encode() in data:
        return "PASS", "%s contains \"%s\"" % (what, needle)
    return "FAIL", "%s does not contain \"%s\": built without the patch" % (what, needle)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for a in ("--repo", "--aosp", "--product-out", "--root", "--toolbin"):
        ap.add_argument(a, required=True, type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path)
    args = ap.parse_args()

    probes = {
        "frameworks/native": lambda: probe_surfaceflinger(args),
        "system/core": lambda: probe_bytes(args.root / "system/bin/init", "ro.boot.carrier", "/system/bin/init"),
        "packages/apps/QcRilAm": lambda: probe_bytes(
            next(iter(sorted((args.root / "system").rglob("QcRilAm.apk"))), args.root / "QcRilAm.apk"),
            "setRequestInterface has not returned after 10 s", "QcRilAm.apk"),
    }
    patches = sorted((args.repo / "patches").rglob("*.patch"))
    seen = set()
    for p in patches:
        project = str(p.parent.relative_to(args.repo / "patches")).replace(chr(92), "/")
        seen.add(project)
        r = run("git", "-C", args.aosp / project, "apply", "--reverse", "--check", p)
        add("PASS" if r.returncode == 0 else "FAIL", "patch.tree:" + project,
            "%s is applied in the source tree" % p.name if r.returncode == 0 else
            "%s is not applied in the source tree: %s" % (p.name, r.stderr.strip()[:200]))
    for project in sorted(seen):
        if project in probes:
            status, text = probes[project]()
            add(status, "patch.image:" + project, text)
        else:
            add("UNKNOWN", "patch.image:" + project, "no image probe is defined for this project")
    if args.out:
        (args.out / "source-patches.json").write_text(json.dumps(results, indent=1))
    sys.exit(1 if any(r["status"] == "FAIL" for r in results) else 0)


if __name__ == "__main__":
    main()
