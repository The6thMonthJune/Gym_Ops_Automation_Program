from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import xlwings as xw


@dataclass
class LockerRecord:
    member_name: str
    locker_room: str       # 정규화된 구역명
    locker_number: int     # 전역 번호 (0 = 미배정)
    has_key: bool          # 보유 대여권 여부
    expiry_date: date | None
    start_date: date | None


# 브로제이 구역명 → 내부 구역명
_ROOM_MAP: dict[str, str] = {
    "남자": "남자 탈의실",
    "남탈": "남자 탈의실",
    "남성": "남자 탈의실",
    "여자": "여회원",
    "여탈": "여회원",
    "여회원": "여회원",
    "여성": "여회원",
    "회원복": "여회원",
    "메인": "메인 락카",
    "일반": "메인 락카",
    "main": "메인 락카",
}

# 구역별 전역 번호 오프셋 (구역 내 1번 → 전역 번호)
SECTION_OFFSET: dict[str, int] = {
    "남자 탈의실": 0,    # 1~84
    "여회원":      84,   # 85~119
    "메인 락카":   119,  # 120~252
}


def _normalize_room(raw: str) -> str:
    r = raw.strip().lower()
    for key, val in _ROOM_MAP.items():
        if key in r:
            return val
    return raw.strip()


def _find_col(headers: list[str], *candidates: str) -> int | None:
    for i, h in enumerate(headers):
        if not h:
            continue
        hl = str(h).lower().strip()
        for c in candidates:
            if c in hl:
                return i
    return None


def _parse_date(val) -> date | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%y.%m.%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _get_cell(row_vals: list, idx: int | None):
    if idx is None or idx >= len(row_vals):
        return None
    return row_vals[idx]


def parse_xls(xls_path: str | Path, delete_after: bool = True) -> list[LockerRecord]:
    """
    브로제이에서 다운로드한 .xls/.xlsx 파일을 파싱해 락카 관련 회원 레코드를 반환한다.

    Args:
        delete_after: True이면 파싱 성공 후 파일을 삭제한다.

    Returns:
        락카 보유 또는 락카가 배정된 회원 레코드 목록
    """
    resolved = Path(xls_path).resolve()
    app = xw.App(visible=False)
    records: list[LockerRecord] = []

    try:
        book = app.books.open(str(resolved))
        sheet = book.sheets[0]

        # 헤더 행 탐색 (최대 10행 이내)
        header_row: int | None = None
        for r in range(1, 11):
            vals = sheet.range((r, 1), (r, 50)).value or []
            strs = [str(v).lower() if v else "" for v in vals]
            if any("회원명" in s or "이름" in s for s in strs):
                header_row = r
                break

        if header_row is None:
            raise ValueError("헤더 행을 찾을 수 없습니다. '회원명' 열이 필요합니다.")

        raw_headers = sheet.range((header_row, 1), (header_row, 50)).value or []
        headers = [str(h).strip() if h else "" for h in raw_headers]

        ci_name   = _find_col(headers, "회원명", "이름")
        ci_key    = _find_col(headers, "보유 대여권", "대여권", "락카권", "락커권", "잔여권")
        ci_room   = _find_col(headers, "락커룸", "락카룸", "구역", "룸")
        ci_num    = _find_col(headers, "락커번호", "락카번호", "번호")
        ci_expiry = _find_col(headers, "만료일", "종료일", "만료")
        ci_start  = _find_col(headers, "시작일", "개시일", "계약일")

        if ci_name is None:
            raise ValueError(f"'회원명' 열을 찾을 수 없습니다.\n발견된 헤더: {headers[:20]}")
        if ci_num is None and ci_key is None:
            raise ValueError(f"'락커번호' 또는 '대여권' 열을 찾을 수 없습니다.\n발견된 헤더: {headers[:20]}")

        for r in range(header_row + 1, 5000):
            row_vals = sheet.range((r, 1), (r, 50)).value or []
            if not any(row_vals):
                break

            name = str(_get_cell(row_vals, ci_name) or "").strip()
            if not name or name.lower() == "none":
                continue

            # 보유 대여권 여부
            key_val = _get_cell(row_vals, ci_key)
            has_key = (
                bool(key_val)
                and str(key_val).strip() not in ("", "0", "None", "없음", "X", "x")
            )

            # 락커 번호
            num_val = _get_cell(row_vals, ci_num)
            locker_num = 0
            if num_val:
                try:
                    locker_num = int(float(str(num_val)))
                except (ValueError, TypeError):
                    locker_num = 0

            # 락카 무관 회원 스킵
            if not has_key and locker_num == 0:
                continue

            # 구역 정규화 + 전역 번호 변환
            room_raw = str(_get_cell(row_vals, ci_room) or "").strip()
            room = _normalize_room(room_raw)
            if locker_num > 0 and room in SECTION_OFFSET:
                locker_num = SECTION_OFFSET[room] + locker_num

            records.append(LockerRecord(
                member_name=name,
                locker_room=room,
                locker_number=locker_num,
                has_key=has_key,
                expiry_date=_parse_date(_get_cell(row_vals, ci_expiry)),
                start_date=_parse_date(_get_cell(row_vals, ci_start)),
            ))

        book.close()
    finally:
        app.quit()

    if delete_after and resolved.exists():
        try:
            resolved.unlink()
        except Exception:
            pass

    return records
