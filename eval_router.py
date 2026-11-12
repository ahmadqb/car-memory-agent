"""python eval_router.py -> fixed queries through the router and the running A2A agents.
Start comfort_agent.py and battery_agent.py first."""
import asyncio

import httpx
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory

import memory
from router import AGENTS, route

# (query, expected agent tag in the calls, text that must appear in the reply)
CASES = [
    ("how much battery is left?", "A2A:battery", "%"),
    ("how far can I drive?", "A2A:battery", "342"),          # 76% x 4.5 km, checked in code
    ("what's my range", "A2A:battery", "342"),
    ("set the temperature to 35 degrees", "A2A:comfort", "allowed range"),
    ("what do you know about me", "router", "know"),         # memory stays local, no A2A call
    ("hello, what can you do?", None, ""),                   # small talk: no tool call at all
]


async def main():
    memory.init_db(reset=False)
    async with httpx.AsyncClient(timeout=120) as http:
        clients = {}
        for name, url in AGENTS.items():
            card = await A2ACardResolver(httpx_client=http, base_url=url).get_agent_card()
            clients[name] = ClientFactory(config=ClientConfig(httpx_client=http)).create(card)

        passed = 0
        for query, tag, must_contain in CASES:
            reply, calls = await route(clients, query, [])
            tags = {c.get("via") or c.get("source") for c in calls}
            routed_ok = (tag in tags) if tag else not calls
            ok = routed_ok and must_contain.lower() in reply.lower()
            passed += ok
            print(f"{'OK  ' if ok else 'FAIL'} {query!r} -> {sorted(t for t in tags if t)}  reply: {reply[:80]!r}")
        print(f"\n{passed}/{len(CASES)} router scenarios passed")


if __name__ == "__main__":
    asyncio.run(main())
