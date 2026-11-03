"""Visit the live Streamlit app with a real (headless) browser so it does not go to sleep.

Streamlit Community Cloud puts apps to sleep after 12 hours without traffic.
A real browser visit counts as traffic; if the app is already asleep, the script
clicks the "Yes, get this app back up!" button and waits for the app to load.
Run by .github/workflows/keep-awake.yml every few hours.
"""

import os
import sys
import time

from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL", "https://plantproof-ai.streamlit.app")
WAKE_TEXT = "Yes, get this app back up"
READY_TEXT = "PlantProof"
TIMEOUT_S = 180


def app_loaded(page) -> bool:
    for frame in page.frames:
        try:
            if frame.get_by_text(READY_TEXT).count() > 0:
                return True
        except Exception:
            pass
    return False


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        print("Opened", URL)

        button = page.get_by_role("button", name=WAKE_TEXT)
        try:
            button.wait_for(timeout=15_000)
            button.click()
            print("App was asleep: clicked the wake-up button.")
        except Exception:
            print("No wake-up button: app is awake or already starting.")

        deadline = time.time() + TIMEOUT_S
        while time.time() < deadline:
            if app_loaded(page):
                time.sleep(10)
                for frame in page.frames:
                    try:
                        text = frame.locator("body").inner_text(timeout=5_000)
                    except Exception:
                        continue
                    if any(w in text for w in ("Traceback", "Error", "Exception")):
                        print("::warning::The app page shows an error:")
                        print(text[:3000])
                print("App loaded and responding.")
                browser.close()
                return 0
            time.sleep(5)

        print(f"::warning::App did not finish loading within {TIMEOUT_S}s. "
              "The visit still counts as traffic; check the app manually.")
        browser.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
