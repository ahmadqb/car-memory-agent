"""PYTHONPATH=. python test_battery_guards.py"""
from battery_guards import guard_reply

assert "342" in guard_reply("how far can I drive?", "You can drive approximately 320 km.", 76)   # invented number
assert "342" in guard_reply("what's my range", "The battery is at 76%.", 76)                    # range question, no range
assert guard_reply("how much battery?", "The battery level is 76%.", 76) == "The battery level is 76%."
assert guard_reply("battery?", "The battery level is 12%.", 12).endswith("charging soon.")
assert guard_reply("hello", "I only handle battery topics.", None) == "I only handle battery topics."
print("BATTERY GUARD TESTS PASSED")
