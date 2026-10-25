"""python test_assistant.py -> same request at two times of day must trigger different tool calls."""
import os
from datetime import datetime

os.environ["MEMORY_DB"] = "test_memory.db"
os.environ["CAR_STATE_FILE"] = "test_car_state.json"   # inherited by the car_server subprocess

import memory
from signals import generate_events
from assistant import USER_ID, build_context, run_assistant

QUERY = "I'm cold, play something to wake me up"


def setup():
    for f in ("test_memory.db", "test_car_state.json"):
        if os.path.exists(f):
            os.remove(f)
    memory.init_db(reset=True)
    for ts, s, v in generate_events(days=14):
        memory.add_observation(USER_ID, s, v, ts, derive=False)
    memory.derive_facts(USER_ID)


def find(calls, name):
    return [c["args"] for c in calls if c["name"] == name]


def check(label, now, temp, genre):
    context = build_context(USER_ID, now)
    assert genre in context and str(int(temp)) in context, f"{label}: wrong context\n{context}"
    reply, calls = run_assistant(QUERY, now)
    print(f"[{label}] tool calls: {calls}\n[{label}] reply: {reply}\n")

    temps = [float(a["temp_c"]) for a in find(calls, "set_cabin_temperature")]
    genres = [str(a["genre"]).lower() for a in find(calls, "play_media")]
    assert temp in temps, f"{label}: expected set_cabin_temperature({temp}), got {temps}"
    assert any(genre in g for g in genres), f"{label}: expected play_media({genre}), got {genres}"
    print(f"OK {label}: {temp} C and {genre}\n")


def check_no_action(label, now, query):
    from guards import claims_action
    reply, calls = run_assistant(query, now)
    print(f"[{label}] tool calls: {calls}\n[{label}] reply: {reply}\n")
    print(f"[{label}] repaired by code: {[c['name'] for c in calls if c.get('source') == 'repair']}")
    assert not os.path.exists(os.environ["CAR_STATE_FILE"]), f"{label}: car state changed although nothing was requested"
    assert not claims_action(reply), f"{label}: reply claims an action that did not happen: {reply}"
    print(f"OK {label}: car untouched, reply honest\n")

if __name__ == "__main__":
    setup()
    # negative tests first: the car state file must NOT be created
    check_no_action("capabilities", datetime(2026, 10, 15, 8, 0), "what can you do?")
    check_no_action("bare topic", datetime(2026, 10, 15, 8, 0), "temperature")
    check_no_action("greeting", datetime(2026, 10, 15, 19, 0), "hello")
    # positive tests
    check("morning", datetime(2026, 10, 15, 8, 0), 22.0, "electronic")
    check("evening", datetime(2026, 10, 15, 19, 0), 21.0, "jazz")
    for f in ("test_memory.db", "test_car_state.json"):
        if os.path.exists(f):
            os.remove(f)
    print("PHASE 2 TESTS PASSED")