"""Fault-injection tests for the failure paths: model failures, the repair loop, ERP outages,
rejected escalations, reconcile/CSV failures and the results artifact. No network, model, ERP
or file writes: everything external is mocked."""
import copy, io, json, sys, unittest, urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import erp, run
from extract import ExtractionError
from policy import Decision

GOOD = {"document_type": "MSA", "vendor_name": "Acme Corporation", "contract_value": 250000, "currency": "USD",
        "start_date": "2024-03-01", "renewal_date": None, "termination_date": None, "auto_renew": True,
        "liability_cap": 500000, "cap_status": "capped", "governing_law": "Delaware, USA", "dpa_status": "signed",
        "region_hint": "NA", "injection_detected": False, "injection_quote": None, "confidence": 0.95,
        "notes": None, "reference_id": None, "_usage": {"cost_usd": 0.0005}}


def facts(**over):
    f = copy.deepcopy(GOOD); f.update(over); return f


class Base(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.object(run, "read_any", lambda path: "contract text"),
                  mock.patch.object(run, "find", lambda name: Path(name)),
                  mock.patch.object(run.time, "sleep", lambda s: self.sleeps.append(s))):
            p.start(); self.addCleanup(p.stop)
        self.sleeps = []


class ModelFailures(Base):
    def test_model_always_fails_escalates_with_backoff(self):
        with mock.patch.object(run, "extract_facts", side_effect=ExtractionError("claude exit 1: usage limit")):
            it = run.analyze("x.pdf")
        self.assertEqual(it.decision.action, "escalate")
        self.assertIn("extraction failed", it.decision.reason)
        self.assertEqual(len(self.sleeps), run.MAX_REPAIRS)      # waited between attempts, not after the last

    def test_unexpected_exception_escalates_not_crashes(self):
        with mock.patch.object(run, "extract_facts", side_effect=RuntimeError("boom")):
            it = run.analyze("x.pdf")
        self.assertEqual(it.decision.action, "escalate")
        self.assertIn("RuntimeError", it.decision.reason)


class RepairLoop(Base):
    def test_bad_date_then_good_loads_after_one_repair(self):
        seen = []
        def fake(text, name, feedback=None):
            seen.append(feedback)
            return facts(start_date="03/01/2024") if feedback is None else facts()
        with mock.patch.object(run, "extract_facts", fake), \
             mock.patch.object(erp, "post_contract", return_value=(200, {"accepted": True})) as post, \
             mock.patch.object(erp, "post_escalation") as esc:
            it = run.analyze("x.pdf"); run.act(it)
        self.assertEqual(it.decision.action, "load")
        self.assertEqual(it.record["start_date"], "2024-03-01")
        self.assertIsNotNone(seen[-1])                      # the error list was fed back
        self.assertIn("start_date", seen[-1])
        self.assertEqual(post.call_count, 1)                # the bad record never reached the ERP
        esc.assert_not_called()
        self.assertIsNone(it.delivery_error)

    def test_erp_422_triggers_repair(self):
        calls = {"n": 0}
        def post(rec):
            calls["n"] += 1
            return (422, {"errors": [{"field": "x", "error": "bad"}]}) if calls["n"] == 1 else (200, {})
        with mock.patch.object(run, "extract_facts", lambda *a, **k: facts()), \
             mock.patch.object(erp, "post_contract", post):
            it = run.analyze("x.pdf"); run.act(it)
        self.assertEqual((it.decision.action, calls["n"], it.first_try), ("load", 2, False))

    def test_bad_date_forever_ends_as_escalation(self):
        sent = []
        with mock.patch.object(run, "extract_facts", lambda *a, **k: facts(start_date="03/01/2024")), \
             mock.patch.object(erp, "post_contract", return_value=(200, {})) as post, \
             mock.patch.object(erp, "post_escalation", lambda *a, **k: sent.append(a) or (200, {})):
            it = run.analyze("x.pdf"); run.act(it)
        self.assertEqual(it.decision.action, "escalate")
        self.assertIn("repair loop exhausted", it.decision.reason)
        self.assertEqual(len(sent), 1)
        post.assert_not_called()
        self.assertIsNone(it.delivery_error)


class ErpFailures(Base):
    def _load_item(self):
        with mock.patch.object(run, "extract_facts", lambda *a, **k: facts()):
            return run.analyze("x.pdf")

    def test_erp_down_on_load_is_a_delivery_failure_not_a_crash(self):
        it = self._load_item()
        extract = mock.Mock(side_effect=AssertionError("must not re-extract: not a schema problem"))
        with mock.patch.object(run, "extract_facts", extract), \
             mock.patch.object(erp, "post_contract", return_value=(0, {"error": "ERP unreachable"})):
            run.act(it)                                     # must not raise
        self.assertIn("status 0", it.delivery_error)

    def test_erp_down_on_escalation_is_a_delivery_failure(self):
        with mock.patch.object(run, "extract_facts", lambda *a, **k: facts(liability_cap=5_000_000)):
            it = run.analyze("x.pdf")
        with mock.patch.object(erp, "post_escalation", return_value=(0, {"error": "ERP unreachable"})):
            run.act(it)
        self.assertEqual(it.decision.action, "escalate")
        self.assertIn("POST /escalate failed", it.delivery_error)

    def test_rejected_escalation_is_not_silently_ignored(self):
        with mock.patch.object(run, "extract_facts", lambda *a, **k: facts(liability_cap=5_000_000)):
            it = run.analyze("x.pdf")
        with mock.patch.object(erp, "post_escalation", return_value=(400, {"detail": "rejected"})):
            run.act(it)
        self.assertIn("400", it.delivery_error)

    def test_client_retries_network_errors_then_reports_status_0(self):
        with mock.patch.object(erp.time, "sleep"), \
             mock.patch.object(erp.urllib.request, "urlopen", side_effect=urllib.error.URLError("refused")) as op:
            status, body = erp._post("/contracts", {})
        self.assertEqual(status, 0)
        self.assertEqual(op.call_count, erp.RETRIES)
        self.assertIn("unreachable", body["error"])

    def test_client_retries_5xx_but_not_4xx(self):
        def http(code):
            return urllib.error.HTTPError("u", code, "m", {}, io.BytesIO(b'{"x": 1}'))
        with mock.patch.object(erp.time, "sleep"):
            with mock.patch.object(erp.urllib.request, "urlopen", side_effect=lambda *a, **k: (_ for _ in ()).throw(http(503))) as op:
                self.assertEqual(erp._post("/contracts", {})[0], 0)
                self.assertEqual(op.call_count, erp.RETRIES)
            with mock.patch.object(erp.urllib.request, "urlopen", side_effect=lambda *a, **k: (_ for _ in ()).throw(http(422))) as op:
                self.assertEqual(erp._post("/contracts", {}), (422, {"x": 1}))
                self.assertEqual(op.call_count, 1)

    def test_healthy_false_when_down(self):
        with mock.patch.object(erp.urllib.request, "urlopen", side_effect=urllib.error.URLError("refused")):
            self.assertFalse(erp.healthy())


class ReconcileAndCsvFailures(Base):
    def _items(self):
        with mock.patch.object(run, "extract_facts", lambda *a, **k: facts()):
            a = run.analyze("a.pdf")
        b = run.Item("b.pdf"); b.decision = Decision("escalate", ["ESCALATE: x"], "already escalated")
        c = run.Item("c.pdf"); c.decision = Decision("quarantine", ["QUARANTINE: x"], "injection")
        return [a, b, c]

    def test_reconcile_crash_means_nothing_auto_loads(self):
        a, b, c = self._items()
        a.merged_into = "stale"
        with mock.patch.object(run, "reconcile", side_effect=RuntimeError("bug")):
            run._safe_reconcile([a, b, c], [])
        self.assertEqual(a.decision.action, "escalate")
        self.assertIn("reconciliation failed", a.decision.reason)
        self.assertIsNone(a.merged_into)
        self.assertEqual((b.decision.action, c.decision.action), ("escalate", "quarantine"))  # untouched

    def test_csv_failure_is_escalated(self):
        with mock.patch.object(run, "analyze_csv", side_effect=OSError("unreadable")):
            items = run._safe_csv()
        self.assertEqual((len(items), items[0].decision.action), (1, "escalate"))
        self.assertIn("legacy_export.csv", items[0].decision.reason)


class ResultsArtifact(Base):
    def test_undelivered_items_are_listed_separately_and_not_claimed(self):
        with mock.patch.object(run, "extract_facts", lambda *a, **k: facts()):
            ok, lost = run.analyze("ok.pdf"), run.analyze("lost.pdf")
        lost.delivery_error = "DeliveryError: ERP unreachable"
        sink = mock.Mock()
        out = run.write_results([ok, lost], sink)
        self.assertEqual([r["source_document"] for r in out["loaded"]], ["ok.pdf"])
        self.assertEqual(out["escalations"], [])
        self.assertEqual(out["undelivered"][0]["source_document"], "lost.pdf")
        self.assertEqual(out["undelivered"][0]["intended_action"], "load")
        json.loads(sink.write_text.call_args[0][0])             # what was written is valid JSON

    def test_no_undelivered_key_when_everything_delivered(self):
        with mock.patch.object(run, "extract_facts", lambda *a, **k: facts()):
            ok = run.analyze("ok.pdf")
        self.assertNotIn("undelivered", run.write_results([ok], mock.Mock()))


if __name__ == "__main__":
    unittest.main()
