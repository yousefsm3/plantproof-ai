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
                                  make_components_modules, make_plotly_modules)

APP = Path(__file__).resolve().parent.parent / "app.py"
PAGES = ("Overview", "AI Early Warning", "Evidence", "AI Fact Check", "Live Sensor", "What If",
         "Blind Test", "Cost", "History", "Handover")


class AppSmokeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["PLANTPROOF_DB"] = str(Path(self.tmp.name) / "smoke.db")
        self.saved = {k: sys.modules.get(k) for k in ("streamlit", "plotly", "plotly.graph_objects",
                                              "streamlit.components", "streamlit.components.v1")}

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        os.environ.pop("PLANTPROOF_DB", None)
        self.tmp.cleanup()

    def run_app(self, overrides, press=False, session=None, query=None):
        overrides = dict(overrides)
        overrides.setdefault("pp_advisor_side", False)   # "press all" must not jump pages
        overrides.setdefault("pp_advisor_fab", False)
        overrides.setdefault("pp_alarm_btn", False)
        overrides.setdefault("pp_ops_side", False)
        session = session if session is not None else SessionState()
        if overrides.get("page") in ("Advisor", "Operations Room"):   # opened from own buttons
            session["view"] = overrides["page"]
            overrides["page"] = "Overview"
        fake = FakeStreamlit(overrides, press_buttons=press, session=session)
        fake.query_params = dict(query or {})
        sys.modules["streamlit"] = fake
        sys.modules.update(make_plotly_modules())
        sys.modules.update(make_components_modules(fake))
        rb_ui = sys.modules.get("reliability_ui")        # a module imported in an earlier run keeps
        if rb_ui is not None and hasattr(rb_ui, "st"):   # its own 'st'; point it at this run's fake
            rb_ui.st = fake
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

    def test_recovers_from_old_modules_left_in_memory(self):
        """Redeploy case: an older plantproof.storage is still in memory (no sync_demo_data)."""
        import plantproof
        import plantproof.storage as old_storage
        plantproof.__dict__.pop("_source_digest", None)

        class OldStore:                      # stands in for the pre-update class
            def __init__(self, *a, **k):
                pass
        real = old_storage.Store
        old_storage.Store = OldStore
        try:
            fake = self.run_app({"page": "Overview", "scenario": "C"})
        finally:
            old_storage.Store = real
        self.assertEqual(self.errors(fake), [])
        self.assertTrue(hasattr(sys.modules["plantproof.storage"].Store, "sync_demo_data"))

    def test_pairing_link_opens_live_sensor_with_code(self):
        session = SessionState()
        fake = self.run_app({"scenario": "A"}, session=session, query={"pair": "123456"})
        self.assertEqual(session.get("page"), "Live Sensor")
        self.assertTrue(any(c[0] == "components.html" for c in fake.calls))
        self.assertEqual(self.errors(fake), [])

    def test_live_alarm_opens_operations_room(self):
        session = SessionState()
        self.run_app({"page": "Live Sensor", "scenario": "C", "pp_alarm_btn": True}, session=session)
        self.assertEqual(session.get("view"), "Operations Room")
        self.assertTrue(session.get("pp_live_alarm"))
        fake = self.run_app({"scenario": "C"}, session=session)
        self.assertEqual(self.errors(fake), [])
        self.assertTrue(any("LIVE ALARM" in str(c[1]) for c in fake.calls))

    def test_operations_room_every_panel_and_advisor(self):
        for sid in ("A", "B", "C"):
            for panel in ("hyp", "cost", "contra", "miss", "ew"):
                session = SessionState()
                session["ops_panel"] = panel
                session["pp_live_alarm"] = "12:00:00 UTC"
                fake = self.run_app({"page": "Operations Room", "scenario": sid,
                                     "Ask :small[:gray[اسأل]]": "هل الزيت سليم؟"},
                                    session=session)
                with self.subTest(sid=sid, panel=panel):
                    self.assertEqual(self.errors(fake), [])
        asked = SessionState()
        self.run_app({"page": "Operations Room", "scenario": "C",
                      "Ask :small[:gray[اسأل]]": "هل الزيت سليم؟"}, press=True, session=asked)
        self.assertEqual(asked.get("ops_answer")[1], "هل الزيت سليم؟")
        cost = SessionState()
        cost["ops_panel"] = "cost"
        fake = self.run_app({"page": "Operations Room", "scenario": "A"}, session=cost)
        shown = " ".join(str(c[1]) for c in fake.calls if c[0] == "markdown")
        for word in ("Best case", "Most likely", "Worst case"):
            self.assertIn(word, shown)

    def test_ops_room_has_its_own_sidebar_button(self):
        session = SessionState()
        self.run_app({"page": "Overview", "scenario": "A", "pp_ops_side": True}, session=session)
        self.assertEqual(session.get("view"), "Operations Room")
        fake = self.run_app({"scenario": "A"}, session=session)
        self.assertTrue(any("Operations Room" in str(c[1]) for c in fake.calls if c[0] == "title"
                            or c[0] == "markdown"))

    # ------------------------------------------------ Reliability Brain feature flag
    def _calls_text(self, fake):
        return " ".join(str(c[1]) for c in fake.calls)

    def test_flag_off_hides_the_brain_completely(self):
        os.environ.pop("PLANTPROOF_RELIABILITY", None)
        session = SessionState()
        session["view"] = "Reliability Brain"          # even if asked for, it must not open
        fake = self.run_app({"page": "Overview", "scenario": "A"}, session=session)
        text = self._calls_text(fake)
        self.assertNotIn("Reliability Brain", text)
        self.assertEqual(self.errors(fake), [])
        self.assertNotIn("reliability_ui", sys.modules)

    def test_flag_on_brain_page_every_case_and_button(self):
        os.environ["PLANTPROOF_RELIABILITY"] = "1"
        os.environ["PLANTPROOF_RB_DB"] = str(Path(self.tmp.name) / "rb.db")
        try:
            for sid in ("A", "B", "C"):
                for press in (False, True):
                    session = SessionState()
                    session["view"] = "Reliability Brain"
                    fake = self.run_app({"page": "Overview", "scenario": sid,
                                         "pp_rb_side": False}, press=press, session=session)
                    with self.subTest(sid=sid, press=press):
                        self.assertEqual(self.errors(fake), [])
                        text = self._calls_text(fake)
                        self.assertIn("Examination progress", text)
                        self.assertIn(f"P-301/{sid}", text)
            for case in ("P-302/routine", "P-303/poor-data", "K-101/routine"):
                session = SessionState()
                session["view"] = "Reliability Brain"
                session["rb_case"] = case
                fake = self.run_app({"page": "Overview", "scenario": "A", "rb_case": case}, session=session)
                with self.subTest(case=case):
                    self.assertEqual(self.errors(fake), [])
            fake = self.run_app({"page": "Operations Room", "scenario": "C"})
            self.assertIn("Highest-priority risk", self._calls_text(fake))
            self.assertEqual(self.errors(fake), [])
        finally:
            os.environ.pop("PLANTPROOF_RELIABILITY", None)
            os.environ.pop("PLANTPROOF_RB_DB", None)

    def test_broken_brain_never_breaks_the_platform(self):
        import types
        os.environ["PLANTPROOF_RELIABILITY"] = "1"
        broken = types.ModuleType("reliability_ui")
        def explode(*a, **k):
            raise RuntimeError("simulated Brain defect")
        broken.render = explode
        broken.ops_summary = explode
        saved = sys.modules.get("reliability_ui")
        sys.modules["reliability_ui"] = broken
        try:
            session = SessionState()
            session["view"] = "Reliability Brain"
            fake = self.run_app({"page": "Overview", "scenario": "A"}, session=session)
            self.assertIn("simulated Brain defect", self._calls_text(fake))
            self.assertTrue(any("Designed" in str(c[1]) for c in fake.calls))   # page finished: footer drawn
            fake = self.run_app({"page": "Operations Room", "scenario": "A"})
            self.assertIn("Reliability Brain summary unavailable", self._calls_text(fake))
            self.assertIn("Most likely cause", self._calls_text(fake))
        finally:
            os.environ.pop("PLANTPROOF_RELIABILITY", None)
            if saved is None:
                sys.modules.pop("reliability_ui", None)
            else:
                sys.modules["reliability_ui"] = saved

    def test_history_page_shows_warning_and_export(self):
        fake = self.run_app({"page": "History", "scenario": "A"})
        warnings = " ".join(str(c[1]) for c in fake.calls if c[0] == "warning")
        self.assertIn("not guaranteed to persist", warnings)
        self.assertTrue(any(c[0] == "download_button" for c in fake.calls))

    # ------------------------------------------------ focused product
    def test_fresh_visit_lands_in_ops_room_with_ai_verdict(self):
        fake = self.run_app({"scenario": "B"}, session=SessionState())
        text = " ".join(str(c[1]) for c in fake.calls)
        self.assertIn("Operations Room", text)
        self.assertIn("MACHINE OR SENSOR?", text)
        self.assertIn("Sensor suspected", text)
        self.assertEqual(self.errors(fake), [])

    def test_focused_pages_render_for_every_scenario(self):
        for sid in ("A", "B", "C"):
            for page in ("Investigation", "Sensor Trust"):
                for press in (False, True):
                    with self.subTest(sid=sid, page=page, press=press):
                        fake = self.run_app({"page": page, "scenario": sid}, press)
                        self.assertEqual(self.errors(fake), [])
                        text = " ".join(str(c[1]) for c in fake.calls)
                        self.assertIn("MACHINE OR SENSOR?", text)

    def test_hidden_tools_are_not_in_the_menu_by_default(self):
        import ast
        tree = ast.parse(APP.read_text(encoding="utf-8"))
        focus = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                     and getattr(n.targets[0], "id", "") == "FOCUS_PAGES")
        names = ast.unparse(focus.value)
        self.assertIn("INV", names)
        self.assertIn("TRUST", names)
        self.assertNotIn("Blind Test", names)
        fake = self.run_app({"page": "Blind Test", "scenario": "A"})   # still reachable by name
        self.assertEqual(self.errors(fake), [])

if __name__ == "__main__":
    unittest.main()
