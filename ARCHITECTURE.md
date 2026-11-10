# Architecture note: "LLM extracts, code decides"

**Goal.** For every document, take exactly one action (load / escalate / quarantine) through the
mock ERP, conformant to the schema, correct under `policy_kb`, with a logged rationale.

```
 data/*.pdf .docx .eml          legacy_export.csv
        |                              |
   ingest (per format)           csv_to_facts (normalise)
        |                              |
   extract  -- claude -p (Haiku), forced JSON schema, tools off, doc wrapped as untrusted data
        |       returns RAW FACTS only: dpa_status, cap_status, injection_detected, dates, amounts...
   text guards -- deterministic DPA-sentence rule, reference-ID regex
        |                              |
   policy: build contract record + decide (pure Python; quarantine > escalate > load)
        \______________ reconcile (duplicates, conflicts, CSV matching) _____________/
                                        |
   act: validate locally -> POST /contracts  (422? re-extract with the error list, max 2, else escalate)
        or POST /escalate (kind = escalate | quarantine)
                                        |
                       audit.jsonl + results.json  ->  evaluate.py / stability.py
```

## Key design decisions
1. **The model never decides.** It reports what the document says; `policy.py` converts that into the
   record, the USD-equivalent thresholds, the risk tier, the region and the action. The hard
   guardrails (cap over $1M, no guessing the DPA, injection) therefore cannot be argued away by
   document text. A regex scan for injection phrases runs beside the model's flag; either one
   quarantines. The CSV notes are scanned too.
2. **Code owns fields whose meaning is a plain text rule.** A 4-run stability check showed the same
   model answering the same DPA sentence three different ways. `dpa_signal` now reads the DPA
   sentence and overrides the model when it is clear (signed, or only inherited by reference);
   the model is the fallback. Reference IDs (PO / SOW numbers) fall back to a regex the same way.
3. **Decide everything, then act.** All documents are analysed and reconciled before anything is
   POSTed, so a load cannot go out before its conflicting twin is seen. Same agreement with
   consistent values loads once; with conflicting key values every copy escalates and the reason
   names the fields (Wayne WE-5567: $40,000 vs $44,000).
4. **Failures degrade to escalation, never to loss.** Extraction errors and ERP 422s feed the error
   back into a bounded retry (2); after that, or on any unexpected exception, the document is
   escalated with the reason. One bad document cannot stop the batch.
5. **Strict DPA reading.** `dpa_signed` is only true when the document itself says a DPA is signed,
   executed or on file. "Not required" (Initech), silence (Gekko, Wayne, Stark) and "unchanged from
   the original MSA" (Hooli, parent not in the data room) all escalate rather than guess.
6. **Auditable and measurable by construction.** Every decision logs its cited rules, reason, extracted
   facts, ERP attempts, cost and time. `evaluate.py` re-checks the hard guardrails on the output
   artifact itself, independent of the labels. Claude Code meters the cost per call.

## Measured (21 documents + 7 CSV rows; against my own labels, see KPI_SUMMARY.md)
28/28 decisions match, 10 of 21 documents auto-loaded, 0 guardrail breaches, 10/10 loads accepted
on first POST, 5.8 s and $0.0005 per document, no decision changes across 4 repeat runs after the
DPA fix (2 of 4 runs flipped one document before it).

## Known limits and judgment calls
- Labels, prompts and fixes are by the same author, so accuracy numbers are a regression baseline.
- Non-US governing law counts as "non-domestic" for the MEDIUM tier (so Canada and Japan are MEDIUM).
- A PO's order date is its start date; a SOW's completion date is its termination date.
- CSV rows that match a document are merged into it (listed under `merged_duplicates`); CSV-only rows
  escalate, since the CSV has no DPA field.
- Model self-reported confidence is only a coarse signal (it varies by 0.05-0.10 between runs).

## What I would harden with more time
- Parallel workers and an API-key backend with prompt caching (throughput is serial today).
- A second, independent injection classifier and adversarial test documents; a real OCR path for
  genuine scans (the pack's scan already has a text layer).
- Look up parent contracts for amendments; a persistent store and review queue for escalations
  with reviewer feedback flowing into the golden set.
- Independent labels for the eval set, calibrated confidence, drift alerts and per-rule volume
  monitoring in production (see the measurement plan in KPI_SUMMARY.md).
