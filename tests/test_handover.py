import json
import unittest
from datetime import datetime, timezone

from plantproof import cost_model, handover
from plantproof.domain import (SCENARIO_DIR, load_engine_config, load_scenario_index,
                               read_observations_csv)
from plantproof.evidence_engine import analyse


class HandoverTests(unittest.TestCase):
    def setUp(self):
        self.res = analyse(read_observations_csv(SCENARIO_DIR / "scenario_A.csv"),
                           load_engine_config())
        self.meta = load_scenario_index()[0]

    def test_markdown_contains_traceable_sections(self):
        est = cost_model.estimate("bearing_wear", cost_model.load_cost_assumptions())
        doc = handover.build_handover(self.res, self.meta, shift="Night", outgoing="Day lead",
                                      incoming="Night lead", notes="Check P-301 before restart",
                                      cost=est, whatif_notes=["Alignment test"],
                                      now=datetime(2026, 10, 14, 6, 0, tzinfo=timezone.utc))
        md = doc.to_markdown()
        for text in ("# Shift handover", "Bearing wear", "A-OPS-0004", "A-INS-0002",
                     "Laser shaft alignment check", "£24,970", "Alignment test",
                     "Check P-301 before restart", "2026-10-14 06:00 UTC"):
            self.assertIn(text, md)
        self.assertEqual(json.loads(doc.to_json())["scenario_id"], "A")

    def test_without_cost_and_long_notes(self):
        doc = handover.build_handover(self.res, self.meta, shift="Day", notes="x" * 5000)
        self.assertIsNone(doc.cost)
        self.assertEqual(len(doc.notes), handover.MAX_NOTES)
        self.assertNotIn("Cost impact", doc.to_markdown())

    def test_actions_cover_every_gap(self):
        doc = handover.build_handover(self.res, self.meta, shift="Day")
        text = " ".join(doc.actions)
        for f in self.res.contradictions + self.res.missing:
            self.assertIn(f.finding_id, text)


if __name__ == "__main__":
    unittest.main()
