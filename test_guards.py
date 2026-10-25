"""python test_guards.py  (no LLM needed, fast and deterministic)"""
import os
from datetime import datetime

os.environ["MEMORY_DB"] = "test_guards.db"
import memory
from signals import generate_events
from guards import plan, classify_result, claims_action, compose_reply

U = "t"
MORNING, EVENING, NIGHT = datetime(2026, 10, 15, 8, 0), datetime(2026, 10, 15, 19, 0), datetime(2026, 10, 15, 2, 0)

if os.path.exists("test_guards.db"):
    os.remove("test_guards.db")
memory.init_db(reset=True)
for ts, s, v in generate_events():
    memory.add_observation(U, s, v, ts, derive=False)
memory.derive_facts(U)

# --- plan ---
p = plan(U, MORNING, "I'm cold, play something to wake me up")
assert p["required"] == {"set_cabin_temperature": 22.0, "play_media": "electronic"}, p
p = plan(U, EVENING, "I'm cold, play something to wake me up")
assert p["required"] == {"set_cabin_temperature": 21.0, "play_media": "jazz"}, p
for q in ["what can you do?", "temperature", "music", "do you have music ?", "hello", "i'm called"]:
    p = plan(U, MORNING, q)
    assert p["required"] == {} and not p["temps"] and not p["genres"], (q, p)
p = plan(U, MORNING, "set it to 24 degrees")
assert p["required"] == {"set_cabin_temperature": 24.0} and p["temps"] == {22.0, 24.0}, p
p = plan(U, MORNING, "30", prev_query="I'm cold")
assert p["required"] == {"set_cabin_temperature": 30.0}, p
assert plan(U, MORNING, "30")["required"] == {}                       # a bare number without context
p = plan(U, MORNING, "pop")
assert p["required"] == {"play_media": "pop"}, p
p = plan(U, MORNING, "play something")
assert p["genres"] == {"electronic"}, p                                # no invented genre like "something"
assert plan(U, MORNING, "play jazz")["required"] == {"play_media": "jazz"}
p = plan(U, NIGHT, "I'm cold")                                         # no stored preference at night
assert p["required"] == {} and p["temps"] == set(), p
print("plan: ok")

# --- classify ---
assert classify_result("Cabin temperature set to 22.0 C.") == "ok"
assert classify_result("Now playing: jazz playlist.") == "ok"
assert classify_result("Refused: 30.0 C is outside the allowed range 16.0-28.0 C.") == "car_refused"
assert classify_result("Refused: the driver did not ask for music") == "guard_refused"
print("classify: ok")

# --- claims ---
assert claims_action("I set the temperature to 22 degrees, as you usually prefer in the morning.") == {"set_cabin_temperature"}
assert claims_action("The electronic playlist is playing as you usually prefer.") == {"play_media"}
assert claims_action("I can control the car's temperature and play music.") == set()
assert claims_action("What temperature would you like the cabin to be set to?") == set()
assert claims_action("I couldn't set the temperature to 35.") == set()
assert claims_action("The cabin temperature is currently set to 21.0°C.") == set()
print("claims: ok")

# --- compose ---
prefs = {"set_cabin_temperature": "22", "play_media": "electronic"}
ok = [{"tool": "set_cabin_temperature", "args": {"temp_c": 22.0}, "status": "ok", "text": ""},
      {"tool": "play_media", "args": {"genre": "electronic"}, "status": "ok", "text": ""}]
r = compose_reply("as you usually prefer", ok, "morning", prefs)
assert r == "I set the cabin temperature to 22°C and started the electronic playlist, as you usually prefer in the morning.", r
r = compose_reply("x", [{"tool": "set_cabin_temperature", "args": {"temp_c": 30.0}, "status": "car_refused",
                         "text": "Refused: 30.0 C is outside the allowed range 16.0-28.0 C."}], "morning", prefs)
assert r == "I couldn't change the temperature: 30.0 C is outside the allowed range 16.0-28.0 C.", r
assert compose_reply("I set the temperature to 22 degrees.", [], "morning", prefs) == "I haven't changed anything yet. What would you like me to do?"
assert compose_reply("as you usually prefer.", [], "morning", prefs).startswith("Could you tell me")
assert compose_reply("I can control the car's temperature and play music.", [], "morning", prefs) == "I can control the car's temperature and play music."
print("compose: ok")


# --- follow-ups: only a bare value continues the previous turn ---
assert plan(U, MORNING, "music", prev_query="chnage temprature to 28")["required"] == {}
assert plan(U, MORNING, "yes", prev_query="warmer")["required"] == {}
assert plan(U, MORNING, "28", prev_query="hello")["required"] == {}
assert plan(U, MORNING, "28", prev_query="I'm cold")["required"] == {"set_cabin_temperature": 28.0}
assert plan(U, MORNING, "pop", prev_query="music")["required"] == {"play_media": "pop"}
print("follow-ups: ok")
# --- typos ---
from guards import fix_typos
assert plan(U, MORNING, "chnage temprature to 28")["required"] == {"set_cabin_temperature": 28.0}
assert plan(U, MORNING, "play musik")["required"] == {"play_media": "electronic"}
assert plan(U, MORNING, "whats the state of charge")["required"] == {}
assert plan(U, MORNING, "battery charge 80")["required"] == {}
assert plan(U, MORNING, "what is the temprature")["required"] == {}      # topic only, still no action
assert fix_typos("state charge battery") == "state charge battery"
print("typos: ok")

# --- guard refusal -> fixed question, no invented explanation ---
ref_m = [{"tool": "play_media", "args": {"genre": "electronic"}, "status": "guard_refused", "text": "Refused: x"}]
assert compose_reply("the car's media player has no electronic music", ref_m, "afternoon", prefs, "music") == "What kind of music would you like me to play?"
ref_t = [{"tool": "set_cabin_temperature", "args": {"temp_c": 22}, "status": "guard_refused", "text": "Refused: x"}]
assert compose_reply("22 degrees is not possible", ref_t, "afternoon", prefs, "yes warmer") == "What temperature would you like me to set?"
both = ref_t + ref_m   # a question about capabilities: no topic -> the model's own answer is kept
assert compose_reply("I can control the cabin temperature and play media.", both, "morning", prefs, "what can you do ?") == "I can control the cabin temperature and play media."
print("refusal questions: ok")

os.remove("test_guards.db")
print("ALL GUARD TESTS PASSED")