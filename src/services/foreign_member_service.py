from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from src.services.locker_service import _compute_membership_state

_DATA_DIR = Path(os.environ.get("APPDATA", "~")).expanduser() / "리와인드자동화"
_FOREIGN_FILE = _DATA_DIR / "foreign_members.json"


@dataclass
class ForeignMember:
    name: str
    phone_number: str
    membership_state: str = "unknown"   # active / imminent / expired / holding / unknown
    expiry_date: date | None = None
    locker_expiry: date | None = None


# ── 영속성 ────────────────────────────────────────────────────────────────────

def load_foreign_members() -> list[ForeignMember]:
    if not _FOREIGN_FILE.exists():
        return []
    try:
        data = json.loads(_FOREIGN_FILE.read_text(encoding="utf-8"))
        result = []
        for item in data:
            result.append(ForeignMember(
                name=item["name"],
                phone_number=item["phone_number"],
                membership_state=item.get("membership_state", "unknown"),
                expiry_date=date.fromisoformat(item["expiry_date"]) if item.get("expiry_date") else None,
                locker_expiry=date.fromisoformat(item["locker_expiry"]) if item.get("locker_expiry") else None,
            ))
        return result
    except Exception:
        return []


def save_foreign_members(members: list[ForeignMember]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = [
        {
            "name": m.name,
            "phone_number": m.phone_number,
            "membership_state": m.membership_state,
            "expiry_date": m.expiry_date.isoformat() if m.expiry_date else None,
            "locker_expiry": m.locker_expiry.isoformat() if m.locker_expiry else None,
        }
        for m in members
    ]
    _FOREIGN_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── CRUD ──────────────────────────────────────────────────────────────────────

def add_foreign_member(name: str, phone_number: str) -> None:
    """외국인 회원을 추가한다. 같은 전화번호가 이미 있으면 이름만 갱신한다."""
    members = load_foreign_members()
    for m in members:
        if m.phone_number == phone_number:
            m.name = name
            save_foreign_members(members)
            return
    members.append(ForeignMember(name=name, phone_number=phone_number))
    save_foreign_members(members)


def remove_foreign_member(phone_number: str) -> None:
    members = [m for m in load_foreign_members() if m.phone_number != phone_number]
    save_foreign_members(members)


# ── DB 동기화 ──────────────────────────────────────────────────────────────────

def sync_from_locker_records(locker_records) -> None:
    """
    로커 레코드 전체를 기준으로 외국인 회원의 상태·만료일을 갱신한다.
    전화번호로 매칭하며, 매칭되지 않는 회원은 state를 'unknown'으로 둔다.
    """
    phone_map = {r.phone_number: r for r in locker_records if r.phone_number}
    members = load_foreign_members()
    for m in members:
        record = phone_map.get(m.phone_number)
        if record:
            m.membership_state = _compute_membership_state(record)
            m.expiry_date = record.expiry_date
            m.locker_expiry = record.locker_expiry
        else:
            m.membership_state = "unknown"
    save_foreign_members(members)


# ── 조회 헬퍼 ──────────────────────────────────────────────────────────────────

def get_active_foreign_members() -> list[ForeignMember]:
    """활성(active/imminent) 외국인 회원만 반환한다."""
    return [m for m in load_foreign_members() if m.membership_state in ("active", "imminent")]


def get_expired_locker_foreign_members() -> list[ForeignMember]:
    """락카가 만료된 외국인 회원만 반환한다."""
    today = date.today()
    result = []
    for m in load_foreign_members():
        expiry = m.locker_expiry or m.expiry_date
        if expiry and expiry < today:
            result.append(m)
    return result
