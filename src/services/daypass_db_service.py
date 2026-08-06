from __future__ import annotations

from datetime import date

import gspread

_HEADER_ROW = 3
_DATA_START_ROW = 4

# 열 번호 (1-based): A=등록여부, B=담당자, C=방문경로, D=금액, E=방문일, F=이름, G=전화번호, H=내용
_COL_NAME = 6   # F열 — 다음 빈 행 탐색 기준


def _current_month_sheet_name() -> str:
    today = date.today()
    return f"{today.strftime('%y')}년 {today.month:02d}월"


def _prev_month_sheet_name() -> str:
    today = date.today()
    m, y = (today.month - 1, today.year) if today.month > 1 else (12, today.year - 1)
    return f"{str(y)[2:]}년 {m:02d}월"


def _find_or_create_sheet(ss: gspread.Spreadsheet, configured_name: str) -> gspread.Worksheet:
    """현재 달 시트 탐색 → 없으면 전월 시트 복사 생성 → 설정값 fallback"""
    auto_name = _current_month_sheet_name()

    # 1. 현재 달 시트 탐색
    try:
        return ss.worksheet(auto_name)
    except gspread.exceptions.WorksheetNotFound:
        pass

    # 2. 전월 시트 복사해서 새 달 시트 생성
    prev_name = _prev_month_sheet_name()
    source: gspread.Worksheet | None = None
    try:
        source = ss.worksheet(prev_name)
    except gspread.exceptions.WorksheetNotFound:
        pass

    if source is not None:
        new_ws = ss.duplicate_sheet(
            source_sheet_id=source.id,
            new_sheet_name=auto_name,
            insert_sheet_index=len(ss.worksheets()),
        )
        new_ws.batch_clear([f"A{_DATA_START_ROW}:H{new_ws.row_count}"])
        return new_ws

    # 3. 설정값 fallback
    if configured_name:
        try:
            return ss.worksheet(configured_name)
        except gspread.exceptions.WorksheetNotFound:
            pass

    raise RuntimeError(f"'{auto_name}' 시트를 찾거나 생성할 수 없습니다.")


def get_daypass_sheet(
    client: gspread.Client, spreadsheet_id: str, sheet_name: str = ""
) -> gspread.Worksheet:
    return _find_or_create_sheet(client.open_by_key(spreadsheet_id), sheet_name)


def _next_empty_row(ws: gspread.Worksheet) -> int:
    col_vals = ws.col_values(_COL_NAME)
    row = _DATA_START_ROW
    for i in range(_DATA_START_ROW - 1, len(col_vals)):
        if str(col_vals[i]).strip():
            row = i + 2
    return row


def append_daypass_entry(ws: gspread.Worksheet, entry: dict) -> int:
    """일일권 DB에 새 행을 추가하고 기록된 행 번호를 반환한다.

    entry keys: manager, route, amount, visit_date (MM/DD), name, phone, content
    A열(등록여부)는 빈 칸으로 두고 나중에 수동 입력한다.
    """
    row_num = _next_empty_row(ws)
    row_data = [
        "",                             # A: 등록여부 (수동)
        entry.get("manager", ""),       # B: 담당자
        entry.get("route", ""),         # C: 방문경로
        entry.get("amount", ""),        # D: 금액
        entry.get("visit_date", ""),    # E: 방문일
        entry.get("name", ""),          # F: 이름
        entry.get("phone", ""),         # G: 전화번호
        entry.get("content", ""),       # H: 내용
    ]
    ws.update(f"A{row_num}:H{row_num}", [row_data], value_input_option="USER_ENTERED")
    return row_num
