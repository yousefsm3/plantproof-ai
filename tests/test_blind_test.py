import ast
import unittest
from pathlib import Path

from plantproof import blind_test as bt
from plantproof.domain import SCENARIO_DIR, load_engine_config, read_observations_csv
from plantproof.evidence_engine import analyse

PKG = Path(__file__).resolve().parent.parent / "plantproof"


class BlindTestTests(unittest.TestCase):
    cfg = load_engine_config()

    def test_engine_scores_on_both_scenarios(self):
        for sid in ("A", "B"):
            res = analyse(read_observations_csv(SCENARIO_DIR / f"scenario_{sid}.csv"), self.cfg)
            score = bt.score(bt.submission_from_analysis(res), bt.load_reference(sid))
            self.assertEqual(score.total, 100.0, sid)
            self.assertEqual(score.grade, "Excellent")

    def test_partial_answers(self):
        ref = bt.load_reference("A")
        sub = bt.Submission(["misalignment", "bearing_wear"], {"A-OPS-0004", "A-OPS-0001"}, set())
        s = bt.score(sub, ref)
        root, contra, missing = s.components
        self.assertEqual(root.points, 25)
        self.assertEqual(contra.true_positives, ["A-OPS-0004"])
        self.assertEqual(contra.false_positives, ["A-OPS-0001"])
        self.assertEqual(contra.false_negatives, ["A-INS-0002"])
        self.assertAlmostEqual(contra.points, 15.0)  # F1 = 0.5
        self.assertEqual(missing.points, 0)
        self.assertEqual(s.total, 40.0)

    def test_wrong_root_cause(self):
        s = bt.score(bt.Submission(["cavitation", "misalignment"]), bt.load_reference("B"))
        self.assertEqual(s.components[0].points, 0)

    def test_unknown_scenario(self):
        with self.assertRaises(KeyError):
            bt.load_reference("Z")

    def test_reference_file_only_read_by_blind_test(self):
        # translations.py only contains UI sentences that mention the file name.
        users = [p.name for p in PKG.glob("*.py") if p.name != "translations.py"
                 and "reference_answers" in p.read_text(encoding="utf-8")]
        tree = ast.parse((PKG / "translations.py").read_text(encoding="utf-8"))
        imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                   and getattr(n, "module", None) != "__future__"]
        opens = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == "open"]
        self.assertEqual((imports, opens), ([], []))
        self.assertEqual(users, ["blind_test.py"])


if __name__ == "__main__":
    unittest.main()
