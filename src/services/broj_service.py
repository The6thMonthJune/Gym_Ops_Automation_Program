from __future__ import annotations

import re
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
    is_holding: bool = False       # 브로제이 A열이 "홀딩"인 회원
    membership_type: str | None = None  # 보유 회원권 문자열 (없으면 회원권 만료)
    phone_number: str | None = None    # 숫자만 추출한 전화번호 (동명이인 구분용)
    locker_expiry: date | None = None  # 락카 만료일 (보유 대여권에서 파싱)


# BROJ 구역명 → 내부 구역명
_ROOM_MAP: dict[str, str] = {
    "남자": "남자 탈의실",
    "남탈": "남자 탈의실",
    "남성": "남자 탈의실",
    "여자": "회원복 락카",
    "여탈": "회원복 락카",
    "회원복 락카": "회원복 락카",
    "여성": "회원복 락카",
    "회원복": "회원복 락카",
    "메인": "메인 락카",
    "일반": "메인 락카",
    "main": "메인 락카",
}

# 구역별 전역 번호 오프셋 (구역 내 1번 → 전역 번호)
SECTION_OFFSET: dict[str, int] = {
    "남자 탈의실": 0,    # 1~84
    "회원복 락카":      84,   # 85~119
    "메인 락카":   119,  # 120~252
}


def _parse_locker_key_expiry(val) -> date | None:
    """보유 대여권 문자열에서 락카 만료일을 추출한다.
    예: '락커 대여권(활성) 2026.04.28~2027.04.27' → date(2027, 4, 27)
    """
    if not val:
        return None
    m = re.search(r"~(\d{4}[.\-/]\d{2}[.\-/]\d{2})", str(val))
    if m:
        return _parse_date(m.group(1))
    return None


def _normalize_phone(val) -> str | None:
    """전화번호에서 숫자만 추출한다. 없으면 None."""
    if not val:
        return None
    digits = re.sub(r"\D", "", str(val).strip())
    return digits if digits else None


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


def _parse_locker_combined(val) -> tuple[str, int]:
    """'구역/번호번' 형식의 값을 (normalized_room, global_number) 로 파싱한다.
    번호는 이미 전역 번호이므로 offset을 추가하지 않는다.
    '27번' 처럼 '번' 접미사가 붙은 경우도 처리한다.
    """
    if not val:
        return "", 0
    s = str(val).strip()
    if "/" in s:
        parts = s.rsplit("/", 1)
        room = _normalize_room(parts[0].strip())
        num_str = parts[1].strip().rstrip("번").strip()
        try:
            return room, int(float(num_str))
        except (ValueError, TypeError):
            return room, 0
    # 슬래시 없는 경우: 숫자(+번)만 있으면 전역 번호로 처리
    try:
        return "", int(float(s.rstrip("번").strip()))
    except (ValueError, TypeError):
        return "", 0


def read_xls_headers(xls_path: str | Path) -> list[str]:
    """XLS 파일의 헤더 행만 빠르게 읽어 반환한다 (디버그용)."""
    resolved = Path(xls_path).resolve()
    app = xw.App(visible=False)
    try:
        book = app.books.open(str(resolved))
        sheet = book.sheets[0]
        for r in range(1, 11):
            vals = sheet.range((r, 1), (r, 50)).value or []
            strs = [str(v).lower() if v else "" for v in vals]
            if any("회원명" in s or "이름" in s for s in strs):
                raw = sheet.range((r, 1), (r, 50)).value or []
                book.close()
                return [str(h).strip() if h else "" for h in raw]
        book.close()
        return []
    finally:
        app.quit()


def parse_xls(xls_path: str | Path, delete_after: bool = True) -> list[LockerRecord]:
    """
    BROJ에서 다운로드한 .xls/.xlsx 파일을 파싱해 락카 관련 회원 레코드를 반환한다.

    BROJ 헤더 기준:
      이름 / 보유 대여권 / 락커룸/락커번호 / 최종 만료일

    Args:
        delete_after: True이면 파싱 성공 후 파일을 삭제한다.
    """
    resolved = Path(xls_path).resolve()
    app = xw.App(visible=False)
    records: list[LockerRecord] = []

    try:
        book = app.books.open(str(resolved))
        sheet = book.sheets[0]

        # 헤더 행 탐색
        header_row: int | None = None
        for r in range(1, 11):
            vals = sheet.range((r, 1), (r, 50)).value or []
            strs = [str(v).lower() if v else "" for v in vals]
            if any("회원명" in s or "이름" in s for s in strs):
                header_row = r
                break

        if header_row is None:
            raise ValueError("헤더 행을 찾을 수 없습니다. '이름' 또는 '회원명' 열이 필요합니다.")

        raw_headers = sheet.range((header_row, 1), (header_row, 50)).value or []
        headers = [str(h).strip() if h else "" for h in raw_headers]

        ci_name   = _find_col(headers, "이름", "회원명")
        ci_key    = _find_col(headers, "보유 대여권", "대여권", "락카권", "락커권")
        ci_locker      = _find_col(headers, "락커룸/락커번호", "락카룸/락카번호", "락커룸", "락카룸")
        ci_expiry      = _find_col(headers, "최종 만료일", "만료일", "종료일")
        ci_start       = _find_col(headers, "최초 등록일", "시작일", "개시일", "계약일")
        ci_membership  = _find_col(headers, "보유 이용권", "이용권", "보유 회원권")
        ci_phone       = _find_col(headers, "연락처", "휴대폰번호", "핸드폰번호", "전화번호", "휴대폰", "핸드폰", "전화")

        if ci_name is None:
            raise ValueError(f"'이름' 열을 찾을 수 없습니다.\n발견된 헤더: {headers[:20]}")

        for r in range(header_row + 1, 5000):
            row_vals = sheet.range((r, 1), (r, 50)).value or []
            if not any(row_vals):
                break

            name = str(_get_cell(row_vals, ci_name) or "").strip()
            if not name or name.lower() == "none":
                continue

            # A열(index 0)이 "홀딩"이면 홀딩 회원
            is_holding = str(row_vals[0] or "").strip() == "홀딩"

            # 보유 대여권 여부
            key_val = _get_cell(row_vals, ci_key)
            has_key = (
                bool(key_val)
                and str(key_val).strip() not in ("", "0", "None", "없음", "X", "x")
            )

            # 락커룸/락커번호 통합 컬럼 파싱
            locker_val = _get_cell(row_vals, ci_locker)
            room, locker_num = _parse_locker_combined(locker_val)

            membership_val = _get_cell(row_vals, ci_membership)
            membership_type = (
                str(membership_val).strip()
                if membership_val and str(membership_val).strip() not in ("", "0", "None", "없음", "X", "x")
                else None
            )

            records.append(LockerRecord(
                member_name=name,
                locker_room=room,
                locker_number=locker_num,
                has_key=has_key,
                expiry_date=_parse_date(_get_cell(row_vals, ci_expiry)),
                start_date=_parse_date(_get_cell(row_vals, ci_start)),
                is_holding=is_holding,
                membership_type=membership_type,
                phone_number=_normalize_phone(_get_cell(row_vals, ci_phone)),
                locker_expiry=_parse_locker_key_expiry(_get_cell(row_vals, ci_key)),
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
