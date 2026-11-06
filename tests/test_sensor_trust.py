import copy
import unittest

from plantproof import sensor_trust
from plantproof.domain import SCENARIO_DIR, read_observations_csv


def load(sid):
    return read_observations_csv(SCENARIO_DIR / f"scenario_{sid}.csv")


class SensorTrustTests(unittest.TestCase):
    def test_bearing_case_is_a_real_machine_fault(self):
        v = sensor_trust.assess(load("A"))
        self.assertEqual(v.verdict, "machine")
        self.assertIsNone(v.suspect)

    def test_lying_transmitter_is_flagged_as_the_sensor(self):
        v = sensor_trust.assess(load("B"))
        self.assertEqual(v.verdict, "sensor")
        self.assertEqual(v.suspect, "vibration_mm_s")
        self.assertEqual(v.support, "High")
        cited = {i for c in v.clues for i in c.record_ids}
        self.assertTrue({"B-INS-0001", "B-CAL-0001"} <= cited)   # handheld and calibration cited

    def test_seal_case_is_a_real_machine_fault(self):
        self.assertEqual(sensor_trust.assess(load("C")).verdict, "machine")

    def test_thin_data_is_undetermined_not_guessed(self):
        self.assertEqual(sensor_trust.assess(load("A")[:40]).verdict, "undetermined")

    def test_healthy_window_is_normal(self):
        obs = [o for o in load("A") if o.timestamp < "2026-10-13T06:00:00" or o.source_type != "sensor"]
        v = sensor_trust.assess(obs)
        self.assertIn(v.verdict, ("normal", "undetermined"))

    def test_observations_are_not_changed(self):
        obs = load("B")
        before = copy.deepcopy(obs)
        sensor_trust.assess(obs)
        self.assertEqual(obs, before)

    def test_every_clue_cites_records(self):
        for sid in "ABC":
            for c in sensor_trust.assess(load(sid)).clues:
                self.assertTrue(c.record_ids, (sid, c.text))


if __name__ == "__main__":
    unittest.main()
