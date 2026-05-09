from __future__ import annotations

import json
import os
from pathlib import Path

_SETTINGS_DIR = Path(os.environ.get("APPDATA", "~")).expanduser() / "리와인드자동화"
_SETTINGS_FILE = _SETTINGS_DIR / "settings.json"

# 설정 키
_KEY_TEMPLATE_FILE = "template_file"
_KEY_DAILY_FILE = "daily_file"
_KEY_TOTAL_SALES_FILE = "total_sales_file"
_KEY_TOTAL_SALES_PASSWORD = "total_sales_password"
_KEY_EXPENSE_DAILY_SHEET = "expense_daily_sheet"
_KEY_PHONE_IP = "phone_ip"
_KEY_NATEON_WEBHOOK_URL = "nateon_webhook_url"


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


def get_password() -> str | None:
    return load_settings().get(_KEY_TOTAL_SALES_PASSWORD) or None


def get_phone_ip() -> str:
    return load_settings().get(_KEY_PHONE_IP, "") or ""


def get_nateon_webhook_url() -> str:
    return load_settings().get(_KEY_NATEON_WEBHOOK_URL, "") or ""


def get_expense_daily_sheet() -> str:
    """데일리 파일의 지출 시트 이름을 반환한다. 미설정 시 기본값 '데일리지출'."""
    return load_settings().get(_KEY_EXPENSE_DAILY_SHEET, "") or "데일리지출"
