"""Router agent. Run (after the agents are up): python router.py"""
import asyncio
import json
import re
from datetime import datetime

import httpx
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory, create_text_message_object

import memory
from extractor import ack, remember
from memory_commands import USER_ID, handle_memory_command

AGENTS = {"comfort": "http://localhost:9001", "battery": "http://localhost:9002"}
BATTERY_RX = re.compile(r"\b(battery|charge|charging|range|state of charge|how far)\b", re.I)


def pick_agent(query: str) -> str:
    """Deterministic routing: which specialist should handle this request?"""
    return "battery" if BATTERY_RX.search(query) else "comfort"


def extract_text(event) -> str | None:
    """A reply is either a Message or a (Task, update) tuple; return the agent's text."""
    if hasattr(event, "parts"):
        msgs = [event]
    elif isinstance(event, tuple) and event[0].history:
        msgs = [m for m in event[0].history if m.role.value == "agent"]
    else:
        return None
    for m in reversed(msgs):
        for p in m.parts:
            if hasattr(p.root, "text"):
                return p.root.text
    return None


async def ask_agent(name: str, client, query: str, history: list) -> tuple[str, list]:
    message = create_text_message_object(content=json.dumps({"query": query, "history": history}))
    text = None
    async for event in client.send_message(message):
        text = extract_text(event) or text
    if text is None:
        return f"The {name} agent gave no answer.", []
    data = json.loads(text)
    return data["reply"], [{**c, "via": f"A2A:{name}"} for c in data["calls"]]


async def route(clients: dict, query: str, history: list):
    """Memory work stays local; everything else goes to a specialist."""
    reply = handle_memory_command(query)
    if reply:
        return reply, [{"name": "memory_command", "source": "router"}]
    now = datetime.now()
    remembered = await asyncio.to_thread(remember, USER_ID, query, now)   # LLM call -> keep off the event loop
    if remembered:
        return ack(remembered), [{"name": "remember", "args": m, "source": "router"} for m in remembered]
    name = pick_agent(query)
    if name not in clients:
        return f"The {name} agent is not available right now.", []
    try:
        return await ask_agent(name, clients[name], query, history)
    except Exception as e:   # agent down or returned a JSON-RPC error: report it, don't crash the loop
        return f"I can't get an answer from the {name} agent ({type(e).__name__}: {e}).", []


async def main():
    memory.init_db(reset=False)
    async with httpx.AsyncClient(timeout=120) as http:
        clients = {}
        for name, url in AGENTS.items():
            try:
                card = await A2ACardResolver(httpx_client=http, base_url=url).get_agent_card()
                clients[name] = ClientFactory(config=ClientConfig(httpx_client=http)).create(card)
                print(f"Connected to: {card.name}  skills={[s.name for s in card.skills]}")
            except Exception as e:
                print(f"WARNING: {name} agent at {url} not reachable ({type(e).__name__})")
        print("(type 'quit' to exit)\n")
        history = []
        while True:
            q = (await asyncio.to_thread(input, "Driver: ")).strip()
            if q.lower() in ("quit", "exit"):
                break
            if not q:
                continue
            reply, calls = await route(clients, q, history)
            print(f"[calls] {calls}\nAssistant: {reply}\n")
            history += [("user", q), ("assistant", reply)]


if __name__ == "__main__":
    asyncio.run(main())