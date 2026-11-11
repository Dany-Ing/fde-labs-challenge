# The Data Room: agentic contract-migration pipeline

Reads Atlas Industrial's messy contract documents (PDF, Word, a forwarded email, a legacy
CSV), extracts structured records with Claude, applies the risk policy in deterministic
code, and takes exactly one action per document through the mock ERP: **load**, **escalate**
or **quarantine**, with a logged rationale for every decision.

- Demo (5-10 min): **TODO: add the demo link here once recorded**
- Architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- KPIs (baseline, target, measured, production plan): [`KPI_SUMMARY.md`](KPI_SUMMARY.md)
- How it was built with AI (decision log, AI failures, prompts): [`BUILD_TRAIL.md`](BUILD_TRAIL.md)
- Run artifact: [`results.json`](results.json)
- The original challenge brief is kept in [`docs/BRIEF.md`](docs/BRIEF.md)

## Requirements

- Python 3.11+
- **Claude Code CLI** installed and logged in (`claude --version`). The extraction step calls
  `claude -p` headlessly; no API key is needed or used.
- The challenge pack at the same root as `src/`: `data/`, `schema/`, `mock_erp/`, `policy_kb/`.
  The pack is not part of the submission zip; the code reads it from the folder it sits in.

## Install and run

```bash
# from the pack root (the folder that contains data/, schema/, mock_erp/ and src/)
python3 -m venv .venv && source .venv/bin/activate
pip install -r mock_erp/requirements.txt -r requirements.txt

python mock_erp/app.py &          # ERP on http://localhost:8000 (do not edit mock_erp/ or schema/)
curl http://localhost:8000/health

python src/run.py --reset --all   # full run: all documents + the CSV; takes ~2.5 minutes
python selfcheck.py               # validates results.json against the published envelope
python src/evaluate.py            # scores the run against eval/expected.json
```

`python src/run.py --reset --all` writes:

| File | What |
|---|---|
| `results.json` | the run artifact: `loaded`, `escalations`, plus an extra `merged_duplicates` list |
| `out/audit.jsonl` | one line per decision: action, cited rules, reason, extracted facts, record, ERP attempts, cost, seconds |

Other commands:

```bash
python src/run.py 001_acme_msa.pdf 010_soylent_msa.pdf   # just these documents (no CSV, no results.json)
python src/run.py --reset --csv 003_globex_po.pdf        # include the CSV rows in reconciliation
python src/stability.py 4        # run the whole pipeline 4 times and diff decisions and fields
python -m unittest discover -s tests      # 25 unit and fault-injection tests, no model or ERP needed
```

`src/evaluate.py` exits 1 if any hard guardrail is breached or any decision differs from the
labels, so it works as a regression gate. `src/stability.py` overwrites `results.json` and the
audit log with those of its last run.

## Failure handling

Model failures and schema rejections retry (with backoff and a repair loop) and then escalate that
document. If the ERP is unreachable or rejects a decision, `src/run.py` retries, then lists the
document under `undelivered` in `results.json`, prints it and exits with status 1. It also refuses to
start if the ERP is not reachable. Details in `ARCHITECTURE.md`; each path is covered in
`tests/test_failure_handling.py`.

## Layout

```
src/ingest.py     text from PDF / DOCX / EML, CSV rows
src/extract.py    Claude extraction (`claude -p`, forced JSON schema, tools off) -> raw facts
src/policy.py     the policy in code: record building, tiering, region, FX, decisions, text guards
src/reconcile.py  duplicates, conflicts and legacy-CSV matching across documents
src/erp.py        ERP client + local validation against schema/contract.schema.json
src/run.py        pipeline: analyze -> reconcile -> act (+ repair loop) -> audit -> results.json
src/evaluate.py   eval harness       src/stability.py   repeat-run check
eval/expected.json   my hand-labelled expected decisions (the eval set)
tests/            unit tests
```

## Notes for reviewers

- The model reports raw facts (for example `dpa_status`, `cap_status`, `injection_detected`);
  Python decides load, escalate or quarantine, so document text cannot talk the system into an
  outcome. Details and trade-offs are in `ARCHITECTURE.md`.
- `eval/expected.json` contains my own labels. Accuracy figures in `KPI_SUMMARY.md` are
  measured against them and are a regression baseline, not an independent accuracy claim.
- Judgment calls I made where the policy is open to two readings are logged in
  `BUILD_TRAIL.md` (D-004 to D-008) and marked in `eval/expected.json`.
