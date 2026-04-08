from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def format_currency(value: int | float) -> str:
    return f"{int(value):,}원"


def build_report_header(target_date: datetime) -> str:
    weekday = WEEKDAY_KR[target_date.weekday()]
    return f"{target_date.month}.{target_date.day} {weekday}"


def read_sales_values(
    excel_path: str | Path,
    sheet_name: str = "데일리매출",
    cash_cell: str = "M5",
    card_cell: str = "M6",
    transfer_cell: str = "M7",
    total_cell: str = "M8",
) -> dict[str, int]:
    workbook = load_workbook(excel_path, data_only=True)

    if sheet_name not in workbook.sheetnames:
        raise ValueError(f"시트를 찾을 수 없습니다: {sheet_name}")

    sheet = workbook[sheet_name]

    values = {
        "cash": sheet[cash_cell].value or 0,
        "card": sheet[card_cell].value or 0,
        "transfer": sheet[transfer_cell].value or 0,
        "total": sheet[total_cell].value or 0,
    }

    return {key: int(value) for key, value in values.items()}


def build_sales_report_text(
    report_date: datetime,
    sales: dict[str, int],
) -> str:
    header = build_report_header(report_date)

    return (
        f"{header}\n\n"
        f"현금:\n{format_currency(sales['cash'])}\n\n"
        f"카드:\n{format_currency(sales['card'])}\n\n"
        f"계좌:\n{format_currency(sales['transfer'])}\n\n"
        f"총합:\n{format_currency(sales['total'])}"
    )
