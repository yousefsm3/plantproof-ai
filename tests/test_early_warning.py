import unittest

from plantproof import early_warning as ew
from plantproof.domain import load_engine_config
from tests.test_evidence_engine import load


class EarlyWarningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_engine_config()
        cls.res = {s: ew.detect(load(s), cls.cfg.limits) for s in "ABC"}

    def test_warns_hours_before_alarm_on_gradual_faults(self):
        self.assertGreaterEqual(self.res["A"].lead_hours, 6)     # bearing wear
        self.assertGreaterEqual(self.res["C"].lead_hours, 6)     # seal leak
        self.assertEqual(self.res["C"].first_warning.drivers[0][0], "seal_pot_level_pct")

    def test_sudden_sensor_step_has_no_fake_lead_time(self):
        b = self.res["B"]
        self.assertEqual(b.lead_hours, 0)
        movers = {p for h in b.hours if h.flagged for p, _z in h.drivers}
        self.assertEqual(movers, {"vibration_mm_s"})

    def test_no_flags_inside_training_window(self):
        for r in self.res.values():
            self.assertFalse(any(h.flagged for h in r.hours[:r.train_hours]))

    def test_warning_records_exist(self):
        for s, r in self.res.items():
            ids = {o.record_id for o in load(s)}
            self.assertTrue(set(r.first_warning.record_ids) <= ids)

    def test_too_little_data(self):
        self.assertIsNone(ew.detect(load("A")[:20], self.cfg.limits))


if __name__ == "__main__":
    unittest.main()
