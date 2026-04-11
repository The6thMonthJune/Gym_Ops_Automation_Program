from __future__ import annotations

import json
import os
from pathlib import Path

_SETTINGS_DIR = Path(os.environ.get("APPDATA", "~")).expanduser() / "리와인드자동화"
_SETTINGS_FILE = _SETTINGS_DIR / "settings.json"

_KEY_TEMPLATE_FILE = "template_file"
_KEY_DAILY_FILE = "daily_file"
_KEY_TOTAL_SALES_FILE = "total_sales_file"


def load_settings() -> dict:
    if not _SETTINGS_FILE.exists():
        return {}
    try:
        return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(settings: dict) -> None:
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
