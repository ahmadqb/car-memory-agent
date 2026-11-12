"""python eval_e2e.py -> fixed scenarios through run_assistant; checks the CAR STATE, not the wording. Needs Ollama."""
import json
import os
from datetime import datetime

os.environ["MEMORY_DB"] = "eval_memory.db"
os.environ["CAR_STATE_FILE"] = "eval_car_state.json"   # inherited by the car_server subprocess

import memory
from signals import generate_events
from assistant import USER_ID, run_assistant

STATE_FILE = os.environ["CAR_STATE_FILE"]
DEFAULT = {"cabin_temp_c": 20.0, "now_playing": None}
MORNING, EVENING, NIGHT = (datetime(2026, 10, 15, h, m) for h, m in [(8, 0), (18, 30), (23, 0)])

CASES = [  # (name, time, query, expected car state)
    ("morning habits", MORNING, "I'm cold, play something to wake me up", {"cabin_temp_c": 22.0, "now_playing": "electronic"}),
    ("evening habits", EVENING, "I'm cold, play something to wake me up", {"cabin_temp_c": 21.0, "now_playing": "jazz"}),
    ("no night habits -> no action", NIGHT, "I'm cold, play something to wake me up", DEFAULT),
    ("small talk", MORNING, "hello, what can you do?", DEFAULT),
    ("only a question", MORNING, "what is the temperature?", DEFAULT),
    ("out of range refused", MORNING, "set the temperature to 35 degrees", DEFAULT),
    ("explicit value", MORNING, "set the temperature to 25 degrees", {"cabin_temp_c": 25.0, "now_playing": None}),
]


def car_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return {**DEFAULT, **json.load(f)}
    except FileNotFoundError:
        return dict(DEFAULT)


def setup():
    if os.path.exists("eval_memory.db"):
        os.remove("eval_memory.db")
    memory.init_db(reset=True)
    for ts, s, v in generate_events(days=14):
        memory.add_observation(USER_ID, s, v, ts, derive=False)
    memory.derive_facts(USER_ID)


if __name__ == "__main__":
    passed = 0
    for name, now, query, expected in CASES:
        setup()
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        reply, calls = run_assistant(query, now=now)
        got = car_state()
        ok = all(got[k] == v for k, v in expected.items())
        passed += ok
        print(f"{'OK  ' if ok else 'FAIL'} {name}: state={ {k: got[k] for k in expected} }"
              + ("" if ok else f"  expected {expected}") + f"\n      reply: {reply[:100]!r}")
    print(f"\n{passed}/{len(CASES)} scenarios passed")
