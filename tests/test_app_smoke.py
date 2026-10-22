"""Smoke test: run app.py with a fake Streamlit on every page and scenario.

This catches Python errors in the UI layer. It cannot check real Streamlit
rendering or argument names - see tests/fake_streamlit.py.
"""

import os
import runpy
import sys
import tempfile
import unittest
from pathlib import Path

from tests.fake_streamlit import (FakeStreamlit, RerunSignal, SessionState,
                                  make_plotly_modules)

APP = Path(__file__).resolve().parent.parent / "app.py"
PAGES = ("Overview", "Evidence", "What If", "Blind Test", "Cost", "History", "Handover")


class AppSmokeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["PLANTPROOF_DB"] = str(Path(self.tmp.name) / "smoke.db")
        self.saved = {k: sys.modules.get(k) for k in ("streamlit", "plotly", "plotly.graph_objects")}

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        os.environ.pop("PLANTPROOF_DB", None)
        self.tmp.cleanup()

    def run_app(self, overrides, press=False, session=None):
        overrides = dict(overrides)
        overrides.setdefault("pp_advisor_side", False)   # "press all" must not jump pages
        overrides.setdefault("pp_advisor_fab", False)
        session = session if session is not None else SessionState()
        if overrides.get("page") == "Advisor":       # Advisor opens from its own button
            overrides["page"] = "Overview"
            session["view"] = "Advisor"
        fake = FakeStreamlit(overrides, press_buttons=press, session=session)
        sys.modules["streamlit"] = fake
        sys.modules.update(make_plotly_modules())
        try:
            runpy.run_path(str(APP), run_name="__main__")
        except RerunSignal:
            pass
        return fake

    def errors(self, fake):
        return [c for c in fake.calls if c[0] == "error"]

    def test_every_page_and_scenario(self):
        for sid in ("A", "B"):
            for page in PAGES:
                for press in (False, True):
                    with self.subTest(sid=sid, page=page, press=press):
                        fake = self.run_app({"page": page, "scenario": sid}, press)
                        self.assertEqual(self.errors(fake), [])

    def test_custom_whatif_builder(self):
        session = SessionState()
        overrides = {"page": "What If", "scenario": "A", "wi_preset": "Custom",
                     "wi_excl": ["operator_log"], "wi_ovr_on": True, "wi_scale_on": True,
                     "wi_add_on": True}
        fake = self.run_app(overrides, press=True, session=session)
        self.assertEqual(self.errors(fake), [])
        self.assertIn("whatif_result", session)
        self.assertTrue(session["whatif_result"][1].originals_unchanged)

    def test_analyst_blind_test_and_handover_flow(self):
        session = SessionState()
        fake = self.run_app({"page": "Blind Test", "scenario": "B"}, press=True, session=session)
        self.assertEqual(self.errors(fake), [])
        self.assertIn("bt_analyst", session)
        self.assertIn("bt_engine", session)
        fake = self.run_app({"page": "Handover", "scenario": "B"}, press=True, session=session)
        names = [c[2].get("file_name", "") for c in fake.calls if c[0] == "download_button"]
        self.assertTrue(any(n.endswith(".html") for n in names))

    def test_advisor_chat_in_arabic(self):
        session = SessionState()
        fake = self.run_app({"page": "Advisor", "scenario": "B",
                             "adv_input": "هل إعادة التشغيل آمنة؟"}, session=session)
        self.assertEqual(self.errors(fake), [])
        chat = session["advisor_chat"][1]
        self.assertEqual(chat[-1][1].intent, "restart")

    def test_advisor_handover_draft(self):
        session = SessionState()
        fake = self.run_app({"page": "Advisor", "scenario": "B",
                             "adv_input": "سلّم الوردية: عطل في الحساس"},
                            press=True, session=session)
        self.assertEqual(self.errors(fake), [])
        names = [c[2].get("file_name", "") for c in fake.calls if c[0] == "download_button"]
        self.assertTrue(any("advisor" in n for n in names))

    def test_advisor_summary_after_saved_handover(self):
        session = SessionState()
        self.run_app({"page": "Advisor", "scenario": "B",
                      "adv_input": "سلّم الوردية: عطل في الحساس"}, press=True, session=session)
        fake = self.run_app({"page": "Advisor", "scenario": "B",
                             "adv_input": "عطني ملخص للشفت الاخير"}, session=session)
        self.assertEqual(self.errors(fake), [])
        ans = session["advisor_chat"][1][-1][1]
        self.assertEqual(ans.intent, "summary")
        self.assertEqual(ans.title_en, "Last shift summary")

    def test_advisor_survives_answers_from_older_version(self):
        class OldAnswer:  # mimics an answer object saved before 'attachment' existed
            intent, title_en, title_ar, items, note_en, note_ar = "help", "x", "x", [], "", ""
        session = SessionState()
        session["advisor_chat"] = ("A", [("old question", OldAnswer())])
        fake = self.run_app({"page": "Advisor", "scenario": "A"}, session=session)
        self.assertEqual(self.errors(fake), [])

    def test_advisor_buttons_open_advisor(self):
        session = SessionState()
        fake = self.run_app({"page": "Overview", "scenario": "A", "pp_advisor_fab": True},
                            session=session)
        self.assertEqual(session.get("view"), "Advisor")
        labels = [c[1][0] for c in fake.calls if c[0] == "button"]
        self.assertTrue(any("AI Advisor" in str(x) for x in labels))
        fake = self.run_app({"page": "Overview", "scenario": "A"}, session=session)
        titles = " ".join(str(c[1]) for c in fake.calls if c[0] == "title")
        self.assertIn("Engineering advisor", titles)

    def test_history_page_shows_warning_and_export(self):
        fake = self.run_app({"page": "History", "scenario": "A"})
        warnings = " ".join(str(c[1]) for c in fake.calls if c[0] == "warning")
        self.assertIn("not guaranteed to persist", warnings)
        self.assertTrue(any(c[0] == "download_button" for c in fake.calls))


if __name__ == "__main__":
    unittest.main()
