"""python test_extractor.py  (fake LLM, deterministic; checks the validation around the model)"""
import os
from datetime import datetime

os.environ["MEMORY_DB"] = "test_extractor.db"
import memory
from signals import generate_events
from guards import plan
from extractor import extract_memories, remember, ack

U = "t"
NOW = datetime(2026, 10, 15, 14, 0)          # afternoon
MORNING = datetime(2026, 10, 15, 8, 0)


class FakeLLM:
    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def invoke(self, messages):
        self.calls += 1
        return type("R", (), {"content": self.reply})()


def temp(v): return '{"memories":[{"signal":"cabin_temp_set","value":%s}]}' % v
def genre(v): return '{"memories":[{"signal":"media_genre_played","value":"%s"}]}' % v


# 1. a request is not a preference: the model is not even called
llm = FakeLLM(genre("jazz"))
assert extract_memories("play some jazz", NOW, llm) == [] and llm.calls == 0
# 2. explicit preference with a time of day
r = extract_memories("I always like it at 23 degrees in the morning", NOW, FakeLLM(temp('"23"')))
assert r == [{"signal": "cabin_temp_set", "bucket": "morning", "value": "23", "bucket_explicit": True}], r
# 3. numeric JSON value, and a fenced JSON answer
assert extract_memories("I always like it at 23 degrees in the morning", NOW, FakeLLM(temp("23")))[0]["value"] == "23"
assert extract_memories("I prefer jazz in the evening", NOW, FakeLLM("```json\n" + genre("jazz") + "\n```"))[0]["value"] == "jazz"
# 4. hallucinated value that is not in the message
assert extract_memories("I always like it at 23 degrees in the morning", NOW, FakeLLM(temp('"25"'))) == []
# 5. out of range
assert extract_memories("I always like it at 35 degrees in the morning", NOW, FakeLLM(temp('"35"'))) == []
# 6. genre not in the message / not a known genre
assert extract_memories("I prefer jazz in the evening", NOW, FakeLLM(genre("rock"))) == []
assert extract_memories("I prefer polka in the evening", NOW, FakeLLM(genre("polka"))) == []
# 7. two times of day -> nothing stored, model not called
llm = FakeLLM(genre("jazz"))
assert extract_memories("I like jazz in the morning and pop in the evening", NOW, llm) == [] and llm.calls == 0
# 8. invalid JSON, wrong shape, unsupported signal
for bad in ["not json", "[1,2]", '{"memories":[{"signal":"seat_heating","value":"3"}]}']:
    assert extract_memories("I always like it at 23 degrees in the morning", NOW, FakeLLM(bad)) == [], bad
# 9. no time of day named -> current bucket, flagged as not explicit
r = extract_memories("I like 24 degrees", NOW, FakeLLM(temp('"24"')))
assert r == [{"signal": "cabin_temp_set", "bucket": "afternoon", "value": "24", "bucket_explicit": False}], r
# 10. two memories in one message
both = '{"memories":[{"signal":"media_genre_played","value":"jazz"},{"signal":"cabin_temp_set","value":"21"}]}'
r = extract_memories("I usually listen to jazz and like 21 degrees in the evening", NOW, FakeLLM(both))
assert {(x["signal"], x["value"]) for x in r} == {("media_genre_played", "jazz"), ("cabin_temp_set", "21")}, r
print("extraction: ok")

# 11. stated memory is stored, wins over the observed fact, and the assistant plan uses it
if os.path.exists("test_extractor.db"):
    os.remove("test_extractor.db")
memory.init_db(reset=True)
for ts, s, v in generate_events():
    memory.add_observation(U, s, v, ts, derive=False)
memory.derive_facts(U)
assert plan(U, MORNING, "I'm cold")["required"] == {"set_cabin_temperature": 22.0}   # observed
items = remember(U, "I always like it at 23 degrees in the morning", NOW, FakeLLM(temp('"23"')))
prof = {f["key"]: f for f in memory.get_profile(U)}
assert prof["cabin_temp_set@morning"]["value"] == "23" and prof["cabin_temp_set@morning"]["source"] == "stated"
assert prof["cabin_temp_set@evening"]["source"] == "observed"                          # others untouched
assert plan(U, MORNING, "I'm cold")["required"] == {"set_cabin_temperature": 23.0}      # stated wins
memory.derive_facts(U)                                                                  # re-deriving keeps it
assert {f["key"]: f for f in memory.get_profile(U)}["cabin_temp_set@morning"]["value"] == "23"
print("stated memory: ok")

# 12. forget removes the stated memory AND the observed one behind it
assert memory.forget(U, "cabin_temp_set@morning") >= 1
memory.derive_facts(U)
assert "cabin_temp_set@morning" not in {f["key"] for f in memory.get_profile(U)}
memory.forget(U)
assert memory.get_profile(U) == []
print("forget: ok")

# 13. acknowledgement text
assert ack([{"signal": "cabin_temp_set", "bucket": "morning", "value": "23", "bucket_explicit": True}]) == "Got it. I'll remember 23°C in the morning."
assert "current one" in ack([{"signal": "media_genre_played", "bucket": "afternoon", "value": "jazz", "bucket_explicit": False}])
print("ack: ok")

os.remove("test_extractor.db")
print("ALL EXTRACTOR TESTS PASSED")