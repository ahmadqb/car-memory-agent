"""Simulated vehicle/user signals for one driver over several days."""
import random
from datetime import datetime, timedelta


def _pick(rng, main, other, p_main):
    return main if rng.random() < p_main else other


def generate_events(days: int = 14, seed: int = 42, start: datetime = datetime(2026, 10, 1)):
    """Returns a list of (timestamp, signal, value). The driver likes 22C and electronic
    music in the morning and 21C and jazz in the evening, but is not 100% consistent."""
    rng = random.Random(seed)
    events = []
    for d in range(days):
        day = start + timedelta(days=d)

        t = day.replace(hour=7, minute=rng.randint(0, 59))
        events.append((t, "cabin_temp_set", _pick(rng, "22", "21", 0.85)))
        events.append((t + timedelta(minutes=1), "media_genre_played", _pick(rng, "electronic", "pop", 0.8)))
        events.append((t + timedelta(minutes=2), "destination_set", _pick(rng, "office", "gym", 0.9)))

        t = day.replace(hour=18, minute=rng.randint(0, 59))
        events.append((t, "cabin_temp_set", _pick(rng, "21", "22", 0.8)))
        events.append((t + timedelta(minutes=1), "media_genre_played", _pick(rng, "jazz", "pop", 0.75)))
        events.append((t + timedelta(minutes=2), "destination_set", _pick(rng, "home", "supermarket", 0.95)))
    return events
