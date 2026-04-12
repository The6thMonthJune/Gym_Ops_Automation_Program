from __future__ import annotations

"""
지출 내역 기록 서비스.

데일리 파일과 총매출 파일의 지출 시트에 ExpenseEntry를 기록한다.
xlwings를 사용해 Excel이 열려 있어도 정상 동작한다.

엑셀 컬럼 구조 (A~I):
  A: 번호  B: 일자  C: 구분  D: 지출내용  E: 금액  F: 결제  G: 담당자  H: 거래처  I: 기타
"""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import xlwings as xw

from src.services.total_sales_service import find_monthly_expense_sheet_name

# 데이터 시작 행
_DAILY_START_ROW = 6
_TOTAL_START_ROW = 14

# 컬럼 번호 (1-based)
_COL_NUM = 1   # A: 번호
_COL_DATE = 2  # B: 일자
_COL_CAT = 3   # C: 구분
_COL_DESC = 4  # D: 지출내용
_COL_AMT = 5   # E: 금액
_COL_PAY = 6   # F: 결제
_COL_MGR = 7   # G: 담당자
_COL_VND = 8   # H: 거래처
_COL_NOTE = 9  # I: 기타

EXPENSE_CATEGORIES = [
    "지점 비품", "수수료", "주차비", "복리후생", "운반비",
    "당직비", "홍보", "회식대", "간식대", "구인", "세금", "환불", "기타",
]
EXPENSE_PAYMENT_METHODS = ["현금", "계좌", "카드", "기타"]


@dataclass
class ExpenseEntry:
    entry_date: date
    category: str       # 구분
    description: str    # 지출내용
    amount: int         # 금액
    payment_method: str # 결제
    manager: str        # 담당자
    vendor: str         # 거래처
    note: str = ""      # 기타


# ── xlwings 헬퍼 ─────────────────────────────────────────────────────────────

def _open_book(path: str | Path) -> tuple:
    """
    파일이 이미 Excel에서 열려 있으면 그 인스턴스에 연결,
    아니면 숨김 Excel 인스턴스를 생성해 반환한다.
    Returns: (book, was_already_open)
    """
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


def _find_next_row(sheet, start_row: int) -> int:
    """B열(일자)이 비어 있는 첫 번째 행 번호를 반환한다.
    A열(번호)은 수동 입력 시 비어 있을 수 있으므로 일자 열로 판단한다."""
    for row in range(start_row, 5000):
        if sheet.range((row, _COL_DATE)).value is None:
            return row
    raise ValueError("빈 행을 찾을 수 없습니다.")


def _get_next_number(sheet, start_row: int) -> int:
    """현재 마지막 번호 + 1을 반환한다. 데이터가 없으면 1."""
    next_row = _find_next_row(sheet, start_row)
    last_data_row = next_row - 1
    if last_data_row < start_row:
        return 1
    # 실제 데이터 행 수 기준으로 다음 번호 계산 (A열 번호가 비어있을 수 있음)
    return last_data_row - start_row + 2


def _write_row(sheet, entry: ExpenseEntry, start_row: int) -> int:
    """지출 내역을 다음 빈 행에 기록하고 행 번호를 반환한다."""
    row_num = _find_next_row(sheet, start_row)
    number = _get_next_number(sheet, start_row)
    entry_datetime = datetime(
        entry.entry_date.year,
        entry.entry_date.month,
        entry.entry_date.day,
    )
    sheet.range((row_num, _COL_NUM)).value = [
        number,                         # A: 번호
        entry_datetime,                 # B: 일자
        entry.category,                 # C: 구분
        entry.description,              # D: 지출내용
        entry.amount,                   # E: 금액
        entry.payment_method,           # F: 결제
        entry.manager or None,          # G: 담당자
        entry.vendor or None,           # H: 거래처
        entry.note or None,             # I: 기타
    ]
    return row_num


# ── 공개 API ──────────────────────────────────────────────────────────────────

def write_expense_to_daily(
    daily_path: str | Path,
    sheet_name: str,
    entry: ExpenseEntry,
) -> int:
    """
    데일리 파일의 지출 시트에 기록한다.
    Returns: 기록된 행 번호
    """
    book, was_open = _open_book(daily_path)
    try:
        sheet = book.sheets[sheet_name]
        row_num = _write_row(sheet, entry, _DAILY_START_ROW)
        book.save()
        return row_num
    finally:
        if not was_open:
            book.app.quit()


def write_expense_to_total(
    total_path: str | Path,
    entry: ExpenseEntry,
    password: str | None = None,
) -> int:
    """
    총매출 파일의 해당 월 지출 시트에 기록한다.
    시트명은 매출 시트와 동일한 fuzzy 매칭으로 탐색한다.
    Returns: 기록된 행 번호
    """
    resolved = Path(total_path).resolve()
    try:
        for app in xw.apps:
            for book in app.books:
                try:
                    if Path(book.fullname).resolve() == resolved:
                        return _write_expense_total(book, entry, was_open=True)
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
        return _write_expense_total(book, entry, was_open=False)
    except Exception:
        new_app.quit()
        raise


def _write_expense_total(book, entry: ExpenseEntry, *, was_open: bool) -> int:
    try:
        sheet_names = [s.name for s in book.sheets]
        sheet_name = find_monthly_expense_sheet_name(
            sheet_names, entry.entry_date.year, entry.entry_date.month
        )
        sheet = book.sheets[sheet_name]
        row_num = _write_row(sheet, entry, _TOTAL_START_ROW)
        book.save()
        return row_num
    finally:
        if not was_open:
            book.app.quit()
