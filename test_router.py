"""PYTHONPATH=. python test_router.py"""
from router import pick_agent

assert pick_agent("how much battery is left?") == "battery"
assert pick_agent("what's my range") == "battery"
assert pick_agent("do I need to charge soon?") == "battery"
assert pick_agent("I'm cold") == "comfort"
assert pick_agent("play some jazz") == "comfort"
assert pick_agent("hello") == "comfort"
print("ROUTER TESTS PASSED")
