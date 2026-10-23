from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import openpyxl

from src.config.constants import DEFAULT_SHEET_NAME
from src.config.settings import get_expense_daily_sheet
from src.core.sheet_layout import (
    CURRENT_LAYOUT,
    SALES_START_ROW,
    SheetLayout,
    last_column,
    offsets,
)

# 열 배치는 src/core/sheet_layout 한 곳에서만 정의한다.
# 데일리 파일을 읽으므로 신/재 칸이 있는 현재 양식을 쓴다.
# 지출 컬럼 (expense_service와 동일)
_EXP_START_ROW = 6
_EXP_COL_DATE = 3
_EXP_COL_CAT = 4
_EXP_COL_DESC = 5
_EXP_COL_AMT = 6
_EXP_COL_PAY = 7
_EXP_COL_MGR = 8
_EXP_COL_VND = 9
_EXP_COL_NOTE = 10


@dataclass
class SalesEntryRow:
    row_num: int
    section: str
    day: int
    name: str
    category: str
    membership: str
    amount: int
    payment_method: str
    approval_number: str
    fc: str
    manager: str
    membership_type: str = ""   # 신/재 — 없는 양식에서는 빈 문자열


@dataclass
class ExpenseEntryRow:
    row_num: int
    day: int
    category: str
    description: str
    amount: int
    payment_method: str
    manager: str
    vendor: str
    note: str


def _cell(row: tuple, col_1based: int):
    """values_only 튜플에서 1-based 컬럼 값을 안전하게 읽는다."""
    idx = col_1based - 1
    return row[idx] if idx < len(row) else None


def _as_int(value) -> int:
    """숫자가 아니면 0. 양식이 어긋나 글자가 들어와도 조회가 통째로 죽지 않게 한다."""
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _text(value) -> str:
    return str(value).strip() if value is not None else ""


def read_sales_entries(
    file_path: str | Path, layout: SheetLayout = CURRENT_LAYOUT
) -> list[SalesEntryRow]:
    """매출 내역을 읽는다.
    read_only=True 모드에서 ws.cell() 임의 접근은 스트리밍 XML을 매번 재탐색해
    행 수가 많으면 UI 스레드를 프리즈시킨다. iter_rows로 교체해 해결.
    """
    wb = openpyxl.load_workbook(str(file_path), data_only=True)
    try:
        if DEFAULT_SHEET_NAME not in wb.sheetnames:
            return []
        ws = wb[DEFAULT_SHEET_NAME]
        entries: list[SalesEntryRow] = []

        rows = list(ws.iter_rows(
            min_row=SALES_START_ROW, max_col=last_column(layout), values_only=True
        ))

        for section, col_start in layout.section_start.items():
            off = offsets(layout, section)

            def read(row, key, _off=off, _start=col_start):
                return _cell(row, _start + _off[key]) if _off[key] >= 0 else None

            for i, row in enumerate(rows):
                name = read(row, "name")
                if name is None or (isinstance(name, str) and name.startswith("=")):
                    continue
                day_val = read(row, "day")
                amount_val = _as_int(read(row, "amount"))
                # 조건부서식/유효성검사 더미 행 제거: 일(day)이 없거나 금액이 0인 경우 건너뜀
                if day_val is None or (amount_val == 0 and day_val == 0):
                    continue
                entries.append(SalesEntryRow(
                    row_num=SALES_START_ROW + i,
                    section=section,
                    day=_as_int(day_val),
                    name=str(name).strip(),
                    category=_text(read(row, "category")),
                    membership_type=_text(read(row, "membership_type")),
                    membership=_text(read(row, "membership")),
                    amount=amount_val,
                    payment_method=_text(read(row, "payment")),
                    approval_number=_text(read(row, "approval")),
                    fc=_text(read(row, "fc")),
                    manager=_text(read(row, "manager")),
                ))

        return sorted(entries, key=lambda e: (e.day, e.row_num))
    finally:
        wb.close()


def read_expense_entries(file_path: str | Path) -> list[ExpenseEntryRow]:
    sheet_name = get_expense_daily_sheet()
    wb = openpyxl.load_workbook(str(file_path), data_only=True)
    try:
        if sheet_name not in wb.sheetnames:
            return []
        ws = wb[sheet_name]
        entries: list[ExpenseEntryRow] = []

        rows = list(ws.iter_rows(min_row=_EXP_START_ROW, max_col=_EXP_COL_NOTE, values_only=True))
        for i, row in enumerate(rows):
            date_val = _cell(row, _EXP_COL_DATE)
            if date_val is None:
                continue
            if isinstance(date_val, (date, datetime)):
                day = date_val.day
            else:
                continue
            amount_val = _cell(row, _EXP_COL_AMT)
            entries.append(ExpenseEntryRow(
                row_num=_EXP_START_ROW + i,
                day=day,
                category=str(_cell(row, _EXP_COL_CAT) or "").strip(),
                description=str(_cell(row, _EXP_COL_DESC) or "").strip(),
                amount=int(amount_val) if amount_val is not None else 0,
                payment_method=str(_cell(row, _EXP_COL_PAY) or "").strip(),
                manager=str(_cell(row, _EXP_COL_MGR) or "").strip(),
                vendor=str(_cell(row, _EXP_COL_VND) or "").strip(),
                note=str(_cell(row, _EXP_COL_NOTE) or "").strip(),
            ))

        return entries
    finally:
        wb.close()


def calc_total_sales(entries: list[SalesEntryRow]) -> int:
    return sum(e.amount for e in entries)
