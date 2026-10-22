import unittest

from plantproof import advisor
from plantproof import cost_model
from plantproof.domain import SCENARIO_DIR, load_engine_config, read_observations_csv
from plantproof.evidence_engine import analyse
from plantproof.whatif import fingerprint


def setup(sid):
    obs = read_observations_csv(SCENARIO_DIR / f"scenario_{sid}.csv")
    cfg = load_engine_config()
    return obs, cfg, analyse(obs, cfg), cost_model.load_cost_assumptions()


class AdvisorTests(unittest.TestCase):
    def test_intents_english_and_arabic(self):
        cases = {"What should I check first?": "checks", "ماذا أفحص أولًا؟": "checks",
                 "Is it safe to restart?": "restart", "هل إعادة التشغيل آمنة؟": "restart",
                 "Why is this hypothesis leading?": "explain", "ليش هذي الفرضية؟": "explain",
                 "What is the action plan?": "plan", "ما خطة العمل؟": "plan",
                 "hello": None, "": None}
        for q, intent in cases.items():
            self.assertEqual(advisor.detect_intent(q), intent, q)

    def test_next_checks_cover_every_gap_and_trace_records(self):
        for sid in ("A", "B"):
            obs, cfg, res, _ = setup(sid)
            checks = advisor.next_best_checks(obs, cfg, res)
            ids = {f.finding_id for f in res.missing + res.contradictions}
            self.assertEqual({c["finding_id"] for c in checks}, ids)
            impacts = [c["impact"] for c in checks]
            self.assertEqual(impacts, sorted(impacts, reverse=True))
            known = {o.record_id for o in obs}
            for c in checks:
                self.assertTrue(set(c["record_ids"]) <= known)

    def test_advisor_never_changes_original_data(self):
        obs, cfg, res, costs = setup("B")
        before = fingerprint(obs)
        for q, _, _ in advisor.SUGGESTED:
            advisor.answer(q, obs, cfg, res, costs)
        self.assertEqual(fingerprint(obs), before)

    def test_restart_not_ready_with_open_contradictions(self):
        for sid in ("A", "B"):
            obs, cfg, res, _ = setup(sid)
            ans = advisor.restart_readiness(res, cfg)
            self.assertTrue(ans.title_en.startswith("Not ready"))
            self.assertIn("procedures", ans.note_en)

    def test_explain_and_plan(self):
        obs, cfg, res, costs = setup("A")
        exp = advisor.explain_leader(res, cfg)
        self.assertIn("Bearing wear", exp.title_en)
        self.assertTrue(any("A-LAB-0001" in i.record_ids for i in exp.items))
        plan = advisor.action_plan(obs, cfg, res, costs)
        self.assertTrue(any("£24,970" in i.en for i in plan.items))

    def test_every_item_has_arabic(self):
        obs, cfg, res, costs = setup("A")
        for q in ("check first", "restart", "why", "plan", "?"):
            for item in advisor.answer(q, obs, cfg, res, costs).items:
                self.assertTrue(item.ar.strip(), item.en)


if __name__ == "__main__":
    unittest.main()
