"""Reliability Brain: known-answer engineering scenarios, orchestration, isolation,
immutability, verification, knowledge store and reports."""

import ast
import dataclasses
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from plantproof import whatif
from plantproof.domain import PROJECT_ROOT, Observation
from plantproof.reliability import KnowledgeStore, PROTOCOL, load_registry, run_all, run_examination
from plantproof.reliability import adapter, registry
from plantproof.reliability.knowledge import compare
from plantproof.reliability.orchestrator import StageSpec
from plantproof.reliability.stages import s2_data_integrity, s4_causal
from plantproof.reliability.types import (Claim, ClaimKind, Check, StageResult, StageStatus,
                                          Verification, frozen_map)

KNOWN = json.loads((PROJECT_ROOT / "data" / "reliability" / "known_answers.json").read_text())["cases"]
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
PKG = PROJECT_ROOT / "plantproof"


def report(case_id, **kw):
    return run_examination(case_id, now=NOW, **kw)


class KnownAnswerTests(unittest.TestCase):
    """Each synthetic case against the conclusion a careful engineer would reach."""

    @classmethod
    def setUpClass(cls):
        cls.reports = {r.case_id: r for r in run_all(now=NOW)}

    def test_every_registered_case_has_a_known_answer(self):
        self.assertEqual(set(self.reports), set(KNOWN))

    def test_outcomes_match_engineering_expectations(self):
        for cid, exp in KNOWN.items():
            r = self.reports[cid]
            with self.subTest(case=cid):
                self.assertEqual(r.overall_status, exp["overall"])
                self.assertEqual(r.condition, exp["condition"])
                self.assertEqual(r.grade, exp["grade"])
                self.assertEqual(r.risk, exp["risk"])
                self.assertEqual(r.leading, exp["leading"])
                self.assertEqual(r.leading_label, exp["label"])
                trust = r.stage("S2").data.get("trust", {}) if r.stage("S2").status is not StageStatus.BLOCKED else {}
                self.assertEqual(sorted(p for p, t in trust.items() if t == "suspect"), exp["suspect_sensors"])
                got = set(r.stage("S2").data.get("contradictions", ())) if trust else set()
                self.assertEqual(got, set(exp["contradictions"]))
                cats = {x.category for x in r.recommendations}
                for must in exp["must_recommend"]:
                    self.assertIn(must, cats)

    def test_disputed_sensor_alarm_is_not_treated_as_confirmed(self):
        b = self.reports["P-301/B"]
        self.assertEqual(b.stage("S3").data["params"]["vibration_mm_s"]["status"], "alarm_unconfirmed")
        first = b.recommendations[0]
        self.assertEqual((first.priority, first.category), ("P1", "diagnose"))
        self.assertIn("transmitter", first.action_en)

    def test_poor_data_never_gives_a_confident_or_reassuring_result(self):
        p = self.reports["P-303/poor-data"]
        self.assertEqual(p.stage("S2").data["cap"], 0.5)
        for h in p.stage("S4").data["ranking"]:
            self.assertLessEqual(h["adjusted"], 0.5)
        self.assertNotEqual(p.risk, "Low")
        self.assertEqual(p.recommendations[0].category, "escalate")
        failed = {c["check_id"] for c in p.stage("S2").data["checks"] if not c["passed"]}
        self.assertTrue({"D1", "D2", "D3", "D5", "D6"} <= failed)
        excluded = set(p.stage("S2").data["excluded_ids"])
        self.assertIn("P303-SEN-9001", excluded)            # conflicting vibration reading

    def test_unsupported_asset_type_stops_at_stage_one(self):
        k = self.reports["K-101/routine"]
        self.assertEqual(k.stage("S1").status, StageStatus.BLOCKED)
        self.assertTrue(all(s.status is StageStatus.BLOCKED for s in k.stages[1:]))
        self.assertIn("not supported", k.final_en.lower() + k.overall_status.lower())

    def test_healthy_pump_gets_monitoring_only(self):
        h = self.reports["P-302/routine"]
        self.assertEqual([x.category for x in h.recommendations], ["monitor"])
        self.assertIn("not proof of health", h.recommendations[0].justification)

    def test_no_probability_or_rul_is_claimed(self):
        for r in self.reports.values():
            s5 = r.stage("S5")
            if s5.status is StageStatus.COMPLETED:
                self.assertEqual(s5.data["rul"], "unavailable")
                self.assertEqual(s5.data["probability"], "not estimated")
            for c in r.claims():
                self.assertNotRegex(c.text_en.lower(), r"probability of failure is|remaining useful life is \d")

    def test_hypotheses_are_never_marked_verified(self):
        for r in self.reports.values():
            for c in r.claims():
                if c.kind is ClaimKind.HYPOTHESIS:
                    self.assertNotEqual(r.verdicts.get(c.claim_id, ("",))[0], "verified")


class EvidenceTraceabilityTests(unittest.TestCase):
    def test_every_cited_record_exists_and_every_conclusion_cites_something(self):
        for r in run_all(now=NOW):
            if r.stage("S1").status is StageStatus.BLOCKED:
                continue
            data = adapter.load_case(registry.find_case(r.case_id, load_registry())[1])
            ids = {x.record_id for x in data.records}
            for c in r.claims():
                with self.subTest(case=r.case_id, claim=c.claim_id):
                    self.assertTrue(set(c.evidence) <= ids, c.evidence)
                    if c.kind in (ClaimKind.MEASURED, ClaimKind.HYPOTHESIS) and (c.confidence or 0) > 0:
                        self.assertTrue(c.evidence, c.text_en)

    def test_checked_claims_re_verify_against_records(self):
        r = report("P-301/A")
        checked = [c for c in r.claims() if c.check is not None]
        self.assertGreater(len(checked), 8)
        for c in checked:
            self.assertEqual(r.verdicts[c.claim_id][0], "verified", c.text_en)


class VerificationRejectsBadClaimsTests(unittest.TestCase):
    """The verification stage must catch claims that are false or unsupported."""

    def _with_fake_stage(self, claims):
        def fake(ctx):
            return StageResult("S5", "Failure risk and degradation", "Failure Risk", StageStatus.COMPLETED,
                               claims=tuple(claims), data=frozen_map({"risk": "Low", "basis": "test",
                                                                      "rul": "unavailable",
                                                                      "probability": "not estimated"}))
        proto = tuple(StageSpec(s.stage_id, s.name, s.division, fake if s.stage_id == "S5" else s.run,
                                s.depends_on) for s in PROTOCOL)
        return run_examination("P-301/A", now=NOW, stages=proto)

    def test_false_value_claim_is_rejected(self):
        # A-SEN-0001 is a normal vibration reading; claiming it exceeds 7.1 must be rejected
        bad = Claim("S5-01", "S5", ClaimKind.MEASURED, "Vibration was above alarm.",
                    evidence=("A-SEN-0001",), check=Check("vibration_mm_s", ">", 7.1, "all"), key=True)
        r = self._with_fake_stage([bad])
        self.assertEqual(r.verdicts["S5-01"][0], "rejected")
        self.assertEqual(r.stage("S6").status, StageStatus.VERIFICATION_REJECTED)
        self.assertTrue(r.overall_status.startswith("Unverified"))
        self.assertEqual(r.recommendations[0].category, "escalate")

    def test_invented_record_id_is_rejected(self):
        bad = Claim("S5-01", "S5", ClaimKind.FINDING, "Seen in record A-SEN-9999.", evidence=("A-SEN-9999",), key=True)
        r = self._with_fake_stage([bad])
        self.assertEqual(r.verdicts["S5-01"][0], "rejected")
        self.assertIn("A-SEN-9999", r.verdicts["S5-01"][1])

    def test_check_on_records_of_another_parameter_is_rejected(self):
        bad = Claim("S5-01", "S5", ClaimKind.MEASURED, "Temperature high.", evidence=("A-SEN-0001",),
                    check=Check("bearing_temp_c", ">", 80, "any"))
        r = self._with_fake_stage([bad])
        self.assertEqual(r.verdicts["S5-01"][0], "rejected")

    def test_unaddressed_contradiction_fails_verification(self):
        def s2_hiding_contradictions(ctx):
            res = s2_data_integrity.run(ctx)
            return dataclasses.replace(res, claims=tuple(c for c in res.claims if not c.finding_refs))
        proto = tuple(StageSpec(s.stage_id, s.name, s.division,
                                s2_hiding_contradictions if s.stage_id == "S2" else s.run, s.depends_on)
                      for s in PROTOCOL)
        # S4 also cites contradictions through its checks; drop those too
        r = run_examination("P-301/A", now=NOW, stages=tuple(
            StageSpec(s.stage_id, s.name, s.division,
                      (lambda f: (lambda ctx: dataclasses.replace(
                          f(ctx), claims=tuple(c for c in f(ctx).claims
                                               if not any(x.startswith("C-") for x in c.finding_refs)))))(s.run)
                      if s.stage_id == "S4" else s.run, s.depends_on) for s in proto))
        self.assertEqual(r.stage("S6").status, StageStatus.VERIFICATION_REJECTED)

    def test_high_label_downgraded_when_required_evidence_missing(self):
        def s4_overconfident(ctx):
            res = s4_causal.run(ctx)
            ranking = [dict(x) for x in res.data["ranking"]]
            ranking[0]["label"] = "High"                     # pretend the leader is High
            self.assertTrue(ranking[0]["missing"])           # while required evidence is missing
            return dataclasses.replace(res, data=frozen_map({**res.data, "ranking": tuple(ranking)}))
        proto = tuple(StageSpec(s.stage_id, s.name, s.division, s4_overconfident if s.stage_id == "S4" else s.run,
                                s.depends_on) for s in PROTOCOL)
        r = run_examination("P-301/B", now=NOW, stages=proto)
        lead_claim = r.stage("S4").data["ranking"][0]["claim_id"]
        self.assertEqual(r.verdicts[lead_claim][0], "downgraded")
        self.assertEqual(r.leading_label, "Medium")


class OrchestrationTests(unittest.TestCase):
    def test_protocol_order_and_divisions(self):
        self.assertEqual([s.stage_id for s in PROTOCOL], ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"])
        r = report("P-301/C")
        self.assertEqual([d[0] for d in r.divisions()], ["Asset Intelligence", "Trust & Verification",
                                                          "Causal Reasoning", "Failure Risk",
                                                          "Decision Intelligence", "Knowledge Engine"])
        for s in r.stages:
            self.assertGreaterEqual(s.duration_ms, 0)

    def test_a_crashing_stage_is_recorded_and_blocks_dependants_only(self):
        def boom(ctx):
            raise RuntimeError("simulated defect")
        proto = tuple(StageSpec(s.stage_id, s.name, s.division, boom if s.stage_id == "S3" else s.run,
                                s.depends_on) for s in PROTOCOL)
        r = run_examination("P-301/A", now=NOW, stages=proto)
        st = {s.stage_id: s.status for s in r.stages}
        self.assertEqual(st["S3"], StageStatus.FAILED)
        self.assertIn("simulated defect", r.stage("S3").error)
        self.assertEqual(st["S1"], StageStatus.COMPLETED)
        self.assertEqual(st["S2"], StageStatus.COMPLETED)
        for sid in ("S4", "S5", "S6", "S7", "S8"):
            self.assertEqual(st[sid], StageStatus.BLOCKED, sid)
        self.assertTrue(r.overall_status.startswith("Incomplete"))

    def test_unreadable_case_file_does_not_raise(self):
        with tempfile.TemporaryDirectory() as d:
            old = adapter.FIXTURE_DIR
            adapter.FIXTURE_DIR = Path(d)          # the fixture file is missing here
            try:
                r = report("P-302/routine")
            finally:
                adapter.FIXTURE_DIR = old
        self.assertIsNotNone(r.load_error)
        self.assertTrue(all(s.status is StageStatus.BLOCKED for s in r.stages))

    def test_unknown_case_is_a_caller_error(self):
        with self.assertRaises(registry.RegistryError):
            report("NOPE/1")

    def test_results_are_reproducible(self):
        a, b = report("P-301/A"), report("P-301/A")
        da, db = a.to_dict(), b.to_dict()
        for d in (da, db):
            d.pop("duration_ms")
            for s in d["stages"]:
                s.pop("duration_ms")
        self.assertEqual(da, db)
        self.assertEqual(a.report_id, b.report_id)


class IsolationAndImmutabilityTests(unittest.TestCase):
    def test_original_modules_never_import_the_brain(self):
        for f in list(PKG.glob("*.py")) + [PROJECT_ROOT / "app.py"]:
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                elif isinstance(node, ast.Import):
                    names = [n.name for n in node.names]
                for n in names:
                    if f.name == "app.py":
                        continue                     # app.py may import it only behind the flag (tested in smoke tests)
                    self.assertNotIn("reliability", n, f"{f.name} imports {n}")

    def test_adapter_uses_only_public_names(self):
        tree = ast.parse((PKG / "reliability" / "adapter.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 2:
                for n in node.names:
                    self.assertFalse(n.name.startswith("_"), n.name)

    def test_original_observations_and_files_are_unchanged(self):
        files = sorted((PROJECT_ROOT / "data" / "scenarios").glob("*")) + \
            sorted((PROJECT_ROOT / "config").glob("*.json"))
        before = {f: f.read_bytes() for f in files}
        reports = run_all(now=NOW)
        for r in reports:
            if r.input_fingerprint:
                self.assertTrue(r.integrity_ok, r.case_id)
        for f, content in before.items():
            self.assertEqual(f.read_bytes(), content, f)

    def test_brain_types_are_frozen(self):
        r = report("P-301/A")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            r.risk = "Low"   # type: ignore[misc]
        with self.assertRaises(TypeError):
            r.stage("S2").data["grade"] = "A"   # type: ignore[index]
        rec = adapter.load_case(registry.find_case("P-301/A", load_registry())[1]).records[0]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            rec.value = 0   # type: ignore[misc]

    def test_platform_store_is_read_not_written(self):
        from plantproof.storage import Store
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "p.db")
            store.sync_demo_data()
            n_obs, n_hist = store.observation_count(), len(store.list_history())
            fp = whatif.fingerprint(store.observations("C"))
            r = report("P-301/C", store=store)
            self.assertEqual(r.source_label, "PlantProof store, scenario C")
            self.assertEqual((store.observation_count(), len(store.list_history())), (n_obs, n_hist))
            self.assertEqual(whatif.fingerprint(store.observations("C")), fp)
            self.assertEqual(r.leading, "seal_failure")


class RegistryTests(unittest.TestCase):
    def test_registry_and_profiles(self):
        assets = load_registry()
        self.assertEqual([a.asset_id for a in assets], ["P-301", "P-302", "P-303", "K-101"])
        self.assertEqual(registry.supported_types(), ("centrifugal_pump",))
        self.assertIsNone(registry.load_profile("reciprocating_compressor"))
        self.assertIsNone(dict(assets[0].specs).get("speed_rpm"))      # never invented

    def test_invalid_registry_is_refused(self):
        bad = {"assets": [{"asset_id": "X", "name": "x", "type": "t", "criticality": "Huge",
                           "cases": [{"case_id": "X/1", "source": "fixture", "file": "x.csv"}]}]}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.json"
            p.write_text(json.dumps(bad))
            with self.assertRaises(registry.RegistryError):
                registry.load_registry(p)
            bad["assets"][0]["criticality"] = None
            bad["assets"][0]["cases"][0]["source"] = "web"
            p.write_text(json.dumps(bad))
            with self.assertRaises(registry.RegistryError):
                registry.load_registry(p)

    def test_tolerant_reader_reports_bad_rows(self):
        obs, bad = adapter.read_tolerant(PROJECT_ROOT / "data" / "reliability" / "P-303_poor_data.csv")
        self.assertTrue(all(isinstance(o, Observation) for o in obs))
        self.assertEqual({b.record_id for b in bad}, {"P303-SEN-9002", "P303-SEN-9003"})


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ks = KnowledgeStore(Path(self.tmp.name) / "rb.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_saving_is_idempotent_and_separate_from_the_platform(self):
        r = report("P-301/A", knowledge=self.ks)
        uid = self.ks.save_investigation(r)
        self.assertEqual(self.ks.save_investigation(r), uid)
        self.assertEqual(len(self.ks.list_investigations("P-301")), 1)
        import sqlite3
        tables = {t for (t,) in sqlite3.connect(self.ks.path).execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables, {"rb_investigations", "rb_outcomes"})

    def test_unconfirmed_hypotheses_never_become_knowledge(self):
        uid = self.ks.save_investigation(report("P-301/A", knowledge=self.ks))
        self.assertEqual(self.ks.knowledge(), {})
        s8 = report("P-301/A", knowledge=self.ks).stage("S8")
        self.assertEqual(s8.data["similar"], ())
        self.assertTrue(any("never confirmed" in c.text_en for c in s8.claims))
        self.ks.record_outcome(uid, "bearing_wear", "confirmed", "Reliability engineer", "Spalled outer race found.")
        self.assertEqual(len(self.ks.knowledge()["bearing_wear"]["confirmed"]), 1)
        s8 = report("P-301/A", knowledge=self.ks).stage("S8")
        self.assertEqual(s8.data["similar"][0]["mechanism"], "bearing_wear")
        self.assertIn("not evidence for this case", " ".join(c.text_en for c in s8.claims))

    def test_outcome_validation(self):
        uid = self.ks.save_investigation(report("P-301/C"))
        with self.assertRaises(ValueError):
            self.ks.record_outcome(uid, "seal_failure", "probably", "Engineer")
        with self.assertRaises(ValueError):
            self.ks.record_outcome(uid, "seal_failure", "confirmed", "  ")
        with self.assertRaises(ValueError):
            self.ks.record_outcome("nope", "seal_failure", "confirmed", "Engineer")

    def test_compare_investigations(self):
        a = self.ks.get(self.ks.save_investigation(report("P-301/A")))
        c = self.ks.get(self.ks.save_investigation(report("P-301/C")))
        diff = compare(a, c)
        self.assertTrue(diff["same_asset"])
        self.assertEqual(diff["leading"], ("bearing_wear", "seal_failure"))
        self.assertTrue(diff["only_first"] and diff["only_second"])


class ReportExportTests(unittest.TestCase):
    def test_seventeen_sections_and_exports_keep_traceability(self):
        r = report("P-301/C")
        secs = r.sections()
        self.assertEqual(len(secs), 17)
        self.assertEqual(secs[-1][0], "17. Traceability")
        md, html, js, csv_text = r.to_markdown(), r.to_html(), r.to_json(), r.evidence_csv()
        for rid in ("C-SEN-0321", "C-LAB-0002", "C-INS-0002"):
            self.assertIn(rid, md)
            self.assertIn(rid, csv_text)
        self.assertIn("not a certified diagnosis", md)
        self.assertIn("<!doctype html>", html)
        self.assertEqual(json.loads(js)["report_id"], r.report_id)
        self.assertTrue(json.loads(js)["integrity_ok"])

    def test_html_report_escapes_text(self):
        self.assertNotIn("<script", report("P-303/poor-data").to_html().lower())


if __name__ == "__main__":
    unittest.main()
