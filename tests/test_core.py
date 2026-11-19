"""Unit tests for the ticket logic. TICKET_MCP_TODAY pins 'today' so date tests are stable."""
import json
from datetime import date, datetime

import pytest

from ticket_mcp import core


@pytest.fixture(autouse=True)
def pinned(monkeypatch, tmp_path):
    monkeypatch.setenv("TICKET_MCP_TODAY", "2026-11-18")  # a Wednesday
    monkeypatch.setattr(core, "PREFS_FILE", tmp_path / "prefs.json")


# ---------------------------------------------------------------- dates
@pytest.mark.parametrize("d,fri", [("2026-11-18", "2026-11-20"), ("2026-11-20", "2026-11-20"),
                                   ("2026-11-21", "2026-11-20"), ("2026-11-22", "2026-11-20"),
                                   ("2026-11-23", "2026-11-27")])
def test_weekend_window(d, fri):
    lo, hi = core._weekend_of(date.fromisoformat(d))
    assert lo.isoformat() == fri and (hi - lo).days == 2 and lo.weekday() == 4


def test_weekday_matches_calendar_for_every_event():
    for e in core.search_events()["events"]:
        assert e["weekday"] == datetime.fromisoformat(e["start_local"]).strftime("%A")


def test_this_weekend_and_next_weekend_never_both_true():
    for e in core.search_events()["events"]:
        assert not (e["is_this_weekend"] and e["is_next_weekend"])


def test_this_weekend_filter_only_returns_fri_to_sun():
    r = core.search_events(this_weekend=True)
    assert r["count"] > 0
    for e in r["events"]:
        assert e["is_this_weekend"] and "2026-11-20" <= e["date"] <= "2026-11-22"


def test_past_events_are_hidden(monkeypatch):
    monkeypatch.setenv("TICKET_MCP_TODAY", "2026-12-15")
    assert all(e["date"] >= "2026-12-15" for e in core.search_events()["events"])


def test_filters_and_bad_dates():
    r = core.search_events(city="kitchener", category="concert")
    assert all(e["city"] == "Kitchener" and e["category"] == "concert" for e in r["events"])
    with pytest.raises(core.ToolError):
        core.search_events(date_from="next friday")
    with pytest.raises(core.ToolError):
        core.search_events(date_from="2026-12-10", date_to="2026-12-01")


# ---------------------------------------------------------------- prices
def test_all_in_price_is_base_plus_fees():
    for l in core.LISTINGS:
        s = core.SELLERS[l["seller_id"]]
        p = core.price(l, 3)
        assert p["fees_each"] == round(l["base_price"] * s["fee_pct"] / 100 + s["fee_fixed"], 2)
        assert p["all_in_total"] == round((l["base_price"] + p["fees_each"]) * 3, 2)


def test_listings_sorted_by_all_in_total_and_budget_respected():
    r = core.compare_listings("E001", quantity=2, max_total=200)
    totals = [x["all_in_total"] for x in r["listings"]]
    assert totals == sorted(totals) and all(t <= 200 for t in totals)


def test_quantity_and_seats_together_filters():
    r = core.compare_listings("E001", quantity=4, require_seats_together=True)
    ids = {x["listing_id"] for x in r["listings"]}
    for l in core.LISTINGS:
        if l["listing_id"] in ids:
            assert l["quantity_available"] >= 4 and l["seats_together"]


def test_lowest_base_price_trap_is_reported_when_it_exists():
    found = 0
    for eid in core.EVENTS:
        r = core.compare_listings(eid, quantity=2, require_seats_together=False)
        rows = r["listings"] if r["count"] <= 5 else core.compare_listings(eid, 2, require_seats_together=False, limit=99)["listings"]
        if not rows:
            continue
        base = min(rows, key=lambda x: (x["base_price_each"], x["listing_id"]))
        total = min(rows, key=lambda x: (x["all_in_total"], x["listing_id"]))
        assert (r["lowest_base_price_is_not_cheapest"] is not None) == (base["listing_id"] != total["listing_id"])
        found += r["lowest_base_price_is_not_cheapest"] is not None
    assert found >= 1, "demo data should contain at least one fee trap"


def test_unknown_event_and_bad_quantity():
    with pytest.raises(core.ToolError):
        core.compare_listings("E999")
    with pytest.raises(core.ToolError):
        core.compare_listings("E001", quantity=0)


# ---------------------------------------------------------------- preferences
def test_preferred_seller_ranked_first_only_within_tolerance():
    r0 = core.compare_listings("E001", quantity=2, limit=99)
    cheapest = r0["listings"][0]
    other = next((x for x in r0["listings"] if x["seller_id"] != cheapest["seller_id"]), None)
    assert other is not None
    gap = 100 * (other["all_in_total"] / cheapest["all_in_total"] - 1)

    core.set_preferences("u1", preferred_seller=other["seller_id"], tolerance_pct=min(25, gap + 0.5))
    r1 = core.compare_listings("E001", quantity=2, user_id="u1", limit=99)
    assert r1["listings"][0]["seller_id"] == other["seller_id"] and r1["preference_note"]

    if gap > 0.5:
        core.set_preferences("u2", preferred_seller=other["seller_id"], tolerance_pct=max(0, gap - 0.5))
        r2 = core.compare_listings("E001", quantity=2, user_id="u2", limit=99)
        assert r2["listings"][0]["listing_id"] == cheapest["listing_id"]


def test_excluded_seller_and_fee_cap():
    core.set_preferences("u3", excluded_sellers=["tixswap"], max_fee_share_pct=15)
    r = core.compare_listings("E001", quantity=1, user_id="u3", limit=99, require_seats_together=False)
    assert all(x["seller_id"] != "tixswap" and x["fee_share_pct"] <= 15 for x in r["listings"])


def test_preferences_persist_and_validate():
    core.set_preferences("u4", preferred_seller="seathub", tolerance_pct=3)
    assert json.loads(core.PREFS_FILE.read_text())["u4"]["preferred_seller"] == "seathub"
    assert core.get_preferences("u4")["preferences"]["tolerance_pct"] == 3
    with pytest.raises(core.ToolError):
        core.set_preferences("u5", preferred_seller="nosuchsite")
    with pytest.raises(core.ToolError):
        core.set_preferences("u5", tolerance_pct=80)
