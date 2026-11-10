"""Stability check: run the full pipeline N times and compare decisions and loaded fields.
usage: python src/stability.py [N]    (default 4).  Writes out/stability_report.json
The pipeline's results.json / audit log end up as those of the last run."""
from __future__ import annotations
import json, subprocess, sys, shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent
N = int(sys.argv[1]) if len(sys.argv) > 1 else 4
runs = []
for i in range(1, N + 1):
    print(f"run {i}/{N} ...", flush=True)
    subprocess.run([sys.executable, str(ROOT / "src" / "run.py"), "--reset", "--all"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    shutil.copy(ROOT / "results.json", ROOT / "out" / f"results_run{i}.json")
    shutil.copy(ROOT / "out" / "audit.jsonl", ROOT / "out" / f"audit_run{i}.jsonl")
    ev = subprocess.run([sys.executable, str(ROOT / "src" / "evaluate.py"), "--note", f"stability run {i}"],
                        capture_output=True, text=True)
    runs.append({"run": i, "eval_exit": ev.returncode, "results": json.loads((ROOT / "results.json").read_text())})


def decisions(r):
    d = {x["source_document"]: "load" for x in r["loaded"]}
    for e in r["escalations"]:
        d[(e["source_document"], e.get("source_row"))] = e["kind"]
    for m in r.get("merged_duplicates", []):
        d[("legacy_export.csv", m["source_row"])] = "merged"
    return d


base = runs[0]["results"]
flips, field_flips = [], []
for run in runs[1:]:
    a, b = decisions(base), decisions(run["results"])
    for k in sorted(set(a) | set(b), key=str):
        if a.get(k) != b.get(k):
            flips.append({"run": run["run"], "decision": str(k), "run1": a.get(k), "this_run": b.get(k)})
    ra = {x["source_document"]: x for x in base["loaded"]}
    for x in run["results"]["loaded"]:
        y = ra.get(x["source_document"])
        if y:
            for f in set(x) | set(y):
                if f in ("notes", "extraction_confidence"):
                    continue
                if x.get(f) != y.get(f):
                    field_flips.append({"run": run["run"], "doc": x["source_document"], "field": f, "run1": y.get(f), "this_run": x.get(f)})
conf_spread = {}
for run in runs:
    for x in run["results"]["loaded"]:
        conf_spread.setdefault(x["source_document"], []).append(x["extraction_confidence"])
rep = {"runs": N, "all_runs_pass_eval": all(r["eval_exit"] == 0 for r in runs),
       "decision_flips": flips, "field_flips": field_flips,
       "confidence_range_by_doc": {d: [min(v), max(v)] for d, v in conf_spread.items() if min(v) != max(v)}}
(ROOT / "out" / "stability_report.json").write_text(json.dumps(rep, indent=2) + "\n")
print(json.dumps(rep, indent=2))
