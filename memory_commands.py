import re

import memory

USER_ID = "driver1"
VIEW_CMD = re.compile(r"\b(what do you (know|remember)|show (me )?(my )?(memory|preferences|profile))\b", re.I)
FORGET_ALL = re.compile(r"\b(forget|delete|erase)\b.*\b(everything|all)\b", re.I)


def handle_memory_command(query: str) -> str | None:
    if FORGET_ALL.search(query):
        memory.forget(USER_ID)
        return "Done. I deleted everything I knew about you."
    if VIEW_CMD.search(query):
        profile = memory.get_profile(USER_ID)
        if not profile:
            return "I don't know any preferences yet."
        lines = ["Here is what I know:"]
        for f in profile:
            how = "you told me" if f["source"] == "stated" else f"learned, confidence {f['confidence']:.0%}"
            lines.append(f"- {f['key'].replace('_', ' ')}: {f['value']} ({how})")
        return "\n".join(lines)
    return None
