"""Pipeline: ingest -> extract -> policy -> reconcile -> act (-> audit).
usage: python src/run.py [--reset] [--csv] (--all | FILE...)

Failure handling (all paths tested in tests/test_failure_handling.py):
- model/extraction failure   -> bounded retries with backoff, then escalate that document
- schema rejection (422)     -> repair loop (re-extract with the error list, max 2), then escalate
- reconcile / CSV step fails -> nothing is auto-loaded (loads become escalations); CSV problem is escalated
- ERP unreachable / rejects  -> retries with backoff; the document is reported under `undelivered`
                                in results.json, the run exits 1 and says so loudly. Never silent.
"""
from __future__ import annotations
import json, sys, time
from dataclasses import dataclass, field
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from ingest import read_any, read_csv_rows
from extract import extract_facts, ExtractionError
from policy import build_record, decide, Decision, apply_text_guards
from reconcile import reconcile, csv_to_facts
import erp

ROOT = Path(__file__).parent.parent
OUT = ROOT / "out"; OUT.mkdir(exist_ok=True)
MAX_REPAIRS = 2
RETRY_DELAYS = (2, 5)       # seconds between model attempts (a usage limit or hiccup rarely clears instantly)


class DeliveryError(Exception):
    """The ERP did not record a decision (unreachable, 5xx after retries, or an unexpected 4xx)."""


@dataclass
class Item:
    name: str
    kind: str = "doc"                 # doc | csv
    source_row: int | None = None
    text: str = ""
    facts: dict = field(default_factory=dict)
    record: dict = field(default_factory=dict)
    decision: Decision | None = None
    extra_notes: list = field(default_factory=list)
    merged_into: str | None = None
    cost: float = 0.0
    seconds: float = 0.0
    attempts: list = field(default_factory=list)
    first_try: bool | None = None
    delivery_error: str | None = None


def find(name: str) -> Path:
    for d in ("data/contracts", "data/emails"):
        if (ROOT / d / name).exists():
            return ROOT / d / name
    raise FileNotFoundError(name)


def all_documents() -> list[str]:
    # skip editor/OS leftovers such as Word lock files (~$name.docx) and dotfiles
    return [p.name for d in ("data/contracts", "data/emails") for p in sorted((ROOT / d).iterdir())
            if p.is_file() and not p.name.startswith(("~$", ".")) and p.suffix.lower() in (".pdf", ".docx", ".eml")]


def _backoff(attempt: int) -> None:
    time.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)])


def analyze(name: str) -> Item:
    """Extract + decide for one document. Never raises: failures become escalations."""
    it, t0 = Item(name), time.time()
    try:
        it.text = read_any(find(name))
        feedback = None
        for attempt in range(MAX_REPAIRS + 1):
            try:
                it.facts = extract_facts(it.text, name, feedback=feedback)
                break
            except ExtractionError as e:
                it.attempts.append({"extract_error": str(e)}); feedback = f"extraction failed: {e}"
                if attempt < MAX_REPAIRS:
                    _backoff(attempt)
        if not it.facts:
            it.decision = Decision("escalate", ["ESCALATE: extraction failed"], f"extraction failed after retries: {feedback}")
        else:
            it.cost += (it.facts.pop("_usage", None) or {}).get("cost_usd") or 0
            apply_text_guards(it.facts, it.text)
            it.record = build_record(it.facts, name)
            it.decision = decide(it.facts, it.record, it.text)
    except Exception as e:  # noqa: BLE001 - one bad document must not stop the batch
        it.decision = Decision("escalate", ["ESCALATE: unexpected processing error"],
                               f"{type(e).__name__}: {e}; needs manual handling")
    it.seconds = round(time.time() - t0, 1)
    return it


def analyze_csv() -> list[Item]:
    items = []
    for i, row in enumerate(read_csv_rows(ROOT / "data" / "legacy_export.csv"), start=1):
        it = Item("legacy_export.csv", "csv", i)
        it.facts = csv_to_facts(row)
        it.record = build_record(it.facts, "legacy_export.csv", f"legacy_export.csv row {i}")
        it.decision = decide(it.facts, it.record, " ".join(str(v) for v in row.values() if v))
        if it.decision.action == "load":     # CSV has no DPA field, so this cannot happen; belt and braces
            it.decision = Decision("escalate", ["ESCALATE: CSV-only row"], "no source document to verify")
        items.append(it)
    return items


def _extract_again(it: Item, feedback: str) -> str | None:
    """One repair attempt. Returns new feedback text if extraction itself failed, else None."""
    try:
        it.facts = extract_facts(it.text, it.name, feedback=feedback)
    except ExtractionError as e:
        return f"extraction failed: {e}"
    it.cost += (it.facts.pop("_usage", None) or {}).get("cost_usd") or 0
    apply_text_guards(it.facts, it.text)
    it.record = build_record(it.facts, it.name)
    it.decision = decide(it.facts, it.record, it.text)
    return None


def _act(it: Item) -> None:
    """Send the decision to the ERP. Raises DeliveryError if the ERP did not record it."""
    if it.merged_into and it.kind == "doc":
        return
    if it.extra_notes and it.record:
        it.record["notes"] = (it.record.get("notes") or "") + "; " + "; ".join(it.extra_notes)
    if it.decision.action == "load":
        feedback = None
        for attempt in range(MAX_REPAIRS + 1):
            errs = erp.local_errors(it.record)
            if not errs:
                status, body = erp.post_contract(it.record)
                it.attempts.append({"attempt": attempt, "erp_status": status})
                if it.first_try is None:
                    it.first_try = status == 200
                if status == 200:
                    return
                if status != 422:        # unreachable (0), 5xx after retries, or an unexpected 4xx: not a schema problem
                    raise DeliveryError(f"POST /contracts failed with status {status}: {body}")
                errs = body.get("errors", [{"error": str(body)}])
            else:
                it.attempts.append({"attempt": attempt, "local_errors": errs})
                if it.first_try is None:
                    it.first_try = False
            feedback = "schema errors: " + json.dumps(errs)
            if attempt == MAX_REPAIRS:
                break
            failed = _extract_again(it, feedback)
            if failed:
                feedback = failed
                _backoff(attempt)
            elif it.decision.action != "load":
                break
        if it.decision.action == "load":
            it.decision = Decision("escalate", ["ESCALATE: could not produce a conformant record"],
                                   f"repair loop exhausted: {feedback}")
    rec = dict(it.record or {})
    if it.source_row:
        rec["source_row"] = it.source_row
    status, body = erp.post_escalation(it.name, it.decision.action, it.decision.reason + " | " + "; ".join(it.decision.rules), rec)
    if status != 200:
        raise DeliveryError(f"POST /escalate failed with status {status}: {body}")


def act(it: Item) -> None:
    """Deliver one decision; a delivery problem is recorded on the item, never raised or ignored."""
    try:
        _act(it)
    except Exception as e:  # noqa: BLE001
        it.delivery_error = f"{type(e).__name__}: {e}"


def write_results(items: list[Item], path: Path) -> dict:
    """results.json = what the ERP accepted, in the published envelope.
    Anything the ERP did not record goes under `undelivered` (extra key), never into loaded/escalations."""
    loaded, escalations, merged, undelivered = [], [], [], []
    for it in items:
        if it.delivery_error:
            undelivered.append({"source_document": it.name, "source_row": it.source_row,
                                "intended_action": it.decision.action, "reason": it.decision.reason,
                                "delivery_error": it.delivery_error, "record": it.record or None})
        elif it.merged_into:
            merged.append({"source_document": it.name, "source_row": it.source_row, "merged_into": it.merged_into,
                           "note": "consistent duplicate; not loaded separately"})
        elif it.decision.action == "load":
            loaded.append(it.record)
        else:
            rec = dict(it.record or {})
            e = {"source_document": it.name, "kind": it.decision.action,
                 "reason": it.decision.reason + " | " + "; ".join(it.decision.rules), "record": rec or None}
            if it.source_row:
                e["source_row"] = it.source_row
                rec["source_row"] = it.source_row
            escalations.append(e)
    out = {"loaded": loaded, "escalations": escalations, "merged_duplicates": merged}
    if undelivered:
        out["undelivered"] = undelivered
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str) + "\n")
    return out


def _safe_csv() -> list[Item]:
    try:
        return analyze_csv()
    except Exception as e:  # noqa: BLE001
        it = Item("legacy_export.csv", "csv")
        it.decision = Decision("escalate", ["ESCALATE: legacy CSV could not be processed"],
                               f"legacy_export.csv could not be read or parsed ({type(e).__name__}: {e}); its rows need manual review")
        return [it]


def _safe_reconcile(docs: list[Item], rows: list[Item]) -> None:
    try:
        reconcile(docs, rows)
    except Exception as e:  # noqa: BLE001 - without duplicate/conflict checks nothing may be auto-loaded
        for it in docs + rows:
            it.merged_into = None
            if it.decision and it.decision.action == "load":
                it.decision = Decision("escalate", ["ESCALATE: reconciliation failed"],
                                       f"cross-document reconciliation failed ({type(e).__name__}: {e}); duplicates and "
                                       "conflicts could not be checked, so this was not auto-loaded")


def run(names: list[str], with_csv: bool) -> list[Item]:
    docs = [analyze(n) for n in names]
    rows = _safe_csv() if with_csv else []
    _safe_reconcile(docs, rows)
    for it in docs + rows:
        if it.kind == "csv" and it.merged_into:
            continue
        act(it)
    with (OUT / "audit.jsonl").open("w" if with_csv else "a") as f:
        for it in docs + rows:
            f.write(json.dumps({
                "source_document": it.name, "source_row": it.source_row,
                "action": "merged" if it.merged_into else it.decision.action,
                "merged_into": it.merged_into, "rules": it.decision.rules, "reason": it.decision.reason,
                "facts": it.facts, "record": it.record, "attempts": it.attempts,
                "first_try_conformant": it.first_try, "cost_usd": it.cost, "seconds": it.seconds,
                "delivery_error": it.delivery_error,
            }, ensure_ascii=False, default=str) + "\n")
    if with_csv and len(names) == len(all_documents()):
        write_results(docs + rows, ROOT / "results.json")
    return docs + rows


if __name__ == "__main__":
    args = sys.argv[1:]
    if not erp.healthy():
        sys.exit(f"ERP not reachable at {erp.BASE}. Start it first: python mock_erp/app.py "
                 "(nothing was processed, no model calls were made).")
    if "--reset" in args:
        status, _ = erp._post("/reset", {}); args.remove("--reset")
        if status != 200:
            sys.exit(f"could not reset the ERP (status {status}); aborting before any processing")
    with_csv = "--csv" in args or "--all" in args
    args = [a for a in args if a != "--csv"]
    names = all_documents() if "--all" in args else [a for a in args if a != "--all"]
    items = run(names, with_csv)
    for it in items:
        tag = f"{it.name}" + (f" row {it.source_row}" if it.source_row else "")
        act_ = f"MERGED into {it.merged_into}" if it.merged_into else it.decision.action.upper()
        print(f"{tag}: {act_}" + ("" if it.merged_into else f"\n  {it.decision.reason[:300]}"), flush=True)
    bad = [it for it in items if it.delivery_error]
    if bad:
        print(f"\n!! {len(bad)} decision(s) NOT recorded by the ERP (see `undelivered` in results.json):", file=sys.stderr)
        for it in bad:
            print(f"   - {it.name}{' row ' + str(it.source_row) if it.source_row else ''}: {it.delivery_error}", file=sys.stderr)
        sys.exit(1)
