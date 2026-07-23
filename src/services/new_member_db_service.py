from __future__ import annotations

from datetime import date

import gspread

_HEADER_ROW = 7
_DATA_START_ROW = 8

# 열 번호 (1-based)
_COL_PART = 2        # B 파트
_COL_TYPE = 3        # C 유형
_COL_DATE = 4        # D 날짜
_COL_MANAGER = 5     # E 담당자
_COL_REG_STATUS = 6  # F 등록여부
_COL_NAME = 7        # G 이름
_COL_PHONE = 8       # H 연락처
# I=9 공백
_COL_VISIT_DATE = 10   # J 방문날짜
_COL_VISIT_TIME = 11   # K 방문시간
_COL_GENDER = 12       # L 성별
_COL_AGE = 13          # M 연령대
_COL_INTEREST = 14     # N 관심종목
_COL_SOURCE = 15       # O 방문경로
_COL_REG_TYPE = 16     # P 등록종목
_COL_REG_PERIOD = 17   # Q 등록기간
_COL_NEW_RE = 18       # R 구분
# S=19 공백
_COL_CONSULT_START = 20  # T 1차 상담자
_CONSULT_STRIDE = 5      # 상담자·날짜·방식·내용 + 공백 1열


def _col_letter(n: int) -> str:
    """1-based 열 번호 → 열 문자 (A, Z, AA, AB …)"""
    result = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


def _current_month_sheet_name() -> str:
    today = date.today()
    return f"{today.strftime('%y')}/{today.month:02d}월"


def _find_sheet(ss: gspread.Spreadsheet, configured_name: str) -> gspread.Worksheet:
    """현재 달 시트명 → 설정값 순으로 시트를 탐색한다."""
    auto_name = _current_month_sheet_name()
    candidates = list(dict.fromkeys([auto_name, configured_name]))
    for name in candidates:
        if not name:
            continue
        try:
            return ss.worksheet(name)
        except gspread.exceptions.WorksheetNotFound:
            continue
    tried = ", ".join(f"'{n}'" for n in candidates if n)
    raise RuntimeError(f"시트를 찾을 수 없습니다 (시도: {tried})")


def get_new_db_sheet(
    client: gspread.Client, spreadsheet_id: str, sheet_name: str = ""
) -> gspread.Worksheet:
    return _find_sheet(client.open_by_key(spreadsheet_id), sheet_name)


def find_by_phone(ws: gspread.Worksheet, phone: str) -> int | None:
    """H열(연락처)에서 전화번호를 찾아 행 번호를 반환한다. 없으면 None."""
    phone = phone.strip()
    col_vals = ws.col_values(_COL_PHONE)
    for i, val in enumerate(col_vals):
        if i + 1 < _DATA_START_ROW:
            continue
        if str(val).strip() == phone:
            return i + 1
    return None


def _next_empty_row(ws: gspread.Worksheet) -> int:
    """데이터 영역에서 다음 빈 행 번호를 반환한다."""
    col_vals = ws.col_values(_COL_PHONE)
    row = _DATA_START_ROW
    for i in range(_DATA_START_ROW - 1, len(col_vals)):
        if str(col_vals[i]).strip():
            row = i + 2
    return row


def _build_base_row(parsed: dict) -> list:
    """B~R 열 값 리스트를 반환한다 (총 17개, B부터)."""
    # 인덱스 0 = B열
    row = [""] * 17
    row[_COL_PART - _COL_PART] = parsed.get("파트", "")
    row[_COL_TYPE - _COL_PART] = parsed.get("유형", "")
    row[_COL_DATE - _COL_PART] = parsed.get("날짜", "")
    row[_COL_MANAGER - _COL_PART] = parsed.get("담당자", "")
    row[_COL_REG_STATUS - _COL_PART] = parsed.get("등록여부", "")
    row[_COL_NAME - _COL_PART] = parsed.get("이름", "")
    row[_COL_PHONE - _COL_PART] = parsed.get("연락처", "")
    # I(인덱스 7) = 공백
    row[_COL_VISIT_DATE - _COL_PART] = parsed.get("방문날짜", "")
    row[_COL_VISIT_TIME - _COL_PART] = parsed.get("방문시간", "")
    row[_COL_GENDER - _COL_PART] = parsed.get("성별", "")
    row[_COL_AGE - _COL_PART] = parsed.get("연령대", "")
    row[_COL_INTEREST - _COL_PART] = parsed.get("관심종목", "")
    row[_COL_SOURCE - _COL_PART] = parsed.get("방문경로", "")
    row[_COL_REG_TYPE - _COL_PART] = parsed.get("등록종목", "")
    row[_COL_REG_PERIOD - _COL_PART] = parsed.get("등록기간", "")
    row[_COL_NEW_RE - _COL_PART] = parsed.get("구분", "")
    return row


def append_new_member(ws: gspread.Worksheet, parsed: dict) -> int:
    """신규 회원 행을 추가하고 행 번호를 반환한다."""
    row_num = _next_empty_row(ws)
    base_row = _build_base_row(parsed)
    ws.update(
        f"B{row_num}:R{row_num}", [base_row], value_input_option="USER_ENTERED"
    )
    _write_consultations(ws, row_num, parsed.get("상담내역", []), existing_dates=set())
    return row_num


def update_consultations(ws: gspread.Worksheet, row_num: int, new_consultations: list) -> None:
    """기존 행에 아직 없는 날짜의 상담 회차만 추가한다."""
    max_check = _COL_CONSULT_START + 20 * _CONSULT_STRIDE
    end_col = _col_letter(max_check)
    raw = ws.get(f"T{row_num}:{end_col}{row_num}")
    existing_row = raw[0] if raw else []

    existing_dates: set[str] = set()
    slot_count = 0
    for i in range(0, len(existing_row), _CONSULT_STRIDE):
        slot = existing_row[i:i + 4]
        if any(str(v).strip() for v in slot):
            date_val = str(existing_row[i + 1]).strip() if i + 1 < len(existing_row) else ""
            if date_val:
                existing_dates.add(date_val)
            slot_count += 1
        else:
            break

    _write_consultations(ws, row_num, new_consultations, existing_dates, start_slot=slot_count)


def _write_consultations(
    ws: gspread.Worksheet,
    row_num: int,
    consultations: list,
    existing_dates: set[str],
    start_slot: int = 0,
) -> None:
    """상담내역 리스트를 해당 행의 상담 컬럼에 기록한다."""
    slot = start_slot
    for c in consultations:
        date_val = str(c.get("날짜", "")).strip()
        if date_val in existing_dates:
            continue
        base = _COL_CONSULT_START + slot * _CONSULT_STRIDE
        col_s = _col_letter(base)
        col_e = _col_letter(base + 3)
        ws.update(
            f"{col_s}{row_num}:{col_e}{row_num}",
            [[c.get("상담자", ""), date_val, c.get("방식", ""), c.get("내용", "")]],
            value_input_option="USER_ENTERED",
        )
        if date_val:
            existing_dates.add(date_val)
        slot += 1


def transfer_all(
    client: gspread.Client,
    consult_ws: gspread.Worksheet,
    new_db_ws: gspread.Worksheet,
    api_key: str,
    defaults: dict,
    rows: list[list],
) -> dict:
    """
    상담 행 목록을 Gemini 분석 후 신규DB 시트에 이관한다.
    Returns {"success": int, "updated": int, "failed": int, "log": list[str]}
    """
    from src.services.gemini_service import analyze_consultation

    success, updated, failed = 0, 0, 0
    log: list[str] = []

    for i, row in enumerate(rows):
        row = list(row) + [""] * (8 - len(row))
        row_data = {
            "reserved_date": row[0],
            "name": row[1],
            "phone": row[2],
            "visit_date": row[3],
            "category": row[4],
            "amount": row[5],
            "is_new": row[6],
            "notes": row[7],
        }
        name = row_data["name"] or f"행 {i + 1}"
        try:
            parsed = analyze_consultation(api_key, row_data, defaults)
            phone = row_data["phone"].strip()
            existing_row = find_by_phone(new_db_ws, phone) if phone else None

            if existing_row:
                update_consultations(new_db_ws, existing_row, parsed.get("상담내역", []))
                log.append(f"[업데이트] {name} → row {existing_row}")
                updated += 1
            else:
                new_row = append_new_member(new_db_ws, parsed)
                log.append(f"[신규추가] {name} → row {new_row}")
                success += 1
        except Exception as exc:
            log.append(f"[실패] {name}: {exc}")
            failed += 1

    return {"success": success, "updated": updated, "failed": failed, "log": log}
