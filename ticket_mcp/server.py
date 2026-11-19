"""MCP server exposing the ticket tools to any MCP client (Claude Desktop, Claude Code, an agent script).

Run over stdio:  .venv/bin/python -m ticket_mcp.server
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field
from mcp.server.mcpserver import MCPServer

from . import core

server = MCPServer(
    "ticket-compare",
    instructions=(
        "Tools for finding live events and comparing ticket listings across sellers (fictional demo data). "
        "Always quote prices from compare_listings: all_in_total already includes each seller's fees. "
        "Use the weekday, date and is_this_weekend fields returned by search_events instead of working dates out yourself."
    ),
)


def _call(fn, **kwargs):
    try:
        return fn(**kwargs)
    except core.ToolError as exc:
        # Return the problem as data so the agent can correct its call instead of the session failing.
        return {"error": str(exc)}


@server.tool()
def search_events(
    city: Annotated[str | None, Field(description="City, e.g. Kitchener, Waterloo, Toronto")] = None,
    category: Annotated[str | None, Field(description="concert, sports, theatre or comedy")] = None,
    query: Annotated[str | None, Field(description="Words in the event or venue name")] = None,
    date_from: Annotated[str | None, Field(description="YYYY-MM-DD, inclusive")] = None,
    date_to: Annotated[str | None, Field(description="YYYY-MM-DD, inclusive")] = None,
    this_weekend: Annotated[bool, Field(description="Only events this Friday to Sunday")] = False,
) -> dict:
    """Find upcoming events. Each result includes the weekday, date, days_from_today and is_this_weekend, computed by the server."""
    return _call(core.search_events, city=city, category=category, query=query,
                 date_from=date_from, date_to=date_to, this_weekend=this_weekend)


@server.tool()
def compare_listings(
    event_id: Annotated[str, Field(description="event_id from search_events, e.g. E004")],
    quantity: Annotated[int, Field(description="Number of tickets, 1-8")] = 2,
    max_total: Annotated[float | None, Field(description="Budget for all tickets together, CAD, fees included")] = None,
    require_seats_together: Annotated[bool, Field(description="Only listings whose seats are together")] = True,
    user_id: Annotated[str | None, Field(description="Apply this user's saved seller preferences")] = None,
) -> dict:
    """Compare listings for one event across sellers, sorted by all-in total (base price plus fees). Applies the user's preferences if user_id is given."""
    return _call(core.compare_listings, event_id=event_id, quantity=quantity, max_total=max_total,
                 require_seats_together=require_seats_together, user_id=user_id)


@server.tool()
def set_preferences(
    user_id: Annotated[str, Field(description="The user's id")],
    preferred_seller: Annotated[str | None, Field(description="Seller id to rank first when close in price: box_office, tixswap, seathub, lastcall")] = None,
    tolerance_pct: Annotated[float, Field(description="How much more (in %) the user will pay to stay with the preferred seller")] = 5.0,
    excluded_sellers: Annotated[list[str] | None, Field(description="Seller ids never to show")] = None,
    max_fee_share_pct: Annotated[float | None, Field(description="Hide listings where fees are more than this % of the all-in price")] = None,
) -> dict:
    """Save a user's seller preferences. Only call this when the user has asked for it."""
    return _call(core.set_preferences, user_id=user_id, preferred_seller=preferred_seller, tolerance_pct=tolerance_pct,
                 excluded_sellers=excluded_sellers, max_fee_share_pct=max_fee_share_pct)


@server.tool()
def get_preferences(user_id: Annotated[str, Field(description="The user's id")]) -> dict:
    """Read a user's saved seller preferences."""
    return _call(core.get_preferences, user_id=user_id)


@server.tool()
def seller_policies() -> dict:
    """Fee rules and buyer guarantees for every seller."""
    return core.seller_policies()


def main():
    server.run()


if __name__ == "__main__":
    main()
