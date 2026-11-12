import asyncio
import os
import sys
from datetime import datetime
import re
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from extractor import ack, remember

import memory
from guards import plan, classify_result, compose_reply

USER_ID = "driver1"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
ACTION_TOOLS = {"set_cabin_temperature", "play_media"}
ALLOWED = {"temps": set(), "genres": set()}   # filled for every request in run_assistant
RELEVANT_SIGNALS = {"cabin_temp_set", "media_genre_played"}


# --- MCP bridge (the car state lives in car_state.json, so a new server process per call is fine) ---
def call_mcp_tool_sync(tool_name: str, args: dict) -> str:
    async def _run():
        params = StdioServerParameters(command=sys.executable, args=["car_server.py"], env={**os.environ})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, args)
                return result.content[0].text
    return asyncio.run(_run())


@tool
def set_cabin_temperature(temp_c: float) -> str:
    """Set the cabin temperature in degrees Celsius (allowed range 16 to 28)."""
    if float(temp_c) not in ALLOWED["temps"]:
        return "Refused: the driver did not ask for a temperature change, or this value is not allowed."
    return call_mcp_tool_sync("set_cabin_temperature", {"temp_c": temp_c})


@tool
def play_media(genre: str) -> str:
    """Start playing a playlist of the given genre, e.g., 'jazz' or 'electronic'."""
    if genre.lower() not in ALLOWED["genres"]:
        return "Refused: the driver did not ask for music, or this genre is not allowed."
    return call_mcp_tool_sync("play_media", {"genre": genre})


@tool
def get_cabin_temperature() -> str:
    """Get the current cabin temperature setpoint."""
    return call_mcp_tool_sync("get_cabin_temperature", {})


# --- Context engineering ---
def build_context(user_id: str, now: datetime | None = None) -> str:
    """Only facts for the CURRENT time bucket and relevant signals go into the prompt (context budget)."""
    now = now or datetime.now()
    bucket = memory.time_bucket(now)
    facts = [f for f in memory.get_profile(user_id)
             if f["key"].endswith(f"@{bucket}") and f["key"].split("@")[0] in RELEVANT_SIGNALS]
    if not facts:
        return f"Current time of day: {bucket}.\nNo specific user preferences are known for this time."
    lines = [f"Current time of day: {bucket}", "Known user preferences:"]
    for f in facts:
        signal = f["key"].split("@")[0].replace("_", " ")
        how = "you told me" if f.get("source") == "stated" else f"confidence {f['confidence']:.0%}, {f['support']} observations"
        lines.append(f"- {signal}: {f['value']} ({how})")
    return "\n".join(lines)


SYSTEM_PROMPT = """You are an in-car assistant. You control the car ONLY through tools.

{context}

Rules:
1. Call a tool only when the driver clearly asks for an action (cold or warm -> temperature, wants music -> media). Questions about what you can do, greetings and small talk get a plain text answer and NO tool call.
2. If the driver only names a topic ("temperature", "music") without saying what they want, ask one short question and call no tool.
3. Use only the preferences listed above. Never invent temperatures or genres. If the needed preference is missing, ask one short question.
4. Never say you did something unless a tool returned success. Answer in complete sentences."""

llm = ChatOllama(model=OLLAMA_MODEL, temperature=0)
agent = create_react_agent(llm, [set_cabin_temperature, play_media, get_cabin_temperature])


def run_assistant(query: str, now: datetime | None = None, history: list | None = None):
    """Returns (reply, calls). history = [("user", text), ("assistant", text), ...]."""
    now = now or datetime.now()
    history = history or []
    
    # Phase 3: an explicit preference statement is remembered, not executed as a command
    remembered = remember(USER_ID, query, now)
    if remembered:
        return ack(remembered), [{"name": "remember", "args": m, "source": "extractor"} for m in remembered]
    prev_user = next((t for role, t in reversed(history) if role == "user"), None)

    p = plan(USER_ID, now, query, prev_user)           # what is allowed / required, decided in code
    ALLOWED["temps"], ALLOWED["genres"] = p["temps"], p["genres"]

    messages = [("system", SYSTEM_PROMPT.format(context=build_context(USER_ID, now)))]
    messages += history[-6:] + [("user", query)]
    result = agent.invoke({"messages": messages})

    outputs = {m.tool_call_id: m.content for m in result["messages"] if m.type == "tool"}
    calls, results = [], []
    for m in result["messages"]:
        if m.type != "ai":
            continue
        for tc in (getattr(m, "tool_calls", None) or []):
            calls.append({"name": tc["name"], "args": tc["args"], "source": "model"})
            if tc["name"] in ACTION_TOOLS:
                out = str(outputs.get(tc["id"], ""))
                results.append({"tool": tc["name"], "args": tc["args"], "status": classify_result(out), "text": out})

    # Repair: the driver clearly asked for it, but the model skipped it -> do it, and record that it was repaired
    handled = {r["tool"] for r in results if r["status"] in ("ok", "car_refused")}
    for tool_name, value in p["required"].items():
        if tool_name in handled:
            continue
        args = {"temp_c": value} if tool_name == "set_cabin_temperature" else {"genre": value}
        out = call_mcp_tool_sync(tool_name, args)
        calls.append({"name": tool_name, "args": args, "source": "repair"})
        results.append({"tool": tool_name, "args": args, "status": classify_result(out), "text": out})

    seen, unique = set(), []
    for r in results:                       # the model sometimes repeats the same call
        k = (r["tool"], str(sorted(r["args"].items())), r["status"])
        if k not in seen:
            seen.add(k)
            unique.append(r)
    results = unique

    reply = compose_reply(str(result["messages"][-1].content), results, p["bucket"], p["prefs"], p["text"])
    return reply, calls


if __name__ == "__main__":
    memory.init_db(reset=False)
    print(f"Starting assistant with model: {OLLAMA_MODEL}  (type 'quit' to exit)")
    print(f"[time bucket now: {memory.time_bucket(datetime.now())}]\n")
    history = []
    while True:
        user_input = input("Driver: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break
        if not user_input:
            continue
        reply, calls = run_assistant(user_input, history=history)
        print(f"[tool calls] {calls}")
        print(f"Assistant: {reply}\n")
        history += [("user", user_input), ("assistant", reply)]