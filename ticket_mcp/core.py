"""Business logic, kept free of MCP so it can be unit-tested directly.

Design rule: anything a model could get wrong by "reasoning" (weekday of a date, whether it is this
weekend, the all-in price after fees, which listing is cheapest) is computed here in code and returned
as data. The calling agent only has to choose and explain.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

DATA = Path(os.environ.get("TICKET_MCP_DATA", Path(__file__).resolve().parent.parent / "data"))


class ToolError(ValueError):
    """Raised for bad input; the server turns it into an error result the agent can read."""


def _load(name):
    return json.loads((DATA / name).read_text())


EVENTS = {e["event_id"]: e for e in _load("events.json")}
LISTINGS = _load("listings.json")
SELLERS = _load("sellers.json")


def today() -> date:
    """'Today' for relative dates. TICKET_MCP_TODAY (YYYY-MM-DD) pins it for tests and demos."""
    pinned = os.environ.get("TICKET_MCP_TODAY")
    return date.fromisoformat(pinned) if pinned else date.today()


def _parse_day(value: str | None, field: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ToolError(f"{field} must be a date like 2026-11-21, got {value!r}") from exc


def _weekend_of(d: date) -> tuple[date, date]:
    """Friday-to-Sunday window for the weekend that contains d, or the next one if d is Mon-Thu."""
    friday = d + timedelta(days=(4 - d.weekday()) % 7) if d.weekday() < 4 else d - timedelta(days=d.weekday() - 4)
    return friday, friday + timedelta(days=2)


def describe_event(e: dict, ref: date) -> dict:
    start = datetime.fromisoformat(e["start_local"])
    fri, sun = _weekend_of(ref)
    days = (start.date() - ref).days
    return {**e, "weekday": start.strftime("%A"), "date": start.date().isoformat(), "time": start.strftime("%H:%M"),
            "days_from_today": days, "is_this_weekend": fri <= start.date() <= sun,
            "is_next_weekend": fri + timedelta(days=7) <= start.date() <= sun + timedelta(days=7)}


def search_events(city: str | None = None, category: str | None = None, query: str | None = None,
                  date_from: str | None = None, date_to: str | None = None, this_weekend: bool = False) -> dict:
    ref = today()
    lo, hi = _parse_day(date_from, "date_from"), _parse_day(date_to, "date_to")
    if this_weekend:
        lo, hi = _weekend_of(ref)
    if lo and hi and lo > hi:
        raise ToolError("date_from is after date_to")
    out = []
    for e in EVENTS.values():
        d = datetime.fromisoformat(e["start_local"]).date()
        if d < ref:
            continue
        if city and city.strip().lower() != e["city"].lower():
            continue
        if category and category.strip().lower() != e["category"]:
            continue
        if query and query.strip().lower() not in (e["name"] + " " + e["venue"]).lower():
            continue
        if (lo and d < lo) or (hi and d > hi):
            continue
        out.append(describe_event(e, ref))
    out.sort(key=lambda x: x["start_local"])
    return {"today": ref.isoformat(), "today_weekday": ref.strftime("%A"), "count": len(out), "events": out}


def price(listing: dict, quantity: int) -> dict:
    s = SELLERS[listing["seller_id"]]
    fee_each = round(listing["base_price"] * s["fee_pct"] / 100 + s["fee_fixed"], 2)
    each = round(listing["base_price"] + fee_each, 2)
    return {"base_price_each": listing["base_price"], "fees_each": fee_each, "all_in_each": each,
            "all_in_total": round(each * quantity, 2),
            "fee_share_pct": round(100 * fee_each / each, 1)}


# ---------------------------------------------------------------- preferences (the "agent preference" idea)
PREFS_FILE = Path(os.environ.get("TICKET_MCP_PREFS", DATA.parent / "prefs.json"))


def _read_prefs() -> dict:
    return json.loads(PREFS_FILE.read_text()) if PREFS_FILE.exists() else {}


def set_preferences(user_id: str, preferred_seller: str | None = None, tolerance_pct: float = 5.0,
                    excluded_sellers: list[str] | None = None, max_fee_share_pct: float | None = None) -> dict:
    if not user_id.strip():
        raise ToolError("user_id is required")
    for sid in [preferred_seller, *(excluded_sellers or [])]:
        if sid and sid not in SELLERS:
            raise ToolError(f"unknown seller {sid!r}; known sellers: {', '.join(SELLERS)}")
    if not 0 <= tolerance_pct <= 25:
        raise ToolError("tolerance_pct must be between 0 and 25")
    prefs = _read_prefs()
    prefs[user_id] = {"preferred_seller": preferred_seller, "tolerance_pct": tolerance_pct,
                      "excluded_sellers": excluded_sellers or [], "max_fee_share_pct": max_fee_share_pct}
    PREFS_FILE.write_text(json.dumps(prefs, indent=1))
    return {"user_id": user_id, "saved": prefs[user_id]}


def get_preferences(user_id: str) -> dict:
    return {"user_id": user_id, "preferences": _read_prefs().get(user_id)}


def compare_listings(event_id: str, quantity: int = 2, max_total: float | None = None,
                     require_seats_together: bool = True, user_id: str | None = None, limit: int = 5) -> dict:
    if event_id not in EVENTS:
        raise ToolError(f"unknown event_id {event_id!r}; call search_events first")
    if not 1 <= quantity <= 8:
        raise ToolError("quantity must be between 1 and 8")
    prefs = (_read_prefs().get(user_id) if user_id else None) or {}
    excluded = set(prefs.get("excluded_sellers") or [])
    rows, dropped = [], {"not_enough_tickets": 0, "seats_not_together": 0, "over_budget": 0,
                         "excluded_seller": 0, "fees_too_high": 0}
    for l in LISTINGS:
        if l["event_id"] != event_id:
            continue
        if l["quantity_available"] < quantity:
            dropped["not_enough_tickets"] += 1; continue
        if require_seats_together and quantity > 1 and not l["seats_together"]:
            dropped["seats_not_together"] += 1; continue
        if l["seller_id"] in excluded:
            dropped["excluded_seller"] += 1; continue
        p = price(l, quantity)
        if prefs.get("max_fee_share_pct") is not None and p["fee_share_pct"] > prefs["max_fee_share_pct"]:
            dropped["fees_too_high"] += 1; continue
        if max_total is not None and p["all_in_total"] > max_total:
            dropped["over_budget"] += 1; continue
        s = SELLERS[l["seller_id"]]
        rows.append({"listing_id": l["listing_id"], "seller": s["name"], "seller_id": l["seller_id"], "seller_type": s["type"],
                     "section": l["section"], "row": l["row"], **p, "fees_shown_upfront_on_seller_site": s["fees_shown_upfront"],
                     "guarantee": s["guarantee"]})
    rows.sort(key=lambda r: (r["all_in_total"], r["listing_id"]))
    note = None
    pref = prefs.get("preferred_seller")
    if rows and pref:
        cheapest = rows[0]["all_in_total"]
        limit_total = round(cheapest * (1 + prefs.get("tolerance_pct", 5.0) / 100), 2)
        best_pref = next((r for r in rows if r["seller_id"] == pref and r["all_in_total"] <= limit_total), None)
        if best_pref and best_pref is not rows[0]:
            rows.remove(best_pref)
            rows.insert(0, best_pref)
            note = (f"Ranked {best_pref['seller']} first because the user prefers it and it is within "
                    f"{prefs.get('tolerance_pct', 5.0)}% of the cheapest all-in total (${cheapest:.2f}).")
        elif not best_pref:
            note = f"Preferred seller {SELLERS[pref]['name']} has no listing within the user's tolerance; sorted by price."
    ev = describe_event(EVENTS[event_id], today())
    by_base = min(rows, key=lambda r: (r["base_price_each"], r["listing_id"])) if rows else None
    by_total = min(rows, key=lambda r: (r["all_in_total"], r["listing_id"])) if rows else None
    base_trap = None
    if by_base and by_total and by_base["listing_id"] != by_total["listing_id"]:
        base_trap = (f"{by_base['listing_id']} ({by_base['seller']}) has the lowest ticket price, but after fees "
                     f"{by_total['listing_id']} ({by_total['seller']}) is cheaper by "
                     f"${by_base['all_in_total'] - by_total['all_in_total']:.2f} in total.")
    return {"event": ev, "quantity": quantity, "currency": "CAD", "count": len(rows), "listings": rows[:limit],
            "filtered_out": dropped, "preference_note": note, "lowest_base_price_is_not_cheapest": base_trap,
            "prices_note": "all_in includes each seller's service and fixed fees; taxes not included"}


def seller_policies() -> dict:
    return {"sellers": SELLERS}
