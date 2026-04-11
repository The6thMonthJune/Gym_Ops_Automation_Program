from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import xlwings as xw

from src.services.total_sales_service import find_monthly_sheet_name

# 카톡 선택지 → 엑셀 기재 형식
PAYMENT_METHOD_EXCEL = {
    "카드": "카드(VAN)",
    "법인계좌": "법인계좌",
    "일반계좌": "일반계좌",
    "현금": "현금",
}

# 이 결제수단의 금액은 부가세(10%)가 포함된 것으로 처리한다
_VAT_INCLUDED_METHODS = {"카드(VAN)", "법인계좌"}


@dataclass
class PaymentEntry:
    entry_date: date
    name: str                    # 회원명
    category: str                # 종목 (헬스 / PT / PTEV / 락카 / 일일권 …)
    membership: str              # 회원권 종류
    amount: int                  # 금액 (부가세 포함)
    payment_method: str          # 카드 / 법인계좌 / 일반계좌 / 현금
    approval_number: str = ""    # 카드 승인번호 (선택)
    fc: str = ""                 # FC 담당자 (선택)
    manager: str = ""            # 담당 (선택)
    note: str = ""               # 기타 / 특이사항 (선택)

    @property
    def payment_method_excel(self) -> str:
        return PAYMENT_METHOD_EXCEL.get(self.payment_method, self.payment_method)

    @property
    def amount_vat_excluded(self) -> float:
        if self.payment_method_excel in _VAT_INCLUDED_METHODS:
            return self.amount / 1.1
        return float(self.amount)


# ── xlwings 헬퍼 ────────────────────────────────────────────────────────────

def _open_book(path: str | Path, password: str | None = None) -> tuple:
    """
    파일이 이미 Excel에서 열려 있으면 그 인스턴스에 연결하고,
    아니면 숨김 Excel 인스턴스를 생성해서 파일을 열어 반환한다.

    Returns:
        (book, was_already_open)
        was_already_open=True 이면 호출자가 book.app.quit()를 하면 안 된다.
    """
    resolved = Path(path).resolve()

    # 실행 중인 Excel 인스턴스에서 이미 열린 파일 탐색
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

    # 열려 있지 않으면 숨김 인스턴스로 열기
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


def _find_next_entry_row(sheet, start_row: int = 12) -> int:
    """D열(회원명)이 None인 첫 번째 빈 행 번호를 반환한다."""
    for row_num in range(start_row, 2000):
        if sheet.range(f"D{row_num}").value is None:
            return row_num
    raise ValueError("빈 행을 찾을 수 없습니다. 엑셀 파일에 입력 행이 부족합니다.")


def _to_list(val) -> list:
    """xlwings 범위 읽기 결과를 항상 flat list로 반환한다."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


def check_duplicate(sheet, entry: PaymentEntry, start_row: int = 12) -> bool:
    """
    같은 날짜(일) + 회원명 + 금액의 항목이 시트에 이미 존재하는지 확인한다.
    중복 감지 기준: C열(일), D열(회원명), G열(금액) 세 값이 모두 일치.
    """
    next_row = _find_next_entry_row(sheet, start_row)
    last_data_row = next_row - 1

    if last_data_row < start_row:
        return False

    names = _to_list(sheet.range(f"D{start_row}:D{last_data_row}").value)
    amounts = _to_list(sheet.range(f"G{start_row}:G{last_data_row}").value)
    days = _to_list(sheet.range(f"C{start_row}:C{last_data_row}").value)

    for name, amount, day in zip(names, amounts, days):
        if (
            name is not None
            and str(name).strip() == entry.name.strip()
            and amount == entry.amount
            and day == entry.entry_date.day
        ):
            return True
    return False


def _write_entry_row(sheet, entry: PaymentEntry) -> int:
    """시트의 다음 빈 행에 결제 내역을 기록하고 행 번호를 반환한다."""
    row_num = _find_next_entry_row(sheet)
    entry_datetime = datetime(
        entry.entry_date.year, entry.entry_date.month, entry.entry_date.day
    )

    # B열부터 M열까지 한 번에 기록 (COM 호출 최소화)
    sheet.range(f"B{row_num}").value = [
        entry_datetime,                     # B: 계약일
        entry.entry_date.day,              # C: D(일)
        entry.name,                        # D: 회원명
        entry.category,                    # E: 종목
        entry.membership,                  # F: 회원권 종류
        entry.amount,                      # G: 금액(부가세)
        entry.amount_vat_excluded,         # H: 금액(부가제외)
        entry.payment_method_excel,        # I: 결제
        entry.approval_number or None,     # J: 승인번호
        entry.fc or None,                  # K: FC
        entry.manager or None,             # L: 담당
        entry.note or None,                # M: 기타
    ]
    return row_num


# ── 공개 API ────────────────────────────────────────────────────────────────

def write_entry_to_daily(
    daily_path: str | Path,
    entry: PaymentEntry,
    force: bool = False,
) -> tuple[int | None, bool]:
    """
    데일리 파일의 '데일리매출' 시트에 결제 내역을 추가한다.

    Args:
        force: True이면 중복 체크를 건너뛰고 강제 입력한다.

    Returns:
        (row_num, is_duplicate)
        중복이 감지되고 force=False이면 row_num=None, is_duplicate=True.
    """
    book, was_open = _open_book(daily_path)
    try:
        sheet = book.sheets["데일리매출"]

        if not force and check_duplicate(sheet, entry):
            return None, True

        row_num = _write_entry_row(sheet, entry)
        book.save()
        return row_num, False
    finally:
        if not was_open:
            book.app.quit()


def write_entry_to_total_sales(
    total_path: str | Path,
    entry: PaymentEntry,
    password: str | None = None,
    force: bool = False,
) -> tuple[int | None, bool]:
    """
    총매출 파일의 해당 연/월 시트에 결제 내역을 추가한다.

    Args:
        force: True이면 중복 체크를 건너뛰고 강제 입력한다.

    Returns:
        (row_num, is_duplicate)
    """
    book, was_open = _open_book(total_path, password=password)
    try:
        sheet_names = [s.name for s in book.sheets]
        sheet_name = find_monthly_sheet_name(
            sheet_names, entry.entry_date.year, entry.entry_date.month
        )
        sheet = book.sheets[sheet_name]

        if not force and check_duplicate(sheet, entry):
            return None, True

        row_num = _write_entry_row(sheet, entry)
        book.save()
        return row_num, False
    finally:
        if not was_open:
            book.app.quit()
