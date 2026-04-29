from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.services.broj_service import LockerRecord

_DATA_DIR  = Path(os.environ.get("APPDATA", "~")).expanduser() / "리와인드자동화"
_LOCKER_JSON = _DATA_DIR / "locker_data.json"

IMMINENT_DAYS = 30            # 락카 그리드 임박 기준 (일)
MEMBERSHIP_IMMINENT_DAYS = 9  # 회원현황보고 임박 기준 (브로제이 기준, 일)

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
    """락카 그리드용: 락카 만료일(보유 대여권) 기준으로 상태를 계산한다."""
    if record.is_holding:
        return "holding"
    today = date.today()
    if record.start_date and record.start_date > today:
        return "scheduled"
    expiry = record.locker_expiry or record.expiry_date  # 락카 만료일 우선
    if expiry:
        delta = (expiry - today).days
        if delta < 0:
            return "expired"
        if delta <= IMMINENT_DAYS:
            return "imminent"
        return "active"
    return "active" if record.has_key else "expired"


def _compute_membership_state(record: LockerRecord) -> str:
    """회원현황보고용: 회원권 만료일(최종 만료일) 기준으로 상태를 계산한다."""
    if record.is_holding:
        return "holding"
    today = date.today()
    if record.start_date and record.start_date > today:
        return "scheduled"
    if record.expiry_date:  # 최종 만료일 = 회원권 만료일
        delta = (record.expiry_date - today).days
        if delta < 0:
            return "expired"
        if delta <= MEMBERSHIP_IMMINENT_DAYS:
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
        expiry = rec.locker_expiry or rec.expiry_date
        days = (expiry - date.today()).days if expiry else None
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


def _record_key(r: LockerRecord) -> str:
    """회원 레코드의 고유 키를 반환한다.
    전화번호 > 락카번호 > 이름 순으로 우선 사용.
    """
    if r.phone_number:
        return f"phone:{r.phone_number}"
    if r.locker_number > 0:
        return f"locker:{r.locker_number}"
    return f"name:{r.member_name}"


def merge_records(
    existing: list[LockerRecord],
    new: list[LockerRecord],
) -> list[LockerRecord]:
    """기존 레코드에 새 레코드를 병합한다.
    전화번호를 primary key로 사용하여 동명이인을 정확히 구분한다.
    분할 가져오기(예: 1000명 + 174명)에서도 모든 회원이 누적된다.
    전화번호 없는 기존 레코드는 새 레코드(전화번호 있음)로 교체된다.
    """
    merged: dict[str, LockerRecord] = {_record_key(r): r for r in existing}

    # 전화번호 없는 기존 레코드의 보조 인덱스 (구버전 데이터 마이그레이션용)
    phoneless_locker: dict[int, str] = {
        r.locker_number: _record_key(r)
        for r in existing
        if not r.phone_number and r.locker_number > 0
    }
    phoneless_name: dict[str, str] = {
        r.member_name: _record_key(r)
        for r in existing
        if not r.phone_number and r.locker_number <= 0
    }

    for r in new:
        key = _record_key(r)
        if r.phone_number:
            # 같은 락카 또는 같은 이름의 전화번호 없는 구버전 레코드 제거
            old_key = (
                phoneless_locker.get(r.locker_number)
                if r.locker_number > 0
                else phoneless_name.get(r.member_name)
            )
            if old_key and old_key != key:
                merged.pop(old_key, None)
        merged[key] = r

    return list(merged.values())


def save_records(records: list[LockerRecord]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = [
        {
            "member_name":    r.member_name,
            "locker_room":    r.locker_room,
            "locker_number":  r.locker_number,
            "has_key":        r.has_key,
            "expiry_date":    r.expiry_date.isoformat() if r.expiry_date else None,
            "start_date":     r.start_date.isoformat() if r.start_date else None,
            "is_holding":     r.is_holding,
            "membership_type": r.membership_type,
            "phone_number":   r.phone_number,
            "locker_expiry":  r.locker_expiry.isoformat() if r.locker_expiry else None,
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
                is_holding=item.get("is_holding", False),
                membership_type=item.get("membership_type"),
                phone_number=item.get("phone_number"),
                locker_expiry=date.fromisoformat(item["locker_expiry"]) if item.get("locker_expiry") else None,
            ))
        return records
    except Exception:
        return []


def get_locker_json_path() -> Path:
    return _LOCKER_JSON


def count_by_state(records: list[LockerRecord]) -> dict[str, int]:
    """상태별 회원 수를 반환한다."""
    counts = {"active": 0, "expired": 0, "scheduled": 0, "imminent": 0, "holding": 0, "unassigned": 0}
    for rec in records:
        if rec.locker_number <= 0 and rec.has_key:
            counts["unassigned"] += 1
        else:
            state = _compute_membership_state(rec)  # 회원권 만료일 + 9일 임박 기준
            if state in counts:
                counts[state] += 1
    return counts


def get_expired_by_category(
    records: list[LockerRecord],
) -> tuple[list[LockerRecord], list[LockerRecord]]:
    """만료된 락카 회원을 두 그룹으로 분류해 반환한다.

    Returns:
        (locker_only, both_expired)
        - locker_only  : 락카 만료 + 보유 회원권 있음 (회원권은 진행중)
        - both_expired : 락카 만료 + 보유 회원권 없음 (둘 다 만료)
    """
    locker_only: list[LockerRecord] = []
    both_expired: list[LockerRecord] = []

    for rec in records:
        if rec.locker_number <= 0:
            continue
        if _compute_state(rec) != "expired":
            continue
        # 필드에 값이 있으면 이용권 보유 중 (활성/임박 모두 포함)
        if rec.membership_type:
            locker_only.append(rec)
        else:
            both_expired.append(rec)

    locker_only.sort(key=lambda r: r.expiry_date or date.min)
    both_expired.sort(key=lambda r: r.expiry_date or date.min)
    return locker_only, both_expired


def build_member_report_text(report_date: date, counts: dict[str, int]) -> str:
    """대표 보고용 유효회원 현황 문구를 반환한다."""
    total = sum(counts.values())
    return (
        f"[{report_date.month}월 {report_date.day}일 리와인드 중산점 유효회원]\n"
        f"활성: {counts.get('active', 0)}명\n"
        f"만료: {counts.get('expired', 0)}명\n"
        f"예정: {counts.get('scheduled', 0)}명\n"
        f"임박: {counts.get('imminent', 0)}명\n"
        f"홀딩: {counts.get('holding', 0)}명\n"
        f"미등록: {counts.get('unassigned', 0)}명\n\n"
        f"총: {total}명"
    )
