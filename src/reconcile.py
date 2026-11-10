"""Cross-document reconciliation: duplicates, conflicts and the legacy CSV.

Policy: the same agreement appearing more than once with CONSISTENT values loads once;
with CONFLICTING key values it escalates (surface the conflict, never pick one).
Pure functions over plain dicts so they are unit-testable without the model.
"""
from __future__ import annotations
import re
from datetime import datetime
from policy import Decision, INJECTION_RE, region_for

LEGAL_SUFFIX = {"inc", "llc", "corp", "corporation", "gmbh", "ltd", "ltda", "co", "ag", "kk", "limited", "plc", "sa", "company"}
TYPE_MAP = {"msa": "MSA", "sow": "SOW", "po": "PO", "purchase order": "PO", "nda": "NDA", "amendment": "AMENDMENT"}
KEY_FIELDS = (("contract_value", "value"), ("currency", "currency"), ("start_date", "start date"), ("liability_cap", "liability cap"))


def vnorm(name: str | None) -> str:
    toks = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower()).split()
    return " ".join(t for t in toks if t not in LEGAL_SUFFIX)


def conflicts(a: dict, b: dict) -> list[str]:
    """Key-field differences where BOTH sides state a value."""
    out = []
    for f, label in KEY_FIELDS:
        x, y = a.get(f), b.get(f)
        if x is None or y is None or x == "UNKNOWN" or y == "UNKNOWN":
            continue
        if x != y:
            out.append(f"{label} {x} vs {y}")
    return out


def to_iso(s: str | None) -> str | None:
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y", "%B %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime((s or "").strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def csv_to_facts(row: dict) -> dict:
    """Normalise one messy CSV row into the same raw-facts shape the model returns."""
    def num(x):
        try:
            return float(str(x).replace(",", "").strip())
        except ValueError:
            return None
    liab = (row.get("liability") or "").strip()
    cap = num(liab)
    ccy = (row.get("ccy") or "").strip().upper()
    law = (row.get("law") or "").strip() or None
    text = " ".join(str(v) for v in row.values() if v)
    hit = INJECTION_RE.search(text)
    return {
        "document_type": TYPE_MAP.get((row.get("type") or "").strip().lower(), "UNKNOWN"),
        "vendor_name": (row.get("vendor") or "").strip() or None,
        "contract_value": num(row.get("amount")),
        "currency": ccy if ccy in ("USD", "EUR", "GBP", "JPY", "CAD", "AUD") else "UNKNOWN",
        "start_date": to_iso(row.get("start")), "renewal_date": to_iso(row.get("renew")),
        "termination_date": None, "auto_renew": None,
        "liability_cap": cap,
        "cap_status": "capped" if cap is not None else ("uncapped" if liab.lower() == "uncapped" else "not_stated"),
        "governing_law": law, "dpa_status": "not_stated",
        "region_hint": region_for(law, None) or "UNKNOWN",
        "injection_detected": bool(hit), "injection_quote": hit.group(0) if hit else None,
        "confidence": 0.85, "notes": row.get("notes"), "reference_id": None,
    }


def _add_rule(item, rule: str, detail: str):
    d = item.decision
    if d.action == "quarantine":
        return
    d.rules.append(rule)
    d.reason = (d.reason + "; " if d.action == "escalate" and d.reason else "") + detail
    d.action = "escalate"


def reconcile(docs: list, rows: list) -> None:
    """Mutates items in place. docs/rows are run.Item objects (rows may be empty)."""
    live = [d for d in docs if d.decision and d.decision.action != "quarantine"]
    groups: dict[tuple, list] = {}
    for d in live:
        r = d.record
        key = (vnorm(r.get("vendor_name")), d.facts.get("reference_id") or (r.get("document_type"), r.get("start_date")))
        groups.setdefault(key, []).append(d)
    for members in groups.values():
        if len(members) < 2:
            continue
        pairs = [(a, b, conflicts(a.record, b.record)) for i, a in enumerate(members) for b in members[i + 1:]]
        bad = [(a, b, c) for a, b, c in pairs if c]
        if bad:
            detail = "; ".join(f"{a.name} vs {b.name}: {', '.join(c)}" for a, b, c in bad)
            for m in members:
                _add_rule(m, "ESCALATE: duplicate conflict", f"same agreement appears more than once with conflicting values ({detail}); not picking one")
        else:
            primary = members[0]
            for dup in members[1:]:
                dup.merged_into = primary.name
                primary.extra_notes.append(f"consistent duplicate {dup.name} merged")
    # CSV rows: match to documents by normalised vendor (+ compatible type)
    for row in rows:
        f = row.facts
        v = vnorm(f.get("vendor_name"))
        matches = [d for d in live if v and vnorm(d.record.get("vendor_name")) == v
                   and f["document_type"] in ("UNKNOWN", d.record.get("document_type"))]
        if not matches:
            continue
        row.merged_into = ", ".join(m.name for m in matches)
        for m in matches:
            diff = conflicts(m.record, {k: f.get(k) for k, _ in KEY_FIELDS})
            if diff:
                _add_rule(m, "ESCALATE: duplicate conflict",
                          f"legacy_export.csv row {row.source_row} conflicts with {m.name} ({', '.join(diff)})")
                m.extra_notes.append(f"CSV row {row.source_row} conflicts: {', '.join(diff)}")
            else:
                m.extra_notes.append(f"legacy_export.csv row {row.source_row} consistent")
