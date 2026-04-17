from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import openpyxl

from src.config.constants import DEFAULT_SHEET_NAME
from src.config.settings import get_expense_daily_sheet

# 매출 섹션 시작 열
_SECTION_START_COL: dict[str, int] = {"센터": 2, "레슨": 16}
_SALES_START_ROW = 12

# 매출 컬럼 오프셋 (섹션 시작 기준)
_OFF_DAY = 1
_OFF_NAME = 2
_OFF_CATEGORY = 3
_OFF_MEMBERSHIP = 4
_OFF_AMOUNT = 5
_OFF_PAYMENT = 6
_OFF_APPROVAL = 7
_OFF_FC = 8
_OFF_MANAGER = 9

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


def read_sales_entries(file_path: str | Path) -> list[SalesEntryRow]:
    wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
    try:
        if DEFAULT_SHEET_NAME not in wb.sheetnames:
            return []
        ws = wb[DEFAULT_SHEET_NAME]
        entries: list[SalesEntryRow] = []

        for section, col_start in _SECTION_START_COL.items():
            col_name = col_start + _OFF_NAME
            for row_num in range(_SALES_START_ROW, (ws.max_row or _SALES_START_ROW) + 1):
                name = ws.cell(row_num, col_name).value
                if name is None or (isinstance(name, str) and name.startswith("=")):
                    continue
                day_val = ws.cell(row_num, col_start + _OFF_DAY).value
                amount_val = ws.cell(row_num, col_start + _OFF_AMOUNT).value
                entries.append(SalesEntryRow(
                    row_num=row_num,
                    section=section,
                    day=int(day_val) if day_val is not None else 0,
                    name=str(name).strip(),
                    category=str(ws.cell(row_num, col_start + _OFF_CATEGORY).value or "").strip(),
                    membership=str(ws.cell(row_num, col_start + _OFF_MEMBERSHIP).value or "").strip(),
                    amount=int(amount_val) if amount_val is not None else 0,
                    payment_method=str(ws.cell(row_num, col_start + _OFF_PAYMENT).value or "").strip(),
                    approval_number=str(ws.cell(row_num, col_start + _OFF_APPROVAL).value or "").strip(),
                    fc=str(ws.cell(row_num, col_start + _OFF_FC).value or "").strip(),
                    manager=str(ws.cell(row_num, col_start + _OFF_MANAGER).value or "").strip(),
                ))

        return sorted(entries, key=lambda e: (e.day, e.row_num))
    finally:
        wb.close()


def read_expense_entries(file_path: str | Path) -> list[ExpenseEntryRow]:
    sheet_name = get_expense_daily_sheet()
    wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
    try:
        if sheet_name not in wb.sheetnames:
            return []
        ws = wb[sheet_name]
        entries: list[ExpenseEntryRow] = []

        for row_num in range(_EXP_START_ROW, (ws.max_row or _EXP_START_ROW) + 1):
            date_val = ws.cell(row_num, _EXP_COL_DATE).value
            if date_val is None:
                continue
            if isinstance(date_val, (date, datetime)):
                day = date_val.day
            else:
                continue
            amount_val = ws.cell(row_num, _EXP_COL_AMT).value
            entries.append(ExpenseEntryRow(
                row_num=row_num,
                day=day,
                category=str(ws.cell(row_num, _EXP_COL_CAT).value or "").strip(),
                description=str(ws.cell(row_num, _EXP_COL_DESC).value or "").strip(),
                amount=int(amount_val) if amount_val is not None else 0,
                payment_method=str(ws.cell(row_num, _EXP_COL_PAY).value or "").strip(),
                manager=str(ws.cell(row_num, _EXP_COL_MGR).value or "").strip(),
                vendor=str(ws.cell(row_num, _EXP_COL_VND).value or "").strip(),
                note=str(ws.cell(row_num, _EXP_COL_NOTE).value or "").strip(),
            ))

        return entries
    finally:
        wb.close()


def calc_total_sales(entries: list[SalesEntryRow]) -> int:
    return sum(e.amount for e in entries)
