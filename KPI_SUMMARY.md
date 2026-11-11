# KPI Summary

Status: DRAFT refreshed 2026-11-09 after the DPA fix and a 4-run stability check. To be
finalised once the last prompt/policy changes are frozen.

**How to read the measured column.** Measured on the 21 provided documents plus 7 CSV rows,
by `python src/evaluate.py` against my own hand labels (`eval/expected.json`). I wrote both the
labels and the fixes that made the system match them, so the accuracy and precision figures
are a regression baseline, not an independent claim. The judges hold the real answer key. The
sample is dense with deliberate traps (injection, conflicts, caps over $1M), so it is not
representative of the 4,200-document backlog. Throughput and cost are metered by Claude Code
per call.

| KPI | Baseline (today) | Target | Measured (this sample) | How to measure in production |
|---|---|---|---|---|
| Throughput | ~160 docs/day (8 analysts) | >= 2,000 docs/day with <= 4 parallel workers | 5.7-6.0 s/doc across runs, about 600-630 docs/hour on one serial stream. Measured. Per-day and parallel figures are extrapolations. | Timestamp start and end per document; report p50/p95 latency, docs/day, queue depth alerts |
| Straight-through rate | 0% | 60-70% on real inbound | 10 of 21 documents (47.6%) auto-loaded, identical in all 4 stability runs. Understates a normal mix because the sample is trap-heavy. | Auto-loaded / total, weekly, split by document type and by triggering rule |
| Field accuracy | ~94% (about 6% error) | >= 97%; 100% on guardrail fields (cap > $1M, DPA, injection) | 77 of 77 fields (100%) on the 10 loaded records vs my labels; no loaded field value changed across 4 runs (one cosmetic wording variation in `governing_law`, see below). Not independent. | Weekly ~5% random sample of loaded records checked by a human and scored per field; golden set with regression alert |
| Escalation precision | Low (~15% sent to Legal, mostly unnecessary) | >= 90% of escalations judged valid; 100% recall on hard guardrails | 14 of 14 non-load decisions match labels (precision 100%, recall 100%); quarantine 2 of 2. 0 hard-guardrail breaches in any run. Includes conservative calls I chose (Initech and Hooli DPA). The 52% escalation rate reflects the traps, not production. | Reviewers mark each escalation valid or unnecessary; precision weekly; audit a sample of loads to estimate misses |
| Cost / document | ~$13 direct + rework | <= $1 including human review of escalations | Model cost $0.0005-0.0007/doc across runs ($0.0101 to $0.0138 for 21; it varies run to run). Blended with human review of escalations (assumption: 52% escalated x 5-20 min x $40/hr) about $3-7/doc on this sample. The review cost is an assumption, not a measurement. | Meter token cost per document; add reviewer minutes per escalation from the review tool; report blended cost |
| Backlog cycle time | ~25 working days for 4,200 docs | <= 3 working days | About 6.8 h of machine time for 4,200 (extrapolated from 5.8 s/doc). Human review is the bottleneck: about 3 days at this sample's escalation rate and 5 min each with 8 analysts; about 1 day at ~20%. | Arrival-to-decision time per document; backlog size over time |
| Auditability | None | 100% of decisions have rationale, cited policy rule and confidence | 28 of 28 decisions (100%) logged with reason, cited rules and confidence in `out/audit.jsonl`; checked automatically by `evaluate.py`. | Same automated completeness check on every decision; immutable log; sampled review |

## Additional measured quality signals
- **Failure handling:** 15 fault-injection tests cover model failure with backoff, the repair loop (bad date then
  good, ERP 422, bad forever), ERP unreachable on load and on escalation, a rejected escalation, reconcile and CSV
  failures, and the `undelivered` artifact. None of these fired on the real data; they are tested by injection.
- **First-try ERP conformance:** 10 of 10 loads accepted on the first POST (no 422s). The repair loop
  (retry with the ERP's error list, then escalate) exists but was not triggered on this data.
- **Stability:** 4 full runs after the final fix: 0 decision flips, 28/28 matching labels in every run.
  Before the DPA fix, 2 of 4 runs flipped a clean load to an escalation (see BUILD_TRAIL iteration #10).
  Four runs is a small sample, not proof; the DPA decision is now made by a deterministic text rule
  with the model as fallback.
- **Remaining variation:** extraction confidence varies by 0.05-0.10 between runs on some documents
  (always far above the 0.70 threshold), and the wording of `governing_law` varied once
  ("Tokyo, Japan" vs "Tokyo, Japan (Gerichtsstand / jurisdiction clause)"); region and decision unaffected.

## Production measurement plan
- Log every decision with rationale, cited rule, confidence, model version and cost (already in `audit.jsonl`).
- Weekly human sample audit of loads (field accuracy, missed escalations) and of escalations (precision).
- Track STP rate, first-try conformance, escalation precision, cost per document, latency and
  per-rule escalation counts over time; alert on drift (e.g. sudden change in STP or in any one rule's volume).
- Keep a golden eval set (this repo's `eval/expected.json`, grown from reviewed production cases);
  re-run `evaluate.py` and `stability.py` on every prompt or model change as a release gate.
- Run the guardrail checks (cap > $1M never loaded, no load without a stated DPA, no duplicate loads,
  injection never loaded) on the output artifact as a blocking check, independent of the model.

## Open items
- Replace the escalation-review cost assumption with real reviewer time if any can be obtained.
- Re-measure after any further prompt or policy change; freeze before submission.
