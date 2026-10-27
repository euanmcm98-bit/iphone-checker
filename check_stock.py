"""
GitHub version: opens Apple's stock-check address for each store in a real
(hidden) Chrome browser, reads the text, and sends an ntfy notification when
the iPhone Duo is available for pickup. Runs once per GitHub schedule.
"""
import json
import os
import sys
import time

import requests
from playwright.sync_api import sync_playwright

PARTS = {
    "MK2E4QN/A": "256GB Night Sky",
    "MK2G4QN/A": "512GB Night Sky",
}
STORES = {
    "R135": "Glasgow",
    "R340": "Braehead",
}
STATE_FILE = "state.json"
BUY_PAGE = "https://www.apple.com/uk/shop/buy-iphone/iphone-duo"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


def store_url(store):
    parts = "".join(f"&parts.{i}={p.replace('/', '%2F')}" for i, p in enumerate(PARTS))
    return ("https://www.apple.com/uk/shop/fulfillment-messages?fae=true&pl=true"
            f"&mts.0=regular{parts}&store={store}&searchNearby=false")


def notify(message, title="iPhone Duo in stock!"):
    r = requests.post(
        f"https://ntfy.sh/{os.environ['NTFY_TOPIC'].strip()}",
        data=message.encode("utf-8"),
        headers={"Title": title, "Priority": "high", "Tags": "iphone", "Click": BUY_PAGE},
        timeout=30,
    )
    print(f"Notification sent (ntfy replied {r.status_code}).")


def fetch_all():
    results = {}
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
            print("Using Google Chrome.")
        except Exception:
            browser = p.chromium.launch(headless=True)
            print("Using Playwright's Chromium.")
        context = browser.new_context(locale="en-GB", user_agent=UA,
                                      timezone_id="Europe/London")
        page = context.new_page()
        for store in STORES:
            url = store_url(store)
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
            status = resp.status if resp else "?"
            print(f"{STORES[store]}: Apple replied HTTP {status}")
            text = resp.text() if resp else ""
            if status != 200:
                print("Start of Apple's reply:", text[:300].replace("\n", " "))
                sys.exit(1)
            results[store] = json.loads(text)
            time.sleep(2)
        browser.close()
    return results


def main():
    if os.environ.get("TEST_NOTIFY", "").lower() == "true":
        notify("Your GitHub iPhone Duo checker can reach your phone.", title="Test notification")
        return

    available = []
    for store, data in fetch_all().items():
        name = STORES[store]
        stores = data.get("body", {}).get("content", {}).get("pickupMessage", {}).get("stores", [])
        match = [s for s in stores if s.get("storeNumber") == store] or stores[:1]
        if not match:
            print(f"Apple's reply for {name} had no store in it.")
            sys.exit(1)
        for part, label in PARTS.items():
            info = match[0].get("partsAvailability", {}).get(part)
            if info is None:
                print(f"  {name}: {label} -> not listed")
                continue
            status = info.get("pickupDisplay", "unknown")
            print(f"  {name}: {label} -> {status} {info.get('pickupSearchQuote', '')}")
            if status == "available":
                available.append(f"{label} at Apple {name}")

    try:
        with open(STATE_FILE) as f:
            previous = set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        previous = set()

    new = sorted(set(available) - previous)
    if new:
        notify("Available for pickup:\n" + "\n".join(new) + "\nTap to open the Apple Store.")
    else:
        print("Nothing new available.")

    with open(STATE_FILE, "w") as f:
        json.dump(sorted(available), f, indent=2)


if __name__ == "__main__":
    main()
