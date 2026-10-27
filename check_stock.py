"""
Checks Apple UK in-store pickup for the iPhone Duo (Night Sky, 256GB or 512GB)
at Apple Glasgow and Apple Braehead, and sends an SMS through Twilio when
stock appears. Only texts when something NEW becomes available, so you
won't get a text every 5 minutes while stock stays in.
"""
import json
import os
import sys

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
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "application/json",
    "Referer": "https://www.apple.com/uk/shop/buy-iphone",
}


def send_sms(body):
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    token = os.environ["TWILIO_AUTH_TOKEN"]
    r = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        data={"From": os.environ["TWILIO_FROM"], "To": os.environ["MY_MOBILE"], "Body": body},
        auth=(sid, token),
        timeout=30,
    )
    if r.status_code >= 300:
        print(f"Twilio error {r.status_code}: {r.text}")
        sys.exit(1)
    print("Text message sent.")


def check_apple():
    params = {"fae": "true", "pl": "true", "mts.0": "regular",
              "searchNearby": "true", "location": POSTCODE}
    for i, part in enumerate(PARTS):
        params[f"parts.{i}"] = part

    r = requests.get(URL, params=params, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        print(f"Apple returned HTTP {r.status_code}. It may be blocking automated checks.")
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
        for part, label in PARTS.items():
            info = store.get("partsAvailability", {}).get(part)
            if info is None:
                print(f"WARNING: Apple didn't recognise part {part} ({label}) at {name}. "
                      "The part number may be wrong.")
                continue
            status = info.get("pickupDisplay", "unknown")
            quote = info.get("pickupSearchQuote", "")
            print(f"  {name}: {label} -> {status} {quote}")
            if status == "available":
                available.append(f"{label} at Apple {name}")
    return sorted(available)


def main():
    if os.environ.get("TEST_SMS", "").lower() == "true":
        send_sms("Test: your iPhone Duo stock checker is set up and can text you.")
        return

    available = check_apple()

    try:
        with open(STATE_FILE) as f:
            previous = set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        previous = set()

    new = [item for item in available if item not in previous]
    if new:
        msg = "iPhone Duo available for pickup:\n" + "\n".join(new) + \
              "\nBuy now: https://www.apple.com/uk/shop/buy-iphone"
        send_sms(msg)
    else:
        print("Nothing new available.")

    with open(STATE_FILE, "w") as f:
        json.dump(available, f, indent=2)


if __name__ == "__main__":
    main()
