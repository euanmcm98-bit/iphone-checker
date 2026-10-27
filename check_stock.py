"""
Checks Apple UK in-store pickup for the iPhone Duo (Night Sky, 256GB or 512GB)
at Apple Glasgow and Apple Braehead, and sends a free push notification
to your phone through ntfy when stock appears. Only notifies when something
NEW becomes available, so you won't be alerted every 5 minutes while stock
stays in.
"""
import json
import os
import re
import sys
import time

import requests

# ---- Settings you might want to change -------------------------------------
PARTS = {
    "MK2E4B/A": "iPhone Duo 256GB Night Sky",
    "MK2G4B/A": "iPhone Duo 512GB Night Sky",
}
STORES = ["Glasgow", "Braehead"]   # Apple's store names, as shown on apple.com/uk
POSTCODE = "G1 2JX"                # Search centre (Apple Glasgow, Buchanan Street)
# ----------------------------------------------------------------------------

STATE_FILE = "state.json"
URL = "https://www.apple.com/uk/shop/fulfillment-messages"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Safari/605.1.15"
)
PAGE_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
API_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://www.apple.com/uk/shop/buy-iphone/iphone-duo",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "X-Requested-With": "XMLHttpRequest",
}


def notify(message, title="iPhone Duo in stock!"):
    topic = os.environ["NTFY_TOPIC"].strip()
    r = requests.post(
        f"https://ntfy.sh/{topic}",
        data=message.encode("utf-8"),
        headers={
            "Title": title,
            "Priority": "high",
            "Tags": "iphone,tada",
            "Click": "https://www.apple.com/uk/shop/buy-iphone",
        },
        timeout=30,
    )
    if r.status_code >= 300:
        print(f"ntfy error {r.status_code}: {r.text}")
        sys.exit(1)
    print("Notification sent.")


def find_real_parts(page_text):
    """Read the actual part numbers from Apple's iPhone Duo page and swap in
    the correct UK versions of the ones in PARTS (matched on the first 5
    characters, e.g. MK2E4)."""
    found = sorted(set(re.findall(r"\bMK2[A-Z0-9]{2,4}/A\b", page_text)))
    print("Part numbers found on Apple's iPhone Duo page:", ", ".join(found) or "none")
    for url in sorted(set(re.findall(r"[\w/.:-]*fulfillment[\w/.-]*", page_text)))[:5]:
        print("Fulfilment address mentioned on page:", url)

    active = {}
    for part, label in PARTS.items():
        if part in found or not found:
            active[part] = label
            continue
        matches = [f for f in found if f.startswith(part[:5])]
        if matches:
            print(f"Using {matches[0]} instead of {part} for {label}")
            active[matches[0]] = label
        else:
            print(f"WARNING: no match on the page for {part} ({label}); trying it anyway.")
            active[part] = label
    return active


def check_apple():
    session = requests.Session()
    page_text = ""
    # Visit the shop pages first, like a browser would, to pick up Apple's cookies.
    for page in ("https://www.apple.com/uk/shop/buy-iphone",
                 "https://www.apple.com/uk/shop/buy-iphone/iphone-duo"):
        try:
            p = session.get(page, headers=PAGE_HEADERS, timeout=30)
            print(f"Visited {page} -> HTTP {p.status_code}")
            page_text = p.text
        except requests.RequestException as e:
            print(f"Couldn't load {page}: {e}")
        time.sleep(2)

    active = find_real_parts(page_text)

    params = {"fae": "true", "pl": "true", "mts.0": "regular",
              "searchNearby": "true", "location": POSTCODE}
    for i, part in enumerate(active):
        params[f"parts.{i}"] = part

    r = None
    for attempt in range(1, 4):
        r = session.get(URL, params=params, headers=API_HEADERS, timeout=30)
        print(f"Availability check attempt {attempt} -> HTTP {r.status_code}")
        if r.status_code == 200:
            break
        time.sleep(5 * attempt)

    if r.status_code != 200:
        print(f"Apple returned HTTP {r.status_code}.")
        print("Address requested:", r.url)
        sys.exit(1)

    stores = r.json().get("body", {}).get("content", {}).get("pickupMessage", {}).get("stores", [])
    if not stores:
        print("Apple's reply contained no stores. The page format may have changed.")
        print(r.text[:1000])
        sys.exit(1)

    print("Stores Apple returned:", ", ".join(s.get("storeName", "?") for s in stores))

    wanted = {name.lower() for name in STORES}
    available = []
    for store in stores:
        name = store.get("storeName", "")
        if name.lower() not in wanted:
            continue
        for part, label in active.items():
            info = store.get("partsAvailability", {}).get(part)
            if info is None:
                print(f"WARNING: Apple didn't recognise part {part} ({label}) at {name}.")
                continue
            status = info.get("pickupDisplay", "unknown")
            quote = info.get("pickupSearchQuote", "")
            print(f"  {name}: {label} -> {status} {quote}")
            if status == "available":
                available.append(f"{label} at Apple {name}")
    return sorted(available)


def main():
    if os.environ.get("TEST_NOTIFY", "").lower() == "true":
        notify("Your iPhone Duo stock checker is set up and can reach your phone.",
               title="Test notification")
        return

    available = check_apple()

    try:
        with open(STATE_FILE) as f:
            previous = set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        previous = set()

    new = [item for item in available if item not in previous]
    if new:
        msg = "Available for pickup:\n" + "\n".join(new) + "\nTap to open the Apple Store."
        notify(msg)
    else:
        print("Nothing new available.")

    with open(STATE_FILE, "w") as f:
        json.dump(available, f, indent=2)


if __name__ == "__main__":
    main()
