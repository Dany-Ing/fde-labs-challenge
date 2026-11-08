#!/usr/bin/env python3
"""
selfcheck.py — run this twice: once now, once before you upload.

It checks the mechanical things that cost marks for no good reason: a corrupted
download, an accidentally modified fixed file, a results.json that doesn't match
the published envelope, a document with no decision. It is not a scorer and it
knows nothing about whether your answers are right.

    python selfcheck.py                 # from the pack root
    python selfcheck.py --root ../mywork # if your work lives elsewhere

Nothing here is secret and nothing phones home. Read it if you like.
"""
# Deliberately written for Python 3.8+ so that it still RUNS on an old
# interpreter and can tell you so, instead of failing like the ERP does.
from __future__ import print_function

import argparse
import csv
import hashlib
import json
import os
import sys

PACK_MARKERS = ("CHECKSUMS.txt", "schema", "data")
DELIVERABLES = [
    ("README.md", "how to install and run your system"),
    ("ARCHITECTURE.md", "the one-page architecture note"),
    ("BUILD_TRAIL.md", "how you built it with AI"),
    ("KPI_SUMMARY.md", "baseline -> expected -> measured + measurement plan"),
    ("results.json", "your run artifact"),
]

GREEN, RED, YELLOW, BLUE, BOLD, OFF = (
    ("\033[32m", "\033[31m", "\033[33m", "\033[34m", "\033[1m", "\033[0m")
    if sys.stdout.isatty() and os.name != "nt" else ("", "", "", "", "", "")
)

results_state = {"fail": 0, "warn": 0}


def ok(msg):
    print("  " + GREEN + "PASS" + OFF + "  " + msg)


def fail(msg, detail=None):
    results_state["fail"] += 1
    print("  " + RED + "FAIL" + OFF + "  " + msg)
    if detail:
        for line in str(detail).splitlines():
            print("        " + line)


def warn(msg, detail=None):
    results_state["warn"] += 1
    print("  " + YELLOW + "WARN" + OFF + "  " + msg)
    if detail:
        for line in str(detail).splitlines():
            print("        " + line)


def info(msg):
    print("  " + BLUE + "info" + OFF + "  " + msg)


def section(title):
    print("\n" + BOLD + title + OFF)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def find_pack(start):
    """Walk up from `start` looking for the unzipped pack."""
    cur = os.path.abspath(start)
    for _ in range(6):
        if all(os.path.exists(os.path.join(cur, m)) for m in PACK_MARKERS):
            return cur
        nxt = os.path.dirname(cur)
        if nxt == cur:
            break
        cur = nxt
    # also try one level down, for work-alongside-pack layouts
    for name in sorted(os.listdir(start)):
        cand = os.path.join(start, name)
        if os.path.isdir(cand) and all(
                os.path.exists(os.path.join(cand, m)) for m in PACK_MARKERS):
            return cand
    return None


# ---------------------------------------------------------------- checks

def check_python():
    section("1. Python version")
    v = sys.version_info
    print("        running %d.%d.%d" % (v[0], v[1], v[2]))
    if v < (3, 11):
        fail("the mock ERP needs Python 3.11+ (you have %d.%d)" % (v[0], v[1]),
             "mock_erp/app.py uses syntax added in 3.10. On an older interpreter it\n"
             "fails with a confusing TypeError from inside Pydantic -- that is a\n"
             "version problem, not a broken pack. Install 3.11+ and retry.")
    else:
        ok("Python %d.%d is new enough for the mock ERP" % (v[0], v[1]))


def check_hashes(pack):
    section("2. Fixed files unmodified  (the one rule with an automatic consequence)")
    path = os.path.join(pack, "CHECKSUMS.txt")
    if not os.path.exists(path):
        fail("CHECKSUMS.txt not found", "looked in " + pack)
        return
    checked = 0
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            want, rel = parts[0], parts[1].strip()
            target = os.path.join(pack, rel)
            if not os.path.exists(target):
                fail(rel + " is MISSING from the pack")
                continue
            got = sha256(target)
            checked += 1
            if got == want:
                ok(rel)
            else:
                fail(rel + " has been MODIFIED",
                     "expected " + want + "\ngot      " + got +
                     "\n\nSomething changed this file -- quite possibly an AI tool "
                     "'fixing' a\nvalidation error for you. Restore it from the "
                     "original zip before you\ngo any further: everything you built "
                     "since is being checked against a\nspec that is not the real one.")
    if checked == 0:
        fail("CHECKSUMS.txt contained no readable entries")


def load_results(path, root=None):
    section("3. results.json loads")
    if not os.path.exists(path):
        # Running this at setup, before anything is built, is expected -- KICKOFF
        # tells you to. Only treat a missing results.json as a failure once other
        # deliverables exist, i.e. once you are plainly near submitting.
        others = [d for d, _ in DELIVERABLES
                  if d != "results.json" and root
                  and os.path.exists(os.path.join(root, d))
                  and not (d == "README.md" and _is_challenge_brief(os.path.join(root, d)))]
        if not others:
            info("no results.json yet -- nothing to check here")
            print("        Expected if you are running this as a setup check. The checks")
            print("        above are the ones that matter today; run this again once your")
            print("        system has produced results.json.")
        else:
            fail("results.json not found", "looked at " + path)
        return None
    try:
        with open(path) as fh:
            data = json.load(fh)
        ok("parses as JSON")
        return data
    except ValueError as exc:
        fail("results.json is not valid JSON", exc)
        return None


def check_envelope(data, pack):
    section("4. results.json matches the published envelope")
    schema_path = os.path.join(pack, "schema", "results.schema.json")
    if not os.path.exists(schema_path):
        fail("schema/results.schema.json not found")
        return
    try:
        from jsonschema import Draft7Validator
    except ImportError:
        # Never pass silently on a check we could not perform.
        fail("cannot validate -- the 'jsonschema' package is not installed",
             "This check is the one the judges score against, so it is not safe to\n"
             "skip. Install it and re-run:\n\n"
             "    pip install jsonschema\n\n"
             "(It is already in mock_erp/requirements.txt, so installing those\n"
             "requirements also fixes this.)")
        return
    with open(schema_path) as fh:
        schema = json.load(fh)
    errors = sorted(Draft7Validator(schema).iter_errors(data),
                    key=lambda e: list(e.path))
    if not errors:
        ok("validates against schema/results.schema.json")
    else:
        fail("%d schema violation(s)" % len(errors))
        for e in errors[:10]:
            where = "/".join(str(p) for p in e.path) or "(root)"
            print("        " + where + ": " + e.message[:110])


def check_loaded_records(data, pack):
    section("5. Every loaded record conforms to the contract schema")
    schema_path = os.path.join(pack, "schema", "contract.schema.json")
    if not os.path.exists(schema_path):
        fail("schema/contract.schema.json not found")
        return
    try:
        from jsonschema import Draft7Validator
    except ImportError:
        fail("cannot validate -- 'jsonschema' not installed (see above)")
        return
    with open(schema_path) as fh:
        schema = json.load(fh)
    v = Draft7Validator(schema, format_checker=Draft7Validator.FORMAT_CHECKER)
    loaded = data.get("loaded") or []
    if not loaded:
        warn("no loaded records at all",
             "Legitimate if you escalated everything, but worth a second look.")
        return
    bad = []
    for rec in loaded:
        clean = dict((k, val) for k, val in rec.items() if not k.startswith("_"))
        errs = list(v.iter_errors(clean))
        if errs:
            bad.append((rec.get("source_document", "<no source_document>"), errs))
    if not bad:
        ok("all %d loaded record(s) are schema-conformant" % len(loaded))
    else:
        fail("%d of %d loaded record(s) would be REJECTED (422) by the API"
             % (len(bad), len(loaded)))
        for src, errs in bad[:5]:
            print("        " + str(src))
            for e in errs[:4]:
                where = "/".join(str(p) for p in e.path) or "(root)"
                print("          " + where + ": " + e.message[:95])


def check_coverage(data, pack):
    section("6. Every document has exactly one decision")
    docs = []
    for sub in ("data/contracts", "data/emails"):
        d = os.path.join(pack, sub)
        if os.path.isdir(d):
            docs += [f for f in sorted(os.listdir(d)) if not f.startswith(".")]
    if not docs:
        fail("found no documents under data/ -- is --root pointing at the pack?")
        return

    seen = {}
    for rec in (data.get("loaded") or []):
        seen.setdefault(rec.get("source_document"), []).append("loaded")
    for e in (data.get("escalations") or []):
        seen.setdefault(e.get("source_document"), []).append(
            e.get("kind") or "escalate")

    missing = [d for d in docs if d not in seen]
    # A spreadsheet is not one document. The legacy CSV holds several rows and
    # more than one of them may legitimately need its own decision, so it is
    # exempt from the one-decision-per-document rule. (Tested against two real
    # submissions, both of which filed several CSV escalations correctly and
    # were wrongly failed by an earlier version of this check.)
    dupes = dict((k, v) for k, v in seen.items()
                 if len(v) > 1 and not str(k).lower().endswith(".csv"))
    csv_entries = dict((k, v) for k, v in seen.items()
                       if len(v) > 1 and str(k).lower().endswith(".csv"))

    if missing:
        fail("%d document(s) have NO decision" % len(missing),
             "\n".join(missing[:12]))
    else:
        ok("all %d document file(s) appear in results.json" % len(docs))
    if dupes:
        fail("%d document(s) have MORE THAN ONE decision" % len(dupes),
             "\n".join("%s -> %s" % (k, ", ".join(v)) for k, v in
                       sorted(dupes.items())[:12]))
    else:
        ok("no document has two decisions")

    for k, v in csv_entries.items():
        info("%s carries %d decisions in your results - not flagged" % (k, len(v)))
        print("        a spreadsheet is not one document; how many decisions its rows")
        print("        warrant is a judgement call the policy covers.")

    extra = [k for k in seen if k and k not in docs]
    if extra:
        info("%d entr(y/ies) reference something other than a document file: %s"
             % (len(extra), ", ".join(sorted(str(x) for x in extra)[:6])))

    # The legacy CSV: report, never reconcile. What it implies is yours to work out.
    csv_path = os.path.join(pack, "data", "legacy_export.csv")
    if os.path.exists(csv_path):
        with open(csv_path) as fh:
            rows = [r for r in csv.DictReader(fh) if any((v or "").strip()
                                                         for v in r.values())]
        info("legacy_export.csv holds %d data row(s). This check does not reconcile "
             "them" % len(rows))
        print("        for you -- whether a row is its own decision, folds into a")
        print("        document's, or is noise is a judgement call the policy covers.")


def check_reasons(data):
    section("7. Every escalation carries a reason")
    escs = data.get("escalations") or []
    if not escs:
        warn("no escalations or quarantines at all",
             "Possible, but the policy describes situations that require them.")
        return
    empty = [e.get("source_document") for e in escs
             if not (e.get("reason") or "").strip()]
    if empty:
        fail("%d escalation(s) have an empty reason" % len(empty),
             "\n".join(str(x) for x in empty[:12]))
    else:
        ok("all %d escalation(s) have a non-empty reason" % len(escs))
    short = [e.get("source_document") for e in escs
             if 0 < len((e.get("reason") or "").strip()) < 15]
    if short:
        warn("%d reason(s) are very short -- a human has to act on these"
             % len(short), "\n".join(str(x) for x in short[:8]))


BRIEF_MARKER = "reinvent a real business process as a working agentic system"


def _is_challenge_brief(path):
    """The pack ships its own README.md -- the brief. If you are working inside
    the pack folder, don't let it be mistaken for YOUR run instructions."""
    try:
        with open(path, errors="replace") as fh:
            return BRIEF_MARKER in fh.read()
    except OSError:
        return False


def check_deliverables(root, pack):
    section("8. All six deliverables present")
    if pack and os.path.abspath(root) == os.path.abspath(pack):
        info("your deliverables folder IS the pack folder, so the pack's own files")
        print("        are in scope here. Checks below ignore the pack's README.md.")
    for name, what in DELIVERABLES:
        target = os.path.join(root, name)
        if name == "README.md" and os.path.exists(target) and _is_challenge_brief(target):
            warn("README.md here is the challenge brief, not your run instructions",
                 "Deliverable 1 is a README that tells a stranger how to run YOUR\n"
                 "system from a clean machine. Either write yours somewhere else and\n"
                 "point --root at it, or replace this one in your submission zip.")
            continue
        if os.path.exists(target):
            ok(name)
        else:
            warn(name + " not found -- " + what,
                 "All six deliverables are required. A missing one costs marks you\n"
                 "cannot recover elsewhere. See SUBMISSION.md section 3.")
    demo_dir = os.path.join(root, "demo")
    has_demo = os.path.isdir(demo_dir) and any(
        not f.startswith(".") for f in os.listdir(demo_dir))
    readme = os.path.join(root, "README.md")
    linked = False
    # a link only counts if it is in YOUR readme, not the pack's brief
    if os.path.exists(readme) and not _is_challenge_brief(readme):
        with open(readme, errors="replace") as fh:
            linked = "http" in fh.read()
    if has_demo or linked:
        ok("demo (file in demo/ or a link in README.md)")
    else:
        warn("no demo file and no link in README.md",
             "The recorded demo is required, not optional: 5-10 minutes, your voice,\n"
             "end to end on the provided data, showing the interesting cases. It is\n"
             "worth 7 points and you lose all of them without it. Too large for the\n"
             "zip? Link it from your README.md instead.")


def summary(data):
    section("Summary")
    if data:
        n_load = len(data.get("loaded") or [])
        escs = data.get("escalations") or []
        n_q = sum(1 for e in escs if e.get("kind") == "quarantine")
        n_e = len(escs) - n_q
        print("        %d loaded, %d escalated, %d quarantined -- %d decisions"
              % (n_load, n_e, n_q, n_load + len(escs)))
    f, w = results_state["fail"], results_state["warn"]
    print()
    if f:
        print("  " + RED + BOLD + "%d FAILURE(S)" % f + OFF +
              " -- fix these before you upload." +
              ("  (%d warning(s) too.)" % w if w else ""))
        return 1
    if w:
        if data is None:
            print("  " + GREEN + BOLD + "SETUP LOOKS GOOD." + OFF +
                  " Your environment and the fixed files are fine.")
            print("        The %d warning(s) are just deliverables you have not written "
                  "yet." % w)
            print("        Run this again once your system has produced results.json.")
        else:
            print("  " + YELLOW + BOLD + "No failures, %d warning(s)." % w + OFF +
                  " Worth a look, but you are submittable.")
        return 0
    print("  " + GREEN + BOLD + "ALL CHECKS PASSED." + OFF +
          " This says your submission is well-formed.")
    print("        It says nothing about whether your answers are right.")
    return 0


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Pre-submission self-check.")
    ap.add_argument("--root", default=here,
                    help="folder holding your deliverables (default: this folder)")
    ap.add_argument("--pack", default=None,
                    help="unzipped pack folder (default: found automatically)")
    ap.add_argument("--results", default=None,
                    help="path to results.json (default: <root>/results.json)")
    a = ap.parse_args()

    root = os.path.abspath(a.root)
    pack = os.path.abspath(a.pack) if a.pack else find_pack(root)

    print(BOLD + "=" * 70)
    print("FDE Labs Challenge -- pre-submission self-check")
    print("=" * 70 + OFF)
    print("  deliverables : " + root)
    print("  pack         : " + (pack or "NOT FOUND"))

    check_python()
    if not pack:
        section("2-6. Pack checks")
        fail("could not locate the unzipped pack",
             "Expected a folder containing CHECKSUMS.txt, schema/ and data/.\n"
             "Pass it explicitly:  python selfcheck.py --pack path/to/pack")
        return summary(None)

    check_hashes(pack)
    data = load_results(a.results or os.path.join(root, "results.json"), root)
    if data is not None:
        check_envelope(data, pack)
        check_loaded_records(data, pack)
        check_coverage(data, pack)
        check_reasons(data)
    check_deliverables(root, pack)
    return summary(data)


if __name__ == "__main__":
    sys.exit(main())
