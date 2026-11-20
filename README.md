# Ticket Compare MCP

A small **Model Context Protocol (MCP) server** that lets an AI agent search live events and compare
ticket listings across sellers by their **all-in price** (base price plus each seller's fees), with
user-set seller preferences. Built with the official MCP Python SDK (`mcp` 2.x, `MCPServer`).

> **All data is fictional.** Every artist, venue, seller, price and fee rule is invented
> (`scripts/make_data.py`, fixed seed). This is a prototype, not connected to any real ticket site.

## Why it is built this way

Agents are good at choosing and explaining, and bad at things like working out the weekday of a date
or adding up fees. So the server does those in code and returns them as data:

- `search_events` returns `weekday`, `date`, `days_from_today`, `is_this_weekend`, `is_next_weekend`,
  computed from a single "today" (pinnable with `TICKET_MCP_TODAY`).
- `compare_listings` returns base price, fees, all-in per ticket and all-in total for every listing,
  sorted by total, and says when **the lowest ticket price is not the cheapest after fees**
  (`lowest_base_price_is_not_cheapest`). It also reports how many listings each filter removed.
- Bad input (unknown event, a date like "next friday") comes back as `{"error": ...}` data that tells
  the agent how to fix the call, instead of failing the session.

## Tools

| tool | what it does |
|---|---|
| `search_events` | city / category / words / date range / this weekend → upcoming events with computed dates |
| `compare_listings` | one event, quantity, budget, seats together, optional `user_id` → listings by all-in total |
| `set_preferences` | save a user's preferred seller, how much more they will pay for it (`tolerance_pct`), excluded sellers, a cap on fee share |
| `get_preferences` | read them back |
| `seller_policies` | fee rules and buyer guarantees per seller |

**Preference rule:** the preferred seller is ranked first only if its all-in total is within
`tolerance_pct` of the cheapest listing; otherwise the list stays sorted by price and the response
says why (`preference_note`).

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install "mcp[cli]" pytest pytest-asyncio anyio google-genai python-dotenv
.venv/bin/python scripts/make_data.py      # regenerate data/ (already committed)
.venv/bin/python -m pytest -q              # 22 tests
.venv/bin/python -m ticket_mcp.server      # MCP server over stdio
```

Use from an MCP client such as Claude Desktop (`claude_desktop_config.json`):

```json
{ "mcpServers": { "ticket-compare": {
    "command": "/absolute/path/to/.venv/bin/python",
    "args": ["-m", "ticket_mcp.server"],
    "cwd": "/absolute/path/to/ticket-compare-mcp" } } }
```

## Agent demo

`scripts/agent_demo.py` launches the server as a subprocess, lists its tools **over MCP (stdio)**,
gives the tool schemas to Gemini as function declarations, and runs a tool-calling loop capped at
8 turns. Transcripts are saved in `runs/`. Needs `GEMINI_API_KEY` in `.env`.

```bash
.venv/bin/python scripts/agent_demo.py weekend prefer trap   # transcripts in runs/
```

## Tests (22)

- `tests/test_core.py` (18): weekend window for every weekday case, weekday matches the calendar for
  every event, past events hidden, date validation, all-in price = base + fees for every listing,
  sorting and budget, quantity / seats-together filters, the "lowest base price is not cheapest"
  flag matches a brute-force check on every event, preference ranking inside vs. outside tolerance,
  excluded sellers, fee cap, preference validation and persistence.
- `tests/test_server.py` (4): through a real MCP client session: tool list and input schemas,
  search → compare round trip, bad input returned as data, preferences round trip.

## Limitations

- Fictional data; no live inventory, checkout, taxes or authentication.
- Preferences are stored in a local JSON file keyed by a plain `user_id` (no real user authorization).
- The agent demo uses one model (Gemini); its recommendations are the model's, not the server's.
