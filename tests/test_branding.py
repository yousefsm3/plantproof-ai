import base64
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"


class BrandingTests(unittest.TestCase):
    def test_assets_are_valid_svg(self):
        for name in ("logo.svg", "equipment.svg"):
            root = ET.parse(ASSETS / name).getroot()
            self.assertTrue(root.tag.endswith("svg"), name)
            self.assertTrue(root.get("viewBox"), name)

    def test_assets_are_original_and_self_contained(self):
        for name in ("logo.svg", "equipment.svg"):
            text = (ASSETS / name).read_text(encoding="utf-8").lower()
            self.assertNotIn("href=\"http", text, name)   # no external images
            self.assertNotIn("<image", text, name)        # drawn shapes only
            self.assertNotIn("aramco", text, name)        # no third-party brand

    def test_data_uri_round_trip(self):
        raw = (ASSETS / "logo.svg").read_bytes()
        uri = "data:image/svg+xml;base64," + base64.b64encode(raw).decode()
        self.assertEqual(base64.b64decode(uri.split(",", 1)[1]), raw)

    def test_app_shows_disclaimer(self):
        src = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("Not affiliated with or endorsed by", src)
        self.assertNotIn("aramco", src.lower())


if __name__ == "__main__":
    unittest.main()
