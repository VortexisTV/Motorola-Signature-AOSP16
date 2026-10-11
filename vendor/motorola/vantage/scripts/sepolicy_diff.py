#!/usr/bin/env python3
"""Compare what two compiled SELinux policies allow selected domains to do.

    sepolicy_diff.py --ours OURS --stock STOCK --domain vendor_qtelephony [--domain ...] --out DIR
    sepolicy_diff.py --ours OURS --query system_app vendor_hal_telephony_service2 service_manager find

OURS is the policy init would build for this ROM (preflight.py --policy-out); STOCK is the
vendor's precompiled policy for the stock system. Rules are expanded to plain
(source type, target type, class, permission) tuples, so differently numbered attributes do
not matter. A tuple stock allows and this ROM does not is a denial the app would hit under
enforcing if it uses that access; the reverse direction is only reported as a count.

Needs the setools Python package (apt install setools). Static: it says what the policy
permits, not what the app does at run time.
"""
import argparse
import json
import sys
from pathlib import Path

try:
    import setools
except ImportError:  # pragma: no cover
    sys.exit("setools is not installed (apt install setools)")


def allowed(policy, domain):
    """{(target, class): {perm, ...}} for allow rules whose source is the domain or one of its attributes."""
    out = {}
    try:
        q = setools.TERuleQuery(policy, ruletype=["allow"], source=domain, source_indirect=True)
        rules = list(q.results())
    except Exception as e:  # unknown type in this policy
        return None, str(e)
    for rule in rules:
        if getattr(rule, "conditional", None) is not None:
            pass  # conditional rules are kept: Android policies have no booleans that matter here
        try:
            targets = list(rule.target.expand())
        except AttributeError:
            targets = [rule.target]
        perms = set(rule.perms)
        for t in targets:
            out.setdefault((str(t), str(rule.tclass)), set()).update(perms)
    return out, None


def live_types(policy, context_dirs):
    """Types that label something, or run something, in the image the policy is for.

    A permission on any other target type cannot be exercised: nothing carries that label."""
    import glob
    import re
    live = set()
    domains = set()
    for d in context_dirs:
        for f in glob.glob(str(Path(d) / "*contexts")):
            for line in open(f, errors="replace"):
                if line.lstrip().startswith("#"):
                    continue
                for m in re.finditer(r"u:object_r:([A-Za-z0-9_]+):s0", line):
                    live.add(m.group(1))
                m = re.search(r"\bdomain=([A-Za-z0-9_]+)", line)
                if m:
                    domains.add(m.group(1))
    for g in policy.genfscons():
        live.add(str(g.context.type_))
    for kind in ("initialsids", "portcons", "netifcons", "nodecons", "fs_uses"):
        for c in getattr(policy, kind)():
            ctx = getattr(c, "context", None)
            if ctx is not None:
                live.add(str(ctx.type_))
    # daemons: domains entered from an executable whose label is assigned
    for rule in setools.TERuleQuery(policy, ruletype=["type_transition"], tclass=["process"]).results():
        try:
            execs = {str(t) for t in rule.target.expand()}
        except AttributeError:
            execs = {str(rule.target)}
        if execs & live:
            domains.add(str(rule.default))
    always = {"kernel", "init", "zygote", "webview_zygote", "app_zygote", "system_server", "su", "shell"}
    return live | domains | always


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ours", required=True)
    ap.add_argument("--stock")
    ap.add_argument("--domain", action="append", default=[])
    ap.add_argument("--query", nargs=4, action="append", default=[], metavar=("SRC", "TGT", "CLASS", "PERM"))
    ap.add_argument("--deny", nargs=4, action="append", default=[], metavar=("SRC", "TGT", "CLASS", "PERM"),
                    help="a permission that must not be granted (repeatable)")
    ap.add_argument("--out")
    ap.add_argument("--contexts", action="append", default=[],
                    help="directory with the *_contexts files of this ROM or the vendor (repeatable); enables "
                         "the split into permissions on labels that exist here and labels that do not")
    args = ap.parse_args()

    ours = setools.SELinuxPolicy(args.ours)
    rc = 0
    for src, tgt, cls, perm in args.query:
        rules, err = allowed(ours, src)
        ok = bool(rules) and perm in rules.get((tgt, cls), set())
        print(f"{'ALLOWED' if ok else 'DENIED '} {src} -> {tgt}:{cls} {perm}" + (f"  ({err})" if err else ""))
        rc |= 0 if ok else 2
    for src, tgt, cls, perm in args.deny:
        rules, err = allowed(ours, src)
        ok = rules is not None and perm not in rules.get((tgt, cls), set())
        print(f"{'REFUSED' if ok else 'ALLOWED'} {src} -> {tgt}:{cls} {perm}  "
              + ("(as intended)" if ok else f"(must not be{': ' + err if err else ''})"))
        rc |= 0 if ok else 2

    if args.domain and not args.stock:
        sys.exit("--domain needs --stock")
    stock = setools.SELinuxPolicy(args.stock) if args.domain else None
    live = live_types(ours, args.contexts) if args.contexts and args.domain else None
    our_types = {str(t) for t in ours.types()}
    report = {}
    for dom in args.domain:
        a, ea = allowed(ours, dom)
        b, eb = allowed(stock, dom)
        if a is None or b is None:
            print(f"{dom}: not comparable (ours: {ea or 'ok'}; stock: {eb or 'ok'})")
            report[dom] = {"error": {"ours": ea, "stock": eb}}
            rc |= 1
            continue
        missing = []
        for key, perms in sorted(b.items()):
            lost = sorted(perms - a.get(key, set()))
            if lost:
                missing.append({"target": key[0], "class": key[1], "perms": lost})
        extra = sum(len(p - b.get(k, set())) for k, p in a.items())
        n_stock = sum(len(p) for p in b.values())
        n_lost = sum(len(m["perms"]) for m in missing)
        print(f"{dom}: stock allows {n_stock} permissions on {len(b)} target/class pairs; "
              f"{n_lost} of them are missing here ({len(missing)} pairs); {extra} exist only here")
        report[dom] = {"stock_permissions": n_stock, "missing_permissions": n_lost, "only_here": extra,
                       "missing": missing}
        if live is not None:
            absent = [m for m in missing if m["target"] not in our_types]
            dead = [m for m in missing if m["target"] in our_types and m["target"] not in live]
            relevant = [m for m in missing if m["target"] in live]
            report[dom].update(target_type_absent=len(absent), target_label_unused=len(dead), relevant=relevant)
            print(f"    of the {len(missing)} pairs: {len(absent)} target a type this ROM does not define, "
                  f"{len(dead)} a type nothing here is labelled with, {len(relevant)} a label that exists here")
            for m in relevant:
                print(f"      RELEVANT {m['class']:18s} {m['target']:34s} {','.join(m['perms'])[:70]}")
            rc |= 4 if relevant else 0
    if args.out and report:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "sepolicy-diff.json").write_text(json.dumps(report, indent=1) + chr(10), encoding="utf-8")
    return rc


if __name__ == "__main__":
    sys.exit(main())
