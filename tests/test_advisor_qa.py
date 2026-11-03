import unittest

from plantproof import advisor, cost_model
from plantproof.advisor_qa import _has, normalise
from plantproof.domain import SCENARIO_DIR, load_engine_config, read_observations_csv
from plantproof.evidence_engine import analyse


def setup(sid):
    obs = read_observations_csv(SCENARIO_DIR / f"scenario_{sid}.csv")
    cfg = load_engine_config()
    return obs, cfg, analyse(obs, cfg), cost_model.load_cost_assumptions()


def ask(q, sid="C"):
    obs, cfg, res, costs = setup(sid)
    return advisor.answer(q, obs, cfg, res, costs), {o.record_id for o in obs}


class FreeQuestionTests(unittest.TestCase):
    def test_routing(self):
        cases = {
            "هل الزيت سليم؟": "topic", "is the oil ok?": "topic",
            "متى آخر صيانة؟": "topic", "is there a seal leak?": "topic",
            "why not bearing wear?": "hypothesis", "ليش مو تكهف؟": "hypothesis",
            "C-LAB-0002": "record", "c-lab-0002 please": "record",
            "وش صار قبل التوقف": "timeline", "كم التكلفة": "cost",
            "what's missing?": "missing", "any contradictions?": "contradictions",
            "what did the technician find": "search",
            "ماذا أفحص أولًا؟": "checks", "هل إعادة التشغيل آمنة؟": "restart",
            "عطني ملخص للشفت الاخير": "summary", "qwerty zxcv": "help",
        }
        for q, intent in cases.items():
            self.assertEqual(ask(q)[0].intent, intent, q)

    def test_every_cited_record_exists(self):
        for q in ("is the oil ok?", "متى آخر صيانة؟", "why not bearing wear?", "وش صار قبل التوقف",
                  "how is the suction pressure", "C-INS-0002", "what did the technician find"):
            ans, ids = ask(q)
            for item in ans.items:
                self.assertTrue(set(item.record_ids) <= ids, (q, item.en))
                self.assertTrue(item.ar.strip(), (q, item.en))

    def test_answers_reflect_the_evidence(self):
        ans, _ = ask("is there a seal leak?")
        text = " ".join(i.en for i in ans.items)
        self.assertIn("18 ml/min", text)
        self.assertIn("Crossed the alarm", text)
        ans, _ = ask("when was the last maintenance?")
        self.assertIn("C-MNT-0001", [r for i in ans.items for r in i.record_ids])

    def test_unknown_record_and_no_guessing(self):
        ans, _ = ask("Z-XXX-9999")
        self.assertIn("not in this investigation", ans.items[0].en)
        ans, _ = ask("qwerty zxcv")
        self.assertIn("does not guess", ans.note_en)

    def test_word_boundaries(self):
        q = normalise("the environment is available")
        self.assertFalse(_has(q, ["iron"]))
        self.assertFalse(_has(q, ["lab"]))
        self.assertTrue(_has(normalise("iron levels"), ["iron"]))
        self.assertTrue(_has(normalise("الاهتزاز عالي"), ["اهتزاز"]))


if __name__ == "__main__":
    unittest.main()
