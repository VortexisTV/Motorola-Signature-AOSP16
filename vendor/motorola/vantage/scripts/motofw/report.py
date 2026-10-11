"""Uniform PASS / FAIL / WARNING / UNKNOWN reporting for the validators.

Status meaning (kept strict on purpose):
  PASS     verified by the test itself
  FAIL     confirmed incompatibility
  WARNING  potential issue that needs a decision or a closer look
  UNKNOWN  cannot be decided statically; requires hardware or carrier validation
A static PASS never means "the feature works on the device".
"""
import json
import time
from pathlib import Path

ORDER = {"FAIL": 0, "WARNING": 1, "UNKNOWN": 2, "PASS": 3}


class Report:
    def __init__(self, title, context=None):
        self.title = title
        self.context = context or {}
        self.results = []
        self.started = time.strftime("%Y-%m-%dT%H:%M:%S")

    def add(self, test_id, status, summary, details=None, area="general"):
        assert status in ORDER, status
        self.results.append(
            {"id": test_id, "area": area, "status": status, "summary": summary, "details": details or []}
        )
        return status

    def passed(self, test_id, summary, details=None, area="general"):
        return self.add(test_id, "PASS", summary, details, area)

    def fail(self, test_id, summary, details=None, area="general"):
        return self.add(test_id, "FAIL", summary, details, area)

    def warn(self, test_id, summary, details=None, area="general"):
        return self.add(test_id, "WARNING", summary, details, area)

    def unknown(self, test_id, summary, details=None, area="general"):
        return self.add(test_id, "UNKNOWN", summary, details, area)

    def counts(self):
        out = {k: 0 for k in ORDER}
        for r in self.results:
            out[r["status"]] += 1
        return out

    def worst(self):
        return min((r["status"] for r in self.results), key=ORDER.get, default="PASS")

    def write(self, out_dir, basename):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "title": self.title,
            "generated": self.started,
            "context": self.context,
            "counts": self.counts(),
            "results": self.results,
        }
        with (out_dir / f"{basename}.json").open("w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=1)
        c = self.counts()
        lines = [
            f"# {self.title}",
            "",
            f"Generated: {self.started}",
            "",
            f"**PASS {c['PASS']} / FAIL {c['FAIL']} / WARNING {c['WARNING']} / UNKNOWN {c['UNKNOWN']}**",
            "",
            "Static analysis only. PASS means the checked property holds in the files; it does not "
            "prove that the feature works on hardware.",
            "",
        ]
        for key, val in self.context.items():
            lines.append(f"- {key}: `{val}`")
        lines += ["", "| Status | Area | Test | Result |", "|---|---|---|---|"]
        for r in sorted(self.results, key=lambda r: (ORDER[r["status"]], r["area"], r["id"])):
            summary = r["summary"].replace("|", "\\|")
            lines.append(f"| {r['status']} | {r['area']} | `{r['id']}` | {summary} |")
        detailed = [r for r in self.results if r["details"]]
        if detailed:
            lines += ["", "## Details", ""]
            for r in sorted(detailed, key=lambda r: (ORDER[r["status"]], r["id"])):
                lines += [f"### {r['status']}: `{r['id']}`", "", r["summary"], ""]
                lines += [f"- {str(d)}" for d in r["details"][:60]]
                if len(r["details"]) > 60:
                    lines.append(f"- ... {len(r['details']) - 60} more (see JSON)")
                lines.append("")
        with (out_dir / f"{basename}.md").open("w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
        return out_dir / f"{basename}.md"

    def print_summary(self):
        c = self.counts()
        print(f"{self.title}: PASS {c['PASS']} FAIL {c['FAIL']} WARNING {c['WARNING']} UNKNOWN {c['UNKNOWN']}")
        for r in sorted(self.results, key=lambda r: (ORDER[r["status"]], r["id"])):
            print(f"  [{r['status']:<7}] {r['id']}: {r['summary']}")
