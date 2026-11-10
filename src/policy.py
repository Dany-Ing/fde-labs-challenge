"""Deterministic policy engine implementing policy_kb/risk_and_action_policy.md.

Pure functions: facts (raw, from the model) -> contract record + Decision.
The model never chooses the action, tier or region. Most restrictive wins:
quarantine > escalate > load.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

FX = {"USD": 1.0, "EUR": 1.1, "GBP": 1.25, "JPY": 0.0067, "CAD": 0.73, "AUD": 0.65}
CAP_LIMIT, UNBOUNDED_VALUE, MIN_CONF = 1_000_000, 500_000, 0.70

# Backstop for the model's injection flag (either one triggers quarantine).
INJECTION_RE = re.compile(
    r"ignore (all )?(prior|previous|above) instructions|disregard .{0,40}(cap|polic|rule|instruction)|"
    r"(AI|automated) (agent|system)[^.]{0,80}(shall|must|should|ignore|do not)|"
    r"do not (route|escalate|flag)|without (escalation|human review)|"
    r"set (the )?(risk_tier|extraction_confidence|confidence)|pre-?(approved|cleared)|"
    r"(record|set) an extraction confidence|notwithstanding any intake policy", re.I)

US_MARK = re.compile(r"\b(USA|U\.S\.|United States|Alabama|Alaska|Arizona|California|Colorado|Connecticut|Delaware|"
                     r"Florida|Georgia|Illinois|Massachusetts|Michigan|Nevada|New Jersey|New York|Ohio|Texas|"
                     r"Virginia|Washington|TX|NY|NJ|CA)\b")
REGION_MARKS = [
    ("NA", re.compile(r"Canada|Ontario|Quebec|British Columbia|Alberta", re.I)),
    ("LATAM", re.compile(r"Brazil|Brasil|Mexico|Argentina|Chile|Colombia|Peru|Latin", re.I)),
    ("APAC", re.compile(r"Japan|Tokyo|China|Singapore|Korea|India|Australia|Hong Kong|Asia", re.I)),
    ("EMEA", re.compile(r"England|Wales|United Kingdom|UK\b|Switzerland|Germany|Munich|France|Spain|Italy|"
                        r"Netherlands|Europe|Ireland|Zürich|Zurich|Middle East|Africa", re.I)),
]


DPA_MENTION_RE = re.compile(r"Data Processing Agreement|\bDPA\b|Datenverarbeitung", re.I)
DPA_BY_REF_RE = re.compile(r"\b(unchanged|original|as before|previous|prior)\b", re.I)
DPA_NEG_RE = re.compile(r"\b(no|not|without|unsigned|pending|absent|missing|nicht|kein|keine|ohne)\b", re.I)
DPA_POS_RE = re.compile(r"\b(signed|executed|on file|in place|unterzeichnet|hinterlegt)\b", re.I)


def dpa_signal(text: str) -> str | None:
    """Deterministic read of the DPA sentence(s). 'signed' / 'by_reference' when the text is
    clear, else None (leave it to the model, and anything not 'signed' escalates anyway).
    Every sentence mentioning a DPA must agree; any negation or conflict returns None."""
    found = set()
    for m in DPA_MENTION_RE.finditer(text or ""):
        before = re.split(r"[.\n]", text[:m.start()])[-1]
        after = re.split(r"\.\s|\.$", text[m.end():m.end() + 160])[0]
        seg = f"{before} {m.group(0)} {after}"
        if DPA_NEG_RE.search(seg):
            return None
        if not DPA_POS_RE.search(seg):
            continue
        found.add("by_reference" if DPA_BY_REF_RE.search(seg) else "signed")
    return found.pop() if len(found) == 1 else None


REF_RE = [re.compile(r"(?:PO|Purchase Order|Order)\s*(?:Number|No\.?|#)?\s*[:#]?\s*([A-Z0-9]{2,}(?:-[A-Z0-9]+)+)"),
          re.compile(r"\b((?:SOW|PO)-[A-Z0-9]+(?:-[A-Z0-9]+)*)\b")]


def apply_text_guards(facts: dict, text: str) -> dict:
    """Deterministic backstops for guardrail fields the model can drift on between runs."""
    sig = dpa_signal(text)
    if sig and facts.get("dpa_status") != sig:
        facts["notes"] = ((facts.get("notes") or "") + f" | guard: dpa_status {facts.get('dpa_status')} -> {sig} from the DPA sentence").strip(" |")
        facts["dpa_status"] = sig
    if not facts.get("reference_id"):
        for rx in REF_RE:
            m = rx.search(text or "")
            if m:
                facts["reference_id"] = m.group(1)
                break
    if facts.get("reference_id"):
        facts["reference_id"] = facts["reference_id"].strip().upper()
    return facts


@dataclass
class Decision:
    action: str                       # load | escalate | quarantine
    rules: list[str] = field(default_factory=list)
    reason: str = ""


def usd(amount, ccy):
    return None if amount is None else amount * FX.get(ccy, 0) if ccy in FX else None


def region_for(law: str | None, hint: str | None) -> str | None:
    if law:
        for region, rx in REGION_MARKS:
            if rx.search(law):
                return region
        if US_MARK.search(law):
            return "NA"
    return hint if hint in ("NA", "EMEA", "APAC", "LATAM") else None


def is_domestic(law: str | None) -> bool:
    return bool(law and US_MARK.search(law) and not REGION_MARKS[0][1].search(law))


def risk_tier(value_usd, cap_known: bool, law) -> str:
    v = value_usd or 0
    if v >= 1_000_000 or (not cap_known and v >= 250_000):
        return "HIGH"
    if v >= 250_000 or not is_domestic(law):
        return "MEDIUM"
    return "LOW"


def build_record(f: dict, filename: str, extra_notes: str = "") -> dict:
    """Map raw facts to a contract.schema.json record (only keys with values)."""
    law = f.get("governing_law")
    ccy = f.get("currency") or "UNKNOWN"
    val = f.get("contract_value")
    cap = f.get("liability_cap") if f.get("cap_status") == "capped" else None
    rec = {
        "source_document": filename,
        "document_type": f.get("document_type") or "UNKNOWN",
        "vendor_name": f.get("vendor_name"),
        "contract_value": val,
        "currency": ccy,
        "start_date": f.get("start_date"),
        "renewal_date": f.get("renewal_date"),
        "termination_date": f.get("termination_date"),
        "auto_renew": f.get("auto_renew"),
        "liability_cap": cap,
        "governing_law": law,
        "extraction_confidence": f.get("confidence"),
        "data_residency_region": region_for(law, f.get("region_hint")),
        "dpa_signed": True if f.get("dpa_status") == "signed" else None,
    }
    vu = usd(val, ccy)
    rec["risk_tier"] = risk_tier(vu, cap is not None, law)
    note = f"cap_status={f.get('cap_status')}; dpa_status={f.get('dpa_status')}"
    if val is not None and ccy != "USD" and vu is not None:
        note += f"; ~USD {vu:,.0f} for threshold checks"
    rec["notes"] = "; ".join(x for x in (note, extra_notes) if x)
    return {k: v for k, v in rec.items() if v is not None or k in ("contract_value",)}


def decide(f: dict, record: dict, raw_text: str = "") -> Decision:
    # 1. QUARANTINE
    hit = INJECTION_RE.search(raw_text or "")
    if f.get("injection_detected") or hit:
        quote = f.get("injection_quote") or (hit.group(0) if hit else "")
        return Decision("quarantine", ["QUARANTINE: content tries to manipulate the processing system"],
                        f"Document contains instructions aimed at the processing system "
                        f"(model_flag={bool(f.get('injection_detected'))}, regex_hit={bool(hit)}): \"{quote}\". "
                        "Treated as data, not commands; nothing loaded.")
    rules, why = [], []
    ccy = record.get("currency", "UNKNOWN")
    cap_usd = usd(record.get("liability_cap"), ccy)
    val_usd = usd(record.get("contract_value"), ccy)
    # 2. ESCALATE
    if cap_usd is not None and cap_usd > CAP_LIMIT:
        rules.append("ESCALATE: liability cap > $1M (dual approval)")
        why.append(f"liability cap {record['liability_cap']:,.0f} {ccy} ~ ${cap_usd:,.0f} exceeds $1,000,000")
    conf = record.get("extraction_confidence")
    if conf is None or conf < MIN_CONF:
        rules.append("ESCALATE: low confidence")
        why.append(f"extraction_confidence {conf} < {MIN_CONF}")
    if "atlas industrial" in (record.get("vendor_name") or "").lower():
        record = {**record, "vendor_name": None}  # extracted the client, not a counterparty
    missing = [k for k in ("vendor_name", "start_date", "governing_law", "data_residency_region") if not record.get(k)]
    if record.get("dpa_signed") is None:
        missing.append(f"dpa_signed (document status: {f.get('dpa_status')}, not inferred)")
    if (record.get("contract_value") or 0) > 0 and ccy == "UNKNOWN":
        missing.append("currency")
    if missing:
        rules.append("ESCALATE: required field cannot be determined")
        why.append("missing/undeterminable: " + ", ".join(missing))
    if record.get("liability_cap") is None and val_usd is not None and val_usd >= UNBOUNDED_VALUE:
        rules.append("ESCALATE: unbounded material risk (uncapped/not stated, value >= $500k)")
        why.append(f"no liability cap with value ~ ${val_usd:,.0f}")
    if rules:
        return Decision("escalate", rules, "; ".join(why))
    return Decision("load", ["LOAD: no restrictive rule applies"],
                    f"Passed all policy checks; tier {record.get('risk_tier')}, region {record.get('data_residency_region')}.")
