"""End-to-end check of phone-to-screen pairing over the public MQTT broker.

Opens assets/live_sensor.html twice in a headless browser: one copy as the screen, one as
the phone sending demo vibration with the screen's code. Passes when the screen learns the
baseline and then detects the injected fault.
"""

import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

SRC = Path(__file__).resolve().parent.parent / "assets" / "live_sensor.html"


def page_file(pair: str) -> str:
    html = SRC.read_text(encoding="utf-8").replace("__APP_URL__", "https://example.invalid")
    f = Path(tempfile.mkdtemp()) / "live.html"
    f.write_text(html.replace("__PAIR__", pair), encoding="utf-8")
    return f.as_uri()


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch()
        screen = b.new_page()
        screen.goto(page_file(""))
        for _ in range(40):
            code = screen.text_content("#code").strip()
            status = screen.text_content("#status")
            if code.isdigit() and "Ready" in status:
                break
            time.sleep(0.5)
        print("screen:", code, "|", status.strip()[:80])
        print("qr drawn:", screen.locator("#qr svg").count() == 1)
        phone = b.new_page()
        phone.goto(page_file(code))
        phone.click("#btnSendDemo")
        for _ in range(60):                  # public brokers can be slow to accept a connection
            time.sleep(1)
            st = phone.text_content("#status")
            if "readings" in st and int(st.split("·")[1].split()[0]) >= 26:
                break
        time.sleep(2)
        print("phone:", phone.text_content("#status").strip()[:80])
        learned = screen.text_content("#status")
        print("screen after learning:", learned.strip()[:90])
        for _ in range(3):
            phone.click("#btnSendFault")
        time.sleep(4)
        final = screen.text_content("#status")
        print("screen after fault:", final.strip()[:90])
        b.close()
    ok = "Model trained" in learned and "Anomaly detected" in final
    print("PAIRING OK" if ok else "::error::pairing check failed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
