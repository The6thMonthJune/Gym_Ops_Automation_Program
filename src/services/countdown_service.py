from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

_SETTINGS_DIR = Path(os.environ.get("APPDATA", "~")).expanduser() / "리와인드자동화"
_COUNTDOWN_FILE = _SETTINGS_DIR / "countdown.json"


def load_countdown() -> dict:
    if not _COUNTDOWN_FILE.exists():
        return {}
    try:
        return json.loads(_COUNTDOWN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_countdown(center: int, pt: int) -> None:
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "date": date.today().isoformat(),
        "center": center,
        "pt": pt,
    }
    _COUNTDOWN_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
