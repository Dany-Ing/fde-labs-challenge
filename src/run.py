"""Thin slice: process named documents end to end.  usage: python src/run.py [--reset] FILE..."""
from __future__ import annotations
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from ingest import read_any
from extract import extract_facts, ExtractionError
from policy import build_record, decide, Decision
import erp

ROOT = Path(__file__).parent.parent
OUT = ROOT / "out"; OUT.mkdir(exist_ok=True)
MAX_REPAIRS = 2


def find(name: str) -> Path:
    for d in ("data/contracts", "data/emails"):
        if (ROOT / d / name).exists():
            return ROOT / d / name
    raise FileNotFoundError(name)


def process(name: str) -> dict:
    path, t0 = find(name), time.time()
    text = read_any(path)
    audit = {"source_document": name, "attempts": [], "cost_usd": 0.0}
    feedback, facts, record, first_try, d = None, None, None, None, None
    for attempt in range(MAX_REPAIRS + 1):
        try:
            facts = extract_facts(text, name, feedback=feedback)
        except ExtractionError as e:
            audit["attempts"].append({"extract_error": str(e)}); feedback = f"extraction failed: {e}"; continue
        audit["cost_usd"] += (facts.get("_usage") or {}).get("cost_usd") or 0
        record = build_record(facts, name)
        d = decide(facts, record, text)
        if d.action != "load":
            break
        errs = erp.local_errors(record)
        if not errs:
            status, body = erp.post_contract(record)
            audit["attempts"].append({"attempt": attempt, "erp_status": status})
            if first_try is None: first_try = status == 200
            if status == 200: break
            errs = body.get("errors", [{"error": str(body)}])
        else:
            audit["attempts"].append({"attempt": attempt, "local_errors": errs})
        feedback = "schema errors: " + json.dumps(errs)
    else:  # loop ran out of attempts without a successful load or a non-load decision
        d = Decision("escalate", ["ESCALATE: could not produce a conformant record"],
                     f"repair loop exhausted after {MAX_REPAIRS + 1} attempts: {feedback}")
    if d.action != "load":
        kind = d.action
        erp.post_escalation(name, kind, d.reason + " | " + "; ".join(d.rules), record)
    audit.update(facts={k: v for k, v in (facts or {}).items() if k != '_usage'}, action=d.action, rules=d.rules, reason=d.reason, record=record,
                 first_try_conformant=first_try, seconds=round(time.time() - t0, 1))
    with (OUT / "audit.jsonl").open("a") as f:
        f.write(json.dumps(audit, ensure_ascii=False) + "\n")
    return audit


def all_documents() -> list[str]:
    return [p.name for d in ("data/contracts", "data/emails") for p in sorted((ROOT / d).iterdir())]


def safe_process(name: str) -> dict:
    """One bad document must never stop the batch or vanish: escalate it."""
    try:
        return process(name)
    except Exception as e:  # noqa: BLE001
        reason = f"unexpected processing error ({type(e).__name__}: {e}); needs manual handling"
        erp.post_escalation(name, "escalate", reason)
        return {"source_document": name, "action": "escalate", "reason": reason, "seconds": 0, "cost_usd": 0.0}


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--reset" in args:
        erp._post("/reset", {}); args.remove("--reset")
    if "--all" in args:
        args = all_documents()
    for n in args:
        a = safe_process(n)
        print(f"{n}: {a['action'].upper()}  ({a['seconds']}s, ${a['cost_usd']:.4f})\n  {a['reason']}", flush=True)
