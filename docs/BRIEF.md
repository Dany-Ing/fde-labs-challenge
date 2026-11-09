# FDE Labs Challenge — "The Data Room"

> **New here? Read `KICKOFF.md` first** — dates, rules, environment setup and FAQ, in five minutes. Then come back to this page for the actual challenge. `SUBMISSION.md` has what to submit and how.
>
> **Deadline: Friday 13 November 2026, 23:59 US Eastern.**

Welcome. You have **4 weeks** — as a side project, fitted around your normal work — to reinvent a real business process as a working agentic system. Use any AI tooling you like (Claude, Copilot, etc.) — we expect you to. This is as much about *how well you build with AI* as it is about *what you build* — and about proving the business outcome, not just shipping code.

---

## The situation — how Atlas does this today

Our client **Atlas Industrial** acquired a competitor and inherited a chaotic data room: thousands of vendor contracts, MSAs, SOWs, and purchase orders in every format imaginable — PDFs, Word documents, a legacy CSV export, a forwarded email, and a low-quality scan.

Today, a team of analysts clears it **by hand** — opening each document, hand-keying fields into the ERP, eyeballing risk, and emailing Legal for anything unusual. It's slow, error-prone, expensive, and there's no record of *why* any decision was made. The full as-is process and its **baseline KPIs** are in `current_state.docx` — read it first.

**Your job: reinvent it.** Replace the manual workflow with an agentic system, and prove the improvement against those KPIs.

## Your task

Replace the manual workflow with an **agentic system**. For every document in `data/`, the outcome you must deliver is:

- A decision — exactly one action per document, **`load`**, **`escalate`**, or **`quarantine`** — taken via the mock ERP API, with a **logged rationale** behind every decision (the manual process has none today).
- Records that **conform to `schema/contract.schema.json`** — the ERP API rejects anything that doesn't.
- Actions that are **correct per the rules in `policy_kb/`**, which define when each action applies.

The inputs are messy, the output format is strict, the policy is non-negotiable, and the integration is live. **How** you get from the data room to correct, auditable, schema-conformant actions — the architecture, the steps, the models and tools — is yours to design. It must be runnable for a demo.

## The Outcome & KPI track (this is scored)

Build like a forward-deployed engineer: tie the work to the business. Alongside the agent, deliver:

1. **Current KPIs** — take the baseline in `current_state.docx` as your starting point.
2. **Expected KPIs** — the targets you believe your solution should hit, with rationale.
3. **Measured KPIs** — your agent's *actual* numbers on the provided data: straight-through rate, field accuracy, % conformant loads, escalation precision, throughput, and estimated cost/document.
4. **A production measurement plan** — how Atlas would track these KPIs once this is live.

`current_state.docx` has the baseline table and a target template to fill in.

## What you're given

```
fde-labs-challenge/
├── README.md                     ← this file — the challenge brief
├── KICKOFF.md                    ← dates, rules, environment setup, FAQ (read first)
├── SUBMISSION.md                 ← what to submit, how, and the deadline
├── CHECKSUMS.txt                 ← hashes of the fixed files — verify these
├── selfcheck.py                  ← run this now, and again before you submit
├── current_state.docx            ← the as-is process + baseline KPIs (read first)
├── schema/
│   ├── contract.schema.json      ← the record format your loads MUST match (API enforces it)
│   └── results.schema.json       ← the envelope for your submitted results.json (validate against this)
├── data/
│   ├── contracts/                ← the messy documents (PDF + Word .docx)
│   ├── emails/                   ← forwarded contract email (.eml)
│   └── legacy_export.csv         ← inconsistent spreadsheet dump
├── policy_kb/                    ← risk & approval rules to retrieve against
└── mock_erp/app.py               ← the ERP API (rejects non-conformant payloads)
```

There is **no starter code**. You get the raw data, the schema, the policy KB, and
the ERP API — the architecture is entirely yours. (`selfcheck.py` is the one script in
the pack; it checks your submission is well-formed and doesn't help you build anything.) The documents are a mix of **PDF,
Word (.docx), a forwarded email (.eml), and a CSV**; getting clean text out of each
format is part of the task. Every document carries a text layer, so no OCR tooling is
needed. Use whatever libraries or models your
AI tooling suggests.

## The mock ERP API

Run it locally:

```bash
# from the pack root, with your virtual environment active (see KICKOFF.md §4)
pip install -r mock_erp/requirements.txt
python mock_erp/app.py   # serves on http://localhost:8000
```

Endpoints:
- `POST /contracts` — load a record. **Returns 422 (with a precise list of what's wrong) if your payload doesn't match the schema.** This is intentional: clean structured output is not optional.
- `POST /escalate` — route a record to human review. Body: `{source_document, reason, record?, kind}` where `kind` is `"escalate"` or `"quarantine"`. A non-empty `reason` is required.
- `GET /health` — sanity check (also reports counts).
- `GET /loaded` — list everything you've successfully loaded (useful for your own dedup checks).
- `GET /escalations` — list your escalations/quarantines.
- `POST /reset` — clear in-memory state while developing.

The API enforces the schema on every load — including **ISO-8601 dates** (`2024-03-01`, not `03/01/2024` or `March 1, 2024`) — so a sloppy extraction will simply bounce with a 422. How your system handles a rejected payload or a malformed model response is up to you; dropping or crashing on the record is not acceptable.

> ⚠️ **The mock ERP is the fixed integration — you are not allowed to change *anything* about it.** That means: do **not** edit `mock_erp/app.py` or the schema files (`schema/contract.schema.json`, `schema/results.schema.json`); do **not** add, remove, or wrap endpoints; do **not** change the port, the validation logic, or the responses; do **not** monkey-patch, proxy, subclass, or otherwise intercept the API to make your payloads pass. It is the exact same API the judges run your submission against, and the fixed files are checksum-verified (`CHECKSUMS.txt`) — any mismatch invalidates your conformance / structured-output scores. Treat the whole of `mock_erp/` and `schema/` as read-only; **all** your code lives outside them. (You may call `POST /reset` freely and *read* the schemas, of course — building your own validation around the schema is encouraged; changing the schema is not.)

## Requirements to watch

A few rules in `policy_kb/` and the schema deserve special attention — they're where correctness and judgment really show:

- **Two required fields on every loaded record:** `data_residency_region` (enum NA/EMEA/APAC/LATAM — infer from the governing law / vendor location) and `dpa_signed` (is a Data Processing Agreement on file?). If a document doesn't state its DPA status and you can't determine it, **escalate** — don't guess.
- **Dual-approval guardrail:** any contract with a **liability cap over $1,000,000** (USD-equivalent) must be **escalated**, never auto-loaded, regardless of anything else.
- Anything ambiguous, low-confidence, conflicting, or manipulative is escalated or quarantined per the policy — never force-loaded.

These are part of the brief from day one — there is no mid-project requirement change.

## What to submit

1. **Your repo** (link or zip) — code + a real README explaining how to run it.
2. **A short demo** — run it end-to-end on the provided data; show the interesting cases.
3. **A one-page architecture note** — how it works, the key design decisions, and what you'd harden with more time.
4. **Your KPI summary** — the filled-in target template from `current_state.docx` (baseline → expected → measured) plus your production measurement plan.
5. **Your build trail** (`BUILD_TRAIL.md`) — *show your working.* We care as much about **how** you built this with AI as about the result. Capture the trail: how you specced the problem, how you drove the tooling (your prompting / "clauding" strategy, what you iterated on, where the AI got it wrong and how you steered it), and the meaningful design decisions and **why** you made them. A dated decision log with saved prompts and transcript excerpts is the format we most like reading.

   > **Write this as a document** — `BUILD_TRAIL.md` or similar, submitted alongside your code. It's the main evidence for the *AI-tooling fluency* part of the AI-native SDLC pillar, and the finalist interview probes the same ground, so the two back each other up. A build with no write-up loses those marks outright and leaves judges scoring your reasoning from code alone — and reasoning they can't see can't be credited. Much easier to keep as you go than to reconstruct in week four. See `SUBMISSION.md`.
   >
   > If you work in git, you're welcome to leave the `.git` folder in your zip — it's useful corroboration. It isn't required, and not using git costs you nothing.
6. **Your run artifact — `results.json`.** A dump of what your system actually decided on the provided data, committed to the repo. This is your record of every decision (and doubles as the *auditability* the manual process never had). One JSON object with two arrays:
   ```json
   {
     "loaded":      [ { ...a record exactly as you POSTed to /contracts... }, ... ],
     "escalations": [ { "source_document": "0NN_some_document.pdf",
                        "kind": "escalate",            // "escalate" or "quarantine"
                        "reason": "<why this needs human review — cite the policy rule>",
                        "record": { ... optional partial ... } }, ... ]
   }
   ```
   Put one entry per document across the two arrays, each with a clear `reason`/rationale. Each record in `loaded` must be schema-conformant (the same `contract.schema.json` the API enforces). The simplest way to produce it is to save what you sent to the API (or dump `GET /loaded` + `GET /escalations` at the end of your run — note the API resets when it restarts, so save it before then).

   The CSV is a second source that overlaps the documents, so it may account for one entry or several. For a decision about a CSV row, use `"source_document": "legacy_export.csv"` and add a `"source_row": <n>` field so we can tell your rows apart.

   **Validate it with `python selfcheck.py` from the pack root** before you submit — that's the exact envelope the judges score against. You may add any extra keys you like; we only read these.

> We're not prescribing *what* to build — the architecture is yours. We *are* asking you to make your process visible. Much of the "AI-native SDLC" score (25%) is about exactly this; an undocumented build, however clever, can't be credited for reasoning we can't see. The `results.json` lets us score your accuracy fairly even if we don't re-run your code.

## How you're scored (summary)

| Pillar | Weight |
|---|---|
| AI-native SDLC — how you built it (velocity, tooling fluency, code quality) | 25% |
| Agentic engineering — architecture, retrieval, failure handling | 30% |
| Structured outputs & data integrity — conformance, repair loop, accuracy, dedup | 20% |
| Outcome & KPI reinvention — baseline vs expected vs measured KPIs + measurement plan | 10% |
| Demo & communication | 15% |
| **Bonus** — cost efficiency, eval harness, and *handling the surprises in the data* | +up to 10% |

> Judging begins 16 November: automated checks and scoring on every entry, then full panel review of a shortlist, then finalist interviews. Winners are announced in early December. `SUBMISSION.md` §6 has the detail, including that we do not give individual feedback.

**Deadline: Friday 13 November 2026, 23:59 US Eastern.** How to submit — `SUBMISSION.md`.
Questions — **FDE_Labs_Challenge@accenture.com**.

Good luck. Build like there's a client in the room — because soon there will be.
