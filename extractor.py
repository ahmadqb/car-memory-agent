"""Phase 3: turn explicit preference statements in chat into stored memories.
The LLM only proposes (signal, value). Code decides the time of day, checks that the value really
appears in the message, checks the allowed range, and only then stores it."""
import json
import os
import re
from datetime import datetime
from typing import Literal, Union

from pydantic import BaseModel, Field, ValidationError

import memory
from guards import KNOWN_GENRES

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
MIN_TEMP, MAX_TEMP = 16.0, 28.0

# Only statements that sound like a lasting preference are even sent to the model.
PREF_GATE = re.compile(
    r"\b(i (always|usually|normally|typically|prefer|like|love|enjoy)|remember|from now on|my favou?rite)\b", re.I)
BUCKET_WORDS = {
    "morning": re.compile(r"\bmornings?\b", re.I),
    "afternoon": re.compile(r"\bafternoons?\b", re.I),
    "evening": re.compile(r"\bevenings?\b", re.I),
    "night": re.compile(r"\bnights?\b", re.I),
}
NUMBER = re.compile(r"(?<![\d.,])(\d{1,2}(?:[.,]\d)?)(?![\d])")

EXTRACT_PROMPT = """You extract driver preferences from ONE message.
Supported types only:
- cabin_temp_set: the preferred cabin temperature in degrees Celsius (a number)
- media_genre_played: the preferred music genre (one word, for example jazz)

Return JSON exactly like {"memories": [{"signal": "cabin_temp_set", "value": "23"}]}.
Only include what the driver states explicitly as a lasting preference.
Requests ("play jazz"), feelings ("I'm cold"), questions and everything else give {"memories": []}.
Never guess a value that is not written in the message."""


class Candidate(BaseModel):
    signal: Literal["cabin_temp_set", "media_genre_played"]
    value: Union[str, int, float]


class Extraction(BaseModel):
    memories: list[Candidate] = Field(default_factory=list)


def get_llm():
    from langchain_ollama import ChatOllama
    return ChatOllama(model=OLLAMA_MODEL, temperature=0, format="json")


def _parse(raw: str) -> Extraction:
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(raw).strip())
    return Extraction.model_validate(json.loads(raw))


def _validate(c: Candidate, text: str):
    """Returns the cleaned value, or None if the candidate is not grounded in the message."""
    if c.signal == "cabin_temp_set":
        m = re.search(r"\d+(?:[.,]\d)?", str(c.value))
        if not m:
            return None
        t = float(m.group().replace(",", "."))
        in_text = {float(x.replace(",", ".")) for x in NUMBER.findall(text)}
        if t not in in_text or not MIN_TEMP <= t <= MAX_TEMP:
            return None
        return f"{t:g}"
    g = str(c.value).strip().lower()
    if g in KNOWN_GENRES and re.search(rf"\b{re.escape(g)}\b", text.lower()):
        return g
    return None


def extract_memories(text: str, now: datetime, llm=None) -> list[dict]:
    if not PREF_GATE.search(text):
        return []
    found = [b for b, rx in BUCKET_WORDS.items() if rx.search(text)]
    if len(found) > 1:          # two times of day in one message: too ambiguous, store nothing
        return []
    bucket, explicit = (found[0], True) if found else (memory.time_bucket(now), False)

    llm = llm or get_llm()
    try:
        data = _parse(llm.invoke([("system", EXTRACT_PROMPT), ("user", text)]).content)
    except (ValueError, ValidationError):   # invalid JSON or wrong shape -> store nothing
        return []

    out, seen = [], set()
    for c in data.memories:
        value = _validate(c, text)
        if value is not None and c.signal not in seen:
            seen.add(c.signal)
            out.append({"signal": c.signal, "bucket": bucket, "value": value, "bucket_explicit": explicit})
    return out


def remember(user_id: str, text: str, now: datetime | None = None, llm=None) -> list[dict]:
    now = now or datetime.now()
    items = extract_memories(text, now, llm)
    for m in items:
        memory.add_stated(user_id, m["signal"], m["bucket"], m["value"], now)
    return items


def ack(items: list[dict]) -> str:
    parts = []
    for m in items:
        what = f"{m['value']}°C" if m["signal"] == "cabin_temp_set" else f"{m['value']} music"
        parts.append(f"{what} in the {m['bucket']}")
    s = "Got it. I'll remember " + " and ".join(parts) + "."
    if not items[0]["bucket_explicit"]:
        s += " You didn't name a time of day, so I used the current one. Tell me if you meant another."
    return s