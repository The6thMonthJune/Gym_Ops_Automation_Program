from __future__ import annotations

import json
import os
from pathlib import Path

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
    key = f"{year}-{month:02d}"
    return key in load_notification_state().get("handled_months", [])


# ── 수신자 ────────────────────────────────────────────────────────────────────

def get_active_foreign_phones() -> list[str]:
    """활성/임박 외국인 회원의 전화번호 목록을 반환한다."""
    from src.services.foreign_member_service import get_active_foreign_members
    return [m.phone_number for m in get_active_foreign_members() if m.phone_number]
