"""Driver memory: raw observations -> derived facts (with confidence), view, forget."""
import os
import sqlite3
from collections import Counter
from datetime import datetime

DB_PATH = os.getenv("MEMORY_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.db"))

WINDOW = 10          # only the last N observations per (signal, time bucket) count -> preferences can change
MIN_SUPPORT = 3      # need at least this many observations before we claim to "know" something
MIN_CONFIDENCE = 0.6 # share of the window that must agree on one value


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(reset: bool = False):
    conn = connect()
    if reset:
        conn.executescript("DROP TABLE IF EXISTS observations; DROP TABLE IF EXISTS facts; DROP TABLE IF EXISTS stated;")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            signal TEXT NOT NULL,
            bucket TEXT NOT NULL,
            value TEXT NOT NULL,
            ts TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS facts (
            user_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            confidence REAL NOT NULL,
            support INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, key)
        );
        CREATE TABLE IF NOT EXISTS stated (
            user_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            ts TEXT NOT NULL,
            PRIMARY KEY (user_id, key)
        );
    """)
    conn.commit()
    conn.close()

def time_bucket(ts: datetime) -> str:
    h = ts.hour
    if 5 <= h < 11:
        return "morning"
    if 11 <= h < 17:
        return "afternoon"
    if 17 <= h < 22:
        return "evening"
    return "night"


def add_observation(user_id: str, signal: str, value: str, ts: datetime | None = None, derive: bool = True):
    """Store one vehicle/user event. Only USER-originated events belong here,
    not actions the assistant did itself (otherwise it would learn from its own behavior)."""
    ts = ts or datetime.now()
    conn = connect()
    conn.execute(
        "INSERT INTO observations (user_id, signal, bucket, value, ts) VALUES (?, ?, ?, ?, ?)",
        (user_id, signal, time_bucket(ts), str(value), ts.isoformat()),
    )
    conn.commit()
    conn.close()
    if derive:
        derive_facts(user_id)


def derive_facts(user_id: str) -> list[dict]:
    """Recompute facts from the most recent observations of every (signal, bucket)."""
    conn = connect()
    groups = conn.execute(
        "SELECT DISTINCT signal, bucket FROM observations WHERE user_id = ?", (user_id,)
    ).fetchall()
    now = datetime.now().isoformat()
    for g in groups:
        rows = conn.execute(
            "SELECT value FROM observations WHERE user_id=? AND signal=? AND bucket=? "
            "ORDER BY ts DESC LIMIT ?",
            (user_id, g["signal"], g["bucket"], WINDOW),
        ).fetchall()
        values = [r["value"] for r in rows]
        top_value, top_count = Counter(values).most_common(1)[0]
        confidence = top_count / len(values)
        key = f"{g['signal']}@{g['bucket']}"
        if len(values) >= MIN_SUPPORT and confidence >= MIN_CONFIDENCE:
            conn.execute(
                "INSERT INTO facts (user_id, key, value, confidence, support, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value, "
                "confidence=excluded.confidence, support=excluded.support, updated_at=excluded.updated_at",
                (user_id, key, top_value, round(confidence, 2), len(values), now),
            )
        else:
            conn.execute("DELETE FROM facts WHERE user_id=? AND key=?", (user_id, key))
    conn.commit()
    conn.close()
    return get_profile(user_id)


def add_stated(user_id: str, signal: str, bucket: str, value: str, ts: datetime | None = None):
    """Something the driver explicitly TOLD the assistant (source = chat)."""
    ts = (ts or datetime.now()).isoformat()
    conn = connect()
    conn.execute(
        "INSERT INTO stated (user_id, key, value, ts) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value, ts=excluded.ts",
        (user_id, f"{signal}@{bucket}", str(value), ts),
    )
    conn.commit()
    conn.close()


def get_profile(user_id: str) -> list[dict]:
    conn = connect()
    derived = conn.execute(
        "SELECT key, value, confidence, support, updated_at FROM facts WHERE user_id=?", (user_id,)
    ).fetchall()
    stated = conn.execute("SELECT key, value, ts FROM stated WHERE user_id=?", (user_id,)).fetchall()
    conn.close()
    merged = {r["key"]: {**dict(r), "source": "observed"} for r in derived}
    for r in stated:   # what the driver said explicitly wins over what we inferred
        merged[r["key"]] = {"key": r["key"], "value": r["value"], "confidence": 1.0,
                            "support": 0, "updated_at": r["ts"], "source": "stated"}
    return [merged[k] for k in sorted(merged)]


def forget(user_id: str, key: str | None = None) -> int:
    """GDPR-style deletion. key=None deletes everything about the user.
    Raw observations are deleted too, otherwise the fact would be re-derived."""
    conn = connect()
    if key is None:
        n = conn.execute("DELETE FROM facts WHERE user_id=?", (user_id,)).rowcount
        n += conn.execute("DELETE FROM stated WHERE user_id=?", (user_id,)).rowcount
        conn.execute("DELETE FROM observations WHERE user_id=?", (user_id,))
    else:
        signal, _, bucket = key.partition("@")
        n = conn.execute("DELETE FROM facts WHERE user_id=? AND key=?", (user_id, key)).rowcount
        n += conn.execute("DELETE FROM stated WHERE user_id=? AND key=?", (user_id, key)).rowcount
        conn.execute(
            "DELETE FROM observations WHERE user_id=? AND signal=? AND bucket=?",
            (user_id, signal, bucket),
        )
    conn.commit()
    conn.close()
    return n
