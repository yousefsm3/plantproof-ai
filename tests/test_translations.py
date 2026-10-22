import ast
import unittest
from pathlib import Path

from plantproof import whatif
from plantproof.domain import load_engine_config, load_scenario_index
from plantproof.translations import AR, ar, bi, bi_plain

APP = Path(__file__).resolve().parent.parent / "app.py"


class TranslationTests(unittest.TestCase):
    def test_helpers(self):
        self.assertEqual(bi("Overview"), "Overview :small[:gray[نظرة عامة]]")
        self.assertEqual(bi_plain("Bearing wear"), "Bearing wear · تآكل المحمل")
        self.assertEqual(bi("no such text"), "no such text")

    def test_no_markdown_breaking_characters(self):
        for en, a in AR.items():
            self.assertNotIn("]", a, en)
            self.assertTrue(a.strip(), en)

    def test_config_text_is_translated(self):
        cfg = load_engine_config()
        for h in cfg.hypotheses:
            for text in [h.name, *h.recommended_actions,
                         *[r.label for r in h.supports + h.refutes],
                         *[r.label for r in h.required]]:
                self.assertTrue(ar(text), f"missing Arabic for: {text}")
        for c in cfg.cross_checks:
            self.assertTrue(ar(f"{c.label} disagree"), c.label)
        for s in load_scenario_index():
            self.assertTrue(ar(s["title"]) and ar(s["asset_name"]), s["id"])
        for t in whatif.EVIDENCE_TEMPLATES.values():
            self.assertTrue(ar(t["label"]), t["label"])

    def test_every_bi_literal_in_app_is_translated(self):
        tree = ast.parse(APP.read_text(encoding="utf-8"))
        literals = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in ("bi", "bi_plain", "with_ar", "page_header")):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                            and len(arg.value) > 2:
                        literals.append(arg.value)
        self.assertGreater(len(literals), 50)
        missing = [x for x in literals if not ar(x)]
        self.assertEqual(missing, [])

if __name__ == "__main__":
    unittest.main()
