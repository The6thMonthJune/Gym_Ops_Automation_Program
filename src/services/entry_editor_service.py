from __future__ import annotations

from datetime import date
from pathlib import Path

import xlwings as xw

from src.config.constants import DEFAULT_SHEET_NAME
from src.config.settings import get_expense_daily_sheet
from src.core.sheet_layout import (
    CURRENT_LAYOUT,
    LEGACY_LAYOUT,
    SheetLayout,
    offsets,
    section_width,
)
from src.services.entry_service import PAYMENT_METHOD_EXCEL
from src.services.total_sales_service import find_monthly_sheet_name
from src.core.file_naming import extract_date_from_filename

# 열 배치는 src/core/sheet_layout 한 곳에서만 정의한다.
# 데일리는 신/재 칸이 있는 현재 양식, 전체 총매는 기존 양식을 쓴다.
_EXP_COL_START = 3      # C: 일자
_EXP_COL_END = 10       # J: 기타
_EXP_COL_CAT = 4
_EXP_COL_DESC = 5
_EXP_COL_AMT = 6
_EXP_COL_PAY = 7
_EXP_COL_MGR = 8
_EXP_COL_VND = 9


def _open_book(path: str | Path, password: str | None = None) -> tuple:
    resolved = Path(path).resolve()
    try:
        for app in xw.apps:
            for book in app.books:
                try:
                    if Path(book.fullname).resolve() == resolved:
                        return book, True
                except Exception:
                    continue
    except Exception:
        pass
    new_app = xw.App(visible=False)
    new_app.display_alerts = False
    try:
        if password:
            book = new_app.books.open(
                str(resolved), password=password,
                update_links=0, ignore_read_only_recommended=True,
            )
        else:
            book = new_app.books.open(
                str(resolved),
                update_links=0, ignore_read_only_recommended=True,
            )
        return book, False
    except Exception:
        new_app.quit()
        raise


def _find_sales_row_in_sheet(
    ws, section: str, day: int, name: str, original_amount: int,
    start_row: int = 12, layout: SheetLayout = CURRENT_LAYOUT,
) -> int | None:
    """시트에서 (구분·일·회원명·금액)이 일치하는 행 번호를 반환한다. 없으면 None."""
    col_start = layout.section_start[section]
    off = offsets(layout, section)
    col_day    = col_start + off["day"]
    col_name   = col_start + off["name"]
    col_amount = col_start + off["amount"]

    for row_num in range(start_row, 2000):
        day_val  = ws.range((row_num, col_day)).value
        name_val = ws.range((row_num, col_name)).value
        amt_val  = ws.range((row_num, col_amount)).value
        # 두 열 모두 비어 있으면 데이터 끝
        if day_val is None and name_val is None:
            break
        if (
            day_val == day
            and name_val is not None
            and str(name_val).strip() == name.strip()
            and amt_val == original_amount
        ):
            return row_num
    return None


def _write_cells(ws, row_num: int, section: str, payment_excel: str,
                 name: str, category: str, membership: str,
                 amount: int, approval_number: str, fc: str, manager: str,
                 membership_type: str = "", layout: SheetLayout = CURRENT_LAYOUT) -> None:
    col_start = layout.section_start[section]
    off = offsets(layout, section)
    values = {
        "name": name,
        "category": category,
        "membership_type": membership_type or None,
        "membership": membership,
        "amount": amount,
        "payment": payment_excel,
        "approval": approval_number or None,
        "fc": fc,
        "manager": manager,
    }
    for key, value in values.items():
        if off[key] < 0:
            continue
        # 신/재는 수정창에서 다루지 않는다. 빈 값으로 덮어써서 지우면 안 된다.
        if key == "membership_type" and not membership_type:
            continue
        ws.range((row_num, col_start + off[key])).value = value


def delete_sales_row(daily_path: str | Path, row_num: int, section: str) -> None:
    """데일리 파일의 매출 행을 삭제(값 초기화)한다. 수식은 보존."""
    col_start = CURRENT_LAYOUT.section_start[section]
    width = section_width(CURRENT_LAYOUT, section)
    book, was_open = _open_book(daily_path)
    try:
        ws = book.sheets[DEFAULT_SHEET_NAME]
        for col in range(col_start, col_start + width):
            cell = ws.range((row_num, col))
            if cell.formula and cell.formula.startswith("="):
                continue
            cell.value = None
        book.save()
    finally:
        if not was_open:
            book.app.quit()


def delete_expense_row(daily_path: str | Path, row_num: int) -> None:
    """데일리 파일의 지출 행을 삭제(값 초기화)한다. B열(번호)은 보존."""
    book, was_open = _open_book(daily_path)
    try:
        ws = book.sheets[get_expense_daily_sheet()]
        for col in range(_EXP_COL_START, _EXP_COL_END + 1):
            ws.range((row_num, col)).value = None
        book.save()
    finally:
        if not was_open:
            book.app.quit()


def edit_sales_row(
    daily_path: str | Path,
    row_num: int,
    section: str,
    *,
    name: str,
    category: str,
    membership: str,
    amount: int,
    payment_method: str,
    approval_number: str,
    fc: str,
    manager: str,
    membership_type: str = "",
    original_name: str = "",
    original_amount: int = 0,
    total_path: str | Path | None = None,
    total_password: str | None = None,
) -> str | None:
    """
    데일리 파일의 매출 행을 수정하고, total_path가 주어지면 총매출 파일도 업데이트한다.

    Returns:
        총매출 파일 업데이트 실패 시 오류 메시지 문자열, 성공 또는 미지정이면 None.
    """
    payment_excel = PAYMENT_METHOD_EXCEL.get(payment_method, payment_method)

    # ── 데일리 파일 수정 ──────────────────────────────────────────
    book, was_open = _open_book(daily_path)
    try:
        ws = book.sheets[DEFAULT_SHEET_NAME]
        _write_cells(ws, row_num, section, payment_excel,
                     name, category, membership, amount, approval_number, fc, manager,
                     membership_type, CURRENT_LAYOUT)
        book.save()
    finally:
        if not was_open:
            book.app.quit()

    # ── 총매출 파일 수정 ──────────────────────────────────────────
    if not total_path:
        return None

    try:
        parsed = extract_date_from_filename(Path(str(daily_path)).name)
        year = date.today().year
        month = parsed.month
        day = parsed.day
    except ValueError:
        return "데일리 파일명에서 날짜를 읽을 수 없어 총매출 파일을 업데이트하지 못했습니다."

    total_book, total_was_open = _open_book(total_path, password=total_password)
    try:
        sheet_names = [s.name for s in total_book.sheets]
        sheet_name = find_monthly_sheet_name(sheet_names, year, month)
        if not sheet_name:
            return f"총매출 파일에서 {year}년 {month}월 시트를 찾을 수 없습니다."

        total_ws = total_book.sheets[sheet_name]
        # 전체 총매는 신/재 칸이 없는 기존 양식이다
        total_row = _find_sales_row_in_sheet(
            total_ws, section, day,
            original_name or name,
            original_amount if original_amount else amount,
            layout=LEGACY_LAYOUT,
        )
        if total_row is None:
            return "총매출 파일에서 해당 내역을 찾지 못했습니다. 수동으로 확인해 주세요."

        _write_cells(total_ws, total_row, section, payment_excel,
                     name, category, membership, amount, approval_number, fc, manager,
                     layout=LEGACY_LAYOUT)
        total_book.save()
        return None
    finally:
        if not total_was_open:
            total_book.app.quit()


def edit_expense_row(
    daily_path: str | Path,
    row_num: int,
    *,
    category: str,
    description: str,
    amount: int,
    payment_method: str,
    manager: str,
    vendor: str,
) -> None:
    """데일리 파일의 지출 행 값을 수정한다. B열(번호)·C열(일자)은 건드리지 않는다."""
    book, was_open = _open_book(daily_path)
    try:
        ws = book.sheets[get_expense_daily_sheet()]
        ws.range((row_num, _EXP_COL_CAT)).value = category
        ws.range((row_num, _EXP_COL_DESC)).value = description
        ws.range((row_num, _EXP_COL_AMT)).value = amount
        ws.range((row_num, _EXP_COL_PAY)).value = payment_method
        ws.range((row_num, _EXP_COL_MGR)).value = manager
        ws.range((row_num, _EXP_COL_VND)).value = vendor
        book.save()
    finally:
        if not was_open:
            book.app.quit()
