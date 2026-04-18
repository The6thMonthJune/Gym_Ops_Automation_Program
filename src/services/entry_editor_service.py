from __future__ import annotations

from datetime import date
from pathlib import Path

import xlwings as xw

from src.config.constants import DEFAULT_SHEET_NAME
from src.config.settings import get_expense_daily_sheet
from src.services.entry_service import PAYMENT_METHOD_EXCEL
from src.services.total_sales_service import find_monthly_sheet_name
from src.core.file_naming import extract_date_from_filename

_SECTION_START_COL: dict[str, int] = {"센터": 2, "레슨": 16}
_SALES_COL_COUNT = 12   # 섹션 시작부터 VAT 수식 열까지
_EXP_COL_START = 3      # C: 일자
_EXP_COL_END = 10       # J: 기타

# 매출 컬럼 오프셋 (섹션 시작 기준, entry_service.py _write_entry_row 기준)
# +0=계약일, +1=일, +2=회원명, +3=종목, +4=회원권, +5=금액(부가세),
# +6=금액(부가제외/수식), +7=결제방법, +8=승인번호, +9=FC, +10=담당
_OFF_NAME = 2
_OFF_CATEGORY = 3
_OFF_MEMBERSHIP = 4
_OFF_AMOUNT = 5
_OFF_PAYMENT = 7
_OFF_APPROVAL = 8
_OFF_FC = 9
_OFF_MANAGER = 10

# 지출 컬럼 (1-based, expense_service와 동일)
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
    try:
        if password:
            book = new_app.books.open(str(resolved), password=password)
        else:
            book = new_app.books.open(str(resolved))
        return book, False
    except Exception:
        new_app.quit()
        raise


def _find_sales_row_in_sheet(ws, section: str, day: int, name: str, original_amount: int, start_row: int = 12) -> int | None:
    """시트에서 (구분·일·회원명·금액)이 일치하는 행 번호를 반환한다. 없으면 None."""
    col_start = _SECTION_START_COL[section]
    col_day    = col_start + _OFF_DAY_FOR_FIND
    col_name   = col_start + _OFF_NAME
    col_amount = col_start + _OFF_AMOUNT

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


_OFF_DAY_FOR_FIND = 1  # col_start + 1 = 일


def _write_cells(ws, row_num: int, col_start: int, payment_excel: str,
                 name: str, category: str, membership: str,
                 amount: int, approval_number: str, fc: str, manager: str) -> None:
    ws.range((row_num, col_start + _OFF_NAME)).value = name
    ws.range((row_num, col_start + _OFF_CATEGORY)).value = category
    ws.range((row_num, col_start + _OFF_MEMBERSHIP)).value = membership
    ws.range((row_num, col_start + _OFF_AMOUNT)).value = amount
    ws.range((row_num, col_start + _OFF_PAYMENT)).value = payment_excel
    ws.range((row_num, col_start + _OFF_APPROVAL)).value = approval_number or None
    ws.range((row_num, col_start + _OFF_FC)).value = fc
    ws.range((row_num, col_start + _OFF_MANAGER)).value = manager


def delete_sales_row(daily_path: str | Path, row_num: int, section: str) -> None:
    """데일리 파일의 매출 행을 삭제(값 초기화)한다. 수식은 보존."""
    col_start = _SECTION_START_COL[section]
    book, was_open = _open_book(daily_path)
    try:
        ws = book.sheets[DEFAULT_SHEET_NAME]
        for col in range(col_start, col_start + _SALES_COL_COUNT):
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
    col_start = _SECTION_START_COL[section]
    payment_excel = PAYMENT_METHOD_EXCEL.get(payment_method, payment_method)

    # ── 데일리 파일 수정 ──────────────────────────────────────────
    book, was_open = _open_book(daily_path)
    try:
        ws = book.sheets[DEFAULT_SHEET_NAME]
        _write_cells(ws, row_num, col_start, payment_excel,
                     name, category, membership, amount, approval_number, fc, manager)
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
        total_row = _find_sales_row_in_sheet(
            total_ws, section, day,
            original_name or name,
            original_amount if original_amount else amount,
        )
        if total_row is None:
            return "총매출 파일에서 해당 내역을 찾지 못했습니다. 수동으로 확인해 주세요."

        _write_cells(total_ws, total_row, col_start, payment_excel,
                     name, category, membership, amount, approval_number, fc, manager)
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
