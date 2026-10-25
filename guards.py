"""Deterministic guardrails around the LLM:
- plan(): which actions the driver actually asked for, which values are allowed, which are required
- classify_result(): did a tool call succeed, or was it refused (by the guard or by the car)?
- compose_reply(): the final reply may only claim what really happened."""
import difflib
import re
from datetime import datetime

import memory

KNOWN_GENRES = {"jazz", "electronic", "pop", "rock", "classical", "techno", "house",
                "lofi", "hiphop", "country", "metal", "blues"}

TEMP_WORDS = re.compile(
    r"\b(cold\w*|freez\w*|chilly|warm\w*|hot|heat\w*|stuffy|degrees?|celsius)\b|°", re.I)
SET_VERB = re.compile(r"\b(set|make|change|put)\b", re.I)
MEDIA_ACTION = re.compile(
    r"\b(play|put on|start|listen|wake me|cheer me|some music|something to (wake|listen))\b", re.I)
NUMBER = re.compile(r"(?<![\d.,])(\d{2}(?:[.,]\d)?)(?![\d])")

# Typo tolerance for a SMALL vocabulary only (a bigger one causes false positives like state -> start)
TYPO_VOCAB = ["change", "temperature", "degrees", "warmer", "colder", "freezing", "music", "playlist", "listen"]
TYPO_PROTECTED = {"charge", "charger", "state", "range", "battery", "location"}
TEMP_TOPIC = re.compile(r"temp|degree|warm|cold|hot|heat|freez|chill|celsius|°", re.I)
MEDIA_TOPIC = re.compile(r"music|song|play|listen|genre|radio|" + "|".join(sorted(KNOWN_GENRES)), re.I)


def fix_typos(text: str) -> str:
    out = []
    for token in re.findall(r"\S+", text):
        core = re.sub(r"[^\w'-]", "", token).lower()
        if len(core) >= 5 and core not in TYPO_VOCAB and core not in TYPO_PROTECTED:
            match = difflib.get_close_matches(core, TYPO_VOCAB, n=1, cutoff=0.8)
            if match:
                token = match[0]
        out.append(token)
    return " ".join(out)


def plan(user_id: str, now: datetime, query: str, prev_query: str | None = None) -> dict:
    bucket = memory.time_bucket(now)
    facts = {f["key"]: f["value"] for f in memory.get_profile(user_id) if f["key"].endswith(f"@{bucket}")}
    pref_temp = facts.get(f"cabin_temp_set@{bucket}")
    pref_genre = facts.get(f"media_genre_played@{bucket}")

    own = fix_typos(query)
    short = len(own.split()) <= 3
    ctx = fix_typos(prev_query) if (short and prev_query) else ""

    named = [t for t in re.findall(r"[a-z\-]+", own.lower()) if t in KNOWN_GENRES]
    numbers = [float(x.replace(",", ".")) for x in NUMBER.findall(own)]
    numbers = [n for n in numbers if 10 <= n <= 40]

    # Intent comes from the message itself. Only a short bare VALUE ("30", "pop") may continue the
    # previous turn; any other short message ("music", "yes") must not re-trigger an old command.
    temp_action = (bool(TEMP_WORDS.search(own))
                   or (bool(SET_VERB.search(own)) and bool(numbers))
                   or (short and bool(numbers) and bool(TEMP_WORDS.search(ctx) or SET_VERB.search(ctx))))
    media_action = bool(MEDIA_ACTION.search(own)) or (short and bool(named))

    temps, genres, required = set(), set(), {}
    if temp_action:
        if pref_temp:
            temps.add(float(pref_temp))
        temps |= set(numbers)
        value = numbers[0] if numbers else (float(pref_temp) if pref_temp else None)
        if value is not None:
            required["set_cabin_temperature"] = value
    if media_action:
        if pref_genre:
            genres.add(pref_genre.lower())
        genres |= set(named)
        value = named[0] if named else pref_genre
        if value:
            required["play_media"] = value.lower()

    return {"bucket": bucket, "text": (own + " " + ctx).strip(), "temps": temps, "genres": genres,
            "required": required,
            "prefs": {"set_cabin_temperature": pref_temp, "play_media": pref_genre}}

def classify_result(content: str) -> str:
    c = str(content).strip()
    if c.startswith("Refused") and "outside the allowed range" in c:
        return "car_refused"
    if c.startswith("Refused"):
        return "guard_refused"
    if c.startswith(("Cabin temperature set", "Now playing")):
        return "ok"
    return "other"


NEGATION = re.compile(r"couldn't|could not|can't|cannot|unable|\bnot\b|n't|refus", re.I)
CLAIM_TEMP = re.compile(
    r"\b(set|changed|adjusted|raised|lowered|turned)\b[^.?!]*?(?:temperature|degrees|cabin|°)", re.I)
CLAIM_MEDIA = re.compile(r"\b(now playing|is playing|are playing|playing|played|started)\b", re.I)


def claims_action(reply: str) -> set:
    """Which actions does the reply claim to have done?"""
    claimed = set()
    for sentence in re.split(r"(?<=[.!?])\s+", reply):
        if "?" in sentence or NEGATION.search(sentence):
            continue
        if CLAIM_TEMP.search(sentence):
            claimed.add("set_cabin_temperature")
        if CLAIM_MEDIA.search(sentence):
            claimed.add("play_media")
    return claimed


def compose_reply(llm_reply: str, results: list[dict], bucket: str, prefs: dict, topic_text: str = "") -> str:
    ok = sorted((r for r in results if r["status"] == "ok"), key=lambda r: r["tool"] != "set_cabin_temperature")
    car_refused = [r for r in results if r["status"] == "car_refused"]

    if ok or car_refused:
        sentences = []
        if ok:
            parts, used_pref = [], []
            for r in ok:
                if r["tool"] == "set_cabin_temperature":
                    t = float(r["args"]["temp_c"])
                    parts.append(f"set the cabin temperature to {t:g}°C")
                    used_pref.append(bool(prefs.get(r["tool"])) and float(prefs[r["tool"]]) == t)
                else:
                    g = str(r["args"]["genre"])
                    parts.append(f"started the {g} playlist")
                    used_pref.append(bool(prefs.get(r["tool"])) and prefs[r["tool"]].lower() == g.lower())
            s = "I " + " and ".join(parts)
            if all(used_pref):
                s += f", as you usually prefer in the {bucket}"
            sentences.append(s + ".")
        for r in car_refused:
            sentences.append("I couldn't change the temperature: " + r["text"].replace("Refused: ", "", 1))
        return " ".join(sentences)

    # The guard blocked a call on a topic the driver did mention: do not let the model explain
    # the refusal (it invents reasons). Ask a fixed clarifying question instead.
    blocked = {r["tool"] for r in results if r["status"] == "guard_refused"}
    questions = []
    if "set_cabin_temperature" in blocked and TEMP_TOPIC.search(topic_text):
        questions.append("What temperature would you like me to set?")
    if "play_media" in blocked and MEDIA_TOPIC.search(topic_text):
        questions.append("What kind of music would you like me to play?")
    if questions:
        return " ".join(questions)

    text = llm_reply.strip()
    if claims_action(text):
        return "I haven't changed anything yet. What would you like me to do?"
    if len(text.split()) < 4 or text[:1].islower():   # fragments like 'as you usually prefer.'
        return "Could you tell me a bit more about what you'd like me to do?"
    return text