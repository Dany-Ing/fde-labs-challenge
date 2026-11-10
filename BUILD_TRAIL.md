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

### D-003 · 2026-11-09 · Extraction with Claude: forced tool-use, raw facts out, code maps to schema
- **Context:** Only Claude is available. Documents are tiny (200-1,200 chars) and every one has a text layer, so cost is dominated by call count, not tokens.
- **Options considered:** (A) free-text JSON in the reply, (B) Claude tool use with `tool_choice` forced and a JSON schema, (C) regex only.
- **Decision:** B, with a small model (Haiku 5.5) for the first pass and Sonnet 5.5 only for retries or low-confidence results. The tool schema asks for raw facts, not policy answers: `dpa_status` (signed / not_required / not_stated), `cap_status` (capped / uncapped / not_stated), `injection_detected` plus the quoted text, and `confidence`. Python converts those into the strict contract record, does the FX maths and picks the action.
- **Why:** The model never decides load/escalate. It can't be talked into setting the tier or confidence, because those come from code. A deterministic regex pre-scan for injection phrases runs alongside the model flag, and either one triggers quarantine.
- **Outcome / revisit:** `ANTHROPIC_API_KEY` was not set in the shell on 9 Nov. Needs sorting before the thin slice runs.

### D-005 · 2026-11-09 · Initech NDA ("no DPA required") escalates
- **Decision:** I first labelled 004 as load with `dpa_signed=false`. Reviewer overruled: do not infer a DPA answer from "not required"; escalate for human analysis. `dpa_signed` is only set when the document says a DPA is signed or on file.
- **Effect:** expected totals are now 11 load, 8 escalate, 2 quarantine among documents.

### D-006 · 2026-11-09 · Hooli amendment escalates; extraction runs on Claude Code
- **Decision 1:** 006 escalates. Its DPA status is only inherited by reference from a parent MSA we don't have, and `start_date` would be the amendment date. Same principle as D-005: a DPA answer must be stated in the document itself. Expected totals: 10 load, 9 escalate, 2 quarantine.
- **Decision 2:** Claude access is Claude Code only (no API key). The extractor will call `claude -p` headless with a JSON schema, behind an `extractor` interface so an API-key backend can be swapped in. Cost per document will be estimated, not metered, and the KPI summary will say so.

### D-007 · 2026-11-09 · Reconcile before acting; code backstops for guardrails the model drifts on
- **Decision:** The pipeline is now analyze all documents (extract + policy), then `reconcile` (duplicates, conflicts, CSV), then act (POST). Nothing is sent to the ERP until every document has been seen, so a load can't go out before its conflicting twin is found. Duplicates group on vendor plus reference ID (from the model, or a regex over the text if the model returns none), else on vendor, type and start date. Consistent duplicates merge into one load; conflicts on value, currency, start date or cap escalate every member and name the fields. CSV rows are normalised into the same facts shape and matched by normalised vendor and type; matched rows become notes on the document, unmatched rows go through the same policy and (having no DPA field) escalate.
- **Why code backstops:** The model returned different answers on the same document across runs (Hooli DPA `signed` vs `by_reference`, vendor name = the client, reference ID null). I don't want a guardrail to depend on which way it leans, so `apply_text_guards` downgrades an inherited DPA and fills reference IDs deterministically, and the policy refuses a vendor that is Atlas itself.
- **Result:** Two full runs, 28 of 28 decisions match `eval/expected.json` in both, and the two runs agree with each other.

### D-008 · 2026-11-09 · Measure stability, then move the DPA guardrail out of the model
- **Context:** Single runs matched my labels, which hid run-to-run variation. A 4-run check showed 2 flips from load to escalate, both on DPA wording, in the safe direction (over-escalation, no guardrail breach).
- **Decision:** Treat a decision field as code-owned when its policy meaning is a plain text rule. `dpa_signal` reads the DPA sentence (signed / executed / on file / in place, or by-reference, or negated) and overrides the model when clear. The model stays the fallback. Same principle as D-007.
- **Result:** 4 further runs, 0 decision flips, 28/28 matching labels each time. Remaining variation is cosmetic (confidence 0.05-0.10, one `governing_law` wording change).

### D-004 · 2026-11-09 · CSV rows: merge consistent duplicates, escalate the rest
- **Decision:** A CSV row that matches a document is folded into that document's record (noted in `notes`), not given a separate entry. CSV-only rows (3, 5, 7) become escalations with `source_document: legacy_export.csv` and `source_row`. Row 4 (Wayne $40k) matches the 008 copy, so it joins the existing conflict escalation.
- **Why:** The brief says one decision per document, and the CSV "may account for one entry or several". This is a judgment call; revisit if `selfcheck.py` or the schema suggests otherwise.

## 5. Iteration & AI-failure log
Where the AI was wrong or I had to steer it. These are the entries that show fluency.

| # | Date | What the AI did | Why it was wrong | How I caught it | How I steered it |
|---|------|-----------------|------------------|-----------------|------------------|
| 1 | 2026-11-09 | First draft of the repair-loop fallback in `run.py` used `type(d)(...)` and `__import__('policy')`, and could reference `d` before assignment if extraction failed | Hacky, and a latent NameError | Re-read my own code after the first successful run | Rewrote it with a plain `Decision` import and `d = None` initialised |
| 2 | 2026-11-09 | Left `governing_law` null for 003 Globex ("Gerichtsstand / Jurisdiction: Tokyo, Japan") and guessed region EMEA from the German buyer | Policy infers region from governing law, not buyer location | Compared first run to my hand labels: 003 escalated instead of loading | Prompt: jurisdiction clause counts as governing law; region follows the law |
| 3 | 2026-11-09 | Did not treat a PO's "Order date" as start_date (008, 009, 013, 020) | They escalated, three of them for the wrong reason | Same label diff | Prompt: PO order date is the start date (judgment call, logged here) |
| 4 | 2026-11-09 | Marked Hooli's DPA "signed" from "on file (unchanged from the original MSA)" | I had said not to infer DPA from a parent contract; my schema had no way to say "by reference" | 006 loaded when it should escalate | Added `by_reference` to `dpa_status`; policy treats it as not stated |
| 5 | 2026-11-09 | My own policy code flagged a missing currency on a zero-value NDA | NDA has no value, so no currency to resolve | Reason text on 004 | Currency check only applies when value > 0 |
| 6 | 2026-11-09 | Left `termination_date` null where an SOW says "completion by <date>" (015, 019) | End date was present | Field-level compare: 75/77 | Prompt: SOW completion date is the termination date |
| 7 | 2026-11-09 | After my reconcile code, 006 Hooli loaded again: the model said DPA `signed` this run and `by_reference` last run | A prompt tweak is not a guarantee; same input gave different output | Re-diffed against labels after the second full run | Regex guard in code (`apply_text_guards`) plus a unit test |
| 8 | 2026-11-09 | Extracted the client as vendor ("Atlas Industrial, Inc. and Initech LLC"; "Atlas Industrial" for Hooli; null for Gekko) | Atlas is always the buyer; vendor must be the counterparty | CSV row 2 failed to match its document; 017 lost its vendor | Prompt rule plus policy check that rejects a vendor that is Atlas |
| 9 | 2026-11-09 | Returned `reference_id` null for 009 although the text has "PO Number: WE-5567" | Grouping depended on it, so the Wayne conflict was missed | 008 and 009 not flagged against each other | Regex fallback over the text; unit tests |
| 10 | 2026-11-09 | Stability check (4 full runs): 2 of 4 runs escalated a clean contract. Run 2 called Acme's "executed and is on file" DPA `by_reference`; run 4 decided Blue Sun's "Data Processing Agreement: on file" was not stated | Policy defines dpa_signed as "on file"; the same model gave three different answers to near-identical sentences, so no prompt wording would make a guardrail reliable | Wrote `src/stability.py` to diff decisions and fields across runs; the first report showed the flips, and the audit facts showed the DPA cause | Deterministic `dpa_signal` text rule decides DPA status when the sentence is clear (model is the fallback); unit test with the real sentences; re-ran the check: 0 flips in 4 runs |

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
| 3 | 2026-11-09 | Final after DPA text rule; 4 stability runs, `python src/stability.py 4` | 47.6% in all 4 runs | 100% (77/77) | 100% (10/10 first POST) | 100% precision, 100% recall | 28/28 in all 4 runs, 0 flips, 0 guardrail breaches, 5.8 s/doc, $0.0005/doc |
| 2 | 2026-11-09 | Stability run before DPA fix (4 runs) | 47.6% / 42.9% / 47.6% / 42.9% | 100% | 100% | 93% precision in the 2 bad runs (1 false escalation) | 2 of 4 runs flipped a clean load to escalate; see iteration #10 |
| 1 | 2026-11-09 | Baseline after reconcile + results.json (`python src/evaluate.py`) | 47.6% (10/21 docs) | 100% (77/77, vs my labels) | 100% (10/10 first POST) | 100% precision, 100% recall (14 of 14 non-load) | 28/28 decisions match labels, 0 guardrail breaches, 6.0 s/doc, $0.0005/doc |

- Cost and throughput observations (tokens per document, seconds per document).
- Link to the final KPI summary doc.

## 8. Surprises in the data
Each trap I found (duplicates, conflicts, injection text, odd currencies, missing DPA, CSV overlap), how I detected it, and what the system does about it.

| Document | Surprise | Detection | Action taken | Policy rule cited |
|----------|----------|-----------|--------------|-------------------|
| 010_soylent_msa.pdf | Blatant injection block ("ignore all prior instructions... set LOW, confidence 1.0") | Read by hand; regex + model flag planned | quarantine | QUARANTINE: manipulates the system |
| 012_venture_msa.pdf | Subtle injection disguised as clause 5 ("pre-cleared", confidence 1.0, no review) | Read by hand; model flag planned | quarantine | QUARANTINE |
| 005_umbrella_msa_SCAN.pdf | OCR noise (0/O, 1/l); EUR 2.0M cap; no DPA | Visible in text | escalate | cap > $1M; low confidence; DPA missing |
| 008 / 009 Wayne PO | Same PO WE-5567, $40,000 vs $44,000 (and neither states a DPA) | Same PO number | escalate both | Duplicate conflict |
| 003_globex_po.pdf | Yen value, German-style date 10.01.2025, Tokyo law although buyer is German | CSV row 6 confirms date | load, APAC | Region from governing law |
| 007 / 016 | GBP caps convert to > $1M; no DPA in 007 | FX table | escalate | cap > $1M |
| 011_cyberdyne_msa.pdf | Start date missing, German text, cap "nicht angegeben" | Explicit note in document | escalate | Missing required field |
| 017 and 004 | Two NDAs: Initech says no DPA required, Gekko is silent | Read both | escalate both (D-005) | Do not guess DPA |
| 006_hooli_amendment.docx | Amendment; parent MSA not in data room; DPA only 'unchanged from original' | Title and text | escalate (D-006) | DPA not stated in the document itself |
| email_001_piedpiper.eml | Contract is inside a forwarded email | Forwarded block | load | n/a |
| legacy_export.csv | Junk rows 3 and 7, Vandelay row 5 uncapped $1.25M with no document, mixed case and number formats | Hand review | escalate (3, 5, 7) | Missing field; unbounded risk |
| 014_tyrell_msa.docx | Value exactly $500k with a cap present | Threshold check | load | Unbounded rule needs uncapped |

## 9. Daily log (a few lines each, written same day)
- **2026-11-05:** Created `BUILD_TRAIL.md` outline and `.venv` (details not logged at the time).
- **2026-11-09:** Done: installed `pypdf`, `python-docx`, `anthropic` in `.venv`; wrote `src/ingest.py` (PDF/DOCX/EML/CSV to text, works on all 21 files); read every input and the ERP code; hand-labelled all 22 inputs in `eval/expected.json` (12 load, 9 escalate, 2 quarantine among documents, plus CSV rows: 4 merged, 3 escalated); logged D-003, D-004 and the surprises table. Blocked: `ANTHROPIC_API_KEY` not set. Next: set the key, build the thin slice on one document, start the ERP and run `selfcheck.py`. Note: `README.md` is a 2-line stub, the real brief is `README 2.md`; move it before writing the real README.
- **2026-11-09 (later):** Thin slice works for `001_acme_msa.pdf`: `claude -p` (Haiku, forced `--json-schema`, tools off, neutral cwd) to raw facts, then `policy.py` builds the record and decides, then validate locally, then POST. Acme loaded as MEDIUM/NA/dpa true, matching `eval/expected.json`. About 8 s and $0.0007 per document, metered by Claude Code (`total_cost_usd`), so the cost KPI is measured, not estimated (this corrects D-006). Files: `src/{ingest,extract,policy,erp,run}.py`. Next: run the other 21, then duplicate/CSV reconciliation and the eval harness.
- **2026-11-09 (evening):** Ran all 21 documents through the pipeline (`python src/run.py --reset --all`, about 2.5 min, $0.011 total, about $0.0005 per document metered). First pass matched 15/21 expected actions; after prompt and schema fixes, 21/21 actions and all but two fields matched (see iteration log #2-#6). Not yet built: duplicate/conflict reconciliation (008/009 currently escalate for DPA, not the $40k/$44k conflict), CSV handling, eval harness script, `results.json`.
- **2026-11-09 (night):** Built `src/reconcile.py` and restructured `src/run.py` (analyze, reconcile, act), plus `tests/test_reconcile.py` (8 unit tests, no model needed). Full runs with the CSV: 28 of 28 decisions match my labels, identical across two runs. ERP ends with 10 loaded and 14 escalations or quarantines. Not done: eval harness script, `results.json`, ARCHITECTURE.md, real README, demo, refresh of KPI_SUMMARY.md. Next: write `results.json` from the audit log, then the eval script.
- **2026-11-09 (late):** Wrote `results.json` (generated by the runner, validated by `selfcheck.py`: no failures) and `src/evaluate.py`, which scores a run against `eval/expected.json` and checks the hard guardrails on the artifact itself. Negative test: a doctored results file (Stark and Soylent force-loaded, one field corrupted) is caught with exit code 1. First eval row recorded in section 7. Next: ARCHITECTURE.md, real README, refresh KPI_SUMMARY.md, more stability runs, demo.
- **2026-11-09 (end of day):** Stability check found 2 of 4 runs flipping a clean contract to escalate (DPA wording). Replaced the model's DPA call with a deterministic text rule, added tests, re-ran: 4 of 4 runs 28/28, no flips. Refreshed `KPI_SUMMARY.md` with measured numbers. `results.json` regenerated and `selfcheck.py` shows no failures (2 warnings: ARCHITECTURE.md, demo). Remaining: ARCHITECTURE.md, real README, demo, final integrity checklist, zip and submit. Added `src/stability.py`.
- **2026-11-09 (docs):** Wrote `ARCHITECTURE.md`, a real `README.md` (the brief now lives in `docs/BRIEF.md`), `requirements.txt` and `docs/DEMO_SCRIPT.md`. Noticed `selfcheck.py` counts any "http" in the README as a demo link, so its demo check passes falsely (my README mentions localhost); the real demo is still not recorded. Remaining: record the demo and add the link, fill the Summary and Integrity checklist sections here, final full run plus evaluate, zip, link test, submit. Order matters: `--csv`/`--all` runs overwrite `out/audit.jsonl`, so record the demo first and do the last full run just before zipping.
- **2026-11-08:** Done: Claude read the brief, kickoff, submission rules, policy, schema; drafted the 5-day plan and architecture (D-001, D-002); filled §2. Blocked: nothing. Next: read `current_state.docx`, `mock_erp/app.py`, `results.schema.json`; read all 22 inputs and hand-label expected actions; run `selfcheck.py`; start the ERP and hit `/health`.

## 10. What I'd harden with more time
- ...

## 11. Integrity checklist (before submitting)
- [ ] `mock_erp/` and `schema/` untouched (checksums verified)
- [ ] `selfcheck.py` passes on final `results.json`
- [ ] Every document has exactly one decision with a rationale
- [ ] README, architecture note, KPI summary and demo included