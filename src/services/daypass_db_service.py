from __future__ import annotations

from datetime import date

import gspread

_HEADER_ROW = 3
_DATA_START_ROW = 4

# 열 번호 (1-based): A=등록여부, B=담당자, C=방문경로, D=금액, E=방문일, F=이름, G=전화번호, H=내용
_COL_NAME = 6   # F열 — 다음 빈 행 탐색 기준


def _current_month_sheet_name() -> str:
    """현재 달 기준 시트명을 반환한다. 예: '26/07월'"""
    today = date.today()
    return f"{today.strftime('%y')}/{today.month:02d}월"


def _find_sheet(ss: gspread.Spreadsheet, configured_name: str) -> gspread.Worksheet:
    """현재 달 시트명 → 설정값 순으로 시트를 탐색한다."""
    auto_name = _current_month_sheet_name()
    candidates = list(dict.fromkeys([auto_name, configured_name]))  # 중복 제거, 순서 유지
    for name in candidates:
        if not name:
            continue
        try:
            return ss.worksheet(name)
        except gspread.exceptions.WorksheetNotFound:
            continue
    tried = ", ".join(f"'{n}'" for n in candidates if n)
    raise RuntimeError(f"시트를 찾을 수 없습니다 (시도: {tried})")


def get_daypass_sheet(
    client: gspread.Client, spreadsheet_id: str, sheet_name: str = ""
) -> gspread.Worksheet:
    return _find_sheet(client.open_by_key(spreadsheet_id), sheet_name)


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
