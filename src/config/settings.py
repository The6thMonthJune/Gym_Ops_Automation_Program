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
_KEY_APARTMENT_COMPLEXES = "apartment_complexes"
_KEY_MONTHLY_TARGET_CENTER = "monthly_target_center"
_KEY_MONTHLY_TARGET_PT = "monthly_target_pt"
_KEY_SMS_GATEWAY_PORT = "sms_gateway_port"
_KEY_SMS_GATEWAY_USERNAME = "sms_gateway_username"
_KEY_SMS_GATEWAY_PASSWORD = "sms_gateway_password"
_KEY_SMS_TEST_PHONE = "sms_test_phone"


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


def get_apartment_complexes() -> list[str]:
    """설정에 저장된 아파트 단지 목록을 반환한다. 미설정 시 빈 리스트."""
    return load_settings().get(_KEY_APARTMENT_COMPLEXES, []) or []


def get_sms_test_phone() -> str:
    return load_settings().get(_KEY_SMS_TEST_PHONE, "") or ""


def get_sms_gateway_credentials() -> tuple[int, str, str]:
    """(포트, 사용자명, 비밀번호) 반환. 미설정 시 기본값."""
    s = load_settings()
    return (
        int(s.get(_KEY_SMS_GATEWAY_PORT) or 8080),
        s.get(_KEY_SMS_GATEWAY_USERNAME) or "user",
        s.get(_KEY_SMS_GATEWAY_PASSWORD) or "password",
    )


def get_monthly_targets() -> tuple[int, int]:
    """(센터 목표금액, 피티 목표금액) 반환. 미설정 시 0."""
    s = load_settings()
    return (
        int(s.get(_KEY_MONTHLY_TARGET_CENTER) or 0),
        int(s.get(_KEY_MONTHLY_TARGET_PT) or 0),
    )
