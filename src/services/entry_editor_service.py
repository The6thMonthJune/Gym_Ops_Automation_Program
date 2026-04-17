from __future__ import annotations

from pathlib import Path

import xlwings as xw

from src.config.constants import DEFAULT_SHEET_NAME
from src.config.settings import get_expense_daily_sheet

_SECTION_START_COL: dict[str, int] = {"센터": 2, "레슨": 16}
_SALES_COL_COUNT = 12   # 섹션 시작부터 VAT 수식 열까지
_EXP_COL_START = 3      # C: 일자
_EXP_COL_END = 10       # J: 기타

# 매출 컬럼 오프셋 (섹션 시작 기준, entry_reader_service와 동일)
_OFF_NAME = 2
_OFF_CATEGORY = 3
_OFF_MEMBERSHIP = 4
_OFF_AMOUNT = 5
_OFF_PAYMENT = 6
_OFF_FC = 8
_OFF_MANAGER = 9

# 지출 컬럼 (1-based, expense_service와 동일)
_EXP_COL_CAT = 4
_EXP_COL_DESC = 5
_EXP_COL_AMT = 6
_EXP_COL_PAY = 7
_EXP_COL_MGR = 8
_EXP_COL_VND = 9


def _open_book(path: str | Path) -> tuple:
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
        book = new_app.books.open(str(resolved))
        return book, False
    except Exception:
        new_app.quit()
        raise


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
    fc: str,
    manager: str,
) -> None:
    """데일리 파일의 매출 행 값을 수정한다. 수식 셀(승인번호 등)은 건드리지 않는다."""
    col_start = _SECTION_START_COL[section]
    book, was_open = _open_book(daily_path)
    try:
        ws = book.sheets[DEFAULT_SHEET_NAME]
        ws.range((row_num, col_start + _OFF_NAME)).value = name
        ws.range((row_num, col_start + _OFF_CATEGORY)).value = category
        ws.range((row_num, col_start + _OFF_MEMBERSHIP)).value = membership
        ws.range((row_num, col_start + _OFF_AMOUNT)).value = amount
        ws.range((row_num, col_start + _OFF_PAYMENT)).value = payment_method
        ws.range((row_num, col_start + _OFF_FC)).value = fc
        ws.range((row_num, col_start + _OFF_MANAGER)).value = manager
        book.save()
    finally:
        if not was_open:
            book.app.quit()


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
