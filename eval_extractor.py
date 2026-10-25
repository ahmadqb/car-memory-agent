"""python eval_extractor.py -> runs the REAL model on labeled sentences (needs Ollama running)."""
from datetime import datetime

from extractor import OLLAMA_MODEL, extract_memories, get_llm

NOW = datetime(2026, 10, 15, 14, 0)   # afternoon

CASES = [
    ("I always like it at 23 degrees in the morning", {("cabin_temp_set", "morning", "23")}),
    ("I prefer jazz in the evening", {("media_genre_played", "evening", "jazz")}),
    ("I love rock in the afternoons", {("media_genre_played", "afternoon", "rock")}),
    ("Remember that I like 21 degrees at night", {("cabin_temp_set", "night", "21")}),
    ("From now on I want 22 degrees in the morning", {("cabin_temp_set", "morning", "22")}),
    ("I usually listen to jazz and like 21 degrees in the evening",
     {("media_genre_played", "evening", "jazz"), ("cabin_temp_set", "evening", "21")}),
    ("I like 24 degrees", {("cabin_temp_set", "afternoon", "24")}),            # no time of day -> current one
    ("I'm cold", set()),
    ("play some jazz", set()),
    ("I like it at 35 degrees in the morning", set()),                          # out of range
    ("I like pizza and my name is Ahmad", set()),                               # unsupported, personal
    ("I like jazz in the morning and pop in the evening", set()),               # two times of day: rejected by design
    ("I hate pop music", set()),                                                # negative preference: unsupported
]

if __name__ == "__main__":
    llm = get_llm()
    tp = fp = fn = 0
    for text, expected in CASES:
        got = {(m["signal"], m["bucket"], m["value"]) for m in extract_memories(text, NOW, llm)}
        tp, fp, fn = tp + len(got & expected), fp + len(got - expected), fn + len(expected - got)
        status = "OK  " if got == expected else "FAIL"
        extra = "" if got == expected else f"   expected {sorted(expected)}"
        print(f"{status} {text!r} -> {sorted(got)}{extra}")
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    print(f"\nmodel: {OLLAMA_MODEL}   precision {precision:.0%}   recall {recall:.0%}   (tp={tp}, fp={fp}, fn={fn})")