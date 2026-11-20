# Build log

Built 2026-11-18 with Claude Code. I set the goal (a ticket MCP server an agent can trust on dates and
prices, with user preferences) and the design rules below; Claude Code wrote the code; I reviewed the
results and transcripts.

## Why this project
While researching a ticket-discovery startup's AI assistant (Nov 18), one of its answers called an event on
the 21st and 22nd "next weekend" right after listing those dates as this weekend, and its seller comparison
noted resale fees that are only revealed at checkout. Both are things code can get right every time, so the server computes them instead of the model.

## Design decisions
- **D1. Compute, don't ask the model.** Weekday, "this weekend", days from today and all-in totals are
  computed in `ticket_mcp/core.py` and returned as fields. The system prompt tells the agent to use them.
- **D2. One pinned "today".** `TICKET_MCP_TODAY` fixes the reference date so tests and demo transcripts are
  reproducible.
- **D3. All-in price is the sort key.** Listings are sorted by base + percentage fee + fixed fee, and the
  response flags when the lowest ticket price is not the cheapest after fees.
- **D4. Errors are data.** Bad input returns `{"error": "..."}` with a hint (e.g. "call search_events first"),
  so the agent can retry instead of the session failing.
- **D5. Preferences can't override price blindly.** A preferred seller is moved to the top only within the
  user's own `tolerance_pct` of the cheapest total; the response explains the decision.
- **D6. Show what was filtered.** `filtered_out` counts listings removed by quantity, seats-together, budget,
  excluded seller and fee cap, so an empty result can be explained.
- **D7. Logic separate from MCP.** `core.py` has no MCP imports and is unit-tested directly; `server.py` only
  declares tools (typed parameters with descriptions become the JSON schemas clients see).
- **D8. Test over the protocol too.** Four tests use a real MCP client session against the server in-process.
- **D9. A real agent over stdio.** `scripts/agent_demo.py` starts the server as a subprocess, converts the
  MCP tool list into Gemini function declarations and runs a capped tool-calling loop.

## Problems met
- **MCP SDK 2.x.** `pip install mcp` installed 2.3.0, where `FastMCP` is renamed `MCPServer` and the import
  fails with a migration message; code written against the 2.x API.
- **Free-tier limits.** The first demo run worked on `gemini-3.5-flash-lite`; the next calls hit its daily
  free quota (it had been used heavily by another project the same day). `gemini-3.5-flash` answered 503
  "high demand" and `gemini-2.5-flash` is no longer offered to new users, so retries with backoff were added
  and the remaining scenarios were run on another model (recorded in each transcript).

## Observed in the first agent run (`runs/*_weekend.md`)
- The agent called `search_events(city="Kitchener", this_weekend=true)`, then `compare_listings` for both
  events in parallel, and quoted totals exactly as returned ($48.36 = 2 × (18.02 + 6.16)).
- It recommended a $78.74 TixSwap listing over a $48.36 one because of the refund guarantee: a judgement the
  server does not make. A next step would be returning a short, explicit trade-off (price vs. guarantee) so
  the recommendation can be checked.

## Observed in the preference run (`runs/*_prefer.md`, gemini-3.8-flash)
- In one turn the agent saved the preferences (SeatHub preferred, 8% tolerance, TixSwap excluded) and
  searched Toronto concerts with a computed December date range; then called `compare_listings` with
  `user_id` and `require_seats_together=true`.
- Its answer matched the server: cheapest 2 seats together $154.76 (Venue Box Office); SeatHub's $294.20 was
  outside the 8% tolerance, so it was not moved up, which is what `preference_note` said. Checked against
  `core.compare_listings` directly.

## Observed in the fee-trap run (`runs/*_trap.md`, gemini-3.5-flash-lite, Nov 19)
- First attempt pointed the scenario at E006, which turned out to have no fee trap (the lowest ticket price
  is also cheapest after fees; `lowest_base_price_is_not_cheapest` is null). Kept as a control run
  (`runs/*_control_E006.md`): the agent correctly said the cheapest ticket was also the best deal.
  A scan of every event found the trap only on E011, so the scenario now uses E011.
- E011: the agent called `compare_listings` once and answered that the lowest ticket price (E011-L06,
  $73.42 each) comes to $172.46 for two after a $12.81 fee per ticket, while E011-L01 is cheaper at $165.58.
  All three numbers match the server.
- Lesson: pick demo cases from the data with a check, not by eye.
