"""Comfort agent as an A2A service. Run: python comfort_agent.py  (port 9001)"""
import asyncio
import json

import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.utils import new_agent_text_message

import memory
from assistant import run_assistant

PORT = 9001


class ComfortExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        payload = json.loads(context.get_user_input())      # {"query": ..., "history": [[role, text], ...]}
        history = [tuple(h) for h in payload.get("history", [])]
        # run_assistant is blocking and uses asyncio.run internally -> run it in a worker thread
        reply, calls = await asyncio.to_thread(run_assistant, payload["query"], None, history)
        await event_queue.enqueue_event(new_agent_text_message(json.dumps({"reply": reply, "calls": calls})))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("cancel not supported")


skill = AgentSkill(
    id="comfort_control",
    name="Cabin comfort and media",
    description="Sets cabin temperature and plays music, using the driver's remembered preferences.",
    tags=["climate", "media", "car"],
    examples=["I'm cold, play something to wake me up"],
)

agent_card = AgentCard(
    name="Comfort Agent",
    description="Controls cabin temperature and media through the car's MCP server.",
    url=f"http://localhost:{PORT}/",
    version="0.1.0",
    default_input_modes=["text"],
    default_output_modes=["text"],
    capabilities=AgentCapabilities(streaming=False),
    skills=[skill],
)

app = A2AStarletteApplication(
    agent_card=agent_card,
    http_handler=DefaultRequestHandler(agent_executor=ComfortExecutor(), task_store=InMemoryTaskStore()),
)

if __name__ == "__main__":
    memory.init_db(reset=False)
    uvicorn.run(app.build(), host="127.0.0.1", port=PORT)
