"""Protocol-level tests: talk to the server through a real MCP client session (in-process)."""
import json

import pytest

from mcp import Client
from ticket_mcp import core
from ticket_mcp.server import server

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def pinned(monkeypatch, tmp_path):
    monkeypatch.setenv("TICKET_MCP_TODAY", "2026-11-18")
    monkeypatch.setattr(core, "PREFS_FILE", tmp_path / "prefs.json")


def payload(result):
    if getattr(result, "structured_content", None):
        return result.structured_content
    return json.loads(result.content[0].text)


async def test_tools_are_listed_with_schemas():
    async with Client(server) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
    assert set(tools) == {"search_events", "compare_listings", "set_preferences", "get_preferences", "seller_policies"}
    props = tools["compare_listings"].input_schema["properties"]
    assert "event_id" in props and "max_total" in props and props["max_total"].get("description")


async def test_search_then_compare_over_protocol():
    async with Client(server) as c:
        found = payload(await c.call_tool("search_events", {"city": "Kitchener", "this_weekend": True}))
        assert found["count"] >= 1
        eid = found["events"][0]["event_id"]
        cmp = payload(await c.call_tool("compare_listings", {"event_id": eid, "quantity": 2, "max_total": 250}))
    assert cmp["event"]["event_id"] == eid
    assert all(x["all_in_total"] <= 250 for x in cmp["listings"])


async def test_bad_input_comes_back_as_data_not_a_crash():
    async with Client(server) as c:
        r = payload(await c.call_tool("compare_listings", {"event_id": "E999"}))
    assert "error" in r and "search_events" in r["error"]


async def test_preferences_round_trip_over_protocol():
    async with Client(server) as c:
        await c.call_tool("set_preferences", {"user_id": "demo", "preferred_seller": "seathub", "tolerance_pct": 10})
        r = payload(await c.call_tool("get_preferences", {"user_id": "demo"}))
    assert r["preferences"]["preferred_seller"] == "seathub"
