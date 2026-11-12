"""python test_memory.py  (plain asserts, no pytest needed)"""
import os
from datetime import datetime, timedelta

os.environ["MEMORY_DB"] = "test_memory.db"
import importlib
import memory
importlib.reload(memory)
from signals import generate_events

U = "t"


def fresh():
    if os.path.exists("test_memory.db"):
        os.remove("test_memory.db")
    memory.init_db(reset=True)


def facts():
    return {f["key"]: f for f in memory.get_profile(U)}


# 1. learns the main preferences from simulated days
fresh()
for ts, s, v in generate_events():
    memory.add_observation(U, s, v, ts, derive=False)
memory.derive_facts(U)
f = facts()
assert f["cabin_temp_set@morning"]["value"] == "22"
assert f["cabin_temp_set@evening"]["value"] == "21"
assert f["media_genre_played@morning"]["value"] == "electronic"
assert f["media_genre_played@evening"]["value"] == "jazz"
print("1 ok: learns preferences")

# 2. too little data -> no fact
fresh()
t0 = datetime(2026, 10, 1, 7, 0)
memory.add_observation(U, "cabin_temp_set", "22", t0)
memory.add_observation(U, "cabin_temp_set", "22", t0 + timedelta(days=1))
assert facts() == {}
print("2 ok: no fact with 2 observations")

# 3. mixed signals -> no fact (no clear preference)
fresh()
for i, v in enumerate(["20", "21", "22", "23", "24", "20"]):
    memory.add_observation(U, "cabin_temp_set", v, t0 + timedelta(days=i))
assert "cabin_temp_set@morning" not in facts()
print("3 ok: no fact without a clear majority")

# 4. preference changes: 10 new observations of 23 replace the old 22
fresh()
for i in range(10):
    memory.add_observation(U, "cabin_temp_set", "22", t0 + timedelta(days=i))
assert facts()["cabin_temp_set@morning"]["value"] == "22"
for i in range(10, 20):
    memory.add_observation(U, "cabin_temp_set", "23", t0 + timedelta(days=i))
assert facts()["cabin_temp_set@morning"]["value"] == "23"
print("4 ok: preference change is picked up")

# 5. forget one key, and it does not come back
fresh()
for i in range(5):
    memory.add_observation(U, "cabin_temp_set", "22", t0 + timedelta(days=i))
memory.add_observation(U, "media_genre_played", "jazz", t0)
assert memory.forget(U, "cabin_temp_set@morning") == 1
memory.derive_facts(U)
assert "cabin_temp_set@morning" not in facts()
print("5 ok: forget one key")

# 6. forget everything
memory.forget(U)
assert facts() == {}
print("6 ok: forget all")

# 7. decay: old observations weigh less, stale facts expire
fresh()
base = datetime(2026, 10, 1, 7, 0)
for i in range(5):    # 5 old votes for 21
    memory.add_observation(U, "cabin_temp_set", "21", base + timedelta(days=i), derive=False)
for i in range(3):    # 3 recent votes for 23, 40 days later
    memory.add_observation(U, "cabin_temp_set", "23", base + timedelta(days=40 + i), derive=False)
memory.derive_facts(U)
assert facts()["cabin_temp_set@morning"]["value"] == "23", facts()
memory.derive_facts(U, now=base + timedelta(days=200))
assert "cabin_temp_set@morning" not in facts()
print("7 ok: decay and expiry")

os.remove("test_memory.db")
print("ALL TESTS PASSED")
