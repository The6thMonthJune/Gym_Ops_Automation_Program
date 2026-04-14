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

# 센터/레슨 구분에 따른 시작 컬럼 (1-based)
# 센터: B열(2)부터, 레슨: P열(16)부터, 양식은 동일한 12컬럼
SECTION_START_COL = {"센터": 2, "레슨": 16}


@dataclass
class PaymentEntry:
    entry_date: date
    name: str                    # 회원명
    category: str                # 종목 (헬스 / PT / PTEV / 락카 / 일일권 …)
    membership: str              # 회원권 종류
    amount: int                  # 금액 (부가세 포함)
    payment_method: str          # 카드 / 법인계좌 / 일반계좌 / 현금
    section: str = "센터"        # 매출 구분: 센터 or 레슨
    approval_number: str = ""    # 카드 승인번호 (선택)
    fc: str = ""                 # FC 담당자 (선택)
    manager: str = ""            # 담당 (선택)
    note: str = ""               # 기타 / 특이사항 (선택)

    @property
    def payment_method_excel(self) -> str:
        return PAYMENT_METHOD_EXCEL.get(self.payment_method, self.payment_method)


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


def _find_next_entry_row(sheet, start_row: int = 12, col: int = 4) -> int:
    """지정된 열이 None인 첫 번째 빈 행 번호를 반환한다.
    col: 1-based 컬럼 번호 (센터=D열=4, 레슨=R열=18)
    """
    for row_num in range(start_row, 2000):
        if sheet.range((row_num, col)).value is None:
            return row_num
    raise ValueError("빈 행을 찾을 수 없습니다. 엑셀 파일에 입력 행이 부족합니다.")


def _to_list(val) -> list:
    """xlwings 범위 읽기 결과를 항상 flat list로 반환한다."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


def _col_letter(n: int) -> str:
    """1-based 컬럼 번호를 Excel 열 문자로 변환 (1→A, 26→Z, 27→AA)."""
    result = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _vat_formula(section: str, col_start: int, row_num: int) -> str:
    """부가세 제외 금액 셀에 넣을 Excel 수식을 반환한다.
    엑셀 원본 양식의 수식과 동일하게 유지해야 다음날 파일 복사 시 양식이 깨지지 않는다.
    """
    amt = f"{_col_letter(col_start + 5)}{row_num}"   # 금액(부가세) 셀
    pay = f"{_col_letter(col_start + 7)}{row_num}"   # 결제방법 셀
    if section == "레슨":
        return (
            f'=IF(OR({pay}="카드(VAN)",{pay}="카드(C-PG)",{pay}="법인계좌",'
            f'{pay}="네이버페이",{pay}="지역화폐"),{amt}/11*10,{amt})'
        )
    # 센터
    return (
        f'=IF(OR({pay}="카드(VAN)",{pay}="카드(C-PG)",{pay}="카드(P-PG)"),'
        f'{amt}/11*10,IF({pay}="네이버페이",{amt}/11*10,'
        f'IF({pay}="법인계좌",{amt}/11*10,IF({pay}="지역화폐",{amt}/11*10,{amt}))))'
    )


def _date_already_written(sheet, row_num: int, col_start: int, entry_date: date) -> bool:
    """같은 날짜가 col_start 열 12행~row_num-1행 사이에 이미 존재하면 True.
    xlwings는 셀 값을 datetime 또는 date로 반환할 수 있으므로 둘 다 처리한다.
    """
    for r in range(12, row_num):
        val = sheet.range((r, col_start)).value
        if val is None:
            continue
        if isinstance(val, datetime):
            if val.date() == entry_date:
                return True
        elif isinstance(val, date):
            if val == entry_date:
                return True
    return False


def check_duplicate(sheet, entry: PaymentEntry, start_row: int = 12) -> bool:
    """
    같은 날짜(일) + 회원명 + 금액의 항목이 시트에 이미 존재하는지 확인한다.
    section에 따라 탐색 컬럼이 달라진다 (센터: C/D/G, 레슨: Q/R/U).
    """
    col_start = SECTION_START_COL.get(entry.section, 2)
    col_day    = col_start + 1   # 센터=C(3), 레슨=Q(17)
    col_name   = col_start + 2   # 센터=D(4), 레슨=R(18)
    col_amount = col_start + 5   # 센터=G(7), 레슨=U(21)

    next_row = _find_next_entry_row(sheet, start_row, col=col_name)
    last_data_row = next_row - 1

    if last_data_row < start_row:
        return False

    names   = _to_list(sheet.range((start_row, col_name),   (last_data_row, col_name)).value)
    amounts = _to_list(sheet.range((start_row, col_amount), (last_data_row, col_amount)).value)
    days    = _to_list(sheet.range((start_row, col_day),    (last_data_row, col_day)).value)

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
    """시트의 다음 빈 행에 결제 내역을 기록하고 행 번호를 반환한다.
    section에 따라 시작 컬럼이 달라진다 (센터: B열, 레슨: P열).
    """
    col_start = SECTION_START_COL.get(entry.section, 2)
    col_name = col_start + 2  # 회원명 컬럼: 센터=D(4), 레슨=R(18)
    row_num = _find_next_entry_row(sheet, start_row=12, col=col_name)
    entry_datetime = datetime(
        entry.entry_date.year, entry.entry_date.month, entry.entry_date.day
    )

    # 같은 날짜가 이미 위에 기록된 경우 계약일 셀을 비워 날짜 중복 표시 방지
    date_val = (
        None
        if _date_already_written(sheet, row_num, col_start, entry.entry_date)
        else entry_datetime
    )

    # +6(부가제외금액)은 Excel 수식으로 별도 입력하므로 여기선 None
    sheet.range((row_num, col_start)).value = [
        date_val,                          # +0: 계약일
        entry.entry_date.day,              # +1: 일
        entry.name,                        # +2: 회원명
        entry.category,                    # +3: 종목
        entry.membership,                  # +4: 회원권 종류
        entry.amount,                      # +5: 금액(부가세)
        None,                              # +6: 금액(부가제외) — 수식으로 대체
        entry.payment_method_excel,        # +7: 결제
        entry.approval_number or None,     # +8: 승인번호
        entry.fc or None,                  # +9: FC
        entry.manager or None,             # +10: 담당
        entry.note or None,                # +11: 기타
    ]

    # 부가세 제외 금액: 엑셀 원본 양식과 동일한 수식을 삽입
    sheet.range((row_num, col_start + 6)).formula = _vat_formula(
        entry.section, col_start, row_num
    )

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
