import unittest

from plantproof import whatif
from plantproof.domain import SCENARIO_DIR, load_engine_config, read_observations_csv
from plantproof.whatif import WhatIfChange as C


def load(sid):
    return read_observations_csv(SCENARIO_DIR / f"scenario_{sid}.csv")


class WhatIfTests(unittest.TestCase):
    cfg = load_engine_config()

    def test_originals_never_modified(self):
        obs = load("A")
        snapshot = [o.to_dict() for o in obs]
        changes = [C("override_value", {"record_id": "A-LAB-0001", "value": 10}),
                   C("scale_parameter", {"parameter": "vibration_mm_s", "factor": 0.5}),
                   C("exclude_source", {"source_type": "operator_log"}),
                   C("add_record", {"parameter": "alignment_offset_mm", "value": 0.3})]
        res = whatif.run_whatif(obs, self.cfg, changes)
        self.assertTrue(res.originals_unchanged)
        self.assertEqual([o.to_dict() for o in obs], snapshot)
        self.assertEqual(len(obs), len(snapshot))

    def test_override_changes_ranking(self):
        res = whatif.run_whatif(load("A"), self.cfg,
                                [C("override_value", {"record_id": "A-LAB-0001", "value": 15})])
        row = next(r for r in res.comparison() if r["hypothesis_id"] == "bearing_wear")
        self.assertLess(row["scenario_confidence"], row["baseline_confidence"])

    def test_added_evidence_closes_gap(self):
        res = whatif.run_whatif(load("A"), self.cfg,
                                [C("add_record", {"parameter": "alignment_offset_mm", "value": 0.03})])
        self.assertIn("inspection:alignment_offset_mm", res.set_changes()["missing_resolved"])
        added = [o for o in whatif.apply_changes(load("A"), res.changes) if o.hypothetical]
        self.assertEqual(added[0].record_id, "WHATIF-001")

    def test_new_calibration_resolves_stale_evidence(self):
        res = whatif.run_whatif(load("B"), self.cfg,
                                [C("add_record", {"parameter": "vib_sensor_cal"})])
        self.assertIn("calibration:vib_sensor_cal", res.set_changes()["missing_resolved"])

    def test_exclude_source_removes_contradiction(self):
        res = whatif.run_whatif(load("A"), self.cfg,
                                [C("exclude_source", {"source_type": "operator_log"})])
        self.assertIn("A-OPS-0004", res.set_changes()["contradictions_resolved"])

    def test_unknown_record_rejected(self):
        with self.assertRaises(ValueError):
            whatif.apply_changes(load("A"), [C("override_value", {"record_id": "NOPE", "value": 1})])
        with self.assertRaises(ValueError):
            whatif.WhatIfChange.from_dict({"kind": "delete_everything"})

    def test_serialisation_round_trip(self):
        ch = C("scale_parameter", {"parameter": "vibration_mm_s", "factor": 0.8})
        self.assertEqual(C.from_dict(ch.to_dict()), ch)
        self.assertIn("0.8", ch.describe())


if __name__ == "__main__":
    unittest.main()
