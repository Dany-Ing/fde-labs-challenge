"""Eval harness: score a finished run against the hand-labelled expectations.

usage: python src/evaluate.py [--results results.json] [--audit out/audit.jsonl] [--note "what changed"]
Reads eval/expected.json (my labels), results.json (what was sent to the ERP) and the audit log
(timing, cost, first-try conformance). Prints a report, writes out/eval_report.json, appends one
line to out/eval_history.jsonl. Exit code 1 if any hard guardrail is breached or any decision differs.
The labels are mine, so this is a regression gate, not an independent accuracy claim.
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from policy import FX

ROOT = Path(__file__).parent.parent
FIELD_MAP = {"risk_tier": "risk_tier", "region": "data_residency_region", "dpa_signed": "dpa_signed",
             "value": "contract_value", "ccy": "currency", "cap": "liability_cap", "start": "start_date",
             "renewal": "renewal_date", "termination": "termination_date"}


def pct(a, b):
    return None if not b else round(100 * a / b, 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "results.json"))
    ap.add_argument("--audit", default=str(ROOT / "out" / "audit.jsonl"))
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    exp = json.loads((ROOT / "eval" / "expected.json").read_text())
    res = json.loads(Path(a.results).read_text())
    audit = [json.loads(l) for l in Path(a.audit).read_text().splitlines() if l.strip()]

    # ---- what the system decided, keyed like the labels
    got = {x["source_document"]: ("load", x) for x in res["loaded"]}
    for e in res["escalations"]:
        if e.get("source_row") is None:
            got[e["source_document"]] = (e["kind"], e)
    rows_got = {e["source_row"]: e["kind"] for e in res["escalations"] if e.get("source_row")}
    rows_got.update({m["source_row"]: "merged" for m in res.get("merged_duplicates", []) if m.get("source_row")})

    mismatches, tp = [], {"escalate_or_quarantine": 0}
    pairs = []  # (label_action, got_action) for every decision incl. CSV rows
    for d, e in exp["documents"].items():
        g = got.get(d, ("MISSING", None))[0]
        pairs.append((e["action"], g, d))
    for r, e in exp["csv_rows"].items():
        pairs.append((e["action"], rows_got.get(int(r), "MISSING"), f"legacy_export.csv row {r}"))
    for want, g, name in pairs:
        if want != g:
            mismatches.append({"decision": name, "expected": want, "got": g})

    def prf(positive):
        P = [(w, g) for w, g, _ in pairs]
        tp_ = sum(1 for w, g in P if g in positive and w in positive)
        fp = sum(1 for w, g in P if g in positive and w not in positive)
        fn = sum(1 for w, g in P if g not in positive and w in positive)
        return {"precision": pct(tp_, tp_ + fp), "recall": pct(tp_, tp_ + fn), "tp": tp_, "fp": fp, "fn": fn}

    # ---- field accuracy on records that were expected AND actually loaded
    ok = bad = 0
    field_errors = []
    for d, e in exp["documents"].items():
        if e["action"] == "load" and got.get(d, ("",))[0] == "load":
            rec = got[d][1]
            for k, f in FIELD_MAP.items():
                if k in e:
                    if rec.get(f) == e[k]:
                        ok += 1
                    else:
                        bad += 1; field_errors.append({"doc": d, "field": f, "got": rec.get(f), "expected": e[k]})

    # ---- hard guardrails, checked on the artifact itself, independent of the labels
    breaches = []
    seen = set()
    for r in res["loaded"]:
        cap, ccy = r.get("liability_cap"), r.get("currency")
        if cap is not None and cap * FX.get(ccy, 0) > 1_000_000:
            breaches.append(f"{r['source_document']}: loaded with cap over $1M")
        if r.get("dpa_signed") is None:
            breaches.append(f"{r['source_document']}: loaded without dpa_signed")
        if r["source_document"] in seen:
            breaches.append(f"{r['source_document']}: loaded twice")
        seen.add(r["source_document"])
        if exp["documents"].get(r["source_document"], {}).get("action") == "quarantine":
            breaches.append(f"{r['source_document']}: injection document was loaded")
    n_docs = len(exp["documents"])
    loaded_docs = sum(1 for d in exp["documents"] if got.get(d, ("",))[0] == "load")
    docs_audit = [x for x in audit if x.get("source_row") is None]
    first = [x["first_try_conformant"] for x in docs_audit if x.get("first_try_conformant") is not None]
    aud_ok = sum(1 for x in audit if x.get("reason") and x.get("rules") is not None and
                 ((x.get("record") or {}).get("extraction_confidence") is not None or (x.get("facts") or {}).get("confidence") is not None))
    secs = sum(x.get("seconds") or 0 for x in audit)
    cost = sum(x.get("cost_usd") or 0 for x in audit)

    rep = {
        "when": time.strftime("%Y-%m-%d %H:%M"), "note": a.note,
        "decisions": {"total": len(pairs), "matching_labels": len(pairs) - len(mismatches), "mismatches": mismatches},
        "straight_through_rate_pct": pct(loaded_docs, n_docs), "docs_loaded": loaded_docs, "docs_total": n_docs,
        "non_load_vs_labels": prf({"escalate", "quarantine"}), "quarantine_vs_labels": prf({"quarantine"}),
        "field_accuracy": {"correct": ok, "total": ok + bad, "pct": pct(ok, ok + bad), "errors": field_errors},
        "first_try_conformant_pct": pct(sum(first), len(first)), "first_try_loads": len(first),
        "guardrail_breaches": breaches,
        "auditability_pct": pct(aud_ok, len(audit)), "audit_entries": len(audit),
        "throughput": {"seconds_total": round(secs, 1), "seconds_per_doc": round(secs / max(len(docs_audit), 1), 1),
                       "docs_per_hour_serial": round(3600 * len(docs_audit) / secs) if secs else None},
        "cost": {"usd_total": round(cost, 4), "usd_per_doc": round(cost / max(len(docs_audit), 1), 5)},
    }
    (ROOT / "out").mkdir(exist_ok=True)
    (ROOT / "out" / "eval_report.json").write_text(json.dumps(rep, indent=2, default=str) + "\n")
    with (ROOT / "out" / "eval_history.jsonl").open("a") as f:
        f.write(json.dumps({k: rep[k] for k in ("when", "note", "straight_through_rate_pct")} |
                           {"matching": rep["decisions"]["matching_labels"], "total": rep["decisions"]["total"],
                            "field_pct": rep["field_accuracy"]["pct"], "breaches": len(breaches)}) + "\n")

    p = rep["non_load_vs_labels"]; q = rep["quarantine_vs_labels"]
    print(f"Decisions matching labels : {rep['decisions']['matching_labels']}/{rep['decisions']['total']} (21 docs + 7 CSV rows)")
    print(f"Straight-through rate     : {rep['straight_through_rate_pct']}%  ({loaded_docs}/{n_docs} documents auto-loaded)")
    print(f"Escalate/quarantine       : precision {p['precision']}%  recall {p['recall']}%  (tp {p['tp']} fp {p['fp']} fn {p['fn']})")
    print(f"Quarantine (injection)    : precision {q['precision']}%  recall {q['recall']}%")
    print(f"Field accuracy (loaded)   : {ok}/{ok + bad} = {rep['field_accuracy']['pct']}%")
    print(f"First-try ERP conformance : {rep['first_try_conformant_pct']}%  ({sum(first)}/{len(first)} loads accepted on first POST)")
    print(f"Auditability              : {rep['auditability_pct']}%  of {len(audit)} decisions have reason + rules + confidence")
    print(f"Throughput                : {rep['throughput']['seconds_per_doc']} s/doc, ~{rep['throughput']['docs_per_hour_serial']} docs/h serial")
    print(f"Cost                      : ${rep['cost']['usd_total']} total, ${rep['cost']['usd_per_doc']}/doc (model only, metered)")
    print(f"Hard guardrail breaches   : {len(breaches)}" + "".join(f"\n  BREACH {b}" for b in breaches))
    for m in mismatches:
        print(f"  MISMATCH {m['decision']}: expected {m['expected']}, got {m['got']}")
    for fe in field_errors:
        print(f"  FIELD {fe['doc']} {fe['field']}: got {fe['got']} expected {fe['expected']}")
    return 1 if (breaches or mismatches) else 0


if __name__ == "__main__":
    sys.exit(main())
