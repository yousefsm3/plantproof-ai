import unittest

from plantproof import fact_check as fc
from plantproof.domain import load_engine_config
from plantproof.evidence_engine import analyse
from tests.test_evidence_engine import load

S, C, N = fc.SUPPORTED, fc.CONTRADICTED, fc.NO_EVIDENCE


class FactCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_engine_config()
        cls.data = {s: (load(s), analyse(load(s), cls.cfg, s)) for s in "ABC"}

    def verdict(self, sid, text):
        obs, res = self.data[sid]
        return fc.check_sentence(text, obs, res, self.cfg).verdict

    def test_sample_drafts_expose_the_planted_mistakes(self):
        expected = {"A": [S, S, C, C, S, N, C], "B": [S, C, S, S, C, C], "C": [S, S, C, S, C, S, N]}
        for sid, verdicts in expected.items():
            obs, res = self.data[sid]
            for drafts in (fc.SAMPLE_DRAFTS, fc.SAMPLE_DRAFTS_AR):
                got = [c.verdict for c in fc.check(drafts[sid], obs, res, self.cfg)]
                self.assertEqual(got, verdicts, sid)

    def test_arabic_negation_is_not_confused_with_words_starting_with_ma(self):
        self.assertEqual(self.verdict("C", "الزيت فيه ماء كثير"), S)          # ماء is water
        self.assertEqual(self.verdict("C", "مستوى خزان مانع التسريب طبيعي"), C)  # مانع is not "ما"
        self.assertEqual(self.verdict("C", "ما فيه تسريب"), C)

    def test_hypothesis_claims(self):
        self.assertEqual(self.verdict("A", "The root cause is bearing wear."), S)
        self.assertEqual(self.verdict("A", "Bearing wear is ruled out."), C)
        self.assertEqual(self.verdict("C", "السبب مو تآكل المحمل"), S)

    def test_record_ids_and_numbers(self):
        self.assertEqual(self.verdict("B", "See record B-CAL-0099."), C)
        self.assertEqual(self.verdict("C", "Water in oil was 900 ppm."), S)
        self.assertEqual(self.verdict("C", "Water in oil was 120 ppm."), C)

    def test_rising_below_alarm_is_supported_but_high_is_not(self):
        self.assertEqual(self.verdict("C", "Bearing temperature rose."), S)
        self.assertEqual(self.verdict("C", "Bearing temperature was high."), C)

    def test_every_cited_record_exists(self):
        for sid, (obs, res) in self.data.items():
            ids = {o.record_id for o in obs}
            for c in fc.check(fc.SAMPLE_DRAFTS[sid], obs, res, self.cfg):
                self.assertTrue(set(c.record_ids) <= ids)
                self.assertTrue(all(len(r) == 2 and r[1] for r in c.reasons))


if __name__ == "__main__":
    unittest.main()
