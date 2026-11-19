"""Generate the fictional event and listing data (fixed seed, so the files are reproducible).

Every artist, venue and seller here is invented. Prices and fee rules are made up to look like
the kinds of fee structures real ticket sites use (percentage service fee, per-ticket fixed fee,
fees shown only at checkout), so the comparison logic has something realistic to work on.

Run: .venv/bin/python scripts/make_data.py
"""
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
random.seed(2026)

VENUES = [
    ("Grand River Hall", "Kitchener"), ("Laurel Creek Theatre", "Waterloo"), ("The Foundry Room", "Kitchener"),
    ("Harbourfront Arena", "Toronto"), ("Queen West Music Hall", "Toronto"), ("Bayfront Centre", "Hamilton"),
    ("Speed River Stage", "Guelph"),
]
EVENTS = [
    ("The Northern Lanterns", "concert"), ("Mila Okafor", "concert"), ("Static Bloom", "concert"),
    ("Waterloo Wolves vs. Hamilton Hawks", "sports"), ("Toronto Comets vs. Ottawa Foxes", "sports"),
    ("A Winter's Tale (new staging)", "theatre"), ("The Lighthouse Keeper", "theatre"),
    ("Priya Ramanathan: Mostly True", "comedy"), ("Open Mic Showcase", "comedy"),
    ("Candlelight: Film Scores", "concert"), ("The Velvet Arcade", "concert"), ("Holiday Jazz Night", "concert"),
]
# Fee models (invented). fee_pct is a percentage of the base price, fee_fixed is per ticket (CAD).
SELLERS = {
    "box_office": {"name": "Venue Box Office", "type": "primary", "fee_pct": 6.0, "fee_fixed": 3.50,
                   "fees_shown_upfront": True, "guarantee": "Issued by the venue; refund only if the event is cancelled."},
    "tixswap": {"name": "TixSwap", "type": "resale", "fee_pct": 24.0, "fee_fixed": 0.0,
                "fees_shown_upfront": False, "guarantee": "Full refund if the ticket is invalid or the event is cancelled."},
    "seathub": {"name": "SeatHub", "type": "resale", "fee_pct": 15.0, "fee_fixed": 2.50,
                "fees_shown_upfront": True, "guarantee": "Buyer guarantee covers late delivery and invalid tickets."},
    "lastcall": {"name": "LastCall Tickets", "type": "resale", "fee_pct": 12.0, "fee_fixed": 4.00,
                 "fees_shown_upfront": False, "guarantee": "Guarantee covers invalid tickets only."},
}
SECTIONS = ["Floor", "Lower 100s", "Lower 200s", "Upper 300s", "Balcony"]


def main():
    start = datetime(2026, 11, 19)
    events, listings = [], []
    for i, (name, category) in enumerate(EVENTS):
        venue, city = VENUES[i % len(VENUES)]
        day = start + timedelta(days=random.randint(0, 30))
        hour = {"concert": 20, "sports": 19, "theatre": 19, "comedy": 21}[category]
        eid = f"E{i + 1:03d}"
        events.append({"event_id": eid, "name": name, "category": category, "venue": venue, "city": city,
                       "start_local": day.replace(hour=hour, minute=30 if category == "theatre" else 0).strftime("%Y-%m-%dT%H:%M"),
                       "timezone": "America/Toronto"})
        face = {"concert": 70, "sports": 55, "theatre": 65, "comedy": 35}[category] + random.randint(-10, 25)
        n = 0
        for sid in SELLERS:
            for _ in range(random.randint(1, 3)):
                n += 1
                section = random.choice(SECTIONS)
                tier = {"Floor": 1.6, "Lower 100s": 1.3, "Lower 200s": 1.1, "Upper 300s": 0.85, "Balcony": 0.75}[section]
                markup = 1.0 if sid == "box_office" else random.uniform(0.85, 1.9)
                listings.append({"listing_id": f"{eid}-L{n:02d}", "event_id": eid, "seller_id": sid, "section": section,
                                  "row": random.choice("ABCDEFGHJK"), "base_price": round(face * tier * markup, 2),
                                  "quantity_available": random.choice([1, 2, 2, 3, 4, 4, 6, 8]),
                                  "seats_together": random.random() > 0.2})
    out = ROOT / "data"
    out.mkdir(exist_ok=True)
    (out / "events.json").write_text(json.dumps(events, indent=1))
    (out / "listings.json").write_text(json.dumps(listings, indent=1))
    (out / "sellers.json").write_text(json.dumps(SELLERS, indent=1))
    print(len(events), "events,", len(listings), "listings")


if __name__ == "__main__":
    main()
