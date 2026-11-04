"""Run against a locally started Streamlit app (real Streamlit, real browser).

Opens each page, records errors, and prints JPEG screenshots (base64) for desktop,
tablet and phone widths so they can be reviewed from the CI log.

Env: APP_URL (default http://localhost:8501), PAGES (comma list), SIZES (comma list of
desktop,tablet,mobile), SHOTS=1 to print screenshots.
"""

import base64
import os
import sys
import time

from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL", "http://localhost:8501")
PAGES = [p for p in os.environ.get("PAGES", "Overview").split(",") if p]
SIZES = {"desktop": (1440, 900), "tablet": (820, 1180), "mobile": (390, 844)}
WANT = [s for s in os.environ.get("SIZES", "desktop,tablet,mobile").split(",") if s]
ERRORS = ("Traceback", "Error:", "Exception", "encountered an error")
BUTTON_PAGES = {"Operations Room", "Reliability Brain"}   # opened from their own sidebar buttons


def wait_ready(page):
    for _ in range(60):
        try:
            if page.locator('[data-testid="stSidebar"]').count() and \
               page.locator('[data-testid="stStatusWidget"]').count() == 0:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def open_page(page, name):
    side = page.locator('[data-testid="stSidebar"]')
    if name in BUTTON_PAGES:
        side.locator("button").filter(has_text=name).first.click()
    else:
        side.locator("label").filter(has_text=name).first.click()
    time.sleep(4)
    wait_ready(page)
    time.sleep(2)


def shot(page, tag):
    if os.environ.get("SHOTS") == "1":
        jpg = page.screenshot(type="jpeg", quality=50, full_page=True)
        print(f"SHOT-BEGIN {tag}")
        print(base64.b64encode(jpg).decode())
        print(f"SHOT-END {tag}")


def main() -> int:
    bad = 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1440, "height": 900})
        page.goto(URL, wait_until="domcontentloaded", timeout=90_000)
        if not wait_ready(page):
            print("::error::app did not load")
            return 1
        for name in PAGES:
            page.set_viewport_size({"width": 1440, "height": 900})
            time.sleep(1)
            try:
                open_page(page, name)
            except Exception as exc:
                print(f"::error::{name}: cannot open ({exc})")
                bad += 1
                continue
            text = page.locator("body").inner_text()
            hit = next((e for e in ERRORS if e in text), None)
            if hit:
                i = text.index(hit)
                print(f"::error::{name}: {text[max(0, i - 200):i + 1200]}")
                bad += 1
            else:
                print(f"OK  {name}")
            # money in dollars: no "$...$" read as maths, no stray escape backslashes
            katex = page.locator(".katex").count()
            slash = "\\$" in text
            if katex or slash:
                print(f"::error::{name}: dollar rendering (katex={katex}, backslash={slash})")
                bad += 1
            dollars = [m for m in text.split() if m.startswith("$")][:3]
            print(f"     {name} dollars: {dollars}")
            for size in WANT:
                w, h = SIZES[size]
                page.set_viewport_size({"width": w, "height": h})
                time.sleep(2)
                over = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
                if over > 4:
                    print(f"WARN {name} [{size}] horizontal overflow {over}px")
                shot(page, f"{name}|{size}")
        b.close()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
