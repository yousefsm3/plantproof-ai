import dataclasses
import json
import unittest
from pathlib import Path

from plantproof.domain import (HYPOTHESES_PATH, SCENARIO_DIR, load_engine_config,
                               parse_engine_config, read_observations_csv)
from plantproof.evidence_engine import analyse

PKG = Path(__file__).resolve().parent.parent / "plantproof"


def load(sid):
    return read_observations_csv(SCENARIO_DIR / f"scenario_{sid}.csv")


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_engine_config()
        cls.a, cls.b = analyse(load("A"), cls.cfg), analyse(load("B"), cls.cfg)

    def test_leading_hypotheses(self):
        self.assertEqual(self.a.top.hypothesis_id, "bearing_wear")
        self.assertEqual(self.a.top.confidence_label, "High")
        self.assertEqual(self.b.top.hypothesis_id, "sensor_fault")

    def test_contradictions_detected(self):
        self.assertEqual({c.key for c in self.a.contradictions}, {"A-OPS-0004", "A-INS-0002"})
        self.assertEqual({c.key for c in self.b.contradictions}, {"B-OPS-0003", "B-INS-0001"})

    def test_missing_and_stale_evidence(self):
        self.assertEqual({m.key for m in self.a.missing},
                         {"inspection:alignment_offset_mm", "inspection:strainer_dp_bar"})
        stale = [m for m in self.b.missing if m.key == "calibration:vib_sensor_cal"]
        self.assertEqual(len(stale), 1)
        self.assertIn("Out of date", stale[0].detail)
        self.assertEqual(stale[0].record_ids, ("B-CAL-0001",))

    def test_every_finding_traces_to_real_records(self):
        for sid, res in (("A", self.a), ("B", self.b)):
            ids = {o.record_id for o in load(sid)}
            for f in res.all_findings():
                self.assertTrue(set(f.record_ids) <= ids, f.finding_id)
                if f.kind in ("contradiction", "support", "refute"):
                    self.assertTrue(f.record_ids, f"{f.finding_id} has no source records")

    def test_input_not_modified(self):
        obs = load("A")
        snapshot = [o.to_dict() for o in obs]
        analyse(obs, self.cfg)
        self.assertEqual([o.to_dict() for o in obs], snapshot)

    def test_deterministic(self):
        self.assertEqual(analyse(load("A"), self.cfg).to_dict(), self.a.to_dict())

    def test_confidence_bounds_and_ranks(self):
        for res in (self.a, self.b):
            self.assertEqual([x.rank for x in res.assessments], [1, 2, 3, 4])
            for x in res.assessments:
                self.assertGreaterEqual(x.confidence, 0)
                self.assertLessEqual(x.confidence, 1)

    def test_empty_input(self):
        res = analyse([], self.cfg, "A")
        self.assertEqual(res.record_count, 0)
        self.assertEqual(res.contradictions, [])
        self.assertTrue(all(x.confidence == 0 for x in res.assessments))

    def test_config_drives_result(self):
        raw = json.loads(HYPOTHESES_PATH.read_text(encoding="utf-8"))
        raw["alarm_limits"]["vibration_mm_s"]["alarm"] = 50
        raw["alarm_limits"]["bearing_temp_c"]["alarm"] = 200
        res = analyse(load("A"), parse_engine_config(raw))
        self.assertEqual([c.key for c in res.contradictions], [])

    def test_engine_never_reads_reference_answers(self):
        for name in ("evidence_engine.py", "domain.py", "whatif.py"):
            src = (PKG / name).read_text(encoding="utf-8")
            self.assertNotIn("reference_answers", src, name)
            self.assertNotIn("blind_test", src, name)


if __name__ == "__main__":
    unittest.main()
