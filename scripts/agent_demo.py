"""A real LLM agent that uses the ticket MCP server over stdio.

The script launches `python -m ticket_mcp.server` as a subprocess, reads its tool list over MCP,
hands those tool schemas to Gemini as function declarations, and runs a tool-calling loop
(max 8 turns). Every tool call goes through the MCP protocol; the full transcript is saved to
runs/<timestamp>_<scenario>.md.

Run: .venv/bin/python scripts/agent_demo.py [scenario ...]     (needs GEMINI_API_KEY in .env)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai
import google.genai.errors  # noqa: F401
from google.genai import types
from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
TODAY = os.environ.get("TICKET_MCP_TODAY", "2026-11-18")

SCENARIOS = {
    "weekend": "Find me two tickets for a show in Kitchener this weekend. Keep it under $200 total including fees. Which one should I buy?",
    "prefer": "I'm user u-demo. I like buying from SeatHub and would pay up to 8% more to use it, but never TixSwap. "
              "Save that, then get me 2 seats together for the cheapest concert in Toronto in December.",
    "trap": "For event E011, which listing for 2 tickets is really cheapest once fees are added? Is the one with the lowest ticket price a good deal?",
}

SYSTEM = ("You are a ticket-buying assistant for a user. Use the tools; never invent events, dates or prices. "
          "Quote all-in totals exactly as compare_listings returns them, and use the weekday/date fields from search_events. "
          f"Today is {TODAY}. Answer in 3-5 sentences.")


def payload(result):
    if getattr(result, "structured_content", None):
        return result.structured_content
    return json.loads(result.content[0].text) if result.content else {}


async def run(name: str, prompt: str) -> Path:
    params = StdioServerParameters(command=sys.executable, args=["-m", "ticket_mcp.server"], cwd=str(ROOT),
                                   env={**os.environ, "TICKET_MCP_TODAY": TODAY, "TICKET_MCP_PREFS": str(ROOT / "prefs.json")})
    log = [f"# Agent run: {name}", f"- model: {MODEL} · server over stdio · today pinned to {TODAY}", "", f"**User:** {prompt}", ""]
    async with Client(params) as mcp:
        tools = (await mcp.list_tools()).tools
        decls = [types.FunctionDeclaration(name=t.name, description=t.description or "",
                                           parameters_json_schema=t.input_schema) for t in tools]
        gem = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        cfg = types.GenerateContentConfig(system_instruction=SYSTEM, temperature=0,
                                          tools=[types.Tool(function_declarations=decls)],
                                          automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
        contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
        for turn in range(8):
            for attempt in range(5):  # the free tier often answers 503 "high demand"; back off and retry
                try:
                    resp = gem.models.generate_content(model=MODEL, contents=contents, config=cfg)
                    break
                except genai.errors.ServerError:
                    if attempt == 4:
                        raise
                    await asyncio.sleep(10 * (attempt + 1))
            cand = resp.candidates[0].content
            contents.append(cand)
            calls = [p.function_call for p in cand.parts if p.function_call]
            if not calls:
                log += [f"**Assistant (turn {turn + 1}):** {resp.text}", ""]
                break
            parts = []
            for fc in calls:
                args = dict(fc.args or {})
                out = payload(await mcp.call_tool(fc.name, args))
                short = json.dumps(out)[:600]
                log += [f"- turn {turn + 1} · tool `{fc.name}` args `{json.dumps(args)}`", f"  - result (first 600 chars): `{short}`"]
                parts.append(types.Part.from_function_response(name=fc.name, response={"result": out}))
            contents.append(types.Content(role="user", parts=parts))
        else:
            log += ["**Stopped:** hit the 8-turn limit.", ""]
    out = ROOT / "runs" / f"{datetime.now():%Y%m%d-%H%M%S}_{name}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(log) + "\n")
    return out


async def main():
    names = sys.argv[1:] or list(SCENARIOS)
    for n in names:
        t = time.time()
        p = await run(n, SCENARIOS[n])
        print(f"{n}: {time.time() - t:.1f}s -> {p.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
