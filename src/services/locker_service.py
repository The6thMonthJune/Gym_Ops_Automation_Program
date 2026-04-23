from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.services.broj_service import LockerRecord

_DATA_DIR  = Path(os.environ.get("APPDATA", "~")).expanduser() / "리와인드자동화"
_LOCKER_JSON = _DATA_DIR / "locker_data.json"

IMMINENT_DAYS = 30  # 만료 임박 기준 (일)

SECTIONS: list[dict] = [
    {"name": "남자 탈의실", "start": 1,   "end": 84,  "cols": 12, "rows": 7},
    {"name": "회원복 락카",      "start": 85,  "end": 119, "cols": 5,  "rows": 7},
    {"name": "메인 락카",   "start": 120, "end": 252, "cols": 19, "rows": 7},
]


@dataclass
class LockerCell:
    number: int
    state: str           # "active" | "imminent" | "expired" | "empty"
    member_name: str
    days_remaining: int | None


def _compute_state(record: LockerRecord) -> str:
    today = date.today()
    # 예정: 시작일이 오늘 이후
    if record.start_date and record.start_date > today:
        return "scheduled"
    if record.expiry_date:
        delta = (record.expiry_date - today).days
        if delta < 0:
            return "expired"
        if delta <= IMMINENT_DAYS:
            return "imminent"
        return "active"
    return "active" if record.has_key else "expired"


def build_grid(records: list[LockerRecord]) -> dict[int, LockerCell]:
    """락카 번호 → LockerCell 딕셔너리를 반환한다."""
    grid: dict[int, LockerCell] = {}
    for rec in records:
        if rec.locker_number <= 0:
            continue
        state = _compute_state(rec)
        days = (rec.expiry_date - date.today()).days if rec.expiry_date else None
        grid[rec.locker_number] = LockerCell(
            number=rec.locker_number,
            state=state,
            member_name=rec.member_name,
            days_remaining=days,
        )
    return grid


def get_unassigned(records: list[LockerRecord]) -> list[LockerRecord]:
    """결제했지만 락카 미배정 회원 목록을 반환한다."""
    return [r for r in records if r.locker_number <= 0 and r.has_key]


def merge_records(
    existing: list[LockerRecord],
    new: list[LockerRecord],
) -> list[LockerRecord]:
    """기존 레코드에 새 레코드를 병합한다.
    락커번호(>0)가 같으면 새 데이터로 덮어쓰고, 기존에 없는 락커는 추가한다.
    락커번호=0인 미배정 회원은 이름으로 중복 체크한다.
    회원이 다른 락커로 이동한 경우 기존 락커 항목을 제거한다.
    """
    # 새 데이터에서 이름 → 새 락커번호 매핑 (락커 이동 감지용)
    new_name_to_locker: dict[str, int] = {
        r.member_name: r.locker_number
        for r in new
        if r.locker_number > 0
    }

    merged: dict[str, LockerRecord] = {}
    for r in existing:
        key = str(r.locker_number) if r.locker_number > 0 else f"name:{r.member_name}"
        # 새 데이터에서 이 회원이 다른 락커로 이동했으면 기존 항목 제외
        new_locker = new_name_to_locker.get(r.member_name)
        if r.locker_number > 0 and new_locker is not None and new_locker != r.locker_number:
            continue
        merged[key] = r

    for r in new:
        key = str(r.locker_number) if r.locker_number > 0 else f"name:{r.member_name}"
        merged[key] = r

    return list(merged.values())


def save_records(records: list[LockerRecord]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = [
        {
            "member_name":   r.member_name,
            "locker_room":   r.locker_room,
            "locker_number": r.locker_number,
            "has_key":       r.has_key,
            "expiry_date":   r.expiry_date.isoformat() if r.expiry_date else None,
            "start_date":    r.start_date.isoformat() if r.start_date else None,
        }
        for r in records
    ]
    _LOCKER_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_records() -> list[LockerRecord]:
    if not _LOCKER_JSON.exists():
        return []
    try:
        data = json.loads(_LOCKER_JSON.read_text(encoding="utf-8"))
        records = []
        for item in data:
            expiry = date.fromisoformat(item["expiry_date"]) if item.get("expiry_date") else None
            start  = date.fromisoformat(item["start_date"])  if item.get("start_date")  else None
            records.append(LockerRecord(
                member_name=item["member_name"],
                locker_room=item.get("locker_room", ""),
                locker_number=item.get("locker_number", 0),
                has_key=item.get("has_key", True),
                expiry_date=expiry,
                start_date=start,
            ))
        return records
    except Exception:
        return []


def get_locker_json_path() -> Path:
    return _LOCKER_JSON
