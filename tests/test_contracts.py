"""Phase 0 regression protection: pin the public interfaces and golden outputs that the
Reliability Brain reads. If any of these change, the Brain's adapter must be reviewed.

These tests describe the platform as it was before the Brain was added (commit d69624a).
They must never be edited to make a regression pass.
"""

import dataclasses
import inspect
import unittest

from plantproof import advisor, cost_model, early_warning, whatif
from plantproof.domain import (OBS_FIELDS, AnalysisResult, Finding, HypothesisAssessment,
                               Observation, load_engine_config, load_scenario_index)
from plantproof.evidence_engine import analyse
from plantproof.storage import Store
from tests.test_evidence_engine import load

GOLDEN = {   # scenario -> (fingerprint, [(hypothesis, confidence, label)], contradictions, missing)
    "A": ("9419075f6f336a95", [("bearing_wear", 0.81, "High"), ("misalignment", 0.113, "Low")],
          ["C-01", "C-02"], ["M-01", "M-02"]),
    "B": ("3d837dd4efb8c033", [("sensor_fault", 0.608, "High"), ("misalignment", 0.101, "Low")],
          ["C-01", "C-02"], ["M-01", "M-02", "M-03"]),
    "C": ("d5ddc769a3a6e78e", [("seal_failure", 0.9, "High"), ("misalignment", 0.125, "Low")],
          ["C-01"], ["M-01", "M-02"]),
}
EW_LEAD = {"A": 12.0, "B": 0.0, "C": 19.0}


class DomainContractTests(unittest.TestCase):
    def test_observation_fields_and_immutability(self):
        self.assertEqual(OBS_FIELDS, ("record_id", "scenario_id", "timestamp", "asset_id",
                                      "source_type", "parameter", "value", "unit", "status",
                                      "subject", "text", "source", "hypothetical"))
        self.assertTrue(Observation.__dataclass_params__.frozen)
        o = load("A")[0]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            o.value = 1.0   # type: ignore[misc]

    def test_result_types_expose_the_fields_the_brain_reads(self):
        a_fields = {f.name for f in dataclasses.fields(HypothesisAssessment)}
        self.assertTrue({"hypothesis_id", "name", "confidence", "confidence_label", "rank",
                         "coverage", "supporting", "refuting", "missing",
                         "recommended_actions"} <= a_fields)
        f_fields = {f.name for f in dataclasses.fields(Finding)}
        self.assertTrue({"finding_id", "kind", "title", "detail", "record_ids",
                         "hypothesis_ids", "key"} <= f_fields)
        r_fields = {f.name for f in dataclasses.fields(AnalysisResult)}
        self.assertTrue({"scenario_id", "record_count", "assessments", "contradictions",
                         "missing"} <= r_fields)
        self.assertEqual(sorted(analyse(load("A"), load_engine_config(), "A").to_dict()),
                         ["assessments", "contradictions", "missing", "record_count",
                          "scenario_id", "window_end", "window_start"])

    def test_public_signatures(self):
        self.assertEqual(list(inspect.signature(analyse).parameters),
                         ["observations", "config", "scenario_id"])
        self.assertEqual(list(inspect.signature(early_warning.detect).parameters)[:2],
                         ["observations", "limits"])
        self.assertEqual(list(inspect.signature(cost_model.estimate).parameters),
                         ["hypothesis_id", "assumptions"])
        self.assertEqual(list(inspect.signature(whatif.fingerprint).parameters), ["observations"])
        for name in ("observations", "list_history", "save", "observation_count"):
            self.assertTrue(callable(getattr(Store, name)), name)

    def test_scenario_index(self):
        ids = [s["id"] for s in load_scenario_index()]
        self.assertEqual(ids, ["A", "B", "C"])
        for s in load_scenario_index():
            self.assertTrue({"id", "title", "asset_id", "asset_name", "summary", "file"} <= set(s))


class GoldenOutputTests(unittest.TestCase):
    """The engine's results for the shipped scenarios, as recorded before the Brain."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = load_engine_config()

    def test_fingerprints_and_engine_results(self):
        for sid, (fp, top2, contra, missing) in GOLDEN.items():
            with self.subTest(sid=sid):
                obs = load(sid)
                self.assertEqual(whatif.fingerprint(obs), fp)
                r = analyse(obs, self.cfg, sid)
                got = [(a.hypothesis_id, round(a.confidence, 3), a.confidence_label)
                       for a in r.assessments[:2]]
                self.assertEqual(got, top2)
                self.assertEqual([f.finding_id for f in r.contradictions], contra)
                self.assertEqual([f.finding_id for f in r.missing], missing)
                self.assertEqual(whatif.fingerprint(obs), fp)   # input untouched

    def test_early_warning_leads(self):
        for sid, lead in EW_LEAD.items():
            with self.subTest(sid=sid):
                self.assertEqual(early_warning.detect(load(sid), self.cfg.limits).lead_hours, lead)

    def test_cost_and_next_checks_shape(self):
        totals = cost_model.estimate("bearing_wear", cost_model.load_cost_assumptions()).totals
        self.assertEqual(set(totals), {"low", "base", "high"})
        self.assertTrue(totals["low"] <= totals["base"] <= totals["high"])
        obs = load("A")
        checks = advisor.next_best_checks(obs, self.cfg, analyse(obs, self.cfg, "A"))
        self.assertTrue(checks)
        self.assertTrue({"kind", "key", "finding_id", "title", "title_ar", "record_ids",
                         "impact"} <= set(checks[0]))


if __name__ == "__main__":
    unittest.main()
