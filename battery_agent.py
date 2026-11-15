"""Battery agent (LLM + read-only MCP tools) as an A2A service. Run: python battery_agent.py  (port 9002)"""
import asyncio
import json
import os

import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.utils import new_agent_text_message
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent

from assistant import call_mcp_tool_sync

from battery_guards import KM_PER_PERCENT, RANGE_WORDS, guard_reply, summary

PORT = 9002
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")



@tool
def get_battery_level() -> str:
    """Battery state of charge in percent."""
    return call_mcp_tool_sync("get_battery_level", {})


@tool
def get_current_location() -> str:
    """Current location of the vehicle."""
    return call_mcp_tool_sync("get_current_location", {})


@tool
def estimate_range_km(battery_pct: float) -> str:
    """Estimated remaining range in kilometres for a given battery percentage."""
    return f"{battery_pct * KM_PER_PERCENT:.0f} km"


SYSTEM_PROMPT = """You are the battery and range specialist of an in-car assistant.
You only READ information; you cannot change anything in the car.
Rules:
1. For any question about the battery or range, call get_battery_level first. For range, then call estimate_range_km with that percentage.
2. Never state a battery level, range or location that did not come from a tool result.
3. If the question is not about battery, range or location, say briefly that you only handle those topics.
Answer in one or two complete sentences."""

agent = create_react_agent(ChatOllama(model=OLLAMA_MODEL, temperature=0),
                           [get_battery_level, get_current_location, estimate_range_km])

def answer(query: str) -> tuple[str, list]:
       result = agent.invoke({"messages": [("system", SYSTEM_PROMPT), ("user", query)]})
       calls = [{"name": tc["name"], "args": tc["args"], "source": "model"}
                for m in result["messages"] if m.type == "ai" for tc in (getattr(m, "tool_calls", None) or [])]
       reply = str(result["messages"][-1].content).strip()

       pct = None
       for m in result["messages"]:
           if m.type == "tool" and m.name == "get_battery_level":
               try:
                   pct = int(float(str(m.content)))
               except ValueError:
                   pass

       # the question was about the battery but the model never read it -> read it in code
       if pct is None and any(w in query.lower() for w in ("battery", "charge") + RANGE_WORDS):
        try:
            pct = int(float(call_mcp_tool_sync("get_battery_level", {})))
        except Exception:                      # tool failed or returned nothing: say so, never guess
            return "I can't read the battery level right now.", calls
        calls.append({"name": "get_battery_level", "args": {}, "source": "repair"})
        reply = summary(pct)

       return guard_reply(query, reply, pct), calls

class BatteryExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        payload = json.loads(context.get_user_input())      # {"query": ..., "history": [...]}
        reply, calls = await asyncio.to_thread(answer, payload["query"])
        await event_queue.enqueue_event(new_agent_text_message(json.dumps({"reply": reply, "calls": calls})))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("cancel not supported")


skill = AgentSkill(
    id="battery_status",
    name="Battery and range",
    description="Reports battery level, estimated range and location; warns when the battery is low.",
    tags=["battery", "range", "location", "car"],
    examples=["How much battery is left?", "How far can I drive?"],
)

agent_card = AgentCard(
    name="Battery Agent",
    description="LLM-based specialist for battery and range, using read-only tools on the car's MCP server.",
    url=f"http://localhost:{PORT}/",
    version="0.2.0",
    default_input_modes=["text"],
    default_output_modes=["text"],
    capabilities=AgentCapabilities(streaming=False),
    skills=[skill],
)

app = A2AStarletteApplication(
    agent_card=agent_card,
    http_handler=DefaultRequestHandler(agent_executor=BatteryExecutor(), task_store=InMemoryTaskStore()),
)

if __name__ == "__main__":
    uvicorn.run(app.build(), host="127.0.0.1", port=PORT)
