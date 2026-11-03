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


def alarm_flow(page, frame) -> bool:
    """Live Sensor demo -> fault -> red alarm bar -> click -> Operations Room shows LIVE ALARM."""
    frame.locator('[data-testid="stSidebar"] label').filter(has_text="Live Sensor").first.click()
    sensor = None
    for _ in range(30):
        time.sleep(1)
        for f in page.frames:
            try:
                if f.locator("#tLocal").count():
                    sensor = f
            except Exception:
                pass
        if sensor:
            break
    if sensor is None:
        print("::error::alarm flow: live sensor widget not found")
        return False
    sensor.click("#tLocal")
    sensor.click("#btnDemo")
    time.sleep(13)
    for _ in range(3):
        sensor.click("#btnFault")
    time.sleep(3)
    bar = frame.locator("#pp-live-alarm")
    print("alarm bar shown:", bar.count() == 1, "| widget:", sensor.text_content("#status").strip()[:60])
    if bar.count() != 1:
        return False
    bar.click()
    time.sleep(6)
    text = frame.locator("body").inner_text(timeout=10_000)
    ok = "LIVE ALARM" in text and "Operations Room" in text
    print("operations room opened with LIVE ALARM:", ok)
    if "Operations Room" in os.environ.get("PRINT_SHOTS", ""):
        jpg = page.screenshot(type="jpeg", quality=55, full_page=True)
        print("SHOT-BEGIN Alarm")
        print(base64.b64encode(jpg).decode())
        print("SHOT-END Alarm")
    return ok


def hard_limit_flow(page, frame) -> bool:
    """Feed the device-motion sensor: steady for 11 s, then a vibration above 55 -> alarm bar."""
    frame.locator('[data-testid="stSidebar"] label').filter(has_text="Live Sensor").first.click()
    sensor = None
    for _ in range(30):
        time.sleep(1)
        sensor = next((f for f in page.frames if _has(f, "#tLocal")), None)
        if sensor:
            break
    if sensor is None:
        return False
    print("widget version:", "sensor v1.3" in sensor.locator("body").inner_text())
    sensor.click("#tLocal")
    sensor.click("#btnPhone")
    sensor.evaluate("""() => { window.__amp = 0.3; setInterval(() => window.dispatchEvent(
        new DeviceMotionEvent('devicemotion', {acceleration: {x: window.__amp + Math.random() * 0.02, y: 0, z: 0}})), 20); }""")
    time.sleep(12)
    print("before shake:", sensor.text_content("#status").strip()[:50])
    sensor.evaluate("() => { window.__amp = 80; }")
    time.sleep(2)
    shown = frame.locator("#pp-live-alarm").count() == 1
    print("hard limit 55 alarm bar shown:", shown, "|", sensor.text_content("#status").strip()[:50])
    return shown


def _has(f, sel) -> bool:
    try:
        return f.locator(sel).count() > 0
    except Exception:
        return False


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
                if name == "Operations Room":      # has its own red button, not a list item
                    frame.locator('[data-testid="stSidebar"] button').filter(has_text=name).first.click()
                else:
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
        if not alarm_flow(page, frame):
            bad += 1
            print("::error::alarm flow failed")
        if not hard_limit_flow(page, frame):
            bad += 1
            print("::error::hard limit flow failed")
        browser.close()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
