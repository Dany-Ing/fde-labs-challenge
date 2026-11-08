# Kickoff brief — dates, rules, setup, FAQ

You're registered. This page is the logistics; `README.md` is the actual challenge.
Read this one first — it takes five minutes and covers the things people email us
about in week three.

---

## 1. The dates

| | |
|---|---|
| **Mon 19 October** | **Kickoff. Pack released. The four-week clock starts.** |
| 19 Oct – 13 Nov | Build window — part-time, around your normal work |
| **Fri 13 November, 23:59 US Eastern** | **Hard submission deadline** |
| From 16 November | Judging: automated checks, then panel review, then finalist interviews |
| **Early December** | Winners announced across Digital Core |

Four weeks sounds generous and is not. The build is deliberately sized for **a few
hours a week**, but the parts that score well — the policy edge cases, the failure
handling, the KPI measurement — are the parts people run out of time for. Get an
end-to-end pipeline working badly in week one, then make it good. Do not spend three
weeks on extraction.

## 2. The rules

**Allowed, and expected:**

- **Any AI tooling you have a licence for** — Claude, Copilot, Cursor, whatever. This
  is an AI-native build; using AI heavily is the point, not a shortcut.
- Any open-source library, any model you can legitimately access, any architecture.
- Reading anything public. Asking an AI anything.

**Required:**

- **Individual entries.** One submission per person, your build end to end. Finalist
  interviews confirm the work is yours — be ready to explain any line of it.
- **Synthetic data only.** The dataset we give you is fabricated. Never put real
  client data, real Accenture data, or anything from a live engagement near this.
- **Don't share your solution** with other participants during the build window.
  Afterwards, please do.

**Not allowed:**

- **Changing the fixed integration.** `mock_erp/app.py`, `schema/contract.schema.json`
  and `schema/results.schema.json` are read-only and checksum-verified. Don't edit,
  wrap, proxy, monkey-patch, or intercept them. Full statement in `README.md`. This is
  the one rule with an automatic consequence: a hash mismatch voids your conformance
  and structured-output scores until it's re-scored against a clean API.
- Posting the dataset or the brief outside Accenture.

## 3. Questions

**All questions go by email to FDE_Labs_Challenge@accenture.com.** There are no
office hours or calls during the build window.

Good questions to send:

- **Problems with the pack** — the mock ERP won't start, a file won't open, a
  checksum doesn't match. Include your operating system, Python version and the exact
  error message, so we can answer in one reply.
- **Genuine ambiguities in the brief or the policy**, where two readings are both
  reasonable.

Anything that affects everyone gets answered to all participants in an FAQ note, so
nobody gains from asking first. Please allow a few working days for a reply. AI
tooling licences are your own to source; we can't provide them.

**We will not give design help.** Not "is this architecture right", not "should I
escalate this document", not "is my interpretation of the policy correct". The
architecture and the judgment calls are what's being scored — answering those for you
would hand you 30% of the rubric and be unfair to everyone else. Ask anyway if you
like; the answer will be a friendly no.

## 4. Set up now, not in week three

Do this today. The most common reason someone drops out is an environment problem they
hit late.

**Prerequisites:** Python 3.11 or newer, and working AI tooling.

```bash
# 1. Unzip the pack, then:
cd fde-labs-challenge

# 2. Check your Python
python3 --version         # must be 3.11+

# 3. Make a virtual environment at the pack root, and use it for everything
python3 -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate

# 4. Start the mock ERP
pip install -r mock_erp/requirements.txt
python mock_erp/app.py            # serves on http://localhost:8000
```

**Use a virtual environment.** On a Homebrew or system-managed Python a bare
`pip install` fails with `externally-managed-environment` (PEP 668). The `.venv`
above avoids it, and keeping it at the pack root rather than inside `mock_erp/`
keeps your files out of the read-only directory.

In a second terminal:

```bash
curl http://localhost:8000/health
```

You should get a JSON response with counts. **If you get that, your environment is
good** — that's the only moving part we supply.

**If `/health` returns `{"detail":"Not Found"}`, something else is already on port
8000.** The mock ERP will start beside another listener without complaining, and
`localhost:8000` then reaches the wrong server. Check with `lsof -i :8000` (macOS/Linux)
or `netstat -ano | findstr :8000` (Windows), stop the other process, and start the ERP
again. Don't change the port — it is part of the fixed integration.

Then confirm the fixed files are intact and your environment is sound:

```bash
# from the pack root
python selfcheck.py
```

`selfcheck.py` checks your Python version, verifies the three fixed files against
`CHECKSUMS.txt`, and — once you have a `results.json` — validates it against the
published envelope and tells you whether every document has exactly one decision. Run
it now, and again before you submit. It works the same on macOS, Linux and Windows.

If you prefer to check the hashes by hand: `shasum -a 256 -c CHECKSUMS.txt` on
macOS/Linux, or `Get-FileHash <file> -Algorithm SHA256` on each of the three files on
Windows PowerShell.

> **If `selfcheck.py` and this pack ever disagree, the pack wins.** The script is a
> convenience, not the specification.

**If any of this fails, email us this week** with the exact error message. Don't spend
a Saturday on it, and don't leave it until week three.

### A note for Windows users

The pack is cross-platform and nothing in it needs WSL or admin rights. If `python`
isn't found, you likely need the Microsoft Store Python or a PATH fix. Your AI tooling
can usually walk you through that faster than we can.

## 5. How to spend four weeks

Not prescriptive — it's your build. But the submissions that do well tend to go in
roughly this order:

- **Week 1** — Read `current_state.docx` and `policy_kb/` properly. Get *something*
  end to end: one document in, one API call out. Write down your baseline KPIs.
- **Week 2** — The real pipeline across all the documents. Expect the API to reject
  things; that's it working as designed.
- **Week 3** — The hard part. Failure handling, the documents that don't behave,
  the policy edges. This is where the points are.
- **Week 4** — Measure your KPIs honestly, write the architecture note and build
  trail, record the demo. **Reserve the last three days for this.** People routinely
  under-budget the write-up and lose marks on work they actually did.

Read `SUBMISSION.md` in week one, not week four. It tells you what to keep as you go —
particularly the build trail, which is nearly impossible to reconstruct from memory.

## 6. FAQ

**Is there starter code?**
No, deliberately. You get the data, the schema, the policy and the API. The
architecture is entirely yours — that's the 30% pillar. (`selfcheck.py` is the one
script in the pack: it checks your submission is well-formed. It doesn't help you
build anything.)

**`python app.py` fails with a `TypeError` mentioning `dict | None`.**
You're on Python 3.9 or older — the API needs 3.11+. Check `python3 --version`. This
is the most common setup problem and it looks like a broken pack; it isn't.

**What AI tooling may I use?**
Anything you can legitimately access: an API key, a coding agent or CLI, an IDE
assistant, a local model, or any combination. We don't provide licences and we don't
require any particular route. You can also build without a model at all — nothing
forbids it, though `policy_kb` judgement calls are what Pillar 2 scores.

**How much time will this take?**
It's sized for a few hours a week over four weeks. People who enjoy it spend more.
It's a side project around BAU; it is not meant to cost you a weekend.

**Will AI tooling be provided?**
No. You build with whatever AI tooling you already have or can obtain through the
normal Accenture channels.

**Can I use a paid API / my own model?**
Yes, within whatever your tooling licence and Accenture policy allow. Cost efficiency
is a bonus criterion, so a cheap good system beats an expensive one of equal quality.

**My company laptop blocks something I need.**
Email us with what's blocked and the exact message. If it's a problem other people
are likely to hit, the answer goes in the FAQ note.

**Are there office hours or calls?**
No. All questions go to FDE_Labs_Challenge@accenture.com.

**What if I can't finish?**
Submit what you have. A partial system with honest KPIs and a clear build trail scores
better than nothing, and the certification-track flag isn't restricted to the top five.

**Do I need to be an AI engineer?**
No. You need to be able to build with AI and tie it to a business outcome. Job titles
aren't scored.

**Can I ask an AI how to design this?**
Yes. Obviously yes — that's the whole premise. Just show us how you did it in your
build trail.

---

## 7. Your five documents

| File | What it is |
|---|---|
| `README.md` | **The challenge brief. Start here.** |
| `current_state.docx` | How Atlas does this today + the baseline KPIs. Read before designing. |
| `policy_kb/risk_and_action_policy.md` | The rules that decide load / escalate / quarantine. Non-negotiable. |
| `KICKOFF.md` | This page — dates, rules, setup, FAQ |
| `SUBMISSION.md` | What to submit, how, and the deadline |

Good luck. Build like there's a client in the room.

**FDE_Labs_Challenge@accenture.com**
