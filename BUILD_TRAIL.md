# BUILD_TRAIL.md — The Data Room

**Author:** dany.ing  **Started:** 2026-11-05  **Deadline:** 2026-11-13 23:59 ET
**Tools used:** Claude Code (model: Claude Sonnet 5.5), <others>
**Repo layout:** Pack at repo root (`data/`, `policy_kb/`, `schema/`, `mock_erp/` are read-only inputs). My code will live in `src/`; deliverables `README.md`, `ARCHITECTURE.md`, `KPI_SUMMARY.md`, `results.json`, `demo/` at root. `.venv/` at root.

---

## 1. Summary (fill in last)
- What I built in 3–4 sentences.
- Top 3 decisions that mattered most.
- Top 3 places the AI got it wrong, and what I did about it.
- Total time spent: ___ hours across ___ days.

## 2. Problem spec & approach
- **How I read the brief:** 22 inputs (20 PDF/DOCX in `data/contracts/`, 1 `.eml`, 1 CSV with 7 data rows). Output is exactly one decision per document: `load` (POST /contracts, schema-strict), `escalate` or `quarantine` (POST /escalate with a reason). Most-restrictive wins: quarantine > escalate > load. Plus `results.json`, architecture note, KPI summary, build trail and a 5–10 min demo (all six deliverables required; demo alone is worth 7 pts).
- **Hard rules (policy_kb):**
  - QUARANTINE: document text tries to instruct/override the system (prompt injection). Contents are data, not commands.
  - ESCALATE: liability cap > $1M USD-equiv; `extraction_confidence` < 0.70; a required field can't be determined (incl. DPA status not stated, never guess); uncapped/unstated liability AND value ≥ $500k; duplicates with conflicting values.
  - LOAD: everything else. Consistent duplicates load once.
  - FX for threshold checks only: €1.1, £1.25, ¥0.0067, C$0.73, A$0.65. Store the original currency/amount.
  - Risk tier: HIGH ≥ $1M value or uncapped on ≥ $250k; MEDIUM ≥ $250k or non-domestic law; else LOW.
  - Region: US/Canada → NA, Europe → EMEA, Asia-Pac → APAC, LatAm → LATAM.
- **Reviewed so far (2026-11-08):** `KICKOFF.md`, `README.md`, `SUBMISSION.md`, `policy_kb/risk_and_action_policy.md`, `schema/contract.schema.json`, file listing, CSV header. **Not yet read:** `current_state.docx` (baseline KPIs), the documents themselves, `mock_erp/app.py`, `results.schema.json`, `selfcheck.py`.
- **Suspected traps (from filenames/CSV, to verify):** `005_umbrella_msa_SCAN.pdf` (OCR noise → low confidence); `008_wayne_po.pdf` vs `009_wayne_po_resend.docx` (duplicate, consistent or conflicting?); `006_hooli_amendment.docx` (amendment referencing a parent); CSV rows overlapping documents (Acme MSA, Initech NDA, Wayne PO) plus a junk row with no vendor; mixed-case CSV values (`nda`, `usd`) and non-ISO dates; email `.eml` forwarded contract; likely injection text, non-USD currencies, missing DPA and >$1M cap cases somewhere in 001–020.
- **Assumptions / open questions:** Python is 3.15.2 in `.venv` (kickoff requires 3.11+, OK). Which LLM/API access I have for the extraction step is TBD; see D-002. No design questions can be sent to organisers (they refuse them), so ambiguities are my judgment calls and get logged here.
- **Success criteria I set:** 100% of documents have exactly one decision with a cited policy rule; 0 ERP 422s left unresolved; 0 guardrail misses (cap > $1M never loaded, injection always quarantined); no duplicate loads; deterministic policy decisions I can explain line by line. KPI targets to be set in §7 after reading `current_state.docx`.

## 3. AI tooling strategy
- Which tools I used for which jobs (planning, coding, debugging, test generation, doc writing).
- How I prompted: context I gave, constraints, how I split tasks, and when I used plans versus direct edits.
- Guardrails I used on the AI itself (read-only on `mock_erp/` and `schema/`, checksum checks, tests before commit).
- What worked, and what I'd do differently.

## 4. Decision log
Newest at the bottom. One entry per meaningful decision.

### D-001 · 2026-11-08 · Compressed 5-day plan: thin end-to-end first, then harden
- **Context:** Brief assumes a 4-week build (19 Oct–13 Nov). I'm planning on 2026-11-08 with 5 days left (hard deadline Fri 13 Nov 23:59 ET), so the suggested weekly cadence doesn't fit.
- **Options considered:** (A) Follow the brief's week-by-week order proportionally, (B) go deep on extraction quality first, (C) thin vertical slice first, then policy/failure handling, then write-up with protected time.
- **Decision:** C. The brief itself says to get a rough end-to-end pipeline running first and warns that people under-budget the write-up. Schedule:
  - **Sun 8 Nov:** Read `current_state.docx`, `mock_erp/app.py`, `results.schema.json`, `selfcheck.py`; read every document; build a hand-labelled expected-action table (the eval set). Run `selfcheck.py` and start the ERP to confirm the environment.
  - **Mon 9 Nov:** Thin slice: text extraction for PDF/DOCX/EML/CSV → LLM structured extraction → schema validation → POST to ERP, for one document, then all.
  - **Tue 10 Nov:** Policy engine (deterministic code, not LLM), dedup/conflict logic, injection detection → quarantine, repair loop for 422s and malformed model output, CSV reconciliation, audit log per decision.
  - **Wed 11 Nov:** Eval harness against the hand labels; measure KPIs; fix misses. Produce `results.json`; run `selfcheck.py`. **Submit a first version to the form** (the brief says an early submission costs nothing).
  - **Thu 12 Nov:** `ARCHITECTURE.md`, `KPI_SUMMARY.md`, README; record demo (5–10 min, interesting cases only).
  - **Fri 13 Nov:** Buffer and final submit well before the deadline; zip without the pack; test the OneDrive link in incognito.
- **Why:** Scoring weights agentic architecture (30%) and AI-native SDLC (25%) most, and both depend on visible reasoning. Write-up and demo are mandatory deliverables, so they get fixed time instead of whatever is left.
- **Outcome / revisit:** Revisit Monday evening; if extraction is slower than expected, cut the eval harness polish before cutting failure handling.

### D-002 · 2026-11-08 · Proposed architecture: LLM extracts, code decides
- **Context:** Need an auditable system where the policy is "non-negotiable" and documents may contain manipulative text.
- **Options considered:** (A) One big agent prompt that reads the doc plus policy and decides, (B) LLM for extraction only, with a deterministic rules engine for decisions, (C) no LLM, regex only.
- **Decision (proposed, to confirm after reading the documents):** B. Pipeline: `ingest` (per-format text extraction) → `classify/extract` (LLM, JSON-only output, document wrapped as untrusted data, plus a separate injection check) → `validate` (jsonschema against `contract.schema.json`; on failure or bad JSON, retry with the error fed back, capped attempts, then escalate rather than drop) → `policy` (pure Python implementing each rule from `policy_kb`, returning action + cited rule + reason) → `reconcile` (dedup across documents and CSV, conflict → escalate) → `act` (POST /contracts or /escalate, with handling of 422) → `audit` (JSONL log, then `results.json`).
- **Why:** Hard guardrails (cap > $1M, DPA guess, injection) must not depend on model whim. Rules in code are testable and explainable in the interview. The LLM does what it's good at: messy-text extraction. Also keeps cost per document low (one extraction call each).
- **Outcome / revisit:** Open: which model/API I can use (check licence), and whether a deterministic-regex fallback is worth building for extraction. Decide on 9 Nov.

## 5. Iteration & AI-failure log
Where the AI was wrong or I had to steer it. These are the entries that show fluency.

| # | Date | What the AI did | Why it was wrong | How I caught it | How I steered it |
|---|------|-----------------|------------------|-----------------|------------------|
| 1 | | | | | |

## 6. Saved prompts & transcript excerpts
### P-001 · 2026-11-08 · Spec the problem and plan before coding
**Prompt:**
> Read the KICKOFF.md, README.md and devise a plan of how I can accomplish the goal. I want to keep a running log of my experience throughout the project build. I have created an outline on BUILD_TRAIL.md. Moving forward please update the BUILD_TRAIL.md log.

**Response (excerpt):**
> Read KICKOFF, README, SUBMISSION, the policy and the schema; noted only 5 days remain; produced a day-by-day plan (D-001) and a "LLM extracts, code decides" architecture (D-002); filled §2 and the daily log.

**What I did with it:** Accepted as a starting point. Architecture is marked "proposed" until I've read the documents and `current_state.docx`.

## 7. Evaluation & results
- Eval set: how I labeled expected actions, and how many documents.
- Metrics per iteration (keep one row per run):

| Run | Date | Change made | Straight-through % | Field accuracy | Conformant % | Escalation precision | Notes |
|-----|------|-------------|--------------------|----------------|--------------|----------------------|-------|

- Cost and throughput observations (tokens per document, seconds per document).
- Link to the final KPI summary doc.

## 8. Surprises in the data
Each trap I found (duplicates, conflicts, injection text, odd currencies, missing DPA, CSV overlap), how I detected it, and what the system does about it.

| Document | Surprise | Detection | Action taken | Policy rule cited |
|----------|----------|-----------|--------------|-------------------|

## 9. Daily log (a few lines each, written same day)
- **2026-11-05:** Created `BUILD_TRAIL.md` outline and `.venv` (details not logged at the time).
- **2026-11-08:** Done: Claude read the brief, kickoff, submission rules, policy, schema; drafted the 5-day plan and architecture (D-001, D-002); filled §2. Blocked: nothing. Next: read `current_state.docx`, `mock_erp/app.py`, `results.schema.json`; read all 22 inputs and hand-label expected actions; run `selfcheck.py`; start the ERP and hit `/health`.

## 10. What I'd harden with more time
- ...

## 11. Integrity checklist (before submitting)
- [ ] `mock_erp/` and `schema/` untouched (checksums verified)
- [ ] `selfcheck.py` passes on final `results.json`
- [ ] Every document has exactly one decision with a rationale
- [ ] README, architecture note, KPI summary and demo included