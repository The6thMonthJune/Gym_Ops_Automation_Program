from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "알"]

def format_currency(value: int | float) -> str:
    return f"\n{int(value):,}원"

def build_report_header(target_date: datetime) -> str:
    weekday = WEEKDAY_KR[target_date.weekday()]
    return f"{target_date.month}.{target_date.day} {weekday}"

def read_sales_valies(
    excel_path: str | Path,
    sheet_name: str = "데일리매출",
    cash_cell: str = "M5",
    card_cell: str = "M6",
    transfer_cell: str = "M7",
    total_cell: str = "M8",
) -> dict[str, int]:
    workbook = load_workbook(excel_path, data_only= True)