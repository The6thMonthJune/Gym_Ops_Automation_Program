from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from src.services.locker_service import _compute_membership_state, load_records

_DATA_DIR = Path(os.environ.get("APPDATA", "~")).expanduser() / "리와인드자동화"
_NOTIF_FILE = _DATA_DIR / "holiday_notification.json"


# ── 발송 이력 ─────────────────────────────────────────────────────────────────

def load_notification_state() -> dict:
    if not _NOTIF_FILE.exists():
        return {}
    try:
        return json.loads(_NOTIF_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def mark_handled(year: int, month: int) -> None:
    """해당 연월을 처리 완료로 기록한다 (발송 또는 건너뛰기)."""
    state = load_notification_state()
    handled: list[str] = state.get("handled_months", [])
    key = f"{year}-{month:02d}"
    if key not in handled:
        handled.append(key)
    state["handled_months"] = handled
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _NOTIF_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def is_handled(year: int, month: int) -> bool:
    state = load_notification_state()
    key = f"{year}-{month:02d}"
    return key in state.get("handled_months", [])


# ── 활성 회원 전화번호 ─────────────────────────────────────────────────────────

def get_active_phone_numbers() -> list[str]:
    """
    활성(active) + 임박(imminent) 회원의 전화번호 목록을 반환한다.
    전화번호가 없는 회원은 제외한다.
    """
    records = load_records()
    phones: set[str] = set()
    for r in records:
        if _compute_membership_state(r) not in ("active", "imminent"):
            continue
        if r.phone_number:
            phones.add(r.phone_number)
    return list(phones)
