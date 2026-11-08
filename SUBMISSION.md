# How to submit

**Deadline: Friday 13 November 2026, 23:59 US Eastern (ET).** Hard close — the upload
folder stops accepting files at that moment. Convert it to your own time zone now and
put it in your calendar.

---

## 1. How to submit — two steps

**Step 1 — share your zip from your own OneDrive.**

1. Upload your zip to your Accenture OneDrive.
2. Select the file → **Share** → open **Link settings** (the gear).
3. Choose **People in Accenture with the link**, and **Can view** — not Can edit.
4. **Apply**, then **Copy link**.
5. **Test it in a private/incognito browser window.** If it asks you to request
   access, we cannot open it either. This is the single most common way a submission
   is lost.

Do **not** use a link restricted to *Specific people* or *Only you* — we will not be
able to open it.

**Step 2 — submit the form.**

> **Submission form:** https://forms.cloud.microsoft/Pages/ResponsePage.aspx?id=OT154DkJbUmxKRmO3ZFv68fv03T8RFtMjv-tDMxSbzVUNEgxQ0ZKRDJVUVg0WTc4R1ZENEpHSFY2Wi4u

The form asks for your EID and your OneDrive link, and records your name, email and a
timestamp automatically. It **closes itself** at the deadline. Nobody can see anyone
else's submission.

**Do not** email your submission. The form is the only route, so nothing gets lost.

## 2. What to name it

```
FDELabs_<LastName>_<FirstName>_<EID>.zip
```

Example: `FDELabs_Smith_Jane_jane.smith.zip`

If you upload a revision, append `_v2`, `_v3`, and so on.

## 3. What goes inside the zip

**All six deliverables are required.** Not a suggestion, not a wish-list — each one is
scored, and a missing one costs marks you can't recover elsewhere. Following the brief is
itself part of what's being assessed: a forward-deployed engineer who ships five of six
agreed deliverables has not finished the job.

**Do not include the pack.** No `data/`, no `schema/`, no `mock_erp/`, no `current_state.docx`.
We re-run against our own copy.

The file names below are suggestions. The six items are not:

```
FDELabs_<LastName>_<FirstName>/
├── README.md              ← 1. how to install and run your system
├── src/ (or whatever you called it)
├── ARCHITECTURE.md        ← 3. the one-page architecture note
├── BUILD_TRAIL.md         ← 5. how you built it with AI — see below
├── KPI_SUMMARY.md         ← 4. baseline → expected → measured + measurement plan
├── results.json           ← 6. your run artifact
└── demo/
    └── demo.mp4 (or a link in README.md)   ← 2. the recorded demo
```

Call the files whatever you like, but **ship all six**. They are listed in `README.md` →
*What to submit*. In particular:

- **The recorded demo is not optional.** 5–10 minutes, your voice, run end to end on the
  provided data, showing the interesting cases. If the file is too large for the zip, link
  it from your `README.md` — but a submission with no demo at all loses the whole demo
  score, and it is worth 7 points.
- **`results.json` is not optional.** Without it there is nothing to score your accuracy
  against, and we will not reconstruct it for you.

Run `python selfcheck.py` before you submit — it tells you which of the six are missing.

### On the build trail — worth reading properly

We are judging *how you built this with AI*, not only what runs. `BUILD_TRAIL.md` is the
main evidence for the **AI-tooling fluency** criterion inside the AI-native SDLC pillar,
and the finalist interview covers the same ground — a judge who can see your reasoning in
both places can score it confidently.

A thin write-up costs you marks directly, and only finalists get an interview — so for
almost everyone this document is the only place your reasoning is visible at all. Reasoning
nobody can see can't be credited.

Write it as you go, not the night before — it's far harder to reconstruct a month of
decisions from memory than to jot them down as you make them. What earns the marks:

- **How you specced the problem** before writing code — how you decomposed it, what
  you decided to build first and why.
- **How you drove the tooling** — your prompting strategy, how you structured context,
  what you asked for in what order. Saved prompts and transcript excerpts are strong
  evidence; paste the ones that mattered.
- **Where the AI got it wrong and how you steered it** — this is the most valuable
  section and the one most people skip. Wrong turns, hallucinated APIs, a plausible
  design you had to reject. Showing you caught it scores better than pretending it
  never happened.
- **The design decisions you made and why** — and what you'd have done with more time.

A dated decision log is the easiest format and the one we most like reading. Length is
not the point; specificity is. Two pages of real decisions beats ten pages of
narration.

**If you work in git, leave the `.git` folder in your zip.** It's genuine corroboration
of how the build actually unfolded, and it's free to include — most zip tools keep
hidden folders by default, so this usually means doing nothing. It is **not required**:
nothing is scored on commit count or message quality, and if you don't use git you lose
nothing at all. It's supporting evidence for the write-up, not a substitute for it.

### Size

Keep the zip **under 200 MB**. If your demo recording pushes you over, put the video
on your own OneDrive, share it **internally (Accenture only)**, and put the link at the
top of your `README.md` instead of the file in the zip. Check the link opens in a
private browser window before you submit.

Exclude `venv/`, `node_modules/`, `__pycache__/`, model weights, and any cached
documents. We re-run against our own copy of the dataset.

### The demo

5–10 minutes, screen recording with your voice. Run it end-to-end on the provided data
and **show the interesting cases** — the documents where your system did something
other than a clean load, and why. A demo that only shows the happy path tells us very
little. No slides needed.

## 4. Before you submit — the two-minute self-check

**Run this first, from the pack root:**

```bash
python selfcheck.py
```

It checks the mechanical things that cost marks for no good reason: your Python
version, the three fixed-file hashes, that `results.json` matches the published
envelope, that every document has exactly one decision, and that every escalation
carries a reason. Fix anything it reports as a FAIL.

It is not a scorer and it knows nothing about whether your answers are right. **If it
ever disagrees with this pack, the pack wins.**

Then check the things a script can't:

- [ ] Your `README.md` tells a stranger how to run your system from a clean machine.
- [ ] All six deliverables are present.
- [ ] The zip opens and the folder structure is intact. Unzip it somewhere else and look.
- [ ] Your OneDrive link opens in a private/incognito window and downloads the zip.

**On document coverage.** Every file in `data/contracts/` and `data/emails/` must
appear exactly once across `loaded` + `escalations`. The CSV is different: it is a
second source that overlaps the documents, so it may produce one entry or several —
see §1 of `README.md` and the policy. For a decision about a CSV row, use
`"source_document": "legacy_export.csv"` and add a `"source_row": <n>` field so we can
tell your rows apart.

## 5. Revisions, late entries, and problems

- **Revisions** are fine up to the deadline. Submit the form again and we take your
  latest response. You do not need to tell us.
- **Late entries are not accepted.** The form closes itself at 23:59 ET.
- **Your file is taken as it stands at the deadline.** We download every submission
  shortly after the form closes. Changes you make to the file after 23:59 ET are not
  considered.
- **If the form or the link fails** — and only then — email
  **FDE_Labs_Challenge@accenture.com** *before* the deadline with the problem. A failure
  you told us about before 23:59 ET is recoverable; one we hear about on Monday is not.
- Submit early. A first submission on Wednesday that you later replace costs you nothing
  and removes the entire category of deadline risk.

## 6. What happens next

| | |
|---|---|
| From 16 November | Judging begins |
| Early December | Winners announced across Digital Core |

**How judging works.** Every submission goes through the same published process:

1. **Automated checks and scoring.** Fixed, pre-published rules applied to every
   entry: the actions you took, schema conformance, field accuracy, deduplication,
   and whether the deliverables are present and substantive. Part of this first-round
   score comes from an **AI reviewer** reading your architecture note, build trail and
   KPI summary against written anchors — two independent runs are averaged, any
   disagreement between them goes to a person, and a sample is spot-checked by hand.
2. **Shortlist.** Entries are ranked by that score, and a shortlist goes forward to
   full panel review. Ties at the line all go through, the boundary band gets a human
   look, and a small number of entries can be brought up by a reviewer who thinks the
   score understates them.
3. **Panel review.** Each shortlisted entry is read by two independent judges against
   the full rubric. Where they disagree materially, they reconcile before a score is
   taken.
4. **Finalist interviews.** A small number of finalists are invited to a short
   conversation with the FDE AI Council: a brief walkthrough, a live run on documents you
   have not seen, and questions about your reasoning. A conversation about your build,
   not a test.
5. **Awards.** Ranked by final score. The Council can depart from strict rank only on
   grounds written down before submissions opened, with reasons recorded and signed.

**We do not give individual feedback.** Everyone hears whether they advanced. Nobody
receives a score, a rank or a critique.

Strong performers are flagged for the FDE certification track whether or not they
finish in the top five.

Questions: **FDE_Labs_Challenge@accenture.com**
