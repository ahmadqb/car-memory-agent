"""Deterministic guard for the battery agent: the reply may only contain numbers the tools produced."""
import re

KM_PER_PERCENT = 4.5   # mock consumption model
LOW_BATTERY = 20
RANGE_WORDS = ("range", "how far", "drive", "km", "distance")


def range_km(pct: int) -> int:
    return round(pct * KM_PER_PERCENT)


def summary(pct: int) -> str:
    return f"The battery is at {pct}%, which is about {range_km(pct)} km of range."


def guard_reply(query: str, reply: str, pct: int | None) -> str:
    if pct is None:
        return reply
    asks_range = any(w in query.lower() for w in RANGE_WORDS)
    allowed = {str(pct), str(range_km(pct))}
    numbers = set(re.findall(r"\d+", reply))
    # invented number, or a range question answered without the computed range -> use the code-built answer
    if numbers - allowed or (asks_range and str(range_km(pct)) not in numbers):
        reply = summary(pct)
    if pct < LOW_BATTERY and "charg" not in reply.lower():
        reply += " The battery is low, so I recommend charging soon."
    return reply
