import unittest

from plantproof import cost_model as cm
from plantproof.domain import (SCENARIO_DIR, ConfigError, load_engine_config,
                               read_observations_csv)
from plantproof.evidence_engine import analyse


class CostTests(unittest.TestCase):
    a = cm.load_cost_assumptions()

    def test_hand_calculated_totals(self):
        t = cm.estimate("bearing_wear", self.a).totals
        self.assertEqual(t["low"], 8 * 1200 + 10 * 45 + 1800)
        self.assertEqual(t["base"], 12 * 1800 + 14 * 55 + 2600)
        self.assertEqual(t["high"], 20 * 2600 + 24 * 70 + 4200)
        self.assertTrue(t["low"] <= t["base"] <= t["high"])

    def test_every_hypothesis_has_a_profile(self):
        for h in load_engine_config().hypotheses:
            cm.estimate(h.id, self.a)

    def test_invalid_ranges_rejected(self):
        with self.assertRaises(ConfigError):
            cm.with_overrides(self.a, "bearing_wear",
                              {"parts": {"low": 5000, "base": 100, "high": 200}})
        with self.assertRaises(ConfigError):
            cm.with_overrides(self.a, "bearing_wear",
                              {"parts": {"low": -1, "base": 100, "high": 200}})

    def test_overrides_do_not_change_defaults(self):
        before = cm.estimate("sensor_fault", self.a).totals
        new = cm.with_overrides(self.a, "sensor_fault",
                                {"downtime_hours": {"low": 10, "base": 20, "high": 30}})
        self.assertGreater(cm.estimate("sensor_fault", new).totals["base"], before["base"])
        self.assertEqual(cm.estimate("sensor_fault", self.a).totals, before)

    def test_weighted_estimate(self):
        res = analyse(read_observations_csv(SCENARIO_DIR / "scenario_A.csv"), load_engine_config())
        w = cm.weighted_estimate(res.assessments, self.a)
        self.assertAlmostEqual(sum(r["weight"] for r in w["rows"]), 1.0, places=2)
        self.assertAlmostEqual(w["value"], sum(r["contribution"] for r in w["rows"]), places=0)
        empty = analyse([], load_engine_config(), "A")
        self.assertIsNone(cm.weighted_estimate(empty.assessments, self.a))

    def test_money_format(self):
        self.assertEqual(cm.format_money(24970), "£24,970")


if __name__ == "__main__":
    unittest.main()
