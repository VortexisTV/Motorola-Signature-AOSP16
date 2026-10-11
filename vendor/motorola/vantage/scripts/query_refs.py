#!/usr/bin/env python3
"""Summarise a check_java_linkage.py --dump-refs report.

For each subject, list the jars that define the external classes it uses and call out
classes outside the AOSP namespaces (i.e. vendor/OEM additions the subject depends on).
"""
import json
import re
import sys

AOSP_NS = re.compile(
    r"^L(java|javax|android|androidx|dalvik|libcore|sun|kotlin|kotlinx|org/json|org/xml|org/w3c|org/apache"
    r"|com/android|com/google|org/xmlpull|jdk)/"
)
report = json.load(open(sys.argv[1]))
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 40
for e in report["results"]:
    print("##", e["subject"], "libs:", [(lib["name"], lib["state"]) for lib in e.get("shared_libraries", [])])
    for prov, classes in sorted(e.get("external_classes", {}).items(), key=lambda kv: -len(kv[1])):
        nonaosp = [c for c in classes if not AOSP_NS.match(c)]
        print(f"   {len(classes):>5} classes from {prov}   outside AOSP namespaces: {len(nonaosp)}")
        for c in nonaosp[:limit]:
            print("          ", c)
