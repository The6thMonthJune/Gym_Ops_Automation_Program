from __future__ import annotations

import os
import sqlite3
from datetime import date
from pathlib import Path

_DATA_DIR = Path(os.environ.get("APPDATA", "~")).expanduser() / "리와인드자동화"
_SNAPSHOT_DB = _DATA_DIR / "member_snapshots.db"


def _connect() -> sqlite3.Connection:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_SNAPSHOT_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS member_snapshots (
            snapshot_date TEXT PRIMARY KEY,
            active        INTEGER DEFAULT 0,
            expired       INTEGER DEFAULT 0,
            scheduled     INTEGER DEFAULT 0,
            imminent      INTEGER DEFAULT 0,
            holding       INTEGER DEFAULT 0,
            unassigned    INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


def save_snapshot(snapshot_date: date, counts: dict[str, int]) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO member_snapshots
                (snapshot_date, active, expired, scheduled, imminent, holding, unassigned)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_date.isoformat(),
                counts.get("active", 0),
                counts.get("expired", 0),
                counts.get("scheduled", 0),
                counts.get("imminent", 0),
                counts.get("holding", 0),
                counts.get("unassigned", 0),
            ),
        )


def get_snapshot(target_date: date) -> dict[str, int] | None:
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT active, expired, scheduled, imminent, holding, unassigned "
                "FROM member_snapshots WHERE snapshot_date = ?",
                (target_date.isoformat(),),
            ).fetchone()
        if not row:
            return None
        keys = ("active", "expired", "scheduled", "imminent", "holding", "unassigned")
        return dict(zip(keys, row))
    except Exception:
        return None


def load_all_snapshots() -> list[dict]:
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT snapshot_date, active, expired, scheduled, imminent, holding, unassigned "
                "FROM member_snapshots ORDER BY snapshot_date"
            ).fetchall()
        keys = ("date", "active", "expired", "scheduled", "imminent", "holding", "unassigned")
        return [dict(zip(keys, row)) for row in rows]
    except Exception:
        return []
