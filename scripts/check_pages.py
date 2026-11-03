"""Open every page of the live app in a headless browser and report errors.

Run on demand by .github/workflows/check-pages.yml. Prints one line per page and a
screenshot per page into ./page-shots (uploaded as a workflow artifact).
"""

import base64
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL", "https://plantproof-ai.streamlit.app")
PAGES = ["Overview", "Operations Room", "AI Early Warning", "Evidence", "AI Fact Check", "Live Sensor", "What If",
         "Blind Test", "Cost", "History", "Handover"]
ERRORS = ("Traceback", "Error:", "Exception", "encountered an error")


def app_frame(page):
    for _ in range(60):
        for f in page.frames:
            try:
                if f.get_by_text("PlantProof").count() > 0 and f.locator('[data-testid="stSidebar"]').count():
                    return f
            except Exception:
                pass
        time.sleep(3)
    return None


def main() -> int:
    out = Path("page-shots")
    out.mkdir(exist_ok=True)
    bad = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        try:
            page.get_by_role("button", name="Yes, get this app back up").click(timeout=10_000)
        except Exception:
            pass
        frame = app_frame(page)
        if frame is None:
            print("::error::App did not load")
            return 1
        for name in PAGES:
            try:
                frame.locator('[data-testid="stSidebar"] label').filter(has_text=name).first.click()
                time.sleep(6)
                text = frame.locator("body").inner_text(timeout=10_000)
                hit = next((e for e in ERRORS if e in text), None)
                page.screenshot(path=str(out / f"{name.replace(' ', '_')}.png"), full_page=True)
                if name in os.environ.get("PRINT_SHOTS", "").split(","):
                    jpg = page.screenshot(type="jpeg", quality=55, full_page=True)
                    print(f"SHOT-BEGIN {name}")
                    print(base64.b64encode(jpg).decode())
                    print(f"SHOT-END {name}")
                if hit:
                    bad += 1
                    i = text.index(hit)
                    print(f"::error::{name}: {text[max(0, i - 300):i + 1500]}")
                else:
                    print(f"OK  {name}")
            except Exception as exc:
                bad += 1
                print(f"::error::{name}: could not open ({exc})")
        browser.close()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
