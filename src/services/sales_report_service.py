from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

from src.core.sheet_layout import CURRENT_LAYOUT, LEGACY_LAYOUT, summary_cells

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def format_currency(value: int | float) -> str:
    return f"{int(value):,}원"


def build_report_header(target_date: datetime) -> str:
    weekday = WEEKDAY_KR[target_date.weekday()]
    return f"{target_date.month}.{target_date.day} {weekday}"


def read_sales_values(
    excel_path: str | Path,
    sheet_name: str = "데일리매출",
    cash_cell: str | None = None,
    card_cell: str | None = None,
    transfer_cell: str | None = None,
    total_cell: str | None = None,
) -> dict[str, int]:
    """데일리 파일의 매출 요약(현금·카드·계좌·총합)을 읽는다.

    요약 셀은 센터 섹션 오른쪽 끝에 붙어 있어 양식이 바뀌면 함께 밀린다.
    신/재 칸이 생기면서 M열 → N열로 옮겨갔다. 현재 양식을 먼저 보고,
    네 칸이 모두 비어 있으면 구양식 위치로 한 번 더 본다. 예전에 만든
    파일도 그대로 열 수 있어야 하기 때문이다.
    """
    workbook = load_workbook(excel_path, data_only=True)

    if sheet_name not in workbook.sheetnames:
        raise ValueError(f"시트를 찾을 수 없습니다: {sheet_name}")

    sheet = workbook[sheet_name]
    override = {
        "cash": cash_cell, "card": card_cell,
        "transfer": transfer_cell, "total": total_cell,
    }

    for layout in (CURRENT_LAYOUT, LEGACY_LAYOUT):
        cells = summary_cells(layout)
        values = {
            key: sheet[override[key] or address].value
            for key, address in cells.items()
        }
        if any(value is not None for value in values.values()):
            return {key: _as_int(value) for key, value in values.items()}

    return {key: 0 for key in cells}


def _as_int(value) -> int:
    """숫자가 아니면 0. 요약 칸에 글자가 있어도 화면이 죽지 않게 한다."""
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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


# ── 월 목표 카운트다운 ────────────────────────────────────────────────

def read_daily_section_totals(daily_path: str | Path) -> dict[str, int]:
    """데일리 파일에서 센터/레슨 매출 합계를 반환한다."""
    from src.services.entry_reader_service import read_sales_entries
    entries = read_sales_entries(daily_path)
    return {
        "center": sum(e.amount for e in entries if e.section == "센터"),
        "pt": sum(e.amount for e in entries if e.section == "레슨"),
    }


def read_range_totals(
    daily_dir: Path,
    start_date: date,
    end_date: date,
) -> dict[str, int]:
    """daily_dir 안의 데일리 파일 중 start_date~end_date에 해당하는 파일을 모두 읽어 합산한다."""
    from src.core.file_naming import extract_date_from_filename

    totals = {"center": 0, "pt": 0}
    if not daily_dir.exists():
        return totals

    years = {start_date.year, end_date.year}

    for xlsx_file in sorted(daily_dir.glob("*.xlsx")):
        if xlsx_file.name.startswith("~$"):
            continue
        try:
            parsed = extract_date_from_filename(xlsx_file.name)
        except ValueError:
            continue

        in_range = False
        for year in years:
            try:
                file_date = parsed.to_date(year)
            except ValueError:
                continue
            if start_date <= file_date <= end_date:
                in_range = True
                break

        if not in_range:
            continue

        try:
            daily = read_daily_section_totals(xlsx_file)
            totals["center"] += daily["center"]
            totals["pt"] += daily["pt"]
        except Exception:
            continue

    return totals



def _legacy_off(section: str) -> dict[str, int]:
    from src.core.sheet_layout import offsets
    return offsets(LEGACY_LAYOUT, section)


# 총매출 파일 월 시트에서 센터/피티 금액 컬럼 (1-based)
# 센터: 시작 B(2) → 이름 D(4), 금액 G(7)
# 레슨: 시작 P(16) → 이름 R(18), 금액 U(21)
_MONTHLY_SECTION_COLS = {
    key: (
        LEGACY_LAYOUT.section_start[section] + _legacy_off(section)["name"],
        LEGACY_LAYOUT.section_start[section] + _legacy_off(section)["amount"],
    )
    for key, section in (("center", "센터"), ("pt", "레슨"))
}
_MONTHLY_DATA_START_ROW = 12


def read_monthly_totals_by_section(
    total_sales_path: str | Path,
    year: int,
    month: int,
    password: str | None = None,
) -> dict[str, int]:
    """총매출 파일의 해당 월 시트에서 센터/피티 매출 합계를 반환한다."""
    from src.services.total_sales_service import find_monthly_sheet_name, open_workbook

    wb = open_workbook(total_sales_path, password=password)
    try:
        sheet_name = find_monthly_sheet_name(wb.sheetnames, year, month)
        ws = wb[sheet_name]
        totals: dict[str, int] = {"center": 0, "pt": 0}
        max_row = ws.max_row or 500
        for key, (name_col, amount_col) in _MONTHLY_SECTION_COLS.items():
            for row_num in range(_MONTHLY_DATA_START_ROW, max_row + 1):
                name_val = ws.cell(row=row_num, column=name_col).value
                if not name_val or (isinstance(name_val, str) and name_val.startswith("=")):
                    continue
                amount_val = ws.cell(row=row_num, column=amount_col).value
                if isinstance(amount_val, (int, float)) and amount_val > 0:
                    totals[key] += int(amount_val)
        return totals
    finally:
        wb.close()


def build_countdown_text(
    accumulated_center: int,
    accumulated_pt: int,
    center_target: int,
    pt_target: int,
) -> str:
    total = accumulated_center + accumulated_pt

    def _remaining(target: int, running: int) -> str:
        diff = target - running
        return "달성! 🎉" if diff <= 0 else format_currency(diff)

    return "\n".join([
        f"센터: {format_currency(accumulated_center)}",
        f"피티: {format_currency(accumulated_pt)}",
        f"총합: {format_currency(total)}",
        "",
        "목표까지 앞으로",
        f"센터: {_remaining(center_target, accumulated_center)}",
        f"피티: {_remaining(pt_target, accumulated_pt)}",
    ])
